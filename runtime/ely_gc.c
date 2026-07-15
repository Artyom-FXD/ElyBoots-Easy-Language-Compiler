/**
 * @file ely_gc.c
 * @brief Поколенческий сборщик мусора для Ely (единая реализация)
 */

#include "ely_gc.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <stdint.h>
#include <stdalign.h>
#include <string.h>
#include "ely_value.h"
#include "collections.h"

#if defined(_WIN32) || defined(_WIN64)
#include <windows.h>
#else
#include <sys/mman.h>
#include <unistd.h>
#endif

/* ============================================================================
 * Внутренние константы и макросы
 * ============================================================================ */

#define ALIGN_UP(size, align) (((size) + (align) - 1) & ~((align) - 1))
#define HEADER_SIZE ALIGN_UP(sizeof(gc_header_t), GC_ALIGNMENT)

static inline gc_header_t* ptr_to_header(void* ptr) {
    return (gc_header_t*)((char*)ptr - HEADER_SIZE);
}

static inline void* header_to_ptr(gc_header_t* hdr) {
    return (char*)hdr + HEADER_SIZE;
}

#ifndef ELY_PAYLOAD_MASK
#define ELY_PAYLOAD_MASK (~0x7ULL) 
#endif

/* ============================================================================
 * Глобальное состояние сборщика
 * ============================================================================ */

static char* young_from = NULL;
static char* young_to   = NULL;
static char* young_top  = NULL;
static char* young_limit = NULL;

static char* old_start = NULL;
static char* old_top   = NULL;
static char* old_limit = NULL;
static size_t old_size = 0;

static gc_header_t* old_free_list = NULL;
static gc_header_t* large_objects = NULL;

static uint64_t** roots = NULL;
static size_t roots_count = 0;
static size_t roots_capacity = 0;

static uint64_t** global_roots = NULL;
static size_t global_roots_count = 0;
static size_t global_roots_capacity = 0;

static gc_header_t** dirty_set = NULL;
static size_t dirty_count = 0;
static size_t dirty_capacity = 0;

static uint64_t young_collections = 0;
static uint64_t old_collections = 0;
static bool gc_enabled = false;
static int old_threshold_percent = 75;

// GigaCage
uintptr_t g_cage_base = 0;
uintptr_t g_cage_limit = 0;
static char* cage_brk = NULL;

/* ============================================================================
 * GIGA CAGE
 * ============================================================================ */
void gc_init_cage(size_t custom_size_bytes) {
    if (g_cage_base != 0) return;
    size_t cage_size = custom_size_bytes > 0 ? custom_size_bytes : (GC_DEFAULT_CAGE_SIZE_GB * 1024ULL * 1024ULL * 1024ULL);

#ifdef _WIN32
    g_cage_base = (uintptr_t)VirtualAlloc(NULL, cage_size, MEM_RESERVE, PAGE_NOACCESS);
#else
    g_cage_base = (uintptr_t)mmap(NULL, cage_size, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if ((void*)g_cage_base == MAP_FAILED) g_cage_base = 0;
#endif
    if (!g_cage_base) {
        fprintf(stderr, "[ELYGC] FATAL ERROR: FAILED TO RESERVE %llu MB FOR GIGACAGE ADRESS SPACE\n", (unsigned long long)(cage_size / (1024 * 1024)));
        exit(1);
    }

    g_cage_limit = g_cage_base + cage_size;
    cage_brk = (char*)g_cage_base;

    // // printf("[ELYGC] GigaCage initialized. Base: 0x%llx, Limit: 0x%llx (%.2f GB reserved)\n",
    //         (unsigned long long)g_cage_base,
    //         (unsigned long long)g_cage_limit,
    //         (double)(cage_size / (1024.0 * 1024.0 * 1024.0))
    // );
}

void* cage_alloc_segment(size_t size) {
    if (g_cage_base == 0) {
        gc_init_cage(0);
    }

    // Выравниваем размер под страницу ОС (4 КБ) для корректной работы системных вызовов
    size_t page_size = 4096;
    size_t aligned_size = (size + page_size - 1) & ~(page_size - 1);

    if (cage_brk + aligned_size > (char*)g_cage_limit) {
        fprintf(stderr, "[ELYGC] FATAL ERROR: GigaCage out of memory during segment allocation!\n");
        abort();
    }

    void* allocated = (void*)cage_brk;

#ifdef _WIN32
    // Переводим зарезервированные страницы Клетки в состояние COMMIT
    if (VirtualAlloc(allocated, aligned_size, MEM_COMMIT, PAGE_READWRITE) == NULL) {
        fprintf(stderr, "[ELYGC] FATAL ERROR: Failed to commit memory segment in GigaCage\n");
        abort();
    }
#else
    // На POSIX меняем защиту страниц с PROT_NONE на чтение/запись
    if (mprotect(allocated, aligned_size, PROT_READ | PROT_WRITE) != 0) {
        fprintf(stderr, "[ELYGC] FATAL ERROR: Failed to mprotect memory segment in GigaCage\n");
        abort();
    }
#endif

    cage_brk += aligned_size;
    return allocated;
}

#ifndef ELY_VALUES_ENUM_DEFINED
#define ELY_VALUES_ENUM_DEFINED
typedef enum ElyValuesEnum {
    ely_VALUE_NULL,
    ely_VALUE_BOOL,
    ely_VALUE_INT,
    ely_VALUE_DOUBLE,
    ely_VALUE_STRING,
    ely_VALUE_ARRAY,
    ely_VALUE_OBJECT
};
#endif

static void* cage_reserve_segment(size_t size) {
    if (g_cage_base == 0) {
        gc_init_cage(0);
    }

    size_t page_size = 4096;
    size_t aligned_size = (size + page_size - 1) & ~(page_size - 1);

    if (cage_brk + aligned_size > (char*)g_cage_limit) {
        fprintf(stderr, "[ELYGC] FATAL ERROR: GigaCage out of address space during segment reservation!\n");
        abort();
    }

    void* allocated = (void*)cage_brk;
    cage_brk += aligned_size;
    return allocated;
}

static bool cage_commit_segment(void* ptr, size_t size) {
    if (!ptr) return false;
    size_t page_size = 4096;
    size_t aligned_size = (size + page_size - 1) & ~(page_size - 1);

#ifdef _WIN32
    return VirtualAlloc(ptr, aligned_size, MEM_COMMIT, PAGE_READWRITE) != NULL;
#else
    return mprotect(ptr, aligned_size, PROT_READ | PROT_WRITE) == 0;
#endif
}

/**
 * @brief Безопасный декоммит физической памяти внутри Клетки без разрушения общего региона адресов
 */
static void cage_decommit_segment(void* ptr, size_t size) {
    if (!ptr) return;
    size_t page_size = 4096;
    size_t aligned_size = (size + page_size - 1) & ~(page_size - 1);

#ifdef _WIN32
    VirtualFree(ptr, aligned_size, MEM_DECOMMIT);
#else
    mprotect(ptr, aligned_size, PROT_NONE);
#   ifdef MADV_DONTNEED
    madvise(ptr, aligned_size, MADV_DONTNEED);
#   endif
#endif
}

/**
 * @brief Стандартный 64-битный хэш FNV-1a для строк Ely
 */
static inline uint64_t ely_str_hash(const char* str) {
    if (!str) return 0;
    uint64_t hash = 14695981039346656037ULL;
    while (*str) {
        hash ^= (unsigned char)*str++;
        hash *= 1099511628211ULL;
    }
    return hash;
}

/* ============================================================================
    Ely-boxing
 * ============================================================================ */

uint8_t get_heap_obj_type(void* ptr) {
    gc_header_t* hdr = (gc_header_t*)((char*)ptr - HEADER_SIZE);
    return hdr->obj_type;
}

/* ============================================================================
 * Прототипы статических функций (чтобы избежать неявных объявлений)
 * ============================================================================ */

static gc_header_t* gc_move_object(gc_header_t* old_hdr);

static void* allocate_old(size_t size, gc_obj_type_t type);
static void collect_young(void);
static void collect_old(void);
static void add_dirty(gc_header_t* hdr);
static void ensure_roots_capacity(void);
static void ensure_global_roots_capacity(void);
static void ensure_dirty_capacity(void);
static void* copy_object(void* obj_ptr);
static void scan_object_fields(void* obj_ptr);
static void mark_object(void* obj_ptr);
static void sweep_old(void);
static void compact_old(void);
static bool is_in_old_generation(void* ptr);
static void update_references(void* obj, ptrdiff_t delta);
static bool expand_old_heap(size_t additional_bytes);

// ============================================================================

/**
 * @brief Эвакуирует объект из текущего полупространства молодого поколения.
 * Перемещает его либо в выжившее полупространство, либо продвигает в старое поколение.
 */
// static gc_header_t* gc_move_object(gc_header_t* old_hdr) {
//     if (!old_hdr) return NULL;

//     // 1. Проверяем, не был ли объект уже перемещен (защита от повторного копирования циклических ссылок)
//     if ((old_hdr->flags & GC_FLAG_MARKED) && old_hdr->u.forwarding != NULL) {
//         return old_hdr->u.forwarding;
//     }

//     // 2. СТРАТЕГИЯ PROMOTION (Продвижение в старшее поколение)
//     // Если объект пережил достаточное количество сборок мусора, эвакуируем его в Old Gen
//     if (old_hdr->age >= PROMOTION_AGE) {
//         size_t body_size = old_hdr->size - HEADER_SIZE;
        
//         // Выделяем память в свободном списке или на вершине старого поколения
//         void* new_mem = allocate_old(body_size, (gc_obj_type_t)old_hdr->obj_type);
//         if (!new_mem) {
//             fprintf(stderr, "[ELYGC] FATAL: Promotion failed during gc_move_object (Old Gen Out of Memory)\n");
//             abort();
//         }

//         // Копируем только тело (полезную нагрузку), так как allocate_old сам инициализирует свежий заголовок
//         memcpy(new_mem, header_to_ptr(old_hdr), body_size);

//         gc_header_t* new_hdr = ptr_to_header(new_mem);
//         new_hdr->flags |= GC_FLAG_IN_OLD;
//         new_hdr->age = 0; // Сбрасываем счетчик поколений для старой кучи

//         // Оставляем адрес пересылки (Forwarding Pointer) в старом заголовке
//         old_hdr->flags |= GC_FLAG_MARKED;
//         old_hdr->u.forwarding = new_hdr;

//         return new_hdr;
//     }

//     // 3. СТРАТЕГИЯ EVACUATION (Перенос в соседнее полупространство молодого поколения)
//     size_t total_size = ALIGN_UP(old_hdr->size, GC_ALIGNMENT);
    
//     // Проверяем, влезет ли объект в текущий регион To-Space
//     if (young_top + total_size > young_limit) {
//         fprintf(stderr, "[ELYGC] FATAL: Young generation overflow during object evacuation!\n");
//         abort();
//     }

//     // Аллоцируем память простым сдвигом указателя (Bump Allocation)
//     gc_header_t* new_hdr = (gc_header_t*)young_top;
//     young_top += total_size;

//     // Копируем объект целиком вместе с его текущим мета-заголовком
//     memcpy(new_hdr, old_hdr, old_hdr->size);
    
//     // Объект успешно пережил сборку в пределах Nursery, инкрементируем его возраст
//     new_hdr->age++;
    
//     // На новом месте объект чист: сбрасываем маркеры перемещения
//     new_hdr->flags &= ~GC_FLAG_MARKED;
//     new_hdr->u.forwarding = NULL;

//     // Записываем мост (Forwarding Pointer) в старый заголовок, чтобы все остальные ссылки на него обновились
//     old_hdr->flags |= GC_FLAG_MARKED;
//     old_hdr->u.forwarding = new_hdr;

//     return new_hdr;
// }

/* ============================================================================
 * Низкоуровневое управление памятью ОС
 * ============================================================================ */

static void* os_alloc(size_t size) {
#ifdef _WIN32
    return VirtualAlloc(NULL, size, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
#else
    void* ptr = mmap(NULL, size, PROT_READ | PROT_WRITE,
                     MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    return (ptr == MAP_FAILED) ? NULL : ptr;
#endif
}

static void os_free(void* ptr, size_t size) {
    if (!ptr) return;
#ifdef _WIN32
    VirtualFree(ptr, 0, MEM_RELEASE);
#else
    munmap(ptr, size);
#endif
}

static void* os_resize(void* old_ptr, size_t old_size, size_t new_size) {
#ifdef _WIN32
    void* new_ptr = os_alloc(new_size);
    if (!new_ptr) return NULL;
    memcpy(new_ptr, old_ptr, old_size);
    os_free(old_ptr, old_size);
    return new_ptr;
#else
    return mremap(old_ptr, old_size, new_size, MREMAP_MAYMOVE);
#endif
}

/* ============================================================================
 * Вспомогательные функции управления памятью
 * ============================================================================ */

static void ensure_roots_capacity(void) {
    if (roots_count >= roots_capacity) {
        roots_capacity = roots_capacity ? roots_capacity * 2 : 64;
        roots = (uint64_t**)realloc(roots, roots_capacity * sizeof(void**));
        if (!roots) { fprintf(stderr, "GC: out of memory for roots\n"); abort(); }
    }
}

static void ensure_global_roots_capacity(void) {
    if (global_roots_count >= global_roots_capacity) {
        global_roots_capacity = global_roots_capacity ? global_roots_capacity * 2 : 64;
        global_roots = (uint64_t**)realloc(global_roots, global_roots_capacity * sizeof(void**));
        if (!global_roots) { fprintf(stderr, "GC: out of memory for global roots\n"); abort(); }
    }
}

static void ensure_dirty_capacity(void) {
    if (dirty_count >= dirty_capacity) {
        dirty_capacity = dirty_capacity ? dirty_capacity * 2 : 64;
        dirty_set = (gc_header_t**)realloc(dirty_set, dirty_capacity * sizeof(gc_header_t*));
        if (!dirty_set) { fprintf(stderr, "GC: out of memory for dirty set\n"); abort(); }
    }
}

static void add_dirty(gc_header_t* hdr) {
    if (!(hdr->flags & GC_FLAG_DIRTY)) {
        hdr->flags |= GC_FLAG_DIRTY;
        ensure_dirty_capacity();
        dirty_set[dirty_count++] = hdr;
    }
}

/* ============================================================================
 * Аллокация в молодом поколении
 * ============================================================================ */

static void* allocate_young(size_t size, gc_obj_type_t type) {
    size_t total = HEADER_SIZE + ALIGN_UP(size, GC_ALIGNMENT);
    if (young_top + total > young_limit) {
        collect_young();
        if (young_top + total > young_limit) {
            return allocate_old(size, type);
        }
    }

    gc_header_t* hdr = (gc_header_t*)young_top;
    young_top += total;

    hdr->size = (uint32_t)total;
    hdr->age = 0;
    hdr->flags = 0;
    hdr->obj_type = (uint8_t)type;
    hdr->u.forwarding = NULL;

    return header_to_ptr(hdr);
}

/* ============================================================================
 * Аллокация в старом поколении (first‑fit из free‑list)
 * ============================================================================ */

static void* allocate_old(size_t size, gc_obj_type_t type) {
    size_t total = HEADER_SIZE + ALIGN_UP(size, GC_ALIGNMENT);

    gc_header_t* prev = NULL;
    gc_header_t* curr = old_free_list;
    while (curr) {
        if (curr->size >= total) {
            if (curr->size >= total + HEADER_SIZE + GC_ALIGNMENT) {
                gc_header_t* remainder = (gc_header_t*)((char*)curr + total);
                remainder->size = curr->size - (uint32_t)total;
                remainder->flags = 0;
                remainder->u.next_free = curr->u.next_free;
                if (prev) prev->u.next_free = remainder;
                else old_free_list = remainder;
                curr->size = (uint32_t)total;
            } else {
                if (prev) prev->u.next_free = curr->u.next_free;
                else old_free_list = curr->u.next_free;
            }
            curr->flags = GC_FLAG_IN_OLD;
            curr->age = 0;
            curr->obj_type = (uint8_t)type;
            curr->u.forwarding = NULL;
            return header_to_ptr(curr);
        }
        prev = curr;
        curr = curr->u.next_free;
    }

    if (old_top + total <= old_limit) {
        gc_header_t* hdr = (gc_header_t*)old_top;
        old_top += total;
        hdr->size = (uint32_t)total;
        hdr->age = 0;
        hdr->flags = GC_FLAG_IN_OLD;
        hdr->obj_type = (uint8_t)type;
        hdr->u.forwarding = NULL;
        return header_to_ptr(hdr);
    }

    collect_old();
    return allocate_old(size, type);
}

/* ============================================================================
 * Аллокация крупных объектов (LOS)
 * ============================================================================ */

static void* allocate_large(size_t size, gc_obj_type_t type) {
    size_t total = HEADER_SIZE + ALIGN_UP(size, GC_ALIGNMENT);
    
    void* mem = cage_alloc_segment(total); 
    if (!mem) return NULL;

    gc_header_t* hdr = (gc_header_t*)mem;
    hdr->size = (uint32_t)total;
    hdr->age = 0;
    hdr->flags = GC_FLAG_LARGE;
    hdr->obj_type = (uint8_t)type;
    hdr->u.next_free = large_objects;
    large_objects = hdr;

    return header_to_ptr(hdr);
}

/* ============================================================================
 * Base allocation
 * ============================================================================ */

void* gc_alloc(size_t size, gc_obj_type_t type) {
    if (!gc_enabled) {
        void* ptr = (void*)malloc(size);
        if (ptr) memset(ptr, 0, size);
        return ptr;
    }

    size_t total = HEADER_SIZE + ALIGN_UP(size, GC_ALIGNMENT);
    if (total >= LARGE_OBJECT_THRESHOLD) {
        void* ptr = allocate_large(size, type);
        if (ptr) memset(ptr, 0, size);
        return ptr;
    }
    void* ptr = allocate_young(size, type);
    if (ptr) memset(ptr, 0, size);
    return ptr;
}

void* gc_calloc(size_t size, gc_obj_type_t type) {
    void* ptr = (void*)gc_alloc(size, type);
    if (ptr) memset(ptr, 0, size);
    return ptr;
}

/* ============================================================================
 * Копирование объектов для молодого поколения (алгоритм Чейни)
 * ============================================================================ */

static void* copy_object(void* obj_ptr) {
    if (!obj_ptr) return NULL;
    gc_header_t* hdr = ptr_to_header(obj_ptr);

    if (hdr->flags & GC_FLAG_MARKED) {
        return header_to_ptr(hdr->u.forwarding);
    }

    if (hdr->age >= PROMOTION_AGE) {
        size_t size = hdr->size;
        void* new_mem = allocate_old(size - HEADER_SIZE, (gc_obj_type_t)hdr->obj_type);
        if (!new_mem) { fprintf(stderr, "GC: promotion failed\n"); abort(); }
        memcpy(new_mem, obj_ptr, size - HEADER_SIZE);
        gc_header_t* new_hdr = ptr_to_header(new_mem);
        new_hdr->flags |= GC_FLAG_IN_OLD;
        new_hdr->age = 0;

        hdr->flags |= GC_FLAG_MARKED;
        hdr->u.forwarding = new_hdr;
        return new_mem;
    }

    size_t total = ALIGN_UP(hdr->size, GC_ALIGNMENT);
    if (young_top + total > young_limit) {
        fprintf(stderr, "GC: young generation overflow during collection\n");
        abort();
    }
    gc_header_t* new_hdr = (gc_header_t*)young_top;
    young_top += total;
    memcpy(new_hdr, hdr, hdr->size);
    new_hdr->age++;
    new_hdr->flags &= ~GC_FLAG_MARKED;

    hdr->flags |= GC_FLAG_MARKED;
    hdr->u.forwarding = new_hdr;

    return header_to_ptr(new_hdr);
}

// Очищаем младшие биты указателя и накладываем тег поверх них в самый низ
#define ELY_REPACK_PTR(target_slot, raw_ptr, type_tag) \
    (target_slot) = (((uint64_t)(raw_ptr) & ELY_PAYLOAD_MASK) | ((uint64_t)(type_tag) & 0x7))

static void scan_object_fields(void* obj_ptr) {
    gc_header_t* hdr = ptr_to_header(obj_ptr);
    switch (hdr->obj_type) {
        case GC_OBJ_VALUE: {
            ely_value* v = (ely_value*)obj_ptr;
            int t = ely_get_type(*v);
            if (t == ely_VALUE_ARRAY || t == ely_VALUE_OBJECT || t == ely_VALUE_STRING) {
                void* old_ptr = ELY_UNBOX_PTR(*v);
                void* new_ptr = copy_object(old_ptr);
                ELY_REPACK_PTR(*v, new_ptr, t);
            }
            break;
        }
        case GC_OBJ_ARR: {
            arr* a = (arr*)obj_ptr;
            for (size_t i = 0; i < a->size; i++) {
                ely_value val = a->data[i];
                int t = ely_get_type(val);
                if (t == ely_VALUE_ARRAY || t == ely_VALUE_OBJECT || t == ely_VALUE_STRING) {
                    void* old_ptr = ELY_UNBOX_PTR(val);
                    void* new_ptr = copy_object(old_ptr);
                    ELY_REPACK_PTR(a->data[i], new_ptr, t);
                }
            }
            break;
        }
        case GC_OBJ_DICT: {
            dict* d = (dict*)obj_ptr;
            /* Копируем buckets-array внутри самого dict */
            d->buckets = (dict_entry**)copy_object(d->buckets);
            for (size_t i = 0; i < d->capacity; i++) {
                dict_entry* e = d->buckets[i];
                while (e) {
                    // Ключ и значение теперь тоже упакованные ely_value
                    int kt = ely_get_type(e->key);
                    if (kt == ely_VALUE_ARRAY || kt == ely_VALUE_OBJECT || kt == ely_VALUE_STRING) {
                        void* new_key = copy_object(ELY_UNBOX_PTR(e->key));
                        ELY_REPACK_PTR(e->key, new_key, kt);
                    }

                    int vt = ely_get_type(e->value);
                    if (vt == ely_VALUE_ARRAY || vt == ely_VALUE_OBJECT || vt == ely_VALUE_STRING) {
                        void* new_val = copy_object(ELY_UNBOX_PTR(e->value));
                        ELY_REPACK_PTR(e->value, new_val, vt);
                    }

                    if (e->next) e->next = (dict_entry*)copy_object(e->next);
                    e = e->next;
                }
            }
            break;
        }
        default: break;
    }
}

static void collect_young(void) {
    young_collections++;

    char* tmp = young_from;
    young_from = young_to;
    young_to = tmp;
    young_top = young_from;
    young_limit = young_from + YOUNG_SIZE;

    void** scan_ptr = (void**)young_from;

    for (size_t i = 0; i < roots_count; i++) {
        if (*roots[i] && ELY_IS_PTR(*roots[i])) {
            uint64_t val = *roots[i];
            int t = ely_get_type(val);
            void* old_ptr = ELY_UNBOX_PTR(val);
            void* new_ptr = copy_object(old_ptr);
            ELY_REPACK_PTR(*roots[i], new_ptr, t); // Сохраняем тип в верхних битах!
        }
    }
    for (size_t i = 0; i < global_roots_count; i++) {
        if (*global_roots[i] && ELY_IS_PTR(*global_roots[i])) {
            uint64_t val = *global_roots[i];
            int t = ely_get_type(val);
            void* old_ptr = ELY_UNBOX_PTR(val);
            void* new_ptr = copy_object(old_ptr);
            ELY_REPACK_PTR(*global_roots[i], new_ptr, t); // Сохраняем тип!
        }
    }

    for (size_t i = 0; i < dirty_count; i++) {
        scan_object_fields(header_to_ptr(dirty_set[i]));
    }

    while ((char*)scan_ptr < young_top) {
        gc_header_t* hdr = (gc_header_t*)scan_ptr;
        scan_object_fields(header_to_ptr(hdr));
        scan_ptr = (void**)((char*)scan_ptr + ALIGN_UP(hdr->size, GC_ALIGNMENT));
    }

    for (size_t i = 0; i < dirty_count; i++) {
        dirty_set[i]->flags &= ~GC_FLAG_DIRTY;
    }
    dirty_count = 0;
}

/* ============================================================================
 * Безопасное обновление указателей для уплотнения Old Gen
 * ============================================================================ */

static void adjust_ptr(uint64_t* slot) {
    if (*slot && ELY_IS_PTR(*slot)) {
        void* raw = ELY_UNBOX_PTR(*slot);
        if (is_in_old_generation(raw)) {
            gc_header_t* hdr = ptr_to_header(raw);
            // Если объект живой и у него есть адрес пересылки
            if (hdr->flags & GC_FLAG_MARKED) {
                int t = ely_get_type(*slot);
                void* new_ptr = header_to_ptr(hdr->u.forwarding);
                ELY_REPACK_PTR(*slot, new_ptr, t);
            }
        }
    }
}

static void adjust_raw_ptr(void** ptr_slot) {
    if (*ptr_slot && is_in_old_generation(*ptr_slot)) {
        gc_header_t* hdr = ptr_to_header(*ptr_slot);
        if (hdr->flags & GC_FLAG_MARKED) {
            *ptr_slot = header_to_ptr(hdr->u.forwarding);
        }
    }
}

static void update_object_pointers(void* obj_ptr) {
    gc_header_t* hdr = ptr_to_header(obj_ptr);
    switch (hdr->obj_type) {
        case GC_OBJ_VALUE: {
            ely_value* v = (ely_value*)obj_ptr;
            adjust_ptr(v);
            break;
        }
        case GC_OBJ_ARR: {
            arr* a = (arr*)obj_ptr;
            for (size_t i = 0; i < a->size; i++) {
                adjust_ptr(&a->data[i]);
            }
            break;
        }
        case GC_OBJ_DICT: {
            dict* d = (dict*)obj_ptr;
            // buckets — это сырой массив указателей, выделенный в GC-куче
            adjust_raw_ptr((void**)&d->buckets);
            if (d->buckets) {
                for (size_t i = 0; i < d->capacity; i++) {
                    adjust_raw_ptr((void**)&d->buckets[i]);
                    dict_entry* e = d->buckets[i];
                    while (e) {
                        adjust_ptr(&e->key);
                        adjust_ptr(&e->value);
                        adjust_raw_ptr((void**)&e->next);
                        e = e->next;
                    }
                }
            }
            break;
        }
        default: break;
    }
}

/* ============================================================================
 * Сборка старого поколения (mark‑sweep)
 * ============================================================================ */

static void mark_object(void* obj_ptr) {
    if (!obj_ptr) return;
    
    // ИСПРАВЛЕНО: Маркируем только то, что реально находится под управлением GC!
    if (is_gc_managed(obj_ptr)) {
        gc_header_t* hdr = ptr_to_header(obj_ptr);
        if (hdr->flags & GC_FLAG_MARKED) return;
        hdr->flags |= GC_FLAG_MARKED;

        switch (hdr->obj_type) {
            case GC_OBJ_VALUE: {
                ely_value* v = (ely_value*)obj_ptr;
                int t = ely_get_type(*v);
                if (t == ely_VALUE_ARRAY || t == ely_VALUE_OBJECT || t == ely_VALUE_STRING) {
                    mark_object(ELY_UNBOX_PTR(*v));
                }
                break;
            }
            case GC_OBJ_ARR: {
                arr* a = (arr*)obj_ptr;
                for (size_t i = 0; i < a->size; i++) {
                    ely_value val = a->data[i];
                    int t = ely_get_type(val);
                    if (t == ely_VALUE_ARRAY || t == ely_VALUE_OBJECT || t == ely_VALUE_STRING) {
                        mark_object(ELY_UNBOX_PTR(val));
                    }
                }
                break;
            }
            case GC_OBJ_DICT: {
                dict* d = (dict*)obj_ptr;
                mark_object(d->buckets);
                if (d->buckets) {
                    for (size_t i = 0; i < d->capacity; i++) {
                        dict_entry* e = d->buckets[i];
                        while (e) {
                            mark_object(e); 
                            int kt = ely_get_type(e->key);
                            if (kt == ely_VALUE_ARRAY || kt == ely_VALUE_OBJECT || kt == ely_VALUE_STRING) {
                                mark_object(ELY_UNBOX_PTR(e->key));
                            }
                            int vt = ely_get_type(e->value);
                            if (vt == ely_VALUE_ARRAY || vt == ely_VALUE_OBJECT || vt == ely_VALUE_STRING) {
                                mark_object(ELY_UNBOX_PTR(e->value));
                            }
                            e = e->next;
                        }
                    }
                }
                break;
            }
            default: break;
        }
    }
}

static void sweep_old(void) {
    old_free_list = NULL;
    char* scan = old_start;

    while (scan < old_top) {
        gc_header_t* hdr = (gc_header_t*)scan;
        size_t size = ALIGN_UP(hdr->size, GC_ALIGNMENT);

        if (hdr->flags & GC_FLAG_MARKED) {
            hdr->flags &= ~GC_FLAG_MARKED;
        } else {
            hdr->u.next_free = old_free_list;
            old_free_list = hdr;
        }
        scan += size;
    }

    if (old_free_list) {
        gc_header_t* curr = old_free_list;
        while (curr && curr->u.next_free) {
            gc_header_t* next = curr->u.next_free;
            if ((char*)curr + ALIGN_UP(curr->size, GC_ALIGNMENT) == (char*)next) {
                curr->size += ALIGN_UP(next->size, GC_ALIGNMENT);
                curr->u.next_free = next->u.next_free;
            } else {
                curr = curr->u.next_free;
            }
        }
    }
}

static void compact_old(void) {
    char* scan = old_start;
    char* dest = old_start;

    // Пасс 1: Вычисляем новые адреса (Forwarding Addresses) для всех живых блоков
    while (scan < old_top) {
        gc_header_t* hdr = (gc_header_t*)scan;
        size_t size = ALIGN_UP(hdr->size, GC_ALIGNMENT);
        if (hdr->flags & GC_FLAG_MARKED) {
            hdr->u.forwarding = (gc_header_t*)dest;
            dest += size;
        }
        scan += size;
    }

    // Пасс 2: Обновляем абсолютно все указатели в системе на новые адреса

    // 2.1. Локальные корни
    for (size_t i = 0; i < roots_count; i++) {
        adjust_ptr(roots[i]);
    }
    // 2.2. Глобальные корни
    for (size_t i = 0; i < global_roots_count; i++) {
        adjust_ptr(global_roots[i]);
    }
    // 2.3. Dirty-set
    for (size_t i = 0; i < dirty_count; i++) {
        adjust_raw_ptr((void**)&dirty_set[i]);
    }
    // 2.4. Указатели внутри Молодого Поколения (они могут вести на уплотняемый Old Gen!)
    scan = young_from;
    while (scan < young_top) {
        gc_header_t* hdr = (gc_header_t*)scan;
        update_object_pointers(header_to_ptr(hdr));
        scan += ALIGN_UP(hdr->size, GC_ALIGNMENT);
    }
    // 2.5. Указатели внутри самого Старого Поколения (пока объекты на старых местах)
    scan = old_start;
    while (scan < old_top) {
        gc_header_t* hdr = (gc_header_t*)scan;
        size_t size = ALIGN_UP(hdr->size, GC_ALIGNMENT);
        if (hdr->flags & GC_FLAG_MARKED) {
            update_object_pointers(header_to_ptr(hdr));
        }
        scan += size;
    }

    // Пасс 3: Физическое перемещение выживших объектов на их новые места
    scan = old_start;
    while (scan < old_top) {
        gc_header_t* hdr = (gc_header_t*)scan;
        size_t size = ALIGN_UP(hdr->size, GC_ALIGNMENT);
        if (hdr->flags & GC_FLAG_MARKED) {
            gc_header_t* new_hdr = hdr->u.forwarding;
            if ((char*)new_hdr != scan) {
                memmove(new_hdr, hdr, hdr->size);
            }
        }
        scan += size;
    }

    // Корректируем вершину старого поколения и сбрасываем свободный список
    old_top = dest;
    old_free_list = NULL;

    // Сбрасываем флаги маркировки у всех выживших
    scan = old_start;
    while (scan < old_top) {
        gc_header_t* hdr = (gc_header_t*)scan;
        hdr->flags &= ~GC_FLAG_MARKED;
        scan += ALIGN_UP(hdr->size, GC_ALIGNMENT);
    }
}

static void update_references(void* obj, ptrdiff_t delta) {
    if (delta == 0) return;
    gc_header_t* hdr = ptr_to_header(obj);
    switch (hdr->obj_type) {
        case GC_OBJ_VALUE: {
            ely_value* v = (ely_value*)obj;
            int t = ely_get_type(*v);
            if ((t == ely_VALUE_ARRAY || t == ely_VALUE_OBJECT || t == ely_VALUE_STRING) && ELY_UNBOX_PTR(*v)) {
                void* new_ptr = (char*)ELY_UNBOX_PTR(*v) + delta;
                ELY_REPACK_PTR(*v, new_ptr, t);
            }
            break;
        }
        case GC_OBJ_ARR: {
            arr* a = (arr*)obj;
            for (size_t i = 0; i < a->size; i++) {
                ely_value val = a->data[i];
                int t = ely_get_type(val);
                if ((t == ely_VALUE_ARRAY || t == ely_VALUE_OBJECT || t == ely_VALUE_STRING) && ELY_UNBOX_PTR(val)) {
                    void* new_ptr = (char*)ELY_UNBOX_PTR(val) + delta;
                    ELY_REPACK_PTR(a->data[i], new_ptr, t);
                }
            }
            break;
        }
        case GC_OBJ_DICT: {
            dict* d = (dict*)obj;
            if (d->buckets) d->buckets = (dict_entry**)((char*)d->buckets + delta);
            for (size_t i = 0; i < d->capacity; i++) {
                dict_entry* e = d->buckets[i];
                while (e) {
                    int kt = ely_get_type(e->key);
                    if ((kt == ely_VALUE_ARRAY || kt == ely_VALUE_OBJECT || kt == ely_VALUE_STRING) && ELY_UNBOX_PTR(e->key)) {
                        void* new_ptr = (char*)ELY_UNBOX_PTR(e->key) + delta;
                        ELY_REPACK_PTR(e->key, new_ptr, kt);
                    }
                    int vt = ely_get_type(e->value);
                    if ((vt == ely_VALUE_ARRAY || vt == ely_VALUE_OBJECT || vt == ely_VALUE_STRING) && ELY_UNBOX_PTR(e->value)) {
                        void* new_ptr = (char*)ELY_UNBOX_PTR(e->value) + delta;
                        ELY_REPACK_PTR(e->value, new_ptr, vt);
                    }
                    if (e->next) e->next = (dict_entry*)((char*)e->next + delta);
                    e = e->next;
                }
            }
            break;
        }
        default: break;
    }
}

static bool is_in_old_generation(void* ptr) {
    char* addr = (char*)ptr;
    return (addr >= old_start && addr < old_limit);
}

static bool expand_old_heap(size_t additional_bytes) {
    size_t old_virtual_max = (OLD_MAX_SIZE > 0) ? OLD_MAX_SIZE : (2ULL * 1024ULL * 1024ULL * 1024ULL);
    if (old_size + additional_bytes > old_virtual_max) {
        fprintf(stderr, "[ELYGC] WARNING: Old generation reached maximum virtual size limit!\n");
        return false; 
    }

    size_t page_size = 4096;
    size_t aligned_additional = (additional_bytes + page_size - 1) & ~(page_size - 1);

    // Коммитим новые физические страницы прямо за текущим лимитом старости
    if (!cage_commit_segment(old_limit, aligned_additional)) {
        fprintf(stderr, "[ELYGC] ERROR: Failed to commit expanded space for old generation\n");
        return false;
    }

    old_size += aligned_additional;
    old_limit = old_start + old_size;
    return true;
}

static void collect_old(void) {
    printf("[GC] collect_old started\n"); fflush(stdout);
    old_collections++;

    // Сброс флагов MARKED
    printf("[GC] clearing marks...\n"); fflush(stdout);
    for (char* scan = old_start; scan < old_top; ) {
        gc_header_t* hdr = (gc_header_t*)scan;
        hdr->flags &= ~GC_FLAG_MARKED;
        scan += ALIGN_UP(hdr->size, GC_ALIGNMENT);
    }
    for (gc_header_t* curr = large_objects; curr; curr = curr->u.next_free)
        curr->flags &= ~GC_FLAG_MARKED;

    // Маркировка из корней
    printf("[GC] marking roots (%zu local, %zu global)...\n", roots_count, global_roots_count); fflush(stdout);
    for (size_t i = 0; i < roots_count; i++) {
        if (*roots[i]) {
            printf("[GC] root %zu: %p\n", i, (void*)(uintptr_t)*roots[i]); fflush(stdout);
            mark_object((void*)*roots[i]);
        }
    }
    for (size_t i = 0; i < global_roots_count; i++)
        if (*global_roots[i] && ELY_IS_PTR(*global_roots[i])) {
			mark_object(ELY_UNBOX_PTR(*global_roots[i]));
		}

    // Маркировка из молодого поколения
    printf("[GC] marking from young generation...\n"); fflush(stdout);
    for (char* scan = young_from; scan < young_top; ) {
        gc_header_t* hdr = (gc_header_t*)scan;
        void* obj = header_to_ptr(hdr);
        if (hdr->obj_type == GC_OBJ_VALUE) {
            ely_value* v = (ely_value*)obj;
            int t = ely_get_type(*v);
            if (t == ely_VALUE_ARRAY || t == ely_VALUE_OBJECT || t == ely_VALUE_STRING) {
                mark_object(ELY_UNBOX_PTR(*v));
            }
        } else if (hdr->obj_type == GC_OBJ_ARR) {
            arr* a = (arr*)obj;
            for (size_t i = 0; i < a->size; i++) {
                ely_value val = a->data[i];
                int t = ely_get_type(val);
                if (t == ely_VALUE_ARRAY || t == ely_VALUE_OBJECT || t == ely_VALUE_STRING) {
                    mark_object(ELY_UNBOX_PTR(val));
                }
            }
        } else if (hdr->obj_type == GC_OBJ_DICT) {
            dict* d = (dict*)obj;
            for (size_t i = 0; i < d->capacity; i++) {
                dict_entry* e = d->buckets[i];
                while (e) {
                    int kt = ely_get_type(e->key);
                    if (kt == ely_VALUE_ARRAY || kt == ely_VALUE_OBJECT || kt == ely_VALUE_STRING) mark_object(ELY_UNBOX_PTR(e->key));
                    int vt = ely_get_type(e->value);
                    if (vt == ely_VALUE_ARRAY || vt == ely_VALUE_OBJECT || vt == ely_VALUE_STRING) mark_object(ELY_UNBOX_PTR(e->value));
                    e = e->next;
                }
            }
        }
        scan += ALIGN_UP(hdr->size, GC_ALIGNMENT);
    }

    // Компактизация старого поколения
    printf("[GC] compacting...\n"); fflush(stdout);
    compact_old();

    // Очистка крупных объектов
    printf("[GC] cleaning large objects...\n"); fflush(stdout);
    gc_header_t** prev = &large_objects;
    gc_header_t* curr = large_objects;
    while (curr) {
        if (curr->flags & GC_FLAG_MARKED) {
            curr->flags &= ~GC_FLAG_MARKED;
            prev = &curr->u.next_free;
            curr = curr->u.next_free;
        } else {
			gc_header_t* to_free = curr;
			*prev = curr->u.next_free;
			curr = curr->u.next_free;
			// ОШИБКА: os_free(to_free, to_free->size);
			cage_decommit_segment(to_free, to_free->size); // ИСПРАВЛЕНИЕ
		}
    }

    printf("[GC] collect_old finished\n"); fflush(stdout);
}

/* ============================================================================
 * Инициализация и завершение
 * ============================================================================ */

static char* young_from_start = NULL;
static char* young_from_limit = NULL;
static char* young_alloc_ptr  = NULL;

void gc_init(void) {
    // Инициализируем Клетку. Передаем 0, чтобы активировать дефолтные 8 ГБ
    gc_init_cage(0);

    // Выделяем регион под Молодое Поколение (оба полупространства young_from и young_to)
    size_t young_total = 2 * YOUNG_SIZE;
    young_from = (char*)cage_alloc_segment(young_total); 
    if (!young_from) { 
        fprintf(stderr, "GC: failed to allocate young generation within GigaCage\n"); 
        abort(); 
    }
    
    young_to = young_from + YOUNG_SIZE;
    young_top = young_from;
    young_limit = young_from + YOUNG_SIZE;

    // ИСПРАВЛЕНИЕ БАГА 3: Резервируем виртуальный диапазон под Старое Поколение (например, 2 ГБ)
    size_t old_virtual_max = (OLD_MAX_SIZE > 0) ? OLD_MAX_SIZE : (2ULL * 1024ULL * 1024ULL * 1024ULL);
    old_start = (char*)cage_reserve_segment(old_virtual_max);
    if (!old_start) { 
        fprintf(stderr, "GC: failed to reserve virtual space for old generation within GigaCage\n"); 
        abort(); 
    }
    
    // Физически коммитим только начальный размер (8 МБ)
    old_size = OLD_INITIAL_SIZE;
    if (!cage_commit_segment(old_start, old_size)) {
        fprintf(stderr, "GC: failed to commit initial old generation within GigaCage\n"); 
        abort(); 
    }

    old_top = old_start;
    old_limit = old_start + old_size;

    // Инициализация остального состояния
    old_free_list = NULL;
    large_objects = NULL;
    roots = NULL;
    roots_count = roots_capacity = 0;
    global_roots = NULL;
    global_roots_count = global_roots_capacity = 0;
    dirty_set = NULL;
    dirty_count = dirty_capacity = 0;

    young_collections = 0;
    old_collections = 0;
    gc_enabled = true;

    ensure_roots_capacity();
    ensure_global_roots_capacity();
    ensure_dirty_capacity();
}

void gc_shutdown(void) {
    if (!young_from) return;

    // Декоммитим крупные объекты
    gc_header_t* curr = large_objects;
    while (curr) {
        gc_header_t* next = curr->u.next_free;
        cage_decommit_segment(curr, curr->size);
        curr = next;
    }

    free(roots);
    free(global_roots);
    free(dirty_set);

    // Освобождаем всю Клетку целиком из ОС (одним системным вызовом базового адреса)
    if (g_cage_base) {
        os_free((void*)g_cage_base, g_cage_limit - g_cage_base);
    }

    young_from = young_to = young_top = young_limit = NULL;
    old_start = old_top = old_limit = NULL;
    old_free_list = NULL;
    large_objects = NULL;
    roots = NULL;
    global_roots = NULL;
    dirty_set = NULL;
    g_cage_base = g_cage_limit = 0;
    cage_brk = NULL;
}

/* ============================================================================
 * Публичные функции управления корнями и барьерами
 * ============================================================================ */

void gc_add_root(uint64_t* ptr) {
    if (!gc_enabled) return;
    ensure_roots_capacity();
    roots[roots_count++] = ptr;
}

void gc_remove_root(uint64_t* ptr) {
    if (!gc_enabled) return;
    for (size_t i = 0; i < roots_count; i++) {
        if (roots[i] == ptr) {
            roots[i] = roots[--roots_count];
            return;
        }
    }
}

void gc_add_global_root(void** ptr) {
    if (!gc_enabled) return;
    ensure_global_roots_capacity();
    global_roots[global_roots_count++] = (uint64_t*)ptr;
}

void gc_remove_global_root(void** ptr) {
    if (!gc_enabled) return;
    for (size_t i = 0; i < global_roots_count; i++) {
        if (global_roots[i] == (uint64_t*)ptr) {
            global_roots[i] = global_roots[--global_roots_count];
            return;
        }
    }
}

void gc_write_barrier(void* parent, void** field, void* new_value) {
    if (!gc_enabled) { *field = new_value; return; }
    *field = new_value;
    if (!parent) return;
    gc_header_t* parent_hdr = ptr_to_header(parent);
    if ((parent_hdr->flags & GC_FLAG_IN_OLD) && new_value) {
        gc_header_t* child_hdr = ptr_to_header(new_value);
        if (!(child_hdr->flags & GC_FLAG_IN_OLD) && !(child_hdr->flags & GC_FLAG_LARGE)) {
            add_dirty(parent_hdr);
        }
    }
}

void gc_write_barrier_global(void** field, void* new_value) {
    *field = new_value;
}

void gc_collect_young(void) { if (gc_enabled) collect_young(); }
void gc_collect_old(void)   { if (gc_enabled) collect_old(); }
void gc_collect(void) {
    if (gc_enabled) {
        collect_young();
        collect_old(); 
    }
}

/* ============================================================================
 * Статистика и информационные функции
 * ============================================================================ */

void gc_dump_stats(void) {
    size_t young_used = (size_t)(young_top - young_from);
    size_t old_used = (size_t)(old_top - old_start);
    size_t free_in_old = 0, free_blocks = 0;
    for (gc_header_t* b = old_free_list; b; b = b->u.next_free) {
        free_in_old += b->size;
        free_blocks++;
    }
    size_t large_count = 0, large_total = 0;
    for (gc_header_t* b = large_objects; b; b = b->u.next_free) {
        large_count++;
        large_total += b->size;
    }

    printf("========== GC Statistics ==========\n");
    printf("Young collections: %llu\n", (unsigned long long)young_collections);
    printf("Old collections:   %llu\n", (unsigned long long)old_collections);
    printf("Young used:        %zu / %d bytes (%.1f%%)\n", young_used, YOUNG_SIZE, 100.0 * young_used / YOUNG_SIZE);
    printf("Old used:          %zu / %zu bytes, %zu free in %zu blocks\n", old_used, old_size, free_in_old, free_blocks);
    printf("Large objects:     %zu objects, %zu bytes\n", large_count, large_total);
    printf("Roots:             %zu local, %zu global\n", roots_count, global_roots_count);
    printf("Dirty objects:     %zu\n", dirty_count);
    printf("GC enabled:        %s\n", gc_enabled ? "yes" : "no");
    printf("===================================\n");
}

size_t gc_get_heap_size(void) {
    size_t total = 2 * YOUNG_SIZE + old_size;
    for (gc_header_t* b = large_objects; b; b = b->u.next_free) total += b->size;
    return total;
}

size_t gc_get_free_bytes(void) {
    size_t free_young = (size_t)(young_limit - young_top);
    size_t free_old = 0;
    for (gc_header_t* b = old_free_list; b; b = b->u.next_free) free_old += b->size;
    free_old += (size_t)(old_limit - old_top);
    return free_young + free_old;
}

size_t gc_get_used_bytes(void) { return gc_get_heap_size() - gc_get_free_bytes(); }
uint64_t gc_get_young_collections(void) { return young_collections; }
uint64_t gc_get_old_collections(void)   { return old_collections; }

void gc_set_enabled(bool enabled) { gc_enabled = enabled; }
bool gc_is_enabled(void)          { return gc_enabled; }

void gc_set_old_threshold(int percent) {
    if (percent < 0) percent = 0;
    if (percent > 100) percent = 100;
    old_threshold_percent = percent;
}

void gc_compact(void) { if (gc_enabled) { collect_old(); compact_old(); } }
bool gc_expand_heap(size_t additional_bytes) { return gc_enabled ? expand_old_heap(additional_bytes) : false; }
void gc_collect_full(void) { if (gc_enabled) { collect_young(); collect_old(); compact_old(); } }

char* gc_strdup(const char* s) {
    if (!s) return NULL;
    size_t len = strlen(s) + 1;
    char* copy = (char*)gc_alloc(len, GC_OBJ_STRING);
    if (copy) memcpy(copy, s, len);
    return copy;
}

static bool is_in_young_generation(void* ptr) {
    char* addr = (char*)ptr;
    return (addr >= young_from && addr < young_from + 2 * YOUNG_SIZE);
}

bool is_gc_managed(void* ptr) {
    if (!ptr) return false;
    char* addr = (char*)ptr;
    // Проверяем молодое поколение (оба полупространства)
    if (addr >= young_from && addr < young_from + 2 * YOUNG_SIZE) return true;
    // Старое поколение
    if (addr >= old_start && addr < old_limit) return true;
    // Крупные объекты (ищем в списке)
    for (gc_header_t* curr = large_objects; curr; curr = curr->u.next_free) {
        if (header_to_ptr(curr) == ptr) return true;
    }
    return false;
}

/**
 * @brief Посещает одну ячейку (слот), содержащую ely_value. 
 * Если там упакован указатель на объект кучи, GC обновляет его (в случае переноса объекта).
 */
void gc_trace_value(ely_value* slot) {
    ely_value v = *slot;

    // Если это не указатель Клетки (число, bool, null) — сборщику мусора тут делать нечего
    if (!ely_is_ptr(v)) {
        return;
    }

    // Извлекаем чистый адрес объекта из битовой сетки
    gc_header_t* old_hdr = (gc_header_t*)((char*)ely_unbox_ptr(v) - HEADER_SIZE);

    // Проверяем, был ли объект уже скопирован (Forwarding pointer)
    if (old_hdr->u.forwarding != NULL) {
        // Объект уже перемещен, просто обновляем ячейку новым адресом
        *slot = ely_box_ptr(header_to_ptr(old_hdr->u.forwarding));
        return;
    }

    // Если объект лежит в молодом поколении и еще не скопирован — копируем его!
    // (Логика твоей функции перемещения, например copy_to_survivor или аналогичной)
    if ((char*)old_hdr >= young_from && (char*)old_hdr < young_limit) {
        gc_header_t* new_hdr = gc_move_object(old_hdr); 
        
        // Записываем новый упакованный адрес обратно в ячейку
        *slot = ely_box_ptr(header_to_ptr(new_hdr));
    }
}

void gc_trace_roots(void) {
    // Обходим локальные корни (стековые переменные)
    for (size_t i = 0; i < roots_count; i++) {
        gc_trace_value(roots[i]);
    }

    // Обходим глобальные переменные
    for (size_t i = 0; i < global_roots_count; i++) {
        gc_trace_value(global_roots[i]);
    }
}

void gc_scan_object(gc_header_t* hdr) {
    switch (hdr->obj_type) {
        case GC_OBJ_ARR: {
            arr* a = (arr*)header_to_ptr(hdr);
            
            // 1. Если буфер данных переместился, обновляем указатель на него
            if (a->data) {
                gc_header_t* data_hdr = ptr_to_header(a->data);
                gc_header_t* new_data_hdr = gc_move_object(data_hdr);
                a->data = (ely_value*)header_to_ptr(new_data_hdr);
            }
            
            // 2. Трассируем все живые элементы внутри массива
            for (size_t i = 0; i < a->size; i++) {
                gc_trace_value(&a->data[i]); 
            }
            break;
        }
        
        case GC_OBJ_DICT: {
            dict* d = (dict*)header_to_ptr(hdr);
            
            // 1. Обновляем указатель на массив бакетов при перемещении
            if (d->buckets) {
                gc_header_t* b_hdr = ptr_to_header(d->buckets);
                gc_header_t* new_b_hdr = gc_move_object(b_hdr);
                d->buckets = (dict_entry**)header_to_ptr(new_b_hdr);
            }
            
            // 2. Проходим по всем бакетам и глубоко копируем/трассируем ноды коллизий
            for (size_t i = 0; i < d->capacity; i++) {
                dict_entry* e = d->buckets[i];
                dict_entry* prev = NULL;
                while (e) {
                    // Перемещаем саму ноду в новое полупространство
                    gc_header_t* e_hdr = ptr_to_header(e);
                    dict_entry* new_e = (dict_entry*)header_to_ptr(gc_move_object(e_hdr));
                    
                    // Перепривязываем указатели в цепочке
                    if (prev) {
                        prev->next = new_e;
                    } else {
                        d->buckets[i] = new_e;
                    }
                    
                    // Трассируем ключ и значение внутри новой копии ноды
                    gc_trace_value(&new_e->key);
                    gc_trace_value(&new_e->value);
                    
                    prev = new_e;
                    e = new_e->next; // Переходим к следующей старой ноде
                }
            }
            break;
        }
        
        case GC_OBJ_STRING:
        case GC_OBJ_DOUBLE:
        case GC_OBJ_VALUE: 
            break;
    }
}

// Сканирование одного Ely-значения
void gc_scan_value(ely_value v) {
    // Если биты говорят, что это указатель на объект внутри GigaCage
    if (ely_is_ptr(v)) {
        void* ptr = (void*)ely_unbox_ptr(v);
        mark_object(ptr); // Маркируем сам объект в куче
    }
}

// Сканирование массива (GC_OBJ_ARR)
void gc_scan_array(arr* a) {
    for (size_t i = 0; i < arr_len(a); i++) {
        // Массив теперь хранит сырые 64-битные ely_value
        ely_value elem = arr_get(a, i); 
        gc_scan_value(elem);
    }
}

// Сканирование словаря/объекта (GC_OBJ_OBJECT)
void gc_scan_dict(dict* d) {
    for (size_t i = 0; i < d->capacity; i++) {
        // ИСПРАВЛЕНИЕ ОШИБКИ: используем buckets вместо entries
        dict_entry* e = d->buckets[i]; 
        while (e) {
            gc_scan_value(e->key);   // На случай, если ключи динамические
            gc_scan_value(e->value); // Маркируем значение под ключом
            e = e->next;
        }
    }
}