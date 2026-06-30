#include "collections.h"
#include "ely_runtime.h"   // Макросы ELY_PAYLOAD_MASK, ely_VALUE_STRING и анбоксинг
#include <string.h>
#include <stdarg.h>

// Примечание: В твоих вызовах gc_alloc первым идет size, вторым – тип объекта.
// Придерживаемся твоей сигнатуры: gc_alloc(size_t size, gc_obj_type_t type)

// -------------------------------------------------------------------
// ------------------------ arr (Динамический массив) ----------------
// -------------------------------------------------------------------

arr* arr_new(void) {
    arr* a = (arr*)gc_alloc(sizeof(arr), GC_OBJ_ARR);
    if (!a) return NULL;
    a->data = NULL;
    a->size = 0;
    a->capacity = 0;
    return a;
}

static void arr_reserve(arr* a, size_t new_cap) {
    if (new_cap <= a->capacity) return;
    
    // Выделяем плоский массив под uint64_t значения
    ely_value* new_data = (ely_value*)gc_alloc(new_cap * sizeof(ely_value), GC_OBJ_ARR);
    if (!new_data) return;
    
    if (a->data) {
        // Копируем упакованные значения как есть
        memcpy(new_data, a->data, a->size * sizeof(ely_value));
    }
    
    // Старый буфер a->data мы просто оставляем куче — GC сам его утилизирует
    a->data = new_data;
    a->capacity = new_cap;
}

void arr_push(arr* a, ely_value elem) {
    if (!a) return;
    if (a->size >= a->capacity) {
        size_t new_cap = a->capacity == 0 ? 4 : a->capacity * 2;
        arr_reserve(a, new_cap);
    }
    
    // Если элемент содержит указатель на объект в куче, пишем через барьер
    gc_write_barrier(a, (void**)&a->data[a->size], (void*)(uintptr_t)elem);
    a->size++;
}

ely_value arr_pop_value(arr* a) {
    if (!a || a->size == 0) return 0; // Или твой дефолтный ELY_TAG_NULL
    return a->data[--a->size];
}

void arr_pop(arr* a) {
    if (a && a->size > 0) a->size--;
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

int arr_remove_value(arr* a, ely_value value) {
    if (!a || a->size == 0) return -1;
    for (size_t i = 0; i < a->size; i++) {
        if (a->data[i] == value) { // Прямое побитовое сравнение 64-битных боксов!
            for (size_t j = i; j < a->size - 1; j++) {
                a->data[j] = a->data[j+1];
            }
            a->size--;
            return 0;
        }
    }
    return -1;
}

int arr_remove_index(arr* a, size_t index) {
    if (!a || index >= a->size) return -1;
    for (size_t j = index; j < a->size - 1; j++) {
        a->data[j] = a->data[j+1];
    }
    a->size--;
    return 0;
}

int arr_insert(arr* a, size_t index, ely_value elem) {
    if (!a || index > a->size) return -1;
    if (a->size >= a->capacity) {
        size_t new_cap = a->capacity == 0 ? 4 : a->capacity * 2;
        arr_reserve(a, new_cap);
    }
    for (size_t j = a->size; j > index; j--) {
        a->data[j] = a->data[j-1];
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
        ely_value elem = va_arg(args, ely_value); // Достаем как плоский uint64_t
        arr_push(a, elem);
    }
    va_end(args);
    return a;
}


// -------------------------------------------------------------------
// ------------------------ dict (Хеш-таблица) -----------------------
// -------------------------------------------------------------------

static unsigned int default_hash(ely_value key) {
    // key теперь uint64_t. Используем классический 64-битный микс-хеш Томаса Ванга
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
    d->capacity = 16;
    d->buckets = (dict_entry**)gc_alloc(d->capacity * sizeof(dict_entry*), GC_OBJ_DICT);
    if (!d->buckets) return NULL;
    
    memset(d->buckets, 0, d->capacity * sizeof(dict_entry*));
    d->size = 0;
    d->hash = hash ? hash : default_hash;
    d->key_cmp = key_cmp ? key_cmp : default_cmp;
    return d;
}

static void dict_resize(dict* d, size_t new_cap) {
    if (new_cap < d->size) return;
    dict_entry** new_buckets = (dict_entry**)gc_alloc(new_cap * sizeof(dict_entry*), GC_OBJ_DICT);
    if (!new_buckets) return;
    memset(new_buckets, 0, new_cap * sizeof(dict_entry*));

    for (size_t i = 0; i < d->capacity; i++) {
        dict_entry* e = d->buckets[i];
        while (e) {
            dict_entry* next = e->next;
            size_t idx = d->hash(e->key) % new_cap;
            
            // Связываем ноду в новом бакете через барьер записи
            gc_write_barrier(e, (void**)&e->next, new_buckets[idx]);
            new_buckets[idx] = e;
            
            e = next;
        }
    }
    // Старые бакеты d->buckets уходят на съедение GC
    d->buckets = new_buckets;
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
            gc_write_barrier(e, (void**)&e->value, (void*)(uintptr_t)value);
            return;
        }
        e = e->next;
    }
    
    // Создаем новую ноду коллизии прямо в GC куче
    e = (dict_entry*)gc_alloc(sizeof(dict_entry), GC_OBJ_DICT);
    if (!e) return;
    
    e->key = key; // Ключ пишется при инициализации
    gc_write_barrier(e, (void**)&e->value, (void*)(uintptr_t)value);
    gc_write_barrier(e, (void**)&e->next, d->buckets[idx]);
    
    // Обновляем указатель в массиве бакетов
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
                gc_write_barrier(prev, (void**)&prev->next, e->next);
            } else {
                gc_write_barrier(d, (void**)&d->buckets[idx], e->next);
            }
            // Нода e больше никем не видима, её прибьет GC. Ручной free(e) удален!
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
    // Проверяем тип тега из верхних байт (сдвиг на 56 бит)
    if ((key >> 56) != ely_VALUE_STRING) return 0;
    
    // Распаковываем указатель на сырую C-строку
    char* str = (char*)(uintptr_t)(key & ELY_PAYLOAD_MASK);
    if (!str) return 0;
    
    unsigned int hash = 5381;
    int c;
    while ((c = (unsigned char)*str++)) {
        hash = ((hash << 5) + hash) + c;
    }
    return hash;
}

int dict_cmp_str(ely_value a, ely_value b) {
    if (a == b) return 0;
    if ((a >> 56) != ely_VALUE_STRING || (b >> 56) != ely_VALUE_STRING) return 1;
    
    char* str_a = (char*)(uintptr_t)(a & ELY_PAYLOAD_MASK);
    char* str_b = (char*)(uintptr_t)(b & ELY_PAYLOAD_MASK);
    if (!str_a || !str_b) return 1;
    
    return strcmp(str_a, str_b);
}