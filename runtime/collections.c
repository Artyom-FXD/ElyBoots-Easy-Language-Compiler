#include "collections.h"

#include <string.h>
#include <stdarg.h>

#include "ely_value.h"

#ifndef ELY_PAYLOAD_MASK
#define ELY_PAYLOAD_MASK (~0x7ULL) 
#endif

#ifndef ELY_STR_DATA_SHIFT
#define ELY_STR_DATA_SHIFT 8
#endif

// -------------------------------------------------------------------
// ------------------------ arr (Динамический массив) ----------------
// -------------------------------------------------------------------

arr* arr_new(void) {
    arr* a = (arr*)gc_alloc(sizeof(arr), GC_OBJ_ARR);
    if (!a) return NULL;
    a->base.type = ELY_HEAP_ARRAY; // Инициализируем тип для рефлексии!
    a->data = NULL;
    a->size = 0;
    a->capacity = 0;
    return a;
}

static void arr_reserve(arr* a, size_t new_cap) {
    if (new_cap <= a->capacity) return;
    
    // Внутренний буфер — это "листовой" объект GC_OBJ_DOUBLE. Он не сканируется сам по себе!
    ely_value* new_data = (ely_value*)gc_alloc(new_cap * sizeof(ely_value), GC_OBJ_DOUBLE);
    if (!new_data) return;
    
    if (a->data) {
        memcpy(new_data, a->data, a->size * sizeof(ely_value));
    }
    
    // Записываем новый буфер через барьер записи на объекте `a`
    gc_write_barrier(a, (void**)&a->data, new_data);
    a->capacity = new_cap;
}

void arr_push(arr* a, ely_value elem) {
    if (!a) return;
    if (a->size >= a->capacity) {
        size_t new_cap = a->capacity == 0 ? 4 : a->capacity * 2;
        arr_reserve(a, new_cap);
    }
    
    // Носителем барьера является родитель `a`, так как буфер `a->data` — листовой объект
    gc_write_barrier(a, (void**)&a->data[a->size], (void*)(uintptr_t)elem);
    a->size++;
}

ely_value arr_pop_value(arr* a) {
    if (!a || a->size == 0) return 0;
    ely_value val = a->data[--a->size];
    a->data[a->size] = 0; // Чистим за собой ссылку, чтобы GC не держал старый объект в памяти
    return val;
}

void arr_pop(arr* a) {
    if (a && a->size > 0) {
        a->size--;
        a->data[a->size] = 0; // Стираем ссылку
    }
}

ely_value arr_get(arr* a, size_t index) {
    if (!a || index >= a->size) return 0;
    return a->data[index];
}

void arr_set(arr* a, size_t index, ely_value elem) {
    if (!a || index >= a->size) return;
    gc_write_barrier(a, (void**)&a->data[index], (void*)(uintptr_t)elem);
}

size_t arr_len(arr* a) {
    return a ? a->size : 0;
}

int arr_remove_index(arr* a, size_t index) {
    if (!a || index >= a->size) return -1;
    for (size_t j = index; j < a->size - 1; j++) {
        // Запись через барьер, так как мы сдвигаем потенциальные ссылки в куче
        gc_write_barrier(a, (void**)&a->data[j], (void*)(uintptr_t)a->data[j+1]);
    }
    a->size--;
    a->data[a->size] = 0; // Обнуляем хвост
    return 0;
}

int arr_remove_value(arr* a, ely_value value) {
    if (!a || a->size == 0) return -1;
    for (size_t i = 0; i < a->size; i++) {
        if (a->data[i] == value) { 
            return arr_remove_index(a, i);
        }
    }
    return -1;
}

int arr_insert(arr* a, size_t index, ely_value elem) {
    if (!a || index > a->size) return -1;
    if (a->size >= a->capacity) {
        size_t new_cap = a->capacity == 0 ? 4 : a->capacity * 2;
        arr_reserve(a, new_cap);
    }
    for (size_t j = a->size; j > index; j--) {
        gc_write_barrier(a, (void**)&a->data[j], (void*)(uintptr_t)a->data[j-1]);
    }
    gc_write_barrier(a, (void**)&a->data[index], (void*)(uintptr_t)elem);
    a->size++;
    return 0;
}

int arr_index(arr* a, ely_value value) {
    if (!a) return -1;
    for (size_t i = 0; i < a->size; i++) {
        if (a->data[i] == value) return (int)i;
    }
    return -1;
}

arr* arr_copy(arr* a) {
    if (!a) return NULL;
    arr* copy = arr_new();
    if (!copy) return NULL;
    arr_reserve(copy, a->capacity);
    for (size_t i = 0; i < a->size; i++) {
        gc_write_barrier(copy, (void**)&copy->data[i], (void*)(uintptr_t)a->data[i]);
    }
    copy->size = a->size;
    return copy;
}

arr* arr_make(size_t count, ...) {
    arr* a = arr_new();
    if (!a) return NULL;
    
    va_list args;
    va_start(args, count);
    for (size_t i = 0; i < count; i++) {
        ely_value elem = va_arg(args, ely_value);
        arr_push(a, elem);
    }
    va_end(args);
    
    return a;
}


// -------------------------------------------------------------------
// ------------------------ dict (Хеш-таблица) -----------------------
// -------------------------------------------------------------------

static unsigned int default_hash(ely_value key) {
    key = (~key) + (key << 21);
    key = key ^ (key >> 24);
    key = (key + (key << 3)) + (key << 8);
    key = key ^ (key >> 14);
    key = (key + (key << 2)) + (key << 4);
    key = key ^ (key >> 28);
    key = key + (key << 31);
    return (unsigned int)key;
}

static int default_cmp(ely_value a, ely_value b) {
    return (a == b) ? 0 : 1;
}

dict* dict_new(unsigned int (*hash)(ely_value), int (*key_cmp)(ely_value, ely_value)) {
    dict* d = (dict*)gc_alloc(sizeof(dict), GC_OBJ_DICT);
    if (!d) return NULL;
    d->base.type = ELY_HEAP_DICT; // Инициализируем тип для рефлексии!
    d->capacity = 16;
    
    d->buckets = (dict_entry**)gc_alloc(d->capacity * sizeof(dict_entry*), GC_OBJ_DOUBLE);
    if (!d->buckets) return NULL;
    
    memset(d->buckets, 0, d->capacity * sizeof(dict_entry*));
    d->size = 0;
    d->hash = hash ? hash : default_hash;
    d->key_cmp = key_cmp ? key_cmp : default_cmp;
    return d;
}

static void dict_resize(dict* d, size_t new_cap) {
    if (new_cap < d->size) return;
    
    // Новый буфер бакетов также делаем плоским GC_OBJ_DOUBLE
    dict_entry** new_buckets = (dict_entry**)gc_alloc(new_cap * sizeof(dict_entry*), GC_OBJ_DOUBLE);
    if (!new_buckets) return;
    memset(new_buckets, 0, new_cap * sizeof(dict_entry*));

    for (size_t i = 0; i < d->capacity; i++) {
        dict_entry* e = d->buckets[i];
        while (e) {
            dict_entry* next = e->next;
            size_t idx = d->hash(e->key) % new_cap;
            
            // В барьер передаем родителя `d`!
            gc_write_barrier(d, (void**)&e->next, new_buckets[idx]);
            new_buckets[idx] = e;
            
            e = next;
        }
    }
    
    // Перезаписываем бакеты в родителе `d`
    gc_write_barrier(d, (void**)&d->buckets, new_buckets);
    d->capacity = new_cap;
}

void dict_set(dict* d, ely_value key, ely_value value) {
    if (!d) return;
    if (d->size >= d->capacity * 0.75) dict_resize(d, d->capacity * 2);
    
    unsigned int h = d->hash(key);
    size_t idx = h % d->capacity;
    dict_entry* e = d->buckets[idx];
    
    while (e) {
        if (d->key_cmp(e->key, key) == 0) {
            // Барьер на `d`, так как `e` — листовой объект кучи
            gc_write_barrier(d, (void**)&e->value, (void*)(uintptr_t)value);
            return;
        }
        e = e->next;
    }
    
    // Нода коллизии тоже выделяется как GC_OBJ_DOUBLE!
    e = (dict_entry*)gc_alloc(sizeof(dict_entry), GC_OBJ_DOUBLE);
    if (!e) return;
    
    e->key = key; 
    gc_write_barrier(d, (void**)&e->value, (void*)(uintptr_t)value);
    gc_write_barrier(d, (void**)&e->next, d->buckets[idx]);
    
    gc_write_barrier(d, (void**)&d->buckets[idx], e);
    d->size++;
}

ely_value dict_get(dict* d, ely_value key) {
    if (!d) return 0;
    unsigned int h = d->hash(key);
    size_t idx = h % d->capacity;
    dict_entry* e = d->buckets[idx];
    while (e) {
        if (d->key_cmp(e->key, key) == 0) return e->value;
        e = e->next;
    }
    return 0;
}

int dict_has(dict* d, ely_value key) {
    return dict_get(d, key) != 0;
}

int dict_delete(dict* d, ely_value key) {
    if (!d) return -1;
    unsigned int h = d->hash(key);
    size_t idx = h % d->capacity;
    dict_entry* e = d->buckets[idx];
    dict_entry* prev = NULL;
    while (e) {
        if (d->key_cmp(e->key, key) == 0) {
            if (prev) {
                gc_write_barrier(d, (void**)&prev->next, e->next);
            } else {
                gc_write_barrier(d, (void**)&d->buckets[idx], e->next);
            }
            d->size--;
            return 0;
        }
        prev = e;
        e = e->next;
    }
    return -1;
}

size_t dict_size(dict* d) {
    return d ? d->size : 0;
}

// -------------------------------------------------------------------
// ------------------------ Работа со строками в Dict ----------------
// -------------------------------------------------------------------

unsigned int dict_hash_str(ely_value key) {
    if (ely_is_immediate_str(key)) {
        size_t len = ely_immediate_str_len(key);
        unsigned int hash = 5381;
        for (size_t i = 0; i < len; i++) {
            int c = (char)((key >> (ELY_STR_DATA_SHIFT + (i * 8))) & 0xFF);
            hash = ((hash << 5) + hash) + c;
        }
        return hash;
    }

    if (ely_is_ptr(key)) {
        ElyHeapObject* obj = (ElyHeapObject*)ely_as_ptr(key);
        if (obj && obj->type == ELY_HEAP_STRING) {
            char* str = ((ElyHeapString*)obj)->data;
            unsigned int hash = 5381;
            int c;
            while ((c = (unsigned char)*str++)) {
                hash = ((hash << 5) + hash) + c;
            }
            return hash;
        }
    }

    return 0; 
}

int dict_cmp_str(ely_value a, ely_value b) {
    if (a == b) return 0;

    bool a_imm = ely_is_immediate_str(a);
    bool b_imm = ely_is_immediate_str(b);

    char buf_a[8];
    char buf_b[8];
    const char* str_a = NULL;
    const char* str_b = NULL;

    if (a_imm) {
        ely_immediate_str_get_chars(a, buf_a);
        str_a = buf_a;
    } else if (ely_is_ptr(a)) {
        ElyHeapObject* obj = (ElyHeapObject*)ely_as_ptr(a);
        if (obj && obj->type == ELY_HEAP_STRING) {
            str_a = ((ElyHeapString*)obj)->data;
        }
    }

    if (b_imm) {
        ely_immediate_str_get_chars(b, buf_b);
        str_b = buf_b;
    } else if (ely_is_ptr(b)) {
        ElyHeapObject* obj = (ElyHeapObject*)ely_as_ptr(b);
        if (obj && obj->type == ELY_HEAP_STRING) {
            str_b = ((ElyHeapString*)obj)->data;
        }
    }

    if (!str_a || !str_b) return 1; // Разные или некорректные типы
    return strcmp(str_a, str_b);
}