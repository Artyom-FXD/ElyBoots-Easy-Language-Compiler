#ifndef ely_RUNTIME_H
#define ely_RUNTIME_H

#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>
typedef uint64_t ely_value;

#include "collections.h"
#include "ely_gc.h"

/* ============================================================================
 * Ely-boxing (ExBoxing + Float Self-Tagging)
 * ============================================================================ */
#pragma once
#include <stdint.h>
#include <string.h>

#define ELY_TAG_MASK          0x7ULL

// Основные теги (Младшие 3 бита)
#define ELY_TAG_PTR           0x0ULL  // 000 - Прямой указатель на кучу (Выровнен по 8 байт)
#define ELY_TAG_INT           0x1ULL  // 001 - Маленькое целое число (Smi / Fixnum, 61 бит)
#define ELY_TAG_STR0          0x2ULL  // 010 - Immediate-строка (Длина до 7 байт прямо в значении)
#define ELY_TAG_SPECIAL       0x3ULL  // 011 - Константы и мелкие типы (Bool, Null, Char, Byte)
// Теги 100, 101, 110, 111 (Бит 2 выставлен в 1) монопольно заняты под нативные Float (flt)

#define ELY_STR_LEN_SHIFT     3
#define ELY_STR_LEN_MASK      0x7ULL
#define ELY_STR_DATA_SHIFT    6

// Подтеги для ELY_TAG_SPECIAL (Биты 3-7)
#define ELY_SUBTAG_MASK       (0x1FULL << 3)
#define ELY_SUBTAG_BOOL       (0x00ULL << 3)
#define ELY_SUBTAG_NULL       (0x01ULL << 3)
#define ELY_SUBTAG_UNDEFINED  (0x02ULL << 3)
#define ELY_SUBTAG_CHAR       (0x03ULL << 3)
#define ELY_SUBTAG_BYTE       (0x04ULL << 3)

// Фиксированные константы рантайм-значений
#define ELY_VAL_FALSE         (ELY_TAG_SPECIAL | ELY_SUBTAG_BOOL | (0ULL << 8))
#define ELY_VAL_TRUE          (ELY_TAG_SPECIAL | ELY_SUBTAG_BOOL | (1ULL << 8))
#define ELY_VAL_NULL          (ELY_TAG_SPECIAL | ELY_SUBTAG_NULL)
#define ELY_VAL_UNDEFINED     (ELY_TAG_SPECIAL | ELY_SUBTAG_UNDEFINED)

/* ============================================================================
 * Предикаты типов (Быстрые проверки за 1 такт)
 * ============================================================================ */

// Если в младших 3 битах выставлен бит 2 (0x4), то это гарантированно Float
#define ELY_IS_FLOAT(v)       (((v) & 0x4ULL) != 0)

// Для остальных типов маска 0x7 работает идеально, т.к. у Float там будет 4,5,6 или 7
#define ELY_IS_PTR(v)         (((v) & ELY_TAG_MASK) == ELY_TAG_PTR)
#define ELY_IS_INT(v)         (((v) & ELY_TAG_MASK) == ELY_TAG_INT)
#define ELY_IS_STR0(v)        (((v) & ELY_TAG_MASK) == ELY_TAG_STR0)
#define ELY_IS_SPECIAL(v)     (((v) & ELY_TAG_MASK) == ELY_TAG_SPECIAL)

#define ELY_IS_BOOL(v)        (ELY_IS_SPECIAL(v) && (((v) & ELY_SUBTAG_MASK) == ELY_SUBTAG_BOOL))
#define ELY_IS_NULL(v)        ((v) == ELY_VAL_NULL)

/* ============================================================================
 * Распаковка / Unboxing (Безопасное извлечение payload)
 * ============================================================================ */

// Очищаем младшие 3 бита тега, восстанавливая чистый выровненный 64-битный адрес кучи
#define ELY_UNBOX_PTR(v)      ((void*)((v) & ~ELY_TAG_MASK))

// Если Fixnum сдвинут влево на 3 бита, то арифметический сдвиг вправо полностью сохранит знак
#define ELY_UNBOX_INT(v)      (((int64_t)(v)) >> 3)

/* ============================================================================
 * Помощники для твоих нативных flt (Float Self-Tagging)
 * ============================================================================ */

// Упаковка 32-bit float в верхнюю половину 64-бит, выставляя бит 2 в единицу (0x4)
inline uint64_t ely_box_float(float f) {
    uint32_t bits;
    memcpy(&bits, &f, sizeof(float));
    return ((uint64_t)bits << 32) | 0x4ULL;
}

// Распаковка обратно в честный float
inline float ely_unbox_float(uint64_t v) {
    uint32_t bits = (uint32_t)(v >> 32);
    float f;
    memcpy(&f, &bits, sizeof(float));
    return f;
}
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
enum ElyGCObjType {
    GC_OBJ_VALUE,
    GC_OBJ_ARR,
    GC_OBJ_DICT,
    GC_OBJ_STRING,
};
#endif

typedef enum {
    ely_VALUE_NULL = 0,
    ely_VALUE_BOOL,
    ely_VALUE_INT,
    ely_VALUE_DOUBLE,
    ely_VALUE_STRING,
    ely_VALUE_ARRAY,
    ely_VALUE_OBJECT,
    ely_VALUE_FUNCTION, // <-- Тот самый потерявшийся тип для рефлексии и методов
    ely_VALUE_UNKNOWN
} ely_type;

ely_class_info* ely_get_class_info(const char* name);

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

/* ============================================================================
 * Предикаты типов (Type Checking)
 * ============================================================================ */

inline int ely_get_type(ely_value v);

static inline bool ely_is_ptr(ely_value v) {
    // Если младшие 3 бита равны 000 и это не чистый ноль — это указатель Клетки
    return (v & ELY_TAG_MASK) == ELY_TAG_PTR && v != 0;
}

static inline bool ely_is_int(ely_value v) {
    return (v & ELY_TAG_MASK) == ELY_TAG_INT;
}

static inline bool ely_is_double(ely_value v) {
    // Быстрая проверка: если горит бит 2, это инлайновый double.
    // (Если бит не горит, double лежит в куче как объект, проверится через ely_is_ptr)
    return (v & 0x4ULL) != 0;
}

static inline bool ely_is_bool(ely_value v) {
    return (v == ELY_VAL_TRUE || v == ELY_VAL_FALSE);
}

static inline bool ely_is_null(ely_value v) {
    return v == ELY_VAL_NULL;
}

static inline bool ely_is_char(ely_value v) {
    return (v & ELY_TAG_MASK) == ELY_TAG_SPECIAL && (v & ELY_SUBTAG_MASK) == ELY_SUBTAG_CHAR;
}

static inline bool ely_is_byte(ely_value v) {
    return (v & ELY_TAG_MASK) == ELY_TAG_SPECIAL && (v & ELY_SUBTAG_MASK) == ELY_SUBTAG_BYTE;
}

/* ============================================================================
 * Инлайн-функции упаковки (Boxing)
 * ============================================================================ */

static inline ely_value ely_box_ptr(void* p) {
    // В силу 8-байтового выравнивания, младшие биты адреса уже равны 000
    return (ely_value)(p);
}

static inline ely_value ely_box_int(int64_t i) {
    // Сдвигаем число на 3 бита влево, освобождая место под тег 001
    return (((ely_value)i) << 3) | ELY_TAG_INT;
}

// Прототип функции медленного пути для экстремальных Double (будет реализован в ely_runtime.c)
ely_value ely_value_new_double_boxed(double d);

static inline ely_value ely_box_double(double d) {
    union { double d; uint64_t u; } cast;
    cast.d = d;
    // Если бит 2 равен 1, число безопасно встраивается в архитектуру (Fast Path)
    if ((cast.u & 0x4ULL) != 0) {
        return cast.u;
    }
    // Если бит 2 равен 0 (коллизия с тегами), пакуем число в кучу (Slow Path)
    return ely_value_new_double_boxed(d);
}

static inline ely_value ely_box_bool(bool b) {
    return b ? ELY_VAL_TRUE : ELY_VAL_FALSE;
}

static inline ely_value ely_box_null(void) {
    return ELY_VAL_NULL;
}

static inline ely_value ely_box_char(char c) {
    return ELY_TAG_SPECIAL | ELY_SUBTAG_CHAR | ((ely_value)(uint8_t)c << 8);
}

static inline ely_value ely_box_byte(uint8_t b) {
    return ELY_TAG_SPECIAL | ELY_SUBTAG_BYTE | ((ely_value)b << 8);
}

/* ============================================================================
 * Инлайн-функции распаковки (Unboxing)
 * ============================================================================ */

static inline void* ely_unbox_ptr(ely_value v) {
    // Маска больше не нужна! Т.к. тег равен 000, значение v — это и есть чистый адрес
    return (void*)(v);
}

static inline int64_t ely_unbox_int(ely_value v) {
    // Арифметический сдвиг вправо (знаковый) автоматически восстанавливает 
    // отрицательные числа. Никаких ручных масок знака!
    return ((int64_t)v) >> 3;
}

// Прототип функции медленного пути для распаковки Double из кучи
double ely_value_as_double_slow(ely_value v);

static inline double ely_unbox_double(ely_value v) {
    union { uint64_t u; double d; } cast;
    cast.u = v;
    return cast.d;
}

static inline bool ely_unbox_bool(ely_value v) {
    return v == ELY_VAL_TRUE;
}

static inline char ely_unbox_char(ely_value v) {
    return (char)(v >> 8);
}

static inline uint8_t ely_unbox_byte(ely_value v) {
    return (uint8_t)(v >> 8);
}

/* Внедряем в блок инлайнов ely_runtime.h */

static inline ely_value ely_box_inline_str(const char* s, size_t len) {
    // Записываем тег строки 010 и сдвинутую длину в биты 3-5
    ely_value v = ELY_TAG_STR0 | (len << 3);
    
    // Побайтово копируем строку в старшие биты, начиная с 6 бита
    for (size_t i = 0; i < len; i++) {
        v |= ((ely_value)(uint8_t)s[i]) << (6 + (i * 8));
    }
    return v;
}

static inline void ely_unbox_inline_str(ely_value v, char* buf) {
    size_t len = (v >> 3) & 0x7ULL; // Извлекаем длину из бит 3-5
    
    for (size_t i = 0; i < len; i++) {
        buf[i] = (char)((v >> (6 + (i * 8))) & 0xFFULL);
    }
    buf[len] = '\0'; // Гарантируем null-терминатор для Си-функций
}

/* ============================================================================
 * SSO
 * ============================================================================ */
inline bool ely_is_immediate_str(ely_value val) {
    return (val & ELY_TAG_MASK) == ELY_TAG_STR0;
}

// Упаковка сырой C-строки в immediate ely_value
ely_value ely_immediate_str_encode(const char* str, size_t len);

// Извлечение длины
inline size_t ely_immediate_str_len(ely_value val) {
    return (val >> ELY_STR_LEN_SHIFT) & ELY_STR_LEN_MASK;
}

// Извлечение символов во временный буфер
void ely_immediate_str_get_chars(ely_value val, char* out_buf);


/* ============================================================================
 * Сигнатуры стандартных функций рантайма (Передача по значению)
 * ============================================================================ */
ely_value ely_to_int(ely_value v);
ely_value ely_to_double(ely_value v);
ely_value ely_to_string(ely_value v);

// Конструкторы объектов Ely (Возвращают упакованное значение прямо в регистре RAX)
ely_value ely_value_new_null(void);
ely_value ely_value_new_bool(int b);
ely_value ely_value_new_int(long long i);
ely_value ely_value_new_double(double d);
ely_value ely_value_new_string(const char* s);
ely_value ely_value_new_array(arr* a);
ely_value ely_value_new_object(dict* d);

// Интерфейс работы с динамическими объектами
int ely_value_as_bool(ely_value v);
ely_value ely_value_index(ely_value v, ely_value index);
ely_value ely_value_get_key(ely_value v, const char* key);
void ely_value_set_key(ely_value v, const char* key, ely_value value);
void ely_value_set_index(ely_value v, ely_value index, ely_value value);
char* ely_value_to_json(ely_value v);
ely_value ely_value_from_json(const char* json, size_t* pos);
char* ely_value_to_string(ely_value v);

// Математическое ядро рантайма
ely_value ely_value_add(ely_value a, ely_value b);
ely_value ely_value_sub(ely_value a, ely_value b);
ely_value ely_value_mul(ely_value a, ely_value b);
ely_value ely_value_div(ely_value a, ely_value b);
ely_value ely_value_mod(ely_value a, ely_value b);
ely_value ely_value_eq(ely_value a, ely_value b);
ely_value ely_value_ne(ely_value a, ely_value b);
ely_value ely_value_lt(ely_value a, ely_value b);
ely_value ely_value_le(ely_value a, ely_value b);
ely_value ely_value_gt(ely_value a, ely_value b);
ely_value ely_value_ge(ely_value a, ely_value b);
ely_value ely_value_and(ely_value a, ely_value b);
ely_value ely_value_or(ely_value a, ely_value b);
ely_value ely_value_not(ely_value a);
ely_value ely_value_neg(ely_value a);

// ------------------------ Консоль ------------------------
void ely_print_int(ely_value v);
void ely_print_byte(ely_value v);
void ely_print_char(ely_value v);
void ely_print_bool(ely_value v);
void ely_print_double(ely_value v);
void ely_println_str(ely_value v);

ely_str ely_input(void);
ely_str ely_input_prompt(const char* prompt);

// ------------------------ Преобразования ------------------------
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

// ------------------------ Строки ------------------------
size_t      ely_str_len(const char* str);
ely_str     ely_str_dup(const char* str);
ely_str     ely_str_concat(const char* a, const char* b);
int         ely_str_cmp(const char* a, const char* b);
ely_str     ely_str_substr(const char* str, size_t start, size_t len);
ely_str     ely_str_trim(const char* str);
ely_str     ely_str_replace(const char* str, const char* old, const char* new_str);

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

// ------------------------ Пути ------------------------
ely_str ely_path_join(const char* a, const char* b);
ely_str ely_path_basename(const char* path);
ely_str ely_path_dirname(const char* path);
int      ely_path_is_absolute(const char* path);

// ------------------------ Динамические библиотеки ------------------------
void* ely_load_library(const char* path);
void* ely_get_function(void* lib, const char* name);
void  ely_close_library(void* lib);
int   ely_call_int_int(void* func, int a, int b);
double ely_call_double_double(void* func, double a);
double ely_call_double_double_double(void* func, double a, double b);
char* ely_call_str_void(void* func);

// ------------------------ Память ------------------------
void* ely_alloc(size_t size);
void  ely_free(void* ptr);

// ------------------------ JSON парсинг ------------------------
dict* ely_dictify(const char* json);

// ------------------------ Обёртки для массивов (ely_value) ------------------------
void ely_array_push(ely_value arr, ely_value elem);
ely_value ely_array_pop(ely_value arr);
size_t ely_array_len(ely_value arr);
ely_value ely_array_get(ely_value arr, size_t index);
void ely_array_set(ely_value arr, size_t index, ely_value elem);
void ely_array_insert(ely_value arr, size_t index, ely_value elem);
int ely_array_remove_value(ely_value arr, ely_value value);
int ely_array_remove_index(ely_value arr, size_t index);
int ely_array_index(ely_value arr, ely_value value);

// ------------------------ Обёртки для словарей (ely_value) ------------------------
ely_value ely_dict_get(ely_value dict, ely_value key);
void ely_dict_set(ely_value dict, ely_value key, ely_value value);
void ely_dict_del(ely_value dict, ely_value key);
int ely_dict_has(ely_value dict, ely_value key);
ely_value ely_dict_keys(ely_value dict);
char* ely_array_to_json(ely_value arr);
char* ely_dict_to_json(ely_value dict);

// Совместимость со старыми именами (временные)
void del(ely_value dict, char* key);
int has(ely_value dict, char* key);
ely_value keys(ely_value dict);
char* toJson(ely_value dict);

// other
ely_bool isType(ely_value value, const char* type_name);
ely_bool isNull(ely_value value);
ely_bool isIn(ely_value value, arr* in);

// ------------------------ Рефлексия ------------------------
char* ely_typeof(ely_value v);
ely_value ely_value_get_fields(ely_value v);
ely_value ely_value_get_methods(ely_value v);
ely_value ely_value_call_method(ely_value obj, const char* method_name, ely_value* args, int argc); // args теперь массив из ely_value (одна звездочка)
ely_value ely_value_new_function(void* func_ptr);
void ely_value_set_method(ely_value obj, const char* name, void* func_ptr);

long long ely_value_as_int(ely_value v);
double ely_value_as_double(ely_value v);

void ely_chdir_to_exe_dir(void);

/* ------------------------ Расширенное время ------------------------ */
long long ely_time_now_ms(void);
ely_value* ely_format_time(ely_value* seconds_val, ely_value* fmt_val);
long long ely_parse_time(const char* str, const char* fmt);

/* ------------------------ Случайные числа ------------------------ */
ely_int ely_rand_int(void);
ely_int ely_rand_int_range(ely_int min, ely_int max);
ely_bool ely_rand_bool(void);

ely_value* ely_make_arr(ely_value* elem);
ely_value* ely_dyn_arr(ely_value* elem);

#ifdef __cplusplus
}
#endif

#endif