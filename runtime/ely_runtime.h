#ifndef ely_RUNTIME_H
#define ely_RUNTIME_H

#include <stddef.h>
#include <collections.h>

#ifdef __cplusplus
extern "C" {
#endif

int ely_file_write_all(char* path, char* data, size_t len);

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
ely_str    ely_str_dup(ely_str str);
ely_str    ely_str_concat(ely_str a, ely_str b);
int         ely_str_cmp(ely_str a, ely_str b);
ely_str    ely_str_substr(ely_str str, size_t start, size_t len);
ely_str    ely_str_trim(ely_str str);
ely_str    ely_str_replace(ely_str str, ely_str old, ely_str new);

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
ely_int    ely_rand(void);
ely_double ely_rand_double(void);

// ------------------------ Время ------------------------
void        ely_sleep(ely_uint milliseconds);
ely_more   ely_time_now(void);
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

// ------------------------ JSON для сложных типов ------------------------
ely_str ely_dict_to_json(ely_dict* dict);
ely_str ely_array_to_json(ely_array* arr);
ely_str ely_jsonify(ely_dict* dict);
ely_dict* ely_dictify(ely_str json);
ely_str ely_value_to_json(ely_value* v);          // убран const
ely_value* ely_value_from_json(char* json, size_t* pos); // убран const

// ------------------------ Методы массивов ------------------------
void* ely_array_pop_value(ely_array* arr);
size_t ely_array_len(ely_array* arr);
int ely_array_remove_value(ely_array* arr, void* value);
int ely_array_remove_index(ely_array* arr, size_t index);
int ely_array_insert(ely_array* arr, size_t index, void* elem);
int ely_array_index(ely_array* arr, void* value);

// ------------------------ DictServer API (с void*) ------------------------
void* load(char* path);
void save(void* host, char* path);
char* getStr(void* host, char* key);
int getInt(void* host, char* key);
int getBool(void* host, char* key);
double getDouble(void* host, char* key);
void* getObj(void* host, char* key);
void setStr(void* host, char* key, char* value);
void setInt(void* host, char* key, int value);
void setBool(void* host, char* key, int value);
void setDouble(void* host, char* key, double value);
void setObj(void* host, char* key, void* value);
void del(void* host, char* key);
int has(void* host, char* key);
ely_array* keys(void* host);
char* toJson(void* host);
void* parse(char* json);
void freeDict(void* host);

#ifdef __cplusplus
}
#endif

#endif