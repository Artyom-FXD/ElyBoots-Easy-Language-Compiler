#ifndef ELY_RUNTIME_H
#define ELY_RUNTIME_H

#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>

#include "collections.h"
#include "ely_gc.h"
#include "ely_value.h"

// Сигнатуры функциональных типов для коллекций
typedef unsigned int (*dict_hash_func)(ely_value);
typedef int (*dict_cmp_func)(ely_value, ely_value);

typedef struct ely_class ely_class;
struct ely_class {
    const char* name;
    ely_class* parent;
    void* vtable;
};

typedef struct {
    const char* name;
    int field_count;
    const char** field_names;
    const char** field_types;
} ely_class_info;

#ifndef ELY_GC_OBJ_TYPES_DEFINED
#define ELY_GC_OBJ_TYPES_DEFINED
typedef enum ElyGCObjType {
    GC_OBJ_VALUE,
    GC_OBJ_ARR,
    GC_OBJ_DICT,
    GC_OBJ_STRING,
} gc_obj_type_t;
#endif

#ifdef __cplusplus
extern "C" {
#endif

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

static inline uint64_t ely_box_float(float f) {
    uint32_t bits;
    memcpy(&bits, &f, sizeof(float));
    return ((uint64_t)bits << 32) | 0x4ULL;
}

static inline float ely_unbox_float(uint64_t v) {
    uint32_t bits = (uint32_t)(v >> 32);
    float f;
    memcpy(&f, &bits, sizeof(float));
    return f;
}

char* ely_value_to_json(ely_value v);
ely_value ely_value_from_json(const char* json, size_t* pos);
char* ely_value_to_string(ely_value v);

void ely_print_int(ely_value v);
void ely_print_byte(ely_value v);
void ely_print_char(ely_value v);
void ely_print_bool(ely_value v);
void ely_print_double(ely_value v);
void ely_println_str(const char* str); // Изменено на const char* для соответствия virtual_main.cpp

ely_str ely_input(void);
ely_str ely_input_prompt(const char* prompt);

ely_int    ely_str_to_int(const char* str);
ely_uint   ely_str_to_uint(const char* str);
ely_more   ely_str_to_more(const char* str);
ely_umore  ely_str_to_umore(const char* str);
ely_flt    ely_str_to_flt(const char* str);
ely_double ely_str_to_double(const char* str);

ely_str ely_int_to_str(ely_int n);
ely_str ely_uint_to_str(ely_uint n);
ely_str ely_more_to_str(ely_more n);
ely_str ely_umore_to_str(ely_umore n);
ely_str ely_flt_to_str(ely_flt f);
ely_str ely_double_to_str(ely_double d);
ely_str ely_bool_to_str(ely_bool b);

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

void        ely_srand(ely_uint seed);
ely_int     ely_rand(void);
ely_double  ely_rand_double(void);

void        ely_sleep(ely_uint milliseconds);
ely_more    ely_time_now(void);
double      ely_time_diff(ely_more start, ely_more end);

typedef struct ely_file ely_file;
ely_file*  ely_file_open(const char* path, const char* mode);
void       ely_file_close(ely_file* f);
int        ely_file_write(ely_file* f, const char* data, size_t len);
char*      ely_file_read(ely_file* f, size_t* out_len);
int        ely_file_exists(const char* path);
char*      ely_file_read_all(const char* path, size_t* out_len);
int        ely_file_remove(const char* path);
int        ely_file_rename(const char* old, const char* new_path);
int        ely_file_write_all(const char* path, const char* data, size_t len);
int        ely_file_write_all_simple(const char* path, const char* data);
char*      ely_file_read_all_simple(const char* path);

ely_str ely_path_join(const char* a, const char* b);
ely_str ely_path_basename(const char* path);
ely_str ely_path_dirname(const char* path);
int      ely_path_is_absolute(const char* path);

void* ely_load_library(const char* path);
void* ely_get_function(void* lib, const char* name);
void  ely_close_library(void* lib);

dict* ely_dictify(const char* json);

void ely_array_push(ely_value arr, ely_value elem);
ely_value ely_array_pop(ely_value arr);
size_t ely_array_len(ely_value arr);
ely_value ely_array_get(ely_value arr, size_t index);
void ely_array_set(ely_value arr, size_t index, ely_value elem);

unsigned int ely_dict_str_hash(ely_value val);
int ely_dict_str_cmp(ely_value a, ely_value b);

ely_value ely_dict_get(ely_value dict, ely_value key);
void ely_dict_set(ely_value dict, ely_value key, ely_value value);
void ely_dict_del(ely_value dict, ely_value key);
char* ely_array_to_json(ely_value arr_val);

void del(ely_value dict, char* key);
int has(ely_value dict, char* key);
ely_value keys(ely_value dict);
char* toJson(ely_value dict);

ely_bool isType(ely_value value, const char* type_name);
ely_bool isNull(ely_value value);
ely_bool isIn(ely_value value, arr* in);

const char* ely_typeof(ely_value v);
ely_value ely_value_get_fields(ely_value v);
ely_value ely_value_get_methods(ely_value v);
ely_value ely_value_call_method(ely_value obj, const char* method_name, ely_value* args, int argc);

void ely_chdir_to_exe_dir(void);

long long ely_time_now_ms(void);
ely_value ely_format_time(ely_value seconds_val, ely_value fmt_val);
long long ely_parse_time(const char* str, const char* fmt);

ely_int     ely_rand_int(void);
ely_int     ely_rand_int_range(ely_int min, ely_int max);
ely_bool    ely_rand_bool(void);

ely_value ely_make_arr(ely_value elem);
ely_value ely_dyn_arr(ely_value elem);
void ely_immediate_str_get_chars(ely_value val, char* out_buf);

#endif