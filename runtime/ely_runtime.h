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

/* ===========================================================================
 *  Ядро Boxing / Unboxing для Double
 * =========================================================================== */
ely_value ely_value_new_double_boxed(double d);
double    ely_value_as_double_slow(ely_value v);

/* ===========================================================================
 *  Конструкторы Базовых Типов Данных
 * =========================================================================== */
ely_value ely_value_new_null(void);
ely_value ely_value_new_bool(int val);
ely_value ely_value_new_int(long long val);
ely_value ely_value_new_double(double val);
ely_value ely_value_new_array(arr* a);
ely_value ely_value_new_object(dict* d);
ely_value ely_value_new_string(const char* s);

/* ===========================================================================
 *  Системные Операторы и Логика Управления
 * =========================================================================== */
int       ely_value_as_bool(ely_value v);

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

/* ===========================================================================
 *  Низкоуровневая Индексация и Доступ к Структурам
 * =========================================================================== */
ely_value ely_value_index(ely_value v, ely_value index);
void      ely_value_set_index(ely_value v, ely_value index, ely_value value);

ely_value ely_value_get_key(ely_value v, const char* key);
void      ely_value_set_key(ely_value v, const char* key, ely_value value);

/* ===========================================================================
 *  Внутренний маппинг для Хэш-Таблиц Garbage Collector
 * =========================================================================== */
unsigned int ely_dict_str_hash(ely_value val);
int          ely_dict_str_cmp(ely_value a, ely_value b);

#ifdef __cplusplus
}
#endif

#endif