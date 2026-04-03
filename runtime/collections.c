#include "collections.h"
#include "ely_runtime.h"   // для ely_value
#include <stdlib.h>
#include <string.h>
#include "ely_gc.h"

// ------------------------ arr ------------------------
arr* arr_new(void) {
    arr* a = (arr*)gc_alloc(sizeof(arr), GC_OBJ_ARR);
    if (!a) return NULL;
    a->data = NULL;
    a->size = 0;
    a->capacity = 0;
    return a;
}

void arr_free(arr* a) {
    if (a) {
        for (size_t i = 0; i < a->size; i++) {
            if (a->data[i]) ely_value_free(a->data[i]);
        }
        free(a->data);
        free(a);
    }
}

static void arr_reserve(arr* a, size_t new_cap) {
    if (new_cap <= a->capacity) return;
    ely_value** new_data = (ely_value**)realloc(a->data, new_cap * sizeof(ely_value*));
    if (!new_data) return;
    a->data = new_data;
    a->capacity = new_cap;
}

void arr_push(arr* a, ely_value* elem) {
    if (!a) return;
    if (a->size >= a->capacity) {
        size_t new_cap = a->capacity == 0 ? 4 : a->capacity * 2;
        arr_reserve(a, new_cap);
    }
    a->data[a->size++] = elem;
}

ely_value* arr_pop_value(arr* a) {
    if (!a || a->size == 0) return NULL;
    return a->data[--a->size];
}

void arr_pop(arr* a) {
    if (a && a->size > 0) a->size--;
}

ely_value* arr_get(arr* a, size_t index) {
    if (!a || index >= a->size) return NULL;
    return a->data[index];
}

void arr_set(arr* a, size_t index, ely_value* elem) {
    if (!a || index >= a->size) return;
    if (a->data[index]) ely_value_free(a->data[index]);
    a->data[index] = elem;
}

size_t arr_len(arr* a) {
    return a ? a->size : 0;
}

int arr_remove_value(arr* a, ely_value* value) {
    if (!a || a->size == 0) return -1;
    for (size_t i = 0; i < a->size; i++) {
        if (a->data[i] == value) {   // сравнение указателей, для точного сравнения нужна функция ely_value_equal
            for (size_t j = i; j < a->size - 1; j++) a->data[j] = a->data[j+1];
            a->size--;
            return 0;
        }
    }
    return -1;
}

int arr_remove_index(arr* a, size_t index) {
    if (!a || index >= a->size) return -1;
    for (size_t j = index; j < a->size - 1; j++) a->data[j] = a->data[j+1];
    a->size--;
    return 0;
}

int arr_insert(arr* a, size_t index, ely_value* elem) {
    if (!a || index > a->size) return -1;
    if (a->size >= a->capacity) {
        size_t new_cap = a->capacity == 0 ? 4 : a->capacity * 2;
        arr_reserve(a, new_cap);
    }
    for (size_t j = a->size; j > index; j--) a->data[j] = a->data[j-1];
    a->data[index] = elem;
    a->size++;
    return 0;
}

int arr_index(arr* a, ely_value* value) {
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
        copy->data[i] = a->data[i];
        if (copy->data[i]) ; // ничего не делаем
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
        ely_value* elem = va_arg(args, ely_value*);
        arr_push(a, elem);
    }
    va_end(args);
    return a;
}

// ------------------------ dict ------------------------
static unsigned int default_hash(ely_value* key) {
    // для простоты, если ключ не строка – хешируем указатель
    return (unsigned int)(size_t)key;
}

static int default_cmp(ely_value* a, ely_value* b) {
    return (a == b) ? 0 : 1;
}

dict* dict_new(unsigned int (*hash)(ely_value*), int (*key_cmp)(ely_value*, ely_value*)) {
    dict* d = (dict*)gc_alloc(sizeof(dict), GC_OBJ_DICT);
    if (!d) return NULL;
    d->capacity = 16;
    d->buckets = (dict_entry**)gc_alloc(d->capacity * sizeof(dict_entry*), GC_OBJ_DICT);
    if (!d->buckets) { free(d); return NULL; }
    d->size = 0;
    d->hash = hash ? hash : default_hash;
    d->key_cmp = key_cmp ? key_cmp : default_cmp;
    return d;
}

void dict_free(dict* d) {
    if (!d) return;
    for (size_t i = 0; i < d->capacity; i++) {
        dict_entry* e = d->buckets[i];
        while (e) {
            dict_entry* next = e->next;
            ely_value_free(e->key);
            ely_value_free(e->value);
            free(e);
            e = next;
        }
    }
    free(d->buckets);
    free(d);
}

static void dict_resize(dict* d, size_t new_cap) {
    if (new_cap < d->size) return;
    dict_entry** new_buckets = (dict_entry**)gc_alloc(new_cap * sizeof(dict_entry*), GC_OBJ_DICT);
    if (!new_buckets) return;
    for (size_t i = 0; i < d->capacity; i++) {
        dict_entry* e = d->buckets[i];
        while (e) {
            dict_entry* next = e->next;
            size_t idx = d->hash(e->key) % new_cap;
            e->next = new_buckets[idx];
            new_buckets[idx] = e;
            e = next;
        }
    }
    free(d->buckets);
    d->buckets = new_buckets;
    d->capacity = new_cap;
}

void dict_set(dict* d, ely_value* key, ely_value* value) {
    if (!d) return;
    if (d->size >= d->capacity * 0.75) {
        dict_resize(d, d->capacity * 2);
    }
    unsigned int h = d->hash(key);
    size_t idx = h % d->capacity;
    dict_entry* e = d->buckets[idx];
    while (e) {
        if (d->key_cmp(e->key, key) == 0) {
            ely_value_free(e->value);
            e->value = value;
            return;
        }
        e = e->next;
    }
    e = (dict_entry*)gc_alloc(sizeof(dict_entry), GC_OBJ_DICT);
    if (!e) return;
    e->key = key;
    e->value = value;
    e->next = d->buckets[idx];
    d->buckets[idx] = e;
    d->size++;
}

ely_value* dict_get(dict* d, ely_value* key) {
    if (!d) return NULL;
    unsigned int h = d->hash(key);
    size_t idx = h % d->capacity;
    dict_entry* e = d->buckets[idx];
    while (e) {
        if (d->key_cmp(e->key, key) == 0)
            return e->value;
        e = e->next;
    }
    return NULL;
}

int dict_has(dict* d, ely_value* key) {
    return dict_get(d, key) != NULL;
}

int dict_delete(dict* d, ely_value* key) {
    if (!d) return -1;
    unsigned int h = d->hash(key);
    size_t idx = h % d->capacity;
    dict_entry* e = d->buckets[idx];
    dict_entry* prev = NULL;
    while (e) {
        if (d->key_cmp(e->key, key) == 0) {
            if (prev) prev->next = e->next;
            else d->buckets[idx] = e->next;
            ely_value_free(e->key);
            ely_value_free(e->value);
            free(e);
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

arr* dict_keys(dict* d) {
    if (!d) return NULL;
    arr* keys = arr_new();
    if (!keys) return NULL;
    for (size_t i = 0; i < d->capacity; i++) {
        dict_entry* e = d->buckets[i];
        while (e) {
            arr_push(keys, e->key);
            e = e->next;
        }
    }
    return keys;
}

arr* dict_values(dict* d) {
    if (!d) return NULL;
    arr* values = arr_new();
    if (!values) return NULL;
    for (size_t i = 0; i < d->capacity; i++) {
        dict_entry* e = d->buckets[i];
        while (e) {
            arr_push(values, e->value);
            e = e->next;
        }
    }
    return values;
}

dict* dict_make(size_t count, ...) {
    dict* d = dict_new(NULL, NULL);
    if (!d) return NULL;
    va_list args;
    va_start(args, count);
    for (size_t i = 0; i < count; i++) {
        ely_value* key = va_arg(args, ely_value*);
        ely_value* value = va_arg(args, ely_value*);
        dict_set(d, key, value);
    }
    va_end(args);
    return d;
}

// Обёртки для строковых ключей
unsigned int dict_hash_str(ely_value* key) {
    if (!key || key->type != ely_VALUE_STRING) return 0;
    unsigned int hash = 5381;
    char* str = key->u.string_val;
    int c;
    while ((c = *str++))
        hash = ((hash << 5) + hash) + c;
    return hash;
}

int dict_cmp_str(ely_value* a, ely_value* b) {
    if (a == b) return 0;
    if (!a || !b) return 1;
    if (a->type != ely_VALUE_STRING || b->type != ely_VALUE_STRING) return 1;
    return strcmp(a->u.string_val, b->u.string_val);
}

dict* dict_new_str(void) {
    return dict_new(dict_hash_str, dict_cmp_str);
}

void dict_set_str(dict* d, char* key, ely_value* value) {
    ely_value* key_val = ely_value_new_string(key);
    dict_set(d, key_val, value);
    // key_val больше не нужен, т.к. dict_set его сохранил (мы передаём владение)
}

ely_value* dict_get_str(dict* d, char* key) {
    ely_value* key_val = ely_value_new_string(key);
    ely_value* res = dict_get(d, key_val);
    ely_value_free(key_val);
    return res;
}

int dict_has_str(dict* d, char* key) {
    ely_value* key_val = ely_value_new_string(key);
    int res = dict_has(d, key_val);
    ely_value_free(key_val);
    return res;
}

int dict_delete_str(dict* d, char* key) {
    ely_value* key_val = ely_value_new_string(key);
    int res = dict_delete(d, key_val);
    ely_value_free(key_val);
    return res;
}

arr* dict_keys_str(dict* d) {
    return dict_keys(d);
}