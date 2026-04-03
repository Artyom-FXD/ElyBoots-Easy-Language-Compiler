#ifndef COLLECTIONS_H
#define COLLECTIONS_H

#include <stddef.h>
#include <stdarg.h>
#include "ely_gc.h"

// forward declaration для ely_value
typedef struct ely_value ely_value;

// ------------------------ arr (динамический массив ely_value*) ------------------------
typedef struct arr {
    ely_value** data;
    size_t size;
    size_t capacity;
} arr;

arr* arr_new(void);
void arr_free(arr* a);
void arr_push(arr* a, ely_value* elem);
ely_value* arr_pop_value(arr* a);
void arr_pop(arr* a);
ely_value* arr_get(arr* a, size_t index);
void arr_set(arr* a, size_t index, ely_value* elem);
size_t arr_len(arr* a);
int arr_remove_value(arr* a, ely_value* value);
int arr_remove_index(arr* a, size_t index);
int arr_insert(arr* a, size_t index, ely_value* elem);
int arr_index(arr* a, ely_value* value);
arr* arr_copy(arr* a);
arr* arr_make(size_t count, ...);

// ------------------------ dict (хеш-таблица ely_value*) ------------------------
typedef struct dict_entry {
    ely_value* key;
    ely_value* value;
    struct dict_entry* next;
} dict_entry;

typedef struct dict {
    dict_entry** buckets;
    size_t size;
    size_t capacity;
    unsigned int (*hash)(ely_value* key);
    int (*key_cmp)(ely_value* a, ely_value* b);
} dict;

dict* dict_new(unsigned int (*hash)(ely_value*), int (*key_cmp)(ely_value*, ely_value*));
void dict_free(dict* d);
void dict_set(dict* d, ely_value* key, ely_value* value);
ely_value* dict_get(dict* d, ely_value* key);
int dict_has(dict* d, ely_value* key);
int dict_delete(dict* d, ely_value* key);
size_t dict_size(dict* d);
arr* dict_keys(dict* d);
arr* dict_values(dict* d);
dict* dict_make(size_t count, ...);

// Удобные обёртки для строковых ключей
unsigned int dict_hash_str(ely_value* key);
int dict_cmp_str(ely_value* a, ely_value* b);
dict* dict_new_str(void);
void dict_set_str(dict* d, char* key, ely_value* value);
ely_value* dict_get_str(dict* d, char* key);
int dict_has_str(dict* d, char* key);
int dict_delete_str(dict* d, char* key);
arr* dict_keys_str(dict* d);  // возвращает arr* из ely_value* (строк)

#endif