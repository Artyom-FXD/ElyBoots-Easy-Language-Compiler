#ifndef COLLECTIONS_H
#define COLLECTIONS_H

#include <stddef.h>
#include <stdarg.h>
#include <stdint.h>
#include "ely_gc.h"

// Тип ely_value (uint64_t) должен приходить из базового рантайма до инклюда коллекции.
typedef uint64_t ely_value; 

// ------------------------ arr (динамический массив ely_value) ------------------------
typedef struct arr {
    ely_value* data;      // БЫЛО: ely_value** data (теперь плоский массив uint64_t элементов)
    size_t size;
    size_t capacity;
} arr;

arr* arr_new(void);
void arr_push(arr* a, ely_value elem);
ely_value arr_pop_value(arr* a);
void arr_pop(arr* a);
ely_value arr_get(arr* a, size_t index);
void arr_set(arr* a, size_t index, ely_value elem); 
size_t arr_len(arr* a);
int arr_remove_value(arr* a, ely_value value);
int arr_remove_index(arr* a, size_t index);
int arr_insert(arr* a, size_t index, ely_value elem);
int arr_index(arr* a, ely_value value);
arr* arr_copy(arr* a);
arr* arr_make(size_t count, ...);

// ------------------------ dict (хеш-таблица ely_value) ------------------------
typedef struct dict_entry {
    ely_value key;        // БЫЛО: ely_value* key
    ely_value value;      // БЫЛО: ely_value* value
    struct dict_entry* next;
} dict_entry;

typedef struct dict {
    dict_entry** buckets;
    size_t size;
    size_t capacity;
    unsigned int (*hash)(ely_value key);         // БЫЛО: ely_value* key
    int (*key_cmp)(ely_value a, ely_value b);    // БЫЛО: ely_value* a, ely_value* b
} dict;

dict* dict_new(unsigned int (*hash)(ely_value), int (*key_cmp)(ely_value, ely_value));
void dict_set(dict* d, ely_value key, ely_value value); // БЫЛО: указатели
ely_value dict_get(dict* d, ely_value key);             // БЫЛО: указатели
int dict_has(dict* d, ely_value key);
int dict_delete(dict* d, ely_value key);
size_t dict_size(dict* d);

#endif // COLLECTIONS_H