#ifndef COLLECTIONS_H
#define COLLECTIONS_H

#include <stddef.h>
#include <stdarg.h>

// ------------------------ ely_value ------------------------
typedef enum {
    ely_VALUE_NULL,
    ely_VALUE_BOOL,
    ely_VALUE_INT,
    ely_VALUE_DOUBLE,
    ely_VALUE_STRING,
    ely_VALUE_ARRAY,
    ely_VALUE_OBJECT
} ely_value_type;

typedef struct ely_value {
    ely_value_type type;
    union {
        int bool_val;
        long long int_val;
        double double_val;
        char* string_val;
        struct ely_array* array_val;
        struct ely_dict* object_val;
    } u;
} ely_value;

// ------------------------ ely_array ------------------------
typedef struct ely_array {
    void* data;
    size_t size;
    size_t capacity;
    size_t elem_size;
} ely_array;

ely_array* ely_array_new(size_t capacity, size_t elem_size);
void ely_array_free(ely_array* arr);
int ely_array_push(ely_array* arr, void* elem);
void ely_array_pop(ely_array* arr);
void* ely_array_get(ely_array* arr, size_t index);
void ely_array_set(ely_array* arr, size_t index, void* elem);
size_t ely_array_size(ely_array* arr);
ely_array* ely_array_make(size_t count, size_t elem_size, ...);

// ------------------------ ely_dict ------------------------
typedef struct ely_dict_entry {
    char* key;   // храним как char*
    void* value;
    struct ely_dict_entry* next;
} ely_dict_entry;

typedef struct ely_dict {
    ely_dict_entry** buckets;
    size_t size;
    size_t capacity;
    size_t value_size;
} ely_dict;

ely_dict* ely_dict_new(size_t capacity, size_t value_size);
void ely_dict_free(ely_dict* dict);
int ely_dict_set(ely_dict* dict, char* key, void* value);
void* ely_dict_get(ely_dict* dict, char* key);
int ely_dict_has(ely_dict* dict, char* key);
int ely_dict_delete(ely_dict* dict, char* key);
ely_dict* ely_dict_make(size_t count, size_t key_size, size_t value_size, ...);

// ------------------------ ely_value helpers (только конструкторы, без to_json/from_json) ------------------------
ely_value* ely_value_new_null(void);
ely_value* ely_value_new_bool(int b);
ely_value* ely_value_new_int(long long i);
ely_value* ely_value_new_double(double d);
ely_value* ely_value_new_string(char* s);
ely_value* ely_value_new_array(ely_array* arr);
ely_value* ely_value_new_object(ely_dict* obj);
void ely_value_free(ely_value* v);

#endif