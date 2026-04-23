#ifndef ely_RUNTIME_H
#define ely_RUNTIME_H

#include <stddef.h>
#include "collections.h"
#include "ely_gc.h"

typedef enum {
    ely_VALUE_NULL,
    ely_VALUE_BOOL,
    ely_VALUE_INT,
    ely_VALUE_DOUBLE,
    ely_VALUE_STRING,
    ely_VALUE_ARRAY,
    ely_VALUE_OBJECT,
    ely_VALUE_FUNCTION
} ely_value_type;

typedef struct ely_value {
    ely_value_type type;
    union {
        int bool_val;
        long long int_val;
        double double_val;
        char* string_val;
        arr* array_val;
        dict* object_val;
        // Указатель на функцию C (для встроенных) или объект с кодом (для Ely-функций)
        struct {
            void* func_ptr;      // указатель на C-функцию
            int is_native;       // 1 если native C, 0 если Ely-функция (пока не используется)
        } function;
    } u;
} ely_value;

#ifdef __cplusplus
extern "C" {
#endif

// Типы
typedef int             ely_int;
typedef unsigned int    ely_uint;
typedef long long       ely_more;
typedef unsigned long long ely_umore;
typedef float           ely_flt;
typedef double          ely_double;
typedef char            ely_char;
typedef unsigned char   ely_byte;
typedef unsigned char   ely_ubyte;
typedef int             ely_bool;
typedef char*           ely_str;

// Конструкторы ely_value
ely_value* ely_value_new_null(void);
ely_value* ely_value_new_bool(int b);
ely_value* ely_value_new_int(long long i);
ely_value* ely_value_new_double(double d);
ely_value* ely_value_new_string(char* s);
ely_value* ely_value_new_array(arr* a);
ely_value* ely_value_new_object(dict* d);
void ely_value_free(ely_value* v);

// Операции над ely_value
int ely_value_as_bool(ely_value* v);
ely_value* ely_value_index(ely_value* v, ely_value* index);
ely_value* ely_value_get_key(ely_value* v, char* key);
void ely_value_set_key(ely_value* v, char* key, ely_value* value);
void ely_value_set_index(ely_value* v, ely_value* index, ely_value* value);
char* ely_value_to_json(ely_value* v);
ely_value* ely_value_from_json(char* json, size_t* pos);
char* ely_value_to_string(ely_value* v);

ely_value* ely_value_add(ely_value* a, ely_value* b);
ely_value* ely_value_sub(ely_value* a, ely_value* b);
ely_value* ely_value_mul(ely_value* a, ely_value* b);
ely_value* ely_value_div(ely_value* a, ely_value* b);
ely_value* ely_value_mod(ely_value* a, ely_value* b);
ely_value* ely_value_eq(ely_value* a, ely_value* b);
ely_value* ely_value_ne(ely_value* a, ely_value* b);
ely_value* ely_value_lt(ely_value* a, ely_value* b);
ely_value* ely_value_le(ely_value* a, ely_value* b);
ely_value* ely_value_gt(ely_value* a, ely_value* b);
ely_value* ely_value_ge(ely_value* a, ely_value* b);
ely_value* ely_value_and(ely_value* a, ely_value* b);
ely_value* ely_value_or(ely_value* a, ely_value* b);
ely_value* ely_value_not(ely_value* a);
ely_value* ely_value_neg(ely_value* a);

// ------------------------ Консоль ------------------------
void ely_print(ely_str str);
void ely_print_int(ely_int n);
void ely_print_uint(ely_uint n);
void ely_print_more(ely_more n);
void ely_print_umore(ely_umore n);
void ely_print_flt(ely_flt f);
void ely_print_double(ely_double d);
void ely_print_bool(ely_bool b);
void ely_print_char(ely_char c);
void ely_print_byte(ely_byte b);
void ely_print_ubyte(ely_ubyte b);
void ely_println(ely_str str);

ely_str ely_input(void);
ely_str ely_input_prompt(ely_str prompt);

// ------------------------ Преобразования ------------------------
ely_int    ely_str_to_int(ely_str str);
ely_uint   ely_str_to_uint(ely_str str);
ely_more   ely_str_to_more(ely_str str);
ely_umore  ely_str_to_umore(ely_str str);
ely_flt    ely_str_to_flt(ely_str str);
ely_double ely_str_to_double(ely_str str);

ely_str ely_int_to_str(ely_int n);
ely_str ely_uint_to_str(ely_uint n);
ely_str ely_more_to_str(ely_more n);
ely_str ely_umore_to_str(ely_umore n);
ely_str ely_flt_to_str(ely_flt f);
ely_str ely_double_to_str(ely_double d);
ely_str ely_bool_to_str(ely_bool b);

// ------------------------ Строки ------------------------
size_t      ely_str_len(ely_str str);
ely_str     ely_str_dup(ely_str str);
ely_str     ely_str_concat(ely_str a, ely_str b);
int         ely_str_cmp(ely_str a, ely_str b);
ely_str     ely_str_substr(ely_str str, size_t start, size_t len);
ely_str     ely_str_trim(ely_str str);
ely_str     ely_str_replace(ely_str str, ely_str old, ely_str new);

// ------------------------ Математика ------------------------
ely_int    ely_abs_int(ely_int n);
ely_more   ely_abs_more(ely_more n);
ely_double ely_fabs(ely_double x);
ely_int    ely_min_int(ely_int a, ely_int b);
ely_more   ely_min_more(ely_more a, ely_more b);
ely_double ely_min_double(ely_double a, ely_double b);
ely_int    ely_max_int(ely_int a, ely_int b);
ely_more   ely_max_more(ely_more a, ely_more b);
ely_double ely_max_double(ely_double a, ely_double b);
ely_double ely_pow(ely_double base, ely_double exp);
ely_double ely_sqrt(ely_double x);
ely_double ely_sin(ely_double x);
ely_double ely_cos(ely_double x);
ely_double ely_tan(ely_double x);

// ------------------------ Случайные числа ------------------------
void        ely_srand(ely_uint seed);
ely_int     ely_rand(void);
ely_double  ely_rand_double(void);

// ------------------------ Время ------------------------
void        ely_sleep(ely_uint milliseconds);
ely_more    ely_time_now(void);
double      ely_time_diff(ely_more start, ely_more end);

// ------------------------ Файлы ------------------------
typedef struct ely_file ely_file;
ely_file* ely_file_open(char* path, char* mode);
void       ely_file_close(ely_file* f);
int        ely_file_write(ely_file* f, char* data, size_t len);
char*      ely_file_read(ely_file* f, size_t* out_len);
int        ely_file_exists(char* path);
char*      ely_file_read_all(char* path, size_t* out_len);
int        ely_file_remove(char* path);
int        ely_file_rename(char* old, char* new);
int        ely_file_write_all(char* path, char* data, size_t len);

// ------------------------ Пути ------------------------
ely_str ely_path_join(ely_str a, ely_str b);
ely_str ely_path_basename(ely_str path);
ely_str ely_path_dirname(ely_str path);
int      ely_path_is_absolute(ely_str path);

// ------------------------ Динамические библиотеки ------------------------
void* ely_load_library(char* path);
void* ely_get_function(void* lib, char* name);
void  ely_close_library(void* lib);
int   ely_call_int_int(void* func, int a, int b);
double ely_call_double_double(void* func, double a);
double ely_call_double_double_double(void* func, double a, double b);
char* ely_call_str_void(void* func);

// ------------------------ Память ------------------------
void* ely_alloc(size_t size);
void  ely_free(void* ptr);

// ------------------------ JSON парсинг ------------------------
dict* ely_dictify(char* json);

// ------------------------ Обёртки для массивов (ely_value*) ------------------------
void ely_array_push(ely_value* arr, ely_value* elem);
ely_value* ely_array_pop(ely_value* arr);
size_t ely_array_len(ely_value* arr);
ely_value* ely_array_get(ely_value* arr, size_t index);
void ely_array_set(ely_value* arr, size_t index, ely_value* elem);
void ely_array_insert(ely_value* arr, size_t index, ely_value* elem);
int ely_array_remove_value(ely_value* arr, ely_value* value);
int ely_array_remove_index(ely_value* arr, size_t index);
int ely_array_index(ely_value* arr, ely_value* value);

// ------------------------ Обёртки для словарей (ely_value*) ------------------------
ely_value* ely_dict_get(ely_value* dict, ely_value* key);
void ely_dict_set(ely_value* dict, ely_value* key, ely_value* value);
void ely_dict_del(ely_value* dict, ely_value* key);
int ely_dict_has(ely_value* dict, ely_value* key);
ely_value* ely_dict_keys(ely_value* dict);
char* ely_array_to_json(ely_value* arr);
char* ely_dict_to_json(ely_value* dict);

// Совместимость со старыми именами (временные)
void del(ely_value* dict, char* key);
int has(ely_value* dict, char* key);
ely_value* keys(ely_value* dict);
char* toJson(ely_value* dict);

// other
ely_bool isType(ely_value* value, const char* type_name);
ely_bool isNull(ely_value* value);
ely_bool isIn(ely_value* value, arr* in);

// ------------------------ Рефлексия ------------------------
char* ely_typeof(ely_value* v);
ely_value* ely_value_get_fields(ely_value* v);
ely_value* ely_value_get_methods(ely_value* v);
ely_value* ely_value_call_method(ely_value* obj, const char* method_name, ely_value** args, int argc);
ely_value* ely_value_new_function(void* func_ptr);
void ely_value_set_method(ely_value* obj, const char* name, void* func_ptr);

long long ely_value_as_int(ely_value* v);
double ely_value_as_double(ely_value* v);

/* ------------------------ Расширенное время ------------------------ */
long long ely_time_now_ms(void);
char* ely_format_time(long long seconds, const char* fmt);
long long ely_parse_time(const char* str, const char* fmt);

/* ------------------------ Случайные числа ------------------------ */
ely_int ely_rand_int(void);
ely_int ely_rand_int_range(ely_int min, ely_int max);
ely_bool ely_rand_bool(void);

#ifdef __cplusplus
}
#endif

#endif