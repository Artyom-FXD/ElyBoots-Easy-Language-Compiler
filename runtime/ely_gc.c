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
#include "ely_runtime.h"

#ifdef _WIN32
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

static void*** roots = NULL;
static size_t roots_count = 0;
static size_t roots_capacity = 0;

static void*** global_roots = NULL;
static size_t global_roots_count = 0;
static size_t global_roots_capacity = 0;

static gc_header_t** dirty_set = NULL;
static size_t dirty_count = 0;
static size_t dirty_capacity = 0;

static uint64_t young_collections = 0;
static uint64_t old_collections = 0;
static bool gc_enabled = true;
static int old_threshold_percent = 75;

/* ============================================================================
 * Прототипы статических функций (чтобы избежать неявных объявлений)
 * ============================================================================ */

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
        roots = realloc(roots, roots_capacity * sizeof(void**));
        if (!roots) { fprintf(stderr, "GC: out of memory for roots\n"); abort(); }
    }
}

static void ensure_global_roots_capacity(void) {
    if (global_roots_count >= global_roots_capacity) {
        global_roots_capacity = global_roots_capacity ? global_roots_capacity * 2 : 64;
        global_roots = realloc(global_roots, global_roots_capacity * sizeof(void**));
        if (!global_roots) { fprintf(stderr, "GC: out of memory for global roots\n"); abort(); }
    }
}

static void ensure_dirty_capacity(void) {
    if (dirty_count >= dirty_capacity) {
        dirty_capacity = dirty_capacity ? dirty_capacity * 2 : 64;
        dirty_set = realloc(dirty_set, dirty_capacity * sizeof(gc_header_t*));
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
    void* mem = os_alloc(total);
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
 * Основная аллокация
 * ============================================================================ */

void* gc_alloc(size_t size, gc_obj_type_t type) {
    if (!gc_enabled) {
        void* ptr = malloc(size);
        memset(ptr, 0, size);
        return ptr;
    }

    size_t total = HEADER_SIZE + ALIGN_UP(size, GC_ALIGNMENT);
    if (total >= LARGE_OBJECT_THRESHOLD) {
        return allocate_large(size, type);
    }
    return allocate_young(size, type);
    // return malloc(size);
}

void* gc_calloc(size_t size, gc_obj_type_t type) {
    void* ptr = gc_alloc(size, type);
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

static void scan_object_fields(void* obj_ptr) {
    gc_header_t* hdr = ptr_to_header(obj_ptr);
    switch (hdr->obj_type) {
        case GC_OBJ_VALUE: {
            ely_value* v = (ely_value*)obj_ptr;
            if (v->type == ely_VALUE_ARRAY) v->u.array_val = copy_object(v->u.array_val);
            else if (v->type == ely_VALUE_OBJECT) v->u.object_val = copy_object(v->u.object_val);
            break;
        }
        case GC_OBJ_ARR: {
            arr* a = (arr*)obj_ptr;
            for (size_t i = 0; i < a->size; i++) a->data[i] = copy_object(a->data[i]);
            break;
        }
        case GC_OBJ_DICT: {
            dict* d = (dict*)obj_ptr;
            for (size_t i = 0; i < d->capacity; i++) {
                dict_entry* e = d->buckets[i];
                while (e) {
                    e->key = copy_object(e->key);
                    e->value = copy_object(e->value);
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
        if (*roots[i]) *roots[i] = copy_object(*roots[i]);
    }
    for (size_t i = 0; i < global_roots_count; i++) {
        if (*global_roots[i]) *global_roots[i] = copy_object(*global_roots[i]);
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
 * Сборка старого поколения (mark‑sweep)
 * ============================================================================ */

static void mark_object(void* obj_ptr) {
    if (!obj_ptr) return;
    if (!is_gc_managed(obj_ptr)) {
        gc_header_t* hdr = ptr_to_header(obj_ptr);
        if (hdr->flags & GC_FLAG_MARKED) return;
        hdr->flags |= GC_FLAG_MARKED;

        switch (hdr->obj_type) {
            case GC_OBJ_VALUE: {
                ely_value* v = (ely_value*)obj_ptr;
                if (v->type == ely_VALUE_ARRAY) mark_object(v->u.array_val);
                else if (v->type == ely_VALUE_OBJECT) mark_object(v->u.object_val);
                break;
            }
            case GC_OBJ_ARR: {
                arr* a = (arr*)obj_ptr;
                for (size_t i = 0; i < a->size; i++) mark_object(a->data[i]);
                break;
            }
            case GC_OBJ_DICT: {
                dict* d = (dict*)obj_ptr;
                for (size_t i = 0; i < d->capacity; i++) {
                    dict_entry* e = d->buckets[i];
                    while (e) {
                        mark_object(e->key);
                        mark_object(e->value);
                        e = e->next;
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

    // Первый проход: вычисляем новые адреса и сохраняем их в forwarding
    while (scan < old_top) {
        gc_header_t* hdr = (gc_header_t*)scan;
        size_t size = ALIGN_UP(hdr->size, GC_ALIGNMENT);
        if (hdr->flags & GC_FLAG_MARKED) {
            hdr->u.forwarding = (gc_header_t*)dest;
            dest += size;
        }
        scan += size;
    }

    // Второй проход: перемещаем объекты и обновляем внутренние ссылки
    scan = old_start;
    while (scan < old_top) {
        gc_header_t* hdr = (gc_header_t*)scan;
        size_t size = ALIGN_UP(hdr->size, GC_ALIGNMENT);
        if (hdr->flags & GC_FLAG_MARKED) {
            gc_header_t* new_hdr = hdr->u.forwarding;
            if ((char*)new_hdr != scan) {
                memmove(new_hdr, hdr, hdr->size);
            }
            // Обновляем ссылки внутри объекта
            update_references(header_to_ptr(new_hdr), (char*)new_hdr - scan);
            scan += size;
        } else {
            scan += size;
        }
    }

    // Обновляем корни
    for (size_t i = 0; i < roots_count; i++) {
        void** root = roots[i];
        if (*root && is_in_old_generation(*root)) {
            gc_header_t* hdr = ptr_to_header(*root);
            if (hdr->flags & GC_FLAG_MARKED) {
                *root = header_to_ptr(hdr->u.forwarding);
            }
        }
    }
    for (size_t i = 0; i < global_roots_count; i++) {
        void** root = global_roots[i];
        if (*root && is_in_old_generation(*root)) {
            gc_header_t* hdr = ptr_to_header(*root);
            if (hdr->flags & GC_FLAG_MARKED) {
                *root = header_to_ptr(hdr->u.forwarding);
            }
        }
    }

    // Обновляем dirty‑set
    for (size_t i = 0; i < dirty_count; i++) {
        gc_header_t* hdr = dirty_set[i];
        if (hdr->flags & GC_FLAG_MARKED) {
            dirty_set[i] = hdr->u.forwarding;
        }
    }

    // Устанавливаем новую вершину кучи и сбрасываем free‑list
    old_top = dest;
    old_free_list = NULL;

    // Сбрасываем флаг MARKED у всех живых объектов
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
            if (v->type == ely_VALUE_ARRAY && v->u.array_val)
                v->u.array_val = (arr*)((char*)v->u.array_val + delta);
            else if (v->type == ely_VALUE_OBJECT && v->u.object_val)
                v->u.object_val = (dict*)((char*)v->u.object_val + delta);
            break;
        }
        case GC_OBJ_ARR: {
            arr* a = (arr*)obj;
            for (size_t i = 0; i < a->size; i++)
                if (a->data[i]) a->data[i] = (ely_value*)((char*)a->data[i] + delta);
            break;
        }
        case GC_OBJ_DICT: {
            dict* d = (dict*)obj;
            for (size_t i = 0; i < d->capacity; i++) {
                dict_entry* e = d->buckets[i];
                while (e) {
                    if (e->key) e->key = (ely_value*)((char*)e->key + delta);
                    if (e->value) e->value = (ely_value*)((char*)e->value + delta);
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
    if (OLD_MAX_SIZE > 0 && old_size + additional_bytes > OLD_MAX_SIZE) return false;
    size_t new_size = old_size + additional_bytes;
    char* new_start = os_resize(old_start, old_size, new_size);
    if (!new_start) return false;

    ptrdiff_t delta = new_start - old_start;
    if (delta != 0) {
        old_start = new_start;
        old_top += delta;
        old_limit = old_start + new_size;
        old_free_list = NULL;
        // Обновление корней и dirty-сета для простоты не делаем, т.к. при следующей сборке всё синхронизируется
    } else {
        old_limit = old_start + new_size;
    }
    old_size = new_size;
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
            printf("[GC] root %zu: %p\n", i, *roots[i]); fflush(stdout);
            mark_object(*roots[i]);
        }
    }
    for (size_t i = 0; i < global_roots_count; i++)
        if (*global_roots[i]) mark_object(*global_roots[i]);

    // Маркировка из молодого поколения
    printf("[GC] marking from young generation...\n"); fflush(stdout);
    for (char* scan = young_from; scan < young_top; ) {
        gc_header_t* hdr = (gc_header_t*)scan;
        void* obj = header_to_ptr(hdr);
        if (hdr->obj_type == GC_OBJ_VALUE) {
            ely_value* v = obj;
            if (v->type == ely_VALUE_ARRAY) mark_object(v->u.array_val);
            else if (v->type == ely_VALUE_OBJECT) mark_object(v->u.object_val);
        } else if (hdr->obj_type == GC_OBJ_ARR) {
            arr* a = obj;
            for (size_t i = 0; i < a->size; i++) mark_object(a->data[i]);
        } else if (hdr->obj_type == GC_OBJ_DICT) {
            dict* d = obj;
            for (size_t i = 0; i < d->capacity; i++) {
                dict_entry* e = d->buckets[i];
                while (e) {
                    mark_object(e->key);
                    mark_object(e->value);
                    e = e->next;
                }
            }
        }
        scan += ALIGN_UP(hdr->size, GC_ALIGNMENT);
    }

    // Компактизация старого поколения (вместо sweep)
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
            os_free(to_free, to_free->size);
        }
    }

    printf("[GC] collect_old finished\n"); fflush(stdout);
}

/* ============================================================================
 * Инициализация и завершение
 * ============================================================================ */

void gc_init(void) {
    size_t young_total = 2 * YOUNG_SIZE;
    young_from = os_alloc(young_total);
    if (!young_from) { fprintf(stderr, "GC: failed to allocate young generation\n"); abort(); }
    young_to = young_from + YOUNG_SIZE;
    young_top = young_from;
    young_limit = young_from + YOUNG_SIZE;

    old_size = OLD_INITIAL_SIZE;
    old_start = os_alloc(old_size);
    if (!old_start) { fprintf(stderr, "GC: failed to allocate old generation\n"); abort(); }
    old_top = old_start;
    old_limit = old_start + old_size;

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
    os_free(young_from, 2 * YOUNG_SIZE);
    os_free(old_start, old_size);

    gc_header_t* curr = large_objects;
    while (curr) {
        gc_header_t* next = curr->u.next_free;
        os_free(curr, curr->size);
        curr = next;
    }

    free(roots);
    free(global_roots);
    free(dirty_set);

    young_from = young_to = young_top = young_limit = NULL;
    old_start = old_top = old_limit = NULL;
    old_free_list = NULL;
    large_objects = NULL;
    roots = NULL;
    global_roots = NULL;
    dirty_set = NULL;
}

/* ============================================================================
 * Публичные функции управления корнями и барьерами
 * ============================================================================ */

void gc_add_root(void** ptr) {
    if (!gc_enabled) return;
    ensure_roots_capacity();
    roots[roots_count++] = ptr;
}

void gc_remove_root(void** ptr) {
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
    global_roots[global_roots_count++] = ptr;
}

void gc_remove_global_root(void** ptr) {
    if (!gc_enabled) return;
    for (size_t i = 0; i < global_roots_count; i++) {
        if (global_roots[i] == ptr) {
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

static bool is_gc_managed(void* ptr) {
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