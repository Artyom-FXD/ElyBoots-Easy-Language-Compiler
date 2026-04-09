// ============================================================
// ely_gc.c — Generational Garbage Collector
// ============================================================

#include "ely_gc.h"
#include "ely_runtime.h"
#include "collections.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <assert.h>

// ------------------- Глобальные структуры данных -------------------

static char* young_from = NULL;
static char* young_to   = NULL;
static char* young_top  = NULL;
static char* young_limit = NULL;

static char* old_start = NULL;
static char* old_top   = NULL;
static char* old_limit = NULL;

static gc_header_t* all_objects = NULL;
static gc_header_t* old_objects = NULL;

static int gc_initialized = 0;

static void*** roots = NULL;
static int roots_count = 0;
static int roots_capacity = 0;

static void*** global_roots = NULL;
static int global_roots_count = 0;
static int global_roots_capacity = 0;

static gc_header_t** dirty_objects = NULL;
static int dirty_count = 0;
static int dirty_capacity = 0;

static int young_collections = 0;
static int old_collections = 0;
static int gc_enabled = 1;

// ------------------- Прототипы статических функций -------------------
static gc_header_t* ptr_to_header(void* ptr);
static void* header_to_ptr(gc_header_t* hdr);
static size_t align_size(size_t size);
static void ensure_roots_capacity(void);
static void ensure_global_roots_capacity(void);
static void ensure_dirty_capacity(void);
static void* alloc_young(size_t size);
static void* alloc_old(size_t size);
static void gc_add_dirty_object(void* obj);
static void* promote_to_old(void* obj);
static void* copy_to_young(void* obj);
static void copy_and_update(void** ptr);
static void visit_value_fields(ely_value* v);
static void visit_arr_fields(arr* a);
static void visit_dict_fields(dict* d);
static void collect_young(void);
static void mark_object(void* obj);
static void mark_value_fields(ely_value* v);
static void mark_arr_fields(arr* a);
static void mark_dict_fields(dict* d);
static void mark_roots_for_old(void);
static void compact_old(void);
static void collect_old(void);

// ------------------- Вспомогательные функции -------------------
static gc_header_t* ptr_to_header(void* ptr) {
    if (!ptr) return NULL;
    return (gc_header_t*)((char*)ptr - sizeof(gc_header_t));
}

static void* header_to_ptr(gc_header_t* hdr) {
    if (!hdr) return NULL;
    return (char*)hdr + sizeof(gc_header_t);
}

static size_t align_size(size_t size) {
    return (size + 7) & ~7;
}

static void ensure_roots_capacity(void) {
    if (roots_count >= roots_capacity) {
        roots_capacity = roots_capacity ? roots_capacity * 2 : 64;
        roots = realloc(roots, roots_capacity * sizeof(void**));
        assert(roots);
    }
}

static void ensure_global_roots_capacity(void) {
    if (global_roots_count >= global_roots_capacity) {
        global_roots_capacity = global_roots_capacity ? global_roots_capacity * 2 : 64;
        global_roots = realloc(global_roots, global_roots_capacity * sizeof(void**));
        assert(global_roots);
    }
}

static void ensure_dirty_capacity(void) {
    if (dirty_count >= dirty_capacity) {
        dirty_capacity = dirty_capacity ? dirty_capacity * 2 : 64;
        dirty_objects = realloc(dirty_objects, dirty_capacity * sizeof(gc_header_t*));
        assert(dirty_objects);
    }
}

// ------------------- Выделение памяти в поколениях (начальные версии) -------------------
static void* alloc_young(size_t size) {
    size_t aligned = align_size(size);
    if (young_top + aligned <= young_limit) {
        void* ptr = young_top;
        young_top += aligned;
        return ptr;
    }
    fprintf(stderr, "GC: out of memory in young generation\n");
    exit(1);
}

static void* alloc_old(size_t size) {
    size_t aligned = align_size(size);
    if (old_top + aligned <= old_limit) {
        void* ptr = old_top;
        old_top += aligned;
        return ptr;
    }
    collect_old();
    if (old_top + aligned <= old_limit) {
        void* ptr = old_top;
        old_top += aligned;
        return ptr;
    }
    fprintf(stderr, "GC: out of memory in old generation after collection\n");
    exit(1);
}

// ------------------- Добавление dirty объекта -------------------
static void gc_add_dirty_object(void* obj) {
    if (!obj) return;
    gc_header_t* hdr = ptr_to_header(obj);
    if (!hdr) return;
    if (!(hdr->flags & 0x08)) {
        hdr->flags |= 0x08;
        ensure_dirty_capacity();
        dirty_objects[dirty_count++] = hdr;
    }
}

// ------------------- Продвижение в старое поколение -------------------
static void* promote_to_old(void* obj) {
    gc_header_t* hdr = ptr_to_header(obj);
    if (!hdr || (hdr->flags & 0x02)) return obj;

    size_t aligned = align_size(hdr->size);
    if (old_top + aligned > old_limit) {
        collect_old();
        if (old_top + aligned > old_limit) {
            fprintf(stderr, "GC: out of memory in old generation during promotion\n");
            exit(1);
        }
    }
    void* new_obj = old_top;
    memcpy(new_obj, obj, hdr->size);
    old_top += aligned;

    gc_header_t* new_hdr = ptr_to_header(new_obj);
    new_hdr->flags = (hdr->flags & ~0x01) | 0x02;
    new_hdr->age = 0;
    new_hdr->forwarding = NULL;
    new_hdr->next = old_objects;
    old_objects = new_hdr;

    hdr->flags |= 0x04;
    hdr->forwarding = new_hdr;

    return new_obj;
}

// ------------------- Копирование в молодое поколение -------------------
static void* copy_to_young(void* obj) {
    gc_header_t* hdr = ptr_to_header(obj);
    if (!hdr) return obj;
    if (hdr->flags & 0x04) return header_to_ptr(hdr->forwarding);

    size_t aligned = align_size(hdr->size);
    if (young_top + aligned > young_limit) {
        fprintf(stderr, "GC: out of space in young generation during copying\n");
        exit(1);
    }
    void* new_obj = young_top;
    memcpy(new_obj, obj, hdr->size);
    young_top += aligned;

    gc_header_t* new_hdr = ptr_to_header(new_obj);
    new_hdr->flags = (hdr->flags & ~0x04) & ~0x02;
    new_hdr->age = hdr->age + 1;
    new_hdr->forwarding = NULL;

    hdr->flags |= 0x04;
    hdr->forwarding = new_hdr;

    return new_obj;
}

// ------------------- Обход полей объектов -------------------
static void copy_and_update(void** ptr) {
    if (!ptr || !*ptr) return;
    void* obj = *ptr;
    gc_header_t* hdr = ptr_to_header(obj);
    if (!hdr) return;

    if (hdr->flags & 0x04) {
        *ptr = header_to_ptr(hdr->forwarding);
        return;
    }

    int promote = 0;
    if (!(hdr->flags & 0x02)) {
        if (hdr->age >= PROMOTION_AGE) promote = 1;
    } else {
        return;
    }

    void* new_obj = promote ? promote_to_old(obj) : copy_to_young(obj);
    *ptr = new_obj;

    gc_header_t* new_hdr = ptr_to_header(new_obj);
    switch (new_hdr->obj_type) {
        case GC_OBJ_VALUE:
            visit_value_fields((ely_value*)new_obj);
            break;
        case GC_OBJ_ARR:
            visit_arr_fields((arr*)new_obj);
            break;
        case GC_OBJ_DICT:
            visit_dict_fields((dict*)new_obj);
            break;
        default: break;
    }
}

static void visit_value_fields(ely_value* v) {
    if (!v) return;
    switch (v->type) {
        case ely_VALUE_ARRAY: copy_and_update((void**)&v->u.array_val); break;
        case ely_VALUE_OBJECT: copy_and_update((void**)&v->u.object_val); break;
        case ely_VALUE_STRING: copy_and_update((void**)&v->u.string_val); break;
        default: break;
    }
}

static void visit_arr_fields(arr* a) {
    if (!a) return;
    for (size_t i = 0; i < a->size; i++)
        copy_and_update((void**)&a->data[i]);
}

static void visit_dict_fields(dict* d) {
    if (!d) return;
    for (size_t i = 0; i < d->capacity; i++) {
        dict_entry* e = d->buckets[i];
        while (e) {
            copy_and_update((void**)&e->key);
            copy_and_update((void**)&e->value);
            e = e->next;
        }
    }
}

// ------------------- Сборка молодого поколения -------------------
static void collect_young(void) {
    young_collections++;

    char* tmp = young_from;
    young_from = young_to;
    young_to = tmp;
    young_top = young_from;
    young_limit = young_from + YOUNG_SIZE;

    for (int i = 0; i < roots_count; i++)
        copy_and_update(roots[i]);
    for (int i = 0; i < global_roots_count; i++)
        copy_and_update(global_roots[i]);

    for (int i = 0; i < dirty_count; i++) {
        gc_header_t* dirty_hdr = dirty_objects[i];
        if (dirty_hdr->flags & 0x02) {
            void* obj = header_to_ptr(dirty_hdr);
            switch (dirty_hdr->obj_type) {
                case GC_OBJ_VALUE: visit_value_fields((ely_value*)obj); break;
                case GC_OBJ_ARR: visit_arr_fields((arr*)obj); break;
                case GC_OBJ_DICT: visit_dict_fields((dict*)obj); break;
                default: break;
            }
        }
        dirty_hdr->flags &= ~0x08;
    }
    dirty_count = 0;
}

// ------------------- Маркировка для старого поколения -------------------
static void mark_object(void* obj) {
    if (!obj) return;
    gc_header_t* hdr = ptr_to_header(obj);
    if (!hdr) return;
    if (hdr->flags & 0x01) return;
    hdr->flags |= 0x01;

    switch (hdr->obj_type) {
        case GC_OBJ_VALUE: mark_value_fields((ely_value*)obj); break;
        case GC_OBJ_ARR: mark_arr_fields((arr*)obj); break;
        case GC_OBJ_DICT: mark_dict_fields((dict*)obj); break;
        default: break;
    }
}

static void mark_value_fields(ely_value* v) {
    if (!v) return;
    switch (v->type) {
        case ely_VALUE_ARRAY: mark_object(v->u.array_val); break;
        case ely_VALUE_OBJECT: mark_object(v->u.object_val); break;
        default: break;
    }
}

static void mark_arr_fields(arr* a) {
    if (!a) return;
    for (size_t i = 0; i < a->size; i++)
        mark_object(a->data[i]);
}

static void mark_dict_fields(dict* d) {
    if (!d) return;
    for (size_t i = 0; i < d->capacity; i++) {
        dict_entry* e = d->buckets[i];
        while (e) {
            mark_object(e->key);
            mark_object(e->value);
            e = e->next;
        }
    }
}

static void mark_roots_for_old(void) {
    for (int i = 0; i < roots_count; i++)
        mark_object(*roots[i]);
    for (int i = 0; i < global_roots_count; i++)
        mark_object(*global_roots[i]);

    char* ptr = young_from;
    while (ptr < young_top) {
        gc_header_t* hdr = (gc_header_t*)ptr;
        if (!(hdr->flags & 0x02)) {
            void* obj = header_to_ptr(hdr);
            switch (hdr->obj_type) {
                case GC_OBJ_VALUE: {
                    ely_value* v = (ely_value*)obj;
                    if (v->type == ely_VALUE_ARRAY) mark_object(v->u.array_val);
                    else if (v->type == ely_VALUE_OBJECT) mark_object(v->u.object_val);
                    break;
                }
                case GC_OBJ_ARR: {
                    arr* a = (arr*)obj;
                    for (size_t i = 0; i < a->size; i++) mark_object(a->data[i]);
                    break;
                }
                case GC_OBJ_DICT: {
                    dict* d = (dict*)obj;
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
        ptr += align_size(hdr->size);
    }
}

// ------------------- Уплотнение старого поколения -------------------
static void compact_old(void) {
    char* scan = old_start;
    char* destination = old_start;
    while (scan < old_top) {
        gc_header_t* hdr = (gc_header_t*)scan;
        if (hdr->flags & 0x01) {
            hdr->forwarding = (gc_header_t*)destination;
            destination += align_size(hdr->size);
        }
        scan += align_size(hdr->size);
    }

    scan = old_start;
    while (scan < old_top) {
        gc_header_t* hdr = (gc_header_t*)scan;
        if (hdr->flags & 0x01) {
            gc_header_t* new_hdr = hdr->forwarding;
            if ((char*)new_hdr != scan)
                memmove(new_hdr, hdr, hdr->size);
            void* obj = header_to_ptr(new_hdr);
            switch (new_hdr->obj_type) {
                case GC_OBJ_VALUE: {
                    ely_value* v = (ely_value*)obj;
                    if (v->type == ely_VALUE_ARRAY) {
                        gc_header_t* arr_hdr = ptr_to_header(v->u.array_val);
                        if (arr_hdr && (arr_hdr->flags & 0x01))
                            v->u.array_val = header_to_ptr(arr_hdr->forwarding);
                    } else if (v->type == ely_VALUE_OBJECT) {
                        gc_header_t* dict_hdr = ptr_to_header(v->u.object_val);
                        if (dict_hdr && (dict_hdr->flags & 0x01))
                            v->u.object_val = header_to_ptr(dict_hdr->forwarding);
                    }
                    break;
                }
                case GC_OBJ_ARR: {
                    arr* a = (arr*)obj;
                    for (size_t i = 0; i < a->size; i++) {
                        gc_header_t* elem_hdr = ptr_to_header(a->data[i]);
                        if (elem_hdr && (elem_hdr->flags & 0x01))
                            a->data[i] = header_to_ptr(elem_hdr->forwarding);
                    }
                    break;
                }
                case GC_OBJ_DICT: {
                    dict* d = (dict*)obj;
                    for (size_t i = 0; i < d->capacity; i++) {
                        dict_entry* e = d->buckets[i];
                        while (e) {
                            gc_header_t* key_hdr = ptr_to_header(e->key);
                            if (key_hdr && (key_hdr->flags & 0x01))
                                e->key = header_to_ptr(key_hdr->forwarding);
                            gc_header_t* val_hdr = ptr_to_header(e->value);
                            if (val_hdr && (val_hdr->flags & 0x01))
                                e->value = header_to_ptr(val_hdr->forwarding);
                            e = e->next;
                        }
                    }
                    break;
                }
                default: break;
            }
        }
        scan += align_size(hdr->size);
    }

    for (int i = 0; i < roots_count; i++) {
        void* obj = *roots[i];
        gc_header_t* hdr = ptr_to_header(obj);
        if (hdr && (hdr->flags & 0x01))
            *roots[i] = header_to_ptr(hdr->forwarding);
    }
    for (int i = 0; i < global_roots_count; i++) {
        void* obj = *global_roots[i];
        gc_header_t* hdr = ptr_to_header(obj);
        if (hdr && (hdr->flags & 0x01))
            *global_roots[i] = header_to_ptr(hdr->forwarding);
    }

    for (int i = 0; i < dirty_count; i++) {
        gc_header_t* dirty_hdr = dirty_objects[i];
        if (dirty_hdr->flags & 0x01)
            dirty_objects[i] = dirty_hdr->forwarding;
    }

    gc_header_t* new_old_objects = NULL;
    scan = old_start;
    while (scan < old_top) {
        gc_header_t* hdr = (gc_header_t*)scan;
        if (hdr->flags & 0x01) {
            gc_header_t* new_hdr = hdr->forwarding;
            new_hdr->next = new_old_objects;
            new_old_objects = new_hdr;
            new_hdr->flags &= ~0x01;
            new_hdr->forwarding = NULL;
        }
        scan += align_size(hdr->size);
    }
    old_objects = new_old_objects;
    old_top = destination;
}

// ------------------- Сборка старого поколения -------------------
static void collect_old(void) {
    old_collections++;
    collect_young();
    mark_roots_for_old();
    compact_old();
    dirty_count = 0;
}

// ------------------- Инициализация GC -------------------
void gc_init(void) {
    young_from = (char*)malloc(YOUNG_SIZE * 2);
    assert(young_from);
    young_to = young_from + YOUNG_SIZE;
    young_top = young_from;
    young_limit = young_from + YOUNG_SIZE;

    old_start = (char*)malloc(OLD_SIZE);
    assert(old_start);
    old_top = old_start;
    old_limit = old_start + OLD_SIZE;

    roots_capacity = 64;
    roots = malloc(roots_capacity * sizeof(void**));
    assert(roots);
    roots_count = 0;

    global_roots_capacity = 64;
    global_roots = malloc(global_roots_capacity * sizeof(void**));
    assert(global_roots);
    global_roots_count = 0;

    dirty_capacity = 64;
    dirty_objects = malloc(dirty_capacity * sizeof(gc_header_t*));
    assert(dirty_objects);
    dirty_count = 0;

    all_objects = NULL;
    old_objects = NULL;
}

// ------------------- Публичная функция сборки -------------------
void gc_collect(void) {
    if (!gc_enabled) return;
    collect_young();
    if (young_collections % 5 == 0)
        collect_old();
}

// ------------------- Публичные функции -------------------
void* gc_alloc(size_t size, gc_obj_type_t type) {
    if (!gc_enabled) {
        void* ptr = malloc(size);
        assert(ptr);
        return ptr;
    }

    size_t total_size = sizeof(gc_header_t) + size;
    void* raw = alloc_young(total_size);
    gc_header_t* hdr = (gc_header_t*)raw;
    hdr->size = total_size;
    hdr->age = 0;
    hdr->flags = 0;
    hdr->obj_type = type;
    hdr->forwarding = NULL;
    hdr->next = all_objects;
    all_objects = hdr;
    void* user_ptr = header_to_ptr(hdr);
    memset(user_ptr, 0, size);
    return user_ptr;
}

void gc_add_root(void** root_ptr) {
    if (!gc_enabled) return;
    ensure_roots_capacity();
    roots[roots_count++] = root_ptr;
}

void gc_remove_root(void** root_ptr) {
    if (!gc_enabled) return;
    for (int i = 0; i < roots_count; i++) {
        if (roots[i] == root_ptr) {
            roots[i] = roots[--roots_count];
            return;
        }
    }
}

void gc_add_global_root(void** root_ptr) {
    if (!gc_enabled) return;
    ensure_global_roots_capacity();
    global_roots[global_roots_count++] = root_ptr;
}

void gc_write_barrier(void* parent_obj, void** field_ptr, void* new_value) {
    if (!gc_enabled) return;
    if (!parent_obj || !field_ptr) return;
    gc_header_t* parent_hdr = ptr_to_header(parent_obj);
    if (!parent_hdr) return;
    if (parent_hdr->flags & 0x02) {
        if (new_value) {
            gc_header_t* child_hdr = ptr_to_header(new_value);
            if (child_hdr && !(child_hdr->flags & 0x02))
                gc_add_dirty_object(parent_obj);
        }
    }
    *field_ptr = new_value;
}

void gc_dump_stats(void) {
    printf("========== GC Statistics ==========\n");
    printf("Young collections: %d\n", young_collections);
    printf("Old collections:   %d\n", old_collections);
    printf("Young used:        %zu bytes\n", (size_t)(young_top - young_from));
    printf("Young total:       %d bytes\n", YOUNG_SIZE);
    printf("Old used:          %zu bytes\n", (size_t)(old_top - old_start));
    printf("Old total:         %d bytes\n", OLD_SIZE);
    printf("Roots count:       %d\n", roots_count);
    printf("Global roots:      %d\n", global_roots_count);
    printf("Dirty objects:     %d\n", dirty_count);
    printf("===================================\n");
}

size_t gc_get_heap_size(void) {
    return YOUNG_SIZE * 2 + OLD_SIZE;
}

size_t gc_get_free_size(void) {
    return (young_limit - young_top) + (old_limit - old_top);
}