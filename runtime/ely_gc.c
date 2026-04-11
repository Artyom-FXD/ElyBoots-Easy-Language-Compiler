/**
 * @file gc_new.c
 * @brief Реализация поколенческого сборщика мусора для языка Ely.
 *
 * Подробное описание алгоритмов см. в gc_new.h и сопроводительной документации.
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

/* Получить заголовок по пользовательскому указателю */
static inline gc_header_t* ptr_to_header(void* ptr) {
    return (gc_header_t*)((char*)ptr - HEADER_SIZE);
}

/* Получить пользовательский указатель по заголовку */
static inline void* header_to_ptr(gc_header_t* hdr) {
    return (char*)hdr + HEADER_SIZE;
}

/* ============================================================================
 * Глобальное состояние сборщика
 * ============================================================================ */

/* Молодое поколение */
static char* young_from = NULL;   /* активное полупространство (from-space) */
static char* young_to   = NULL;   /* неактивное полупространство (to-space) */
static char* young_top  = NULL;   /* текущая вершина from-space */
static char* young_limit = NULL;  /* конец from-space */

/* Старое поколение */
static char* old_start = NULL;    /* начало кучи */
static char* old_top   = NULL;    /* текущая вершина выделения (если нет free-list) */
static char* old_limit = NULL;    /* конец выделенной памяти */
static size_t old_size = 0;       /* текущий размер кучи */

/* Free-list для старого поколения (односвязный список) */
static gc_header_t* old_free_list = NULL;

/* Список крупных объектов (LOS) */
static gc_header_t* large_objects = NULL;

/* Корни */
static void*** roots = NULL;           /* динамический массив локальных корней */
static size_t roots_count = 0;
static size_t roots_capacity = 0;

static void*** global_roots = NULL;    /* массив глобальных корней */
static size_t global_roots_count = 0;
static size_t global_roots_capacity = 0;

/* Dirty‑объекты (старые объекты, содержащие ссылки на молодые) */
static gc_header_t** dirty_set = NULL;
static size_t dirty_count = 0;
static size_t dirty_capacity = 0;

/* Статистика */
static uint64_t young_collections = 0;
static uint64_t old_collections = 0;
static bool gc_enabled = true;

/* Порог заполнения старого поколения для запуска сборки (в процентах) */
static int old_threshold_percent = 75;

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
    /* Windows не имеет простого аналога mremap. Выделяем новый блок и копируем. */
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
        if (!roots) {
            fprintf(stderr, "GC: out of memory for roots\n");
            abort();
        }
    }
}

static void ensure_global_roots_capacity(void) {
    if (global_roots_count >= global_roots_capacity) {
        global_roots_capacity = global_roots_capacity ? global_roots_capacity * 2 : 64;
        global_roots = realloc(global_roots, global_roots_capacity * sizeof(void**));
        if (!global_roots) {
            fprintf(stderr, "GC: out of memory for global roots\n");
            abort();
        }
    }
}

static void ensure_dirty_capacity(void) {
    if (dirty_count >= dirty_capacity) {
        dirty_capacity = dirty_capacity ? dirty_capacity * 2 : 64;
        dirty_set = realloc(dirty_set, dirty_capacity * sizeof(gc_header_t*));
        if (!dirty_set) {
            fprintf(stderr, "GC: out of memory for dirty set\n");
            abort();
        }
    }
}

/* Добавить объект в dirty‑set, если его там ещё нет */
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
        /* Не хватает места, запускаем сборку молодого поколения */
        collect_young();
        if (young_top + total > young_limit) {
            /* После сборки всё ещё нет места – продвигаем в старое */
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

    /* 1. Поиск в free‑list */
    gc_header_t* prev = NULL;
    gc_header_t* curr = old_free_list;
    while (curr) {
        if (curr->size >= total) {
            /* Подходящий блок */
            if (curr->size >= total + HEADER_SIZE + GC_ALIGNMENT) {
                /* Разбиваем блок: оставляем остаток в free‑list */
                gc_header_t* remainder = (gc_header_t*)((char*)curr + total);
                remainder->size = curr->size - (uint32_t)total;
                remainder->flags = 0;
                remainder->u.next_free = curr->u.next_free;
                if (prev) prev->u.next_free = remainder;
                else old_free_list = remainder;
                curr->size = (uint32_t)total;
            } else {
                /* Используем блок целиком */
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

    /* 2. Выделение из конца кучи */
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

    /* 3. Нехватка памяти – сборка старого поколения */
    collect_old();
    /* Повторяем поиск в free‑list и выделение из конца кучи (рекурсивный вызов) */
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
    hdr->u.next_free = (gc_header_t*)large_objects; /* вставляем в список */
    large_objects = hdr;

    return header_to_ptr(hdr);
}

/* ============================================================================
 * Основная аллокация
 * ============================================================================ */

void* gc_alloc(size_t size, gc_obj_type_t type) {
    if (!gc_enabled) {
        /* Режим отладки: используем malloc */
        void* ptr = malloc(size);
        memset(ptr, 0, size);
        return ptr;
    }

    size_t total = HEADER_SIZE + ALIGN_UP(size, GC_ALIGNMENT);
    if (total >= LARGE_OBJECT_THRESHOLD) {
        return allocate_large(size, type);
    }
    return allocate_young(size, type);
}

void* gc_calloc(size_t size, gc_obj_type_t type) {
    void* ptr = gc_alloc(size, type);
    if (ptr) memset(ptr, 0, size);
    return ptr;
}

/* ============================================================================
 * Сборка молодого поколения (копирующая)
 * ============================================================================ */

static void collect_young(void) {
    young_collections++;
    /* Меняем местами from и to */
    char* tmp = young_from;
    young_from = young_to;
    young_to = tmp;
    young_top = young_from;
    young_limit = young_from + YOUNG_SIZE;

    /* Функция копирования и обновления ссылок */
    /* (реализация опущена для краткости, будет использовать forwarding) */

    /* Обход корней и dirty‑объектов, копирование достижимых объектов */
    /* ... */

    /* Сброс dirty‑set */
    for (size_t i = 0; i < dirty_count; i++) {
        dirty_set[i]->flags &= ~GC_FLAG_DIRTY;
    }
    dirty_count = 0;
}

/* ============================================================================
 * Сборка старого поколения (mark‑sweep‑compact)
 * ============================================================================ */

static void collect_old(void) {
    old_collections++;
    /* Фаза mark (STW) */
    /* ... */

    /* Фаза sweep (построение free‑list) */
    /* ... */

    /* При необходимости – уплотнение */
    /* ... */
}

/* ============================================================================
 * Полная сборка
 * ============================================================================ */

void gc_collect(void) {
    if (!gc_enabled) return;
    collect_young();
    collect_old();
}

void gc_collect_young(void) {
    if (!gc_enabled) return;
    collect_young();
}

void gc_collect_old(void) {
    if (!gc_enabled) return;
    collect_old();
}

/* ============================================================================
 * Инициализация и завершение
 * ============================================================================ */

void gc_init(void) {
    /* Молодое поколение: выделяем 2 * YOUNG_SIZE */
    size_t young_total = 2 * YOUNG_SIZE;
    young_from = os_alloc(young_total);
    if (!young_from) {
        fprintf(stderr, "GC: failed to allocate young generation\n");
        abort();
    }
    young_to = young_from + YOUNG_SIZE;
    young_top = young_from;
    young_limit = young_from + YOUNG_SIZE;

    /* Старое поколение */
    old_size = OLD_INITIAL_SIZE;
    old_start = os_alloc(old_size);
    if (!old_start) {
        fprintf(stderr, "GC: failed to allocate old generation\n");
        abort();
    }
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

    /* Предварительное выделение небольших массивов */
    ensure_roots_capacity();
    ensure_global_roots_capacity();
    ensure_dirty_capacity();
}

void gc_shutdown(void) {
    if (!young_from) return;

    /* Освобождение памяти ОС */
    os_free(young_from, 2 * YOUNG_SIZE);
    os_free(old_start, old_size);

    /* Освобождение крупных объектов */
    gc_header_t* curr = large_objects;
    while (curr) {
        gc_header_t* next = curr->u.next_free;
        os_free(curr, curr->size);
        curr = next;
    }

    free(roots);
    free(global_roots);
    free(dirty_set);

    /* Обнуление указателей */
    young_from = young_to = young_top = young_limit = NULL;
    old_start = old_top = old_limit = NULL;
    old_free_list = NULL;
    large_objects = NULL;
    roots = NULL;
    global_roots = NULL;
    dirty_set = NULL;
}

/* ============================================================================
 * Управление корнями
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

/* ============================================================================
 * Барьер записи
 * ============================================================================ */

void gc_write_barrier(void* parent, void** field, void* new_value) {
    if (!gc_enabled) return;
    if (!parent) return;
    *field = new_value;
    gc_header_t* parent_hdr = ptr_to_header(parent);
    if ((parent_hdr->flags & GC_FLAG_IN_OLD) && new_value) {
        gc_header_t* child_hdr = ptr_to_header(new_value);
        if (!(child_hdr->flags & GC_FLAG_IN_OLD)) {
            add_dirty(parent_hdr);
        }
    }
    /* TODO: поддержка concurrent marking */
}

void gc_write_barrier_global(void** field, void* new_value) {
    *field = new_value;
    /* Для глобальных переменных не требуется dirty‑барьер, т.к. они всегда корни */
}

/* ============================================================================
 * Статистика и информация
 * ============================================================================ */

void gc_dump_stats(void) {
    size_t young_used = (size_t)(young_top - young_from);
    size_t old_used = (size_t)(old_top - old_start);
    size_t free_in_old = 0;
    for (gc_header_t* b = old_free_list; b; b = b->u.next_free) {
        free_in_old += b->size;
    }

    printf("========== GC Statistics ==========\n");
    printf("Young collections: %llu\n", (unsigned long long)young_collections);
    printf("Old collections:   %llu\n", (unsigned long long)old_collections);
    printf("Young used:        %zu / %d bytes\n", young_used, YOUNG_SIZE);
    printf("Old used:          %zu / %zu bytes (free list: %zu)\n", old_used, old_size, free_in_old);
    printf("Roots count:       %zu (global: %zu)\n", roots_count, global_roots_count);
    printf("Dirty objects:     %zu\n", dirty_count);
    printf("===================================\n");
}

size_t gc_get_heap_size(void) {
    return 2 * YOUNG_SIZE + old_size;
}

size_t gc_get_free_bytes(void) {
    size_t free_young = (size_t)(young_limit - young_top);
    size_t free_old = 0;
    for (gc_header_t* b = old_free_list; b; b = b->u.next_free) {
        free_old += b->size;
    }
    free_old += (size_t)(old_limit - old_top);
    return free_young + free_old;
}

size_t gc_get_used_bytes(void) {
    size_t young_used = (size_t)(young_top - young_from);
    size_t old_used = (size_t)(old_top - old_start);
    size_t free_in_old = 0;
    for (gc_header_t* b = old_free_list; b; b = b->u.next_free) {
        free_in_old += b->size;
    }
    return young_used + (old_used - free_in_old);
}

uint64_t gc_get_young_collections(void) { return young_collections; }
uint64_t gc_get_old_collections(void)   { return old_collections; }

/* ============================================================================
 * Управление режимом
 * ============================================================================ */

void gc_set_enabled(bool enabled) { gc_enabled = enabled; }
bool gc_is_enabled(void)           { return gc_enabled; }

void gc_set_old_threshold(int percent) {
    if (percent < 0) percent = 0;
    if (percent > 100) percent = 100;
    old_threshold_percent = percent;
}

/* ============================================================================
 * Сборка молодого поколения (копирующая, алгоритм Чейни)
 * ============================================================================ */

/* Вспомогательная функция копирования одного объекта и обновления ссылок */
static void* copy_object(void* obj_ptr) {
    if (!obj_ptr) return NULL;
    gc_header_t* hdr = ptr_to_header(obj_ptr);
    
    /* Если объект уже скопирован, возвращаем forwarding‑указатель */
    if (hdr->flags & GC_FLAG_MARKED) {  /* в молодом поколении MARKED означает forwarded */
        return header_to_ptr(hdr->u.forwarding);
    }
    
    /* Проверяем, не пора ли продвинуть объект в старое поколение */
    if (hdr->age >= PROMOTION_AGE) {
        /* Продвижение: копируем в старую кучу */
        size_t size = hdr->size;
        void* new_mem = allocate_old(size - HEADER_SIZE, (gc_obj_type_t)hdr->obj_type);
        if (!new_mem) {
            fprintf(stderr, "GC: promotion failed, out of memory\n");
            abort();
        }
        memcpy(new_mem, obj_ptr, size - HEADER_SIZE);
        gc_header_t* new_hdr = ptr_to_header(new_mem);
        new_hdr->flags |= GC_FLAG_IN_OLD;
        new_hdr->age = 0;  /* сброс счётчика выживаний */
        
        /* Устанавливаем forwarding в исходном объекте */
        hdr->flags |= GC_FLAG_MARKED;
        hdr->u.forwarding = new_hdr;
        return new_mem;
    }
    
    /* Обычное копирование в to‑space */
    size_t total = ALIGN_UP(hdr->size, GC_ALIGNMENT);
    if (young_top + total > young_limit) {
        fprintf(stderr, "GC: young generation overflow during collection\n");
        abort();
    }
    gc_header_t* new_hdr = (gc_header_t*)young_top;
    young_top += total;
    memcpy(new_hdr, hdr, hdr->size);
    new_hdr->age++;  /* увеличиваем счётчик выживаний */
    new_hdr->flags &= ~GC_FLAG_MARKED;  /* сбрасываем флаг forwarded */
    
    /* Устанавливаем forwarding в исходном объекте */
    hdr->flags |= GC_FLAG_MARKED;
    hdr->u.forwarding = new_hdr;
    
    return header_to_ptr(new_hdr);
}

/* Обход и обновление полей объекта в зависимости от его типа */
static void scan_object_fields(void* obj_ptr) {
    gc_header_t* hdr = ptr_to_header(obj_ptr);
    switch (hdr->obj_type) {
        case GC_OBJ_VALUE: {
            ely_value* v = (ely_value*)obj_ptr;
            switch (v->type) {
                case ely_VALUE_ARRAY:
                    v->u.array_val = copy_object(v->u.array_val);
                    break;
                case ely_VALUE_OBJECT:
                    v->u.object_val = copy_object(v->u.object_val);
                    break;
                case ely_VALUE_STRING:
                    /* строки не содержат указателей, но сам буфер является частью объекта */
                    break;
                default:
                    break;
            }
            break;
        }
        case GC_OBJ_ARR: {
            arr* a = (arr*)obj_ptr;
            for (size_t i = 0; i < a->size; i++) {
                a->data[i] = copy_object(a->data[i]);
            }
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
        default:
            break;
    }
}

/* Основная функция сборки молодого поколения */
static void collect_young(void) {
    young_collections++;
    
    /* Меняем местами полупространства */
    char* tmp = young_from;
    young_from = young_to;
    young_to = tmp;
    young_top = young_from;
    young_limit = young_from + YOUNG_SIZE;
    
    /* Начальный набор объектов для сканирования (корни) */
    void** scan_ptr = (void**)young_from;  /* указатель на ещё не отсканированные объекты в to‑space */
    
    /* Копируем все корни (локальные и глобальные) */
    for (size_t i = 0; i < roots_count; i++) {
        void** root = roots[i];
        if (*root) {
            *root = copy_object(*root);
        }
    }
    for (size_t i = 0; i < global_roots_count; i++) {
        void** root = global_roots[i];
        if (*root) {
            *root = copy_object(*root);
        }
    }
    
    /* Копируем объекты, на которые ссылаются dirty‑объекты старого поколения */
    for (size_t i = 0; i < dirty_count; i++) {
        gc_header_t* dirty_hdr = dirty_set[i];
        void* obj = header_to_ptr(dirty_hdr);
        scan_object_fields(obj);  /* это обновит ссылки внутри dirty‑объекта */
    }
    
    /* Основной цикл Чейни: пока есть неотсканированные объекты */
    while ((char*)scan_ptr < young_top) {
        gc_header_t* hdr = (gc_header_t*)scan_ptr;
        void* obj = header_to_ptr(hdr);
        scan_object_fields(obj);
        scan_ptr = (void**)((char*)scan_ptr + ALIGN_UP(hdr->size, GC_ALIGNMENT));
    }
    
    /* Очистка dirty‑set */
    for (size_t i = 0; i < dirty_count; i++) {
        dirty_set[i]->flags &= ~GC_FLAG_DIRTY;
    }
    dirty_count = 0;
}

/* ============================================================================
 * Сборка старого поколения (mark‑sweep)
 * ============================================================================ */

/* Рекурсивная маркировка объекта */
static void mark_object(void* obj_ptr) {
    if (!obj_ptr) return;
    gc_header_t* hdr = ptr_to_header(obj_ptr);
    if (hdr->flags & GC_FLAG_MARKED) return;
    hdr->flags |= GC_FLAG_MARKED;
    
    /* Маркируем дочерние объекты в зависимости от типа */
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

/* Фаза sweep: построение free‑list из непомеченных объектов */
static void sweep_old(void) {
    old_free_list = NULL;
    char* scan = old_start;
    
    while (scan < old_top) {
        gc_header_t* hdr = (gc_header_t*)scan;
        size_t size = ALIGN_UP(hdr->size, GC_ALIGNMENT);
        
        if (hdr->flags & GC_FLAG_MARKED) {
            /* Живой объект – сбрасываем флаг для следующей сборки */
            hdr->flags &= ~GC_FLAG_MARKED;
        } else {
            /* Мёртвый объект – добавляем в free‑list */
            hdr->u.next_free = old_free_list;
            old_free_list = hdr;
        }
        scan += size;
    }
    
    /* Слияние соседних свободных блоков (coalescing) */
    if (old_free_list) {
        gc_header_t* curr = old_free_list;
        while (curr && curr->u.next_free) {
            gc_header_t* next = curr->u.next_free;
            if ((char*)curr + ALIGN_UP(curr->size, GC_ALIGNMENT) == (char*)next) {
                curr->size += ALIGN_UP(next->size, GC_ALIGNMENT);
                curr->u.next_free = next->u.next_free;
                /* остаёмся на том же curr, так как next был поглощён */
            } else {
                curr = curr->u.next_free;
            }
        }
    }
}

/* Основная функция сборки старого поколения */
static void collect_old(void) {
    old_collections++;
    
    /* 1. Сброс флагов marked у всех объектов старого поколения */
    for (char* scan = old_start; scan < old_top; ) {
        gc_header_t* hdr = (gc_header_t*)scan;
        hdr->flags &= ~GC_FLAG_MARKED;
        scan += ALIGN_UP(hdr->size, GC_ALIGNMENT);
    }
    for (gc_header_t* curr = large_objects; curr; curr = curr->u.next_free) {
        curr->flags &= ~GC_FLAG_MARKED;
    }
    
    /* 2. Маркировка из корней */
    for (size_t i = 0; i < roots_count; i++) {
        if (*roots[i]) mark_object(*roots[i]);
    }
    for (size_t i = 0; i < global_roots_count; i++) {
        if (*global_roots[i]) mark_object(*global_roots[i]);
    }
    
    /* 3. Маркировка из молодого поколения (объекты в молодом поколении могут ссылаться на старое) */
    for (char* scan = young_from; scan < young_top; ) {
        gc_header_t* hdr = (gc_header_t*)scan;
        void* obj = header_to_ptr(hdr);
        /* Проверяем, содержит ли объект указатели */
        if (hdr->obj_type == GC_OBJ_VALUE) {
            ely_value* v = (ely_value*)obj;
            if (v->type == ely_VALUE_ARRAY) mark_object(v->u.array_val);
            else if (v->type == ely_VALUE_OBJECT) mark_object(v->u.object_val);
        } else if (hdr->obj_type == GC_OBJ_ARR) {
            arr* a = (arr*)obj;
            for (size_t i = 0; i < a->size; i++) mark_object(a->data[i]);
        } else if (hdr->obj_type == GC_OBJ_DICT) {
            dict* d = (dict*)obj;
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
    
    /* 4. Sweep */
    sweep_old();
    
    /* 5. Обработка крупных объектов */
    gc_header_t** prev = &large_objects;
    gc_header_t* curr = large_objects;
    while (curr) {
        if (curr->flags & GC_FLAG_MARKED) {
            curr->flags &= ~GC_FLAG_MARKED;
            prev = &curr->u.next_free;
            curr = curr->u.next_free;
        } else {
            /* Удаляем крупный объект */
            gc_header_t* to_free = curr;
            *prev = curr->u.next_free;
            curr = curr->u.next_free;
            os_free(to_free, to_free->size);
        }
    }
}

/* ============================================================================
 * Публичные функции сборки
 * ============================================================================ */

void gc_collect_young(void) {
    if (!gc_enabled) return;
    collect_young();
}

void gc_collect_old(void) {
    if (!gc_enabled) return;
    collect_old();
}

void gc_collect(void) {
    if (!gc_enabled) return;
    collect_young();
    collect_old();
}

/* ============================================================================
 * Управление корнями (уже были в предыдущем фрагменте, но для полноты)
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

/* ============================================================================
 * Удаление глобального корня
 * ============================================================================ */

void gc_remove_global_root(void** ptr) {
    if (!gc_enabled) return;
    for (size_t i = 0; i < global_roots_count; i++) {
        if (global_roots[i] == ptr) {
            /* Сдвигаем оставшиеся элементы */
            global_roots[i] = global_roots[--global_roots_count];
            return;
        }
    }
    /* Если корень не найден, ничего не делаем (безопасное игнорирование) */
}

/* ============================================================================
 * Барьеры записи
 * ============================================================================ */

void gc_write_barrier(void* parent, void** field, void* new_value) {
    if (!gc_enabled) {
        *field = new_value;
        return;
    }
    
    /* Сначала выполняем присваивание */
    *field = new_value;
    
    /* Если parent == NULL, это может быть присваивание в глобальную переменную,
       но для глобальных есть отдельный барьер. */
    if (!parent) return;
    
    gc_header_t* parent_hdr = ptr_to_header(parent);
    
    /* Проверяем, находится ли родитель в старом поколении */
    if (parent_hdr->flags & GC_FLAG_IN_OLD) {
        /* Если новое значение указывает на молодой объект, помечаем родителя как dirty */
        if (new_value) {
            gc_header_t* child_hdr = ptr_to_header(new_value);
            if (!(child_hdr->flags & GC_FLAG_IN_OLD) && !(child_hdr->flags & GC_FLAG_LARGE)) {
                add_dirty(parent_hdr);
            }
        }
    }
    
    /* TODO: Поддержка concurrent marking (будет добавлена на следующих этапах).
       При активной фазе concurrent mark нужно также поместить new_value в очередь маркировки,
       если оно ещё не помечено. */
}

void gc_write_barrier_global(void** field, void* new_value) {
    if (!gc_enabled) {
        *field = new_value;
        return;
    }
    
    *field = new_value;
    
    /* Глобальные переменные всегда считаются корнями, поэтому дополнительных действий
       для поколенческого сборщика не требуется. Однако для concurrent marking
       может потребоваться отметка new_value. Пока оставляем заглушку. */
}

/* ============================================================================
 * Статистика и информационные функции
 * ============================================================================ */

void gc_dump_stats(void) {
    /* Вычисляем использование молодого поколения */
    size_t young_used = (size_t)(young_top - young_from);
    size_t young_total = YOUNG_SIZE;
    
    /* Вычисляем использование старого поколения */
    size_t old_used = (size_t)(old_top - old_start);
    size_t old_total = old_size;
    
    /* Подсчитываем суммарный размер свободных блоков в free‑list */
    size_t free_in_old = 0;
    size_t free_blocks = 0;
    for (gc_header_t* b = old_free_list; b; b = b->u.next_free) {
        free_in_old += b->size;
        free_blocks++;
    }
    
    /* Крупные объекты */
    size_t large_count = 0;
    size_t large_total = 0;
    for (gc_header_t* b = large_objects; b; b = b->u.next_free) {
        large_count++;
        large_total += b->size;
    }
    
    printf("========== GC Statistics ==========\n");
    printf("Young collections: %llu\n", (unsigned long long)young_collections);
    printf("Old collections:   %llu\n", (unsigned long long)old_collections);
    printf("Young generation:  %zu / %zu bytes used (%.1f%%)\n",
           young_used, young_total, 100.0 * young_used / young_total);
    printf("Old generation:    %zu / %zu bytes allocated, %zu free in %zu blocks\n",
           old_used, old_total, free_in_old, free_blocks);
    printf("Large objects:     %zu objects, %zu bytes total\n", large_count, large_total);
    printf("Roots:             %zu local, %zu global\n", roots_count, global_roots_count);
    printf("Dirty set:         %zu objects\n", dirty_count);
    printf("GC enabled:        %s\n", gc_enabled ? "yes" : "no");
    printf("===================================\n");
}

size_t gc_get_heap_size(void) {
    size_t total = 2 * YOUNG_SIZE + old_size;
    for (gc_header_t* b = large_objects; b; b = b->u.next_free) {
        total += b->size;
    }
    return total;
}

/* ============================================================================
 * Дополнительные функции (могут быть запрошены следующими)
 * ============================================================================ */

size_t gc_get_free_bytes(void) {
    size_t free_young = (size_t)(young_limit - young_top);
    size_t free_old = 0;
    for (gc_header_t* b = old_free_list; b; b = b->u.next_free) {
        free_old += b->size;
    }
    free_old += (size_t)(old_limit - old_top);
    return free_young + free_old;
}

size_t gc_get_used_bytes(void) {
    return gc_get_heap_size() - gc_get_free_bytes();
}

uint64_t gc_get_young_collections(void) {
    return young_collections;
}

uint64_t gc_get_old_collections(void) {
    return old_collections;
}

/* ============================================================================
 * Управление режимом работы
 * ============================================================================ */

void gc_set_enabled(bool enabled) {
    gc_enabled = enabled;
}

bool gc_is_enabled(void) {
    return gc_enabled;
}

void gc_set_old_threshold(int percent) {
    if (percent < 0) percent = 0;
    if (percent > 100) percent = 100;
    old_threshold_percent = percent;
}

/* ============================================================================
 * Компактизация старого поколения (mark‑compact)
 * ============================================================================ */

/* Вычисляет новые адреса для живых объектов и строит таблицу перемещений */
static void compact_old(void) {
    /* Шаг 1: вычислить смещения для каждого живого объекта */
    char* scan = old_start;
    char* dest = old_start;
    
    /* Временный массив для хранения пар (старый_адрес -> новый_адрес).
       Для простоты используем два прохода: первый – подсчёт смещений,
       второй – фактическое копирование и обновление ссылок. */
    
    /* Первый проход: вычисляем новые позиции */
    while (scan < old_top) {
        gc_header_t* hdr = (gc_header_t*)scan;
        size_t size = ALIGN_UP(hdr->size, GC_ALIGNMENT);
        
        if (hdr->flags & GC_FLAG_MARKED) {
            /* Живой объект – он будет перемещён в dest */
            hdr->u.forwarding = (gc_header_t*)dest;  /* временно храним новый адрес */
            dest += size;
        }
        scan += size;
    }
    
    /* Второй проход: копируем объекты и обновляем все указатели */
    scan = old_start;
    while (scan < old_top) {
        gc_header_t* hdr = (gc_header_t*)scan;
        size_t size = ALIGN_UP(hdr->size, GC_ALIGNMENT);
        
        if (hdr->flags & GC_FLAG_MARKED) {
            gc_header_t* new_hdr = hdr->u.forwarding;
            if ((char*)new_hdr != scan) {
                /* Перемещаем объект */
                memmove(new_hdr, hdr, hdr->size);
            }
            new_hdr->u.forwarding = NULL;  /* очищаем временное поле */
        }
        scan += size;
    }
    
    /* Третий проход: обновляем все указатели внутри объектов и в корнях */
    scan = old_start;
    dest = old_start;  /* теперь dest указывает на конец уплотнённых данных */
    while (scan < old_top) {
        gc_header_t* hdr = (gc_header_t*)scan;
        size_t size = ALIGN_UP(hdr->size, GC_ALIGNMENT);
        
        if (hdr->flags & GC_FLAG_MARKED) {
            void* obj = header_to_ptr(hdr);
            /* Обновляем внутренние ссылки */
            update_references(obj, (char*)hdr - scan);
            scan += size;
            dest = (char*)hdr + size;
        } else {
            scan += size;
        }
    }
    
    /* Обновляем корни */
    for (size_t i = 0; i < roots_count; i++) {
        void** root = roots[i];
        if (*root && is_in_old_generation(*root)) {
            gc_header_t* hdr = ptr_to_header(*root);
            if (hdr->flags & GC_FLAG_MARKED) {
                *root = header_to_ptr(hdr);
            }
        }
    }
    for (size_t i = 0; i < global_roots_count; i++) {
        void** root = global_roots[i];
        if (*root && is_in_old_generation(*root)) {
            gc_header_t* hdr = ptr_to_header(*root);
            if (hdr->flags & GC_FLAG_MARKED) {
                *root = header_to_ptr(hdr);
            }
        }
    }
    
    /* Обновляем dirty‑set */
    for (size_t i = 0; i < dirty_count; i++) {
        gc_header_t* hdr = dirty_set[i];
        if (hdr->flags & GC_FLAG_MARKED) {
            dirty_set[i] = hdr;  /* адрес мог измениться */
        }
    }
    
    /* Устанавливаем новую вершину кучи и сбрасываем free‑list */
    old_top = dest;
    old_free_list = NULL;
    
    /* Сбрасываем флаг MARKED у всех живых объектов */
    scan = old_start;
    while (scan < old_top) {
        gc_header_t* hdr = (gc_header_t*)scan;
        hdr->flags &= ~GC_FLAG_MARKED;
        scan += ALIGN_UP(hdr->size, GC_ALIGNMENT);
    }
}

/* Вспомогательная функция для обновления ссылок внутри объекта */
static void update_references(void* obj, ptrdiff_t delta) {
    if (delta == 0) return;
    gc_header_t* hdr = ptr_to_header(obj);
    switch (hdr->obj_type) {
        case GC_OBJ_VALUE: {
            ely_value* v = (ely_value*)obj;
            if (v->type == ely_VALUE_ARRAY && v->u.array_val) {
                v->u.array_val = (arr*)((char*)v->u.array_val + delta);
            } else if (v->type == ely_VALUE_OBJECT && v->u.object_val) {
                v->u.object_val = (dict*)((char*)v->u.object_val + delta);
            }
            break;
        }
        case GC_OBJ_ARR: {
            arr* a = (arr*)obj;
            for (size_t i = 0; i < a->size; i++) {
                if (a->data[i]) {
                    a->data[i] = (ely_value*)((char*)a->data[i] + delta);
                }
            }
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

/* Проверяет, находится ли объект в старом поколении */
static bool is_in_old_generation(void* ptr) {
    if (!ptr) return false;
    char* addr = (char*)ptr;
    return (addr >= old_start && addr < old_limit);
}

/* ============================================================================
 * Расширение старого поколения
 * ============================================================================ */

static bool expand_old_heap(size_t additional_bytes) {
    if (OLD_MAX_SIZE > 0 && old_size + additional_bytes > OLD_MAX_SIZE) {
        return false;
    }
    
    size_t new_size = old_size + additional_bytes;
    char* new_start = os_resize(old_start, old_size, new_size);
    if (!new_start) return false;
    
    /* Корректируем указатели, если куча переместилась */
    ptrdiff_t delta = new_start - old_start;
    if (delta != 0) {
        /* Обновляем все внутренние указатели, связанные со старым поколением */
        old_start = new_start;
        old_top += delta;
        old_limit = old_start + new_size;
        
        /* Обновляем корни, dirty‑set, free‑list */
        for (size_t i = 0; i < roots_count; i++) {
            void** root = roots[i];
            if (*root && is_in_old_generation((char*)*root - delta)) {
                *root = (char*)*root + delta;
            }
        }
        for (size_t i = 0; i < global_roots_count; i++) {
            void** root = global_roots[i];
            if (*root && is_in_old_generation((char*)*root - delta)) {
                *root = (char*)*root + delta;
            }
        }
        for (size_t i = 0; i < dirty_count; i++) {
            gc_header_t* hdr = dirty_set[i];
            if ((char*)hdr >= old_start - delta && (char*)hdr < old_limit - delta) {
                dirty_set[i] = (gc_header_t*)((char*)hdr + delta);
            }
        }
        /* free‑list тоже нужно обновить, но проще сбросить и заново построить при следующей sweep */
        old_free_list = NULL;
    } else {
        old_limit = old_start + new_size;
    }
    
    old_size = new_size;
    return true;
}

/* ============================================================================
 * Публичные функции для управления кучей и отладки
 * ============================================================================ */

void gc_compact(void) {
    if (!gc_enabled) return;
    /* Принудительная компактизация старого поколения */
    collect_old();  /* включает mark и sweep, после чего можно вызвать compact_old */
    compact_old();
}

bool gc_expand_heap(size_t additional_bytes) {
    if (!gc_enabled) return false;
    return expand_old_heap(additional_bytes);
}

void gc_collect_full(void) {
    if (!gc_enabled) return;
    collect_young();
    collect_old();
    compact_old();
}

/* ============================================================================
 * Получение статистики в структуру
 * ============================================================================ */

typedef struct gc_stats {
    uint64_t young_collections;
    uint64_t old_collections;
    size_t young_used;
    size_t young_total;
    size_t old_used;
    size_t old_total;
    size_t free_blocks;
    size_t free_bytes;
    size_t large_objects_count;
    size_t large_objects_bytes;
    size_t roots_local;
    size_t roots_global;
    size_t dirty_count;
    bool enabled;
} gc_stats_t;

void gc_get_stats(gc_stats_t* stats) {
    if (!stats) return;
    stats->young_collections = young_collections;
    stats->old_collections = old_collections;
    stats->young_used = (size_t)(young_top - young_from);
    stats->young_total = YOUNG_SIZE;
    stats->old_used = (size_t)(old_top - old_start);
    stats->old_total = old_size;
    
    stats->free_blocks = 0;
    stats->free_bytes = 0;
    for (gc_header_t* b = old_free_list; b; b = b->u.next_free) {
        stats->free_blocks++;
        stats->free_bytes += b->size;
    }
    
    stats->large_objects_count = 0;
    stats->large_objects_bytes = 0;
    for (gc_header_t* b = large_objects; b; b = b->u.next_free) {
        stats->large_objects_count++;
        stats->large_objects_bytes += b->size;
    }
    
    stats->roots_local = roots_count;
    stats->roots_global = global_roots_count;
    stats->dirty_count = dirty_count;
    stats->enabled = gc_enabled;
}

static char* gc_strdup(const char* s) {
    if (!s) return NULL;
    size_t len = strlen(s) + 1;
    char* copy = (char*)gc_alloc(len, GC_OBJ_STRING);
    if (copy) memcpy(copy, s, len);
    return copy;
}

/* ============================================================================
 * Проверка целостности кучи (для отладки)
 * ============================================================================ */

#ifdef GC_DEBUG
void gc_verify_heap(void) {
    /* Проверка молодого поколения */
    for (char* scan = young_from; scan < young_top; ) {
        gc_header_t* hdr = (gc_header_t*)scan;
        assert(hdr->size >= HEADER_SIZE);
        assert(hdr->size <= YOUNG_SIZE);
        scan += ALIGN_UP(hdr->size, GC_ALIGNMENT);
    }
    
    /* Проверка старого поколения */
    char* scan = old_start;
    while (scan < old_top) {
        gc_header_t* hdr = (gc_header_t*)scan;
        assert(hdr->size >= HEADER_SIZE);
        size_t size = ALIGN_UP(hdr->size, GC_ALIGNMENT);
        assert(scan + size <= old_top);
        scan += size;
    }
    
    /* Проверка free‑list */
    for (gc_header_t* b = old_free_list; b; b = b->u.next_free) {
        assert((char*)b >= old_start && (char*)b < old_top);
        assert((b->flags & GC_FLAG_IN_OLD) == 0);
    }
    
    /* Проверка large objects */
    for (gc_header_t* b = large_objects; b; b = b->u.next_free) {
        assert(b->flags & GC_FLAG_LARGE);
    }
    
    printf("Heap verification passed.\n");
}
#else
void gc_verify_heap(void) { /* nothing */ }
#endif