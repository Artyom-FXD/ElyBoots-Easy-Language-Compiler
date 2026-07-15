#include "ely_runtime.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "ely_value.h"

typedef struct {
    double value;
} ely_boxed_double_t;

#ifndef ELY_VALUES_ENUM_DEFINED
#define ELY_VALUES_ENUM_DEFINED
typedef enum ElyValuesEnum {
    ely_VALUE_NULL,
    ely_VALUE_BOOL,
    ely_VALUE_INT,
    ely_VALUE_DOUBLE,
    ely_VALUE_STRING,
    ely_VALUE_ARRAY,
    ely_VALUE_OBJECT
};
#endif

#ifndef ELY_GC_OBJ_TYPES_DEFINED
#define ELY_GC_OBJ_TYPES_DEFINED
typedef enum ElyGCObjType {
    GC_OBJ_VALUE,       /**< ely_value* – содержит указатели на другие объекты */
    GC_OBJ_ARR,         /**< arr* – массив указателей на ely_value */
    GC_OBJ_DICT,        /**< dict* – словарь с ключами и значениями */
    GC_OBJ_STRING,      /**< char* – строка (не содержит указателей) */
    GC_OBJ_DOUBLE
} gc_obj_type_t;
#endif

/* ===========================================================================
 *  Ядро Диспетчеризации Типов (Ely-Boxing)
 * =========================================================================== */

ely_value ely_value_new_double_boxed(double d) {
    ely_boxed_double_t* obj = (ely_boxed_double_t*)gc_alloc(sizeof(ely_boxed_double_t), GC_OBJ_VALUE);
    if (!obj) {
        fprintf(stderr, "Fatal: Out of memory while boxing double.\n");
        abort();
    }
    obj->value = d;
    return ely_box_ptr(obj);
}

double ely_value_as_double_slow(ely_value v) {
    ely_boxed_double_t* obj = (ely_boxed_double_t*)ELY_UNBOX_PTR(v);
    return obj->value;
}

/* ===========================================================================
 *  Конструкторы Значений
 * =========================================================================== */
ely_value ely_value_new_null(void) { return ELY_VAL_NULL; }
ely_value ely_value_new_bool(int val) { return val ? ELY_VAL_TRUE : ELY_VAL_FALSE; }
ely_value ely_value_new_int(long long val) { return ely_box_int(val); }
ely_value ely_value_new_double(double val) { return ely_box_double(val); }

ely_value ely_value_new_array(arr* a) { return ELY_TAG_PTR | ((uint64_t)a); }
ely_value ely_value_new_object(dict* d) { return ELY_TAG_PTR | ((uint64_t)d); }

ely_value ely_value_new_string(const char* s) {
    if (!s) return ELY_VAL_NULL;
    size_t len = strlen(s);
    if (len <= 7) return ely_box_inline_str(s, len);
    
    char* heap_str = (char*)gc_alloc(len + 1, GC_OBJ_STRING); 
    if (!heap_str) {
        fprintf(stderr, "Fatal: Out of memory while allocating string.\n");
        abort();
    }
    memcpy(heap_str, s, len + 1);
    return ely_box_ptr(heap_str);
}

/* ===========================================================================
 *  Арифметика и Базовые Операции
 * =========================================================================== */
int ely_value_as_bool(ely_value v) {
    switch (ely_get_type(v)) {
        case ely_VALUE_BOOL:   return ely_unbox_bool(v);
        case ely_VALUE_INT:    return ely_unbox_int(v) != 0;
        case ely_VALUE_DOUBLE: return ely_unbox_double(v) != 0.0;
        case ely_VALUE_STRING: {
            if (ely_is_immediate_str(v)) return ely_immediate_str_len(v) > 0;
            const char* s = (const char*)ely_unbox_ptr(v);
            return s && *s != '\0';
        }
        default:               return 0;
    }
}

ely_value ely_value_add(ely_value a, ely_value b) {
    if (ELY_IS_INT(a) && ELY_IS_INT(b)) {
        return a + b - 1; 
    }
    if (ELY_IS_FLOAT(a) && ELY_IS_FLOAT(b)) {
        union { ely_value u; double d; } va, vb, vres;
        va.u = a; vb.u = b;
        vres.d = va.d + vb.d;
        if (ELY_IS_FLOAT(vres.u)) return vres.u;
        return ely_value_new_double_boxed(vres.d);
    }
    int type_a = ely_get_type(a);
    int type_b = ely_get_type(b);
    if ((type_a == ely_VALUE_INT || type_a == ely_VALUE_DOUBLE) &&
        (type_b == ely_VALUE_INT || type_b == ely_VALUE_DOUBLE)) {
        double da = (type_a == ely_VALUE_INT) ? (double)ely_unbox_int(a) : ely_unbox_double(a);
        double db = (type_b == ely_VALUE_INT) ? (double)ely_unbox_int(b) : ely_unbox_double(b);
        return ely_box_double(da + db);
    }
    return ely_box_int(0);
}

ely_value ely_value_sub(ely_value a, ely_value b) {
    if (ELY_IS_INT(a) && ELY_IS_INT(b)) {
        return a - b + 1;
    }
    int type_a = ely_get_type(a);
    int type_b = ely_get_type(b);
    if ((type_a == ely_VALUE_INT || type_a == ely_VALUE_DOUBLE) &&
        (type_b == ely_VALUE_INT || type_b == ely_VALUE_DOUBLE)) {
        double da = (type_a == ely_VALUE_INT) ? (double)ely_unbox_int(a) : ely_unbox_double(a);
        double db = (type_b == ely_VALUE_INT) ? (double)ely_unbox_int(b) : ely_unbox_double(b);
        return ely_box_double(da - db);
    }
    return ely_box_int(0);
}

ely_value ely_value_mul(ely_value a, ely_value b) {
    int type_a = ely_get_type(a);
    int type_b = ely_get_type(b);
    if (type_a == ely_VALUE_INT && type_b == ely_VALUE_INT) {
        return ely_box_int(ely_unbox_int(a) * ely_unbox_int(b));
    }
    if ((type_a == ely_VALUE_INT || type_a == ely_VALUE_DOUBLE) &&
        (type_b == ely_VALUE_INT || type_b == ely_VALUE_DOUBLE)) {
        double da = (type_a == ely_VALUE_INT) ? (double)ely_unbox_int(a) : ely_unbox_double(a);
        double db = (type_b == ely_VALUE_INT) ? (double)ely_unbox_int(b) : ely_unbox_double(b);
        return ely_box_double(da * db);
    }
    return ely_box_int(0);
}

ely_value ely_value_div(ely_value a, ely_value b) {
    int type_a = ely_get_type(a);
    int type_b = ely_get_type(b);
    if ((type_a == ely_VALUE_INT || type_a == ely_VALUE_DOUBLE) &&
        (type_b == ely_VALUE_INT || type_b == ely_VALUE_DOUBLE)) {
        double da = (type_a == ely_VALUE_INT) ? (double)ely_unbox_int(a) : ely_unbox_double(a);
        double db = (type_b == ely_VALUE_INT) ? (double)ely_unbox_int(b) : ely_unbox_double(b);
        if (db == 0.0) return ELY_VAL_NULL;
        return ely_box_double(da / db);
    }
    return ELY_VAL_NULL;
}

ely_value ely_value_mod(ely_value a, ely_value b) {
    if (ely_get_type(a) == ely_VALUE_INT && ely_get_type(b) == ely_VALUE_INT) {
        long long bv = ely_unbox_int(b);
        if (bv == 0) return ELY_VAL_NULL;
        return ely_box_int(ely_unbox_int(a) % bv);
    }
    return ELY_VAL_NULL;
}

ely_value ely_value_eq(ely_value a, ely_value b) {
    if (a == b) return ELY_VAL_TRUE;
    
    int type_a = ely_get_type(a);
    int type_b = ely_get_type(b);
    if (type_a != type_b) return ELY_VAL_FALSE;
    
    if (type_a == ely_VALUE_STRING) {
        char buf_a[64], buf_b[64];
        const char* sa = ely_is_immediate_str(a) ? (ely_unbox_inline_str(a, buf_a), buf_a) : (const char*)ely_unbox_ptr(a);
        const char* sb = ely_is_immediate_str(b) ? (ely_unbox_inline_str(b, buf_b), buf_b) : (const char*)ely_unbox_ptr(b);
        return strcmp(sa, sb) == 0 ? ELY_VAL_TRUE : ELY_VAL_FALSE;
    }
    return ELY_VAL_FALSE;
}

ely_value ely_value_ne(ely_value a, ely_value b) {
    return ely_value_eq(a, b) == ELY_VAL_TRUE ? ELY_VAL_FALSE : ELY_VAL_TRUE;
}

ely_value ely_value_lt(ely_value a, ely_value b) {
    int type_a = ely_get_type(a);
    int type_b = ely_get_type(b);
    if ((type_a == ely_VALUE_INT || type_a == ely_VALUE_DOUBLE) &&
        (type_b == ely_VALUE_INT || type_b == ely_VALUE_DOUBLE)) {
        double da = (type_a == ely_VALUE_INT) ? (double)ely_unbox_int(a) : ely_unbox_double(a);
        double db = (type_b == ely_VALUE_INT) ? (double)ely_unbox_int(b) : ely_unbox_double(b);
        return ely_box_bool(da < db);
    }
    return ELY_VAL_FALSE;
}

ely_value ely_value_le(ely_value a, ely_value b) { return ely_box_bool(ely_value_lt(a, b) == ELY_VAL_TRUE || ely_value_eq(a, b) == ELY_VAL_TRUE); }
ely_value ely_value_gt(ely_value a, ely_value b) { return ely_box_bool(ely_value_lt(b, a) == ELY_VAL_TRUE); }
ely_value ely_value_ge(ely_value a, ely_value b) { return ely_box_bool(ely_value_lt(a, b) == ELY_VAL_FALSE); }
ely_value ely_value_and(ely_value a, ely_value b) { return ely_box_bool(ely_value_as_bool(a) && ely_value_as_bool(b)); }
ely_value ely_value_or(ely_value a, ely_value b) { return ely_box_bool(ely_value_as_bool(a) || ely_value_as_bool(b)); }
ely_value ely_value_not(ely_value a) { return ely_box_bool(!ely_value_as_bool(a)); }

ely_value ely_value_neg(ely_value a) {
    int type = ely_get_type(a);
    if (type == ely_VALUE_INT) return ely_box_int(-ely_unbox_int(a));
    if (type == ely_VALUE_DOUBLE) return ely_box_double(-ely_unbox_double(a));
    return ELY_VAL_NULL;
}

/* ===========================================================================
 *  Индексация Списков и Словариков
 * =========================================================================== */
ely_value ely_value_index(ely_value v, ely_value index) {
    int v_type = ely_get_type(v);
    int idx_type = ely_get_type(index);

    if (v_type == ely_VALUE_ARRAY && idx_type == ely_VALUE_INT) {
        size_t i = (size_t)ely_unbox_int(index);
        arr* a = (arr*)ely_unbox_ptr(v);
        if (i < arr_len(a)) return arr_get(a, i);
    } else if (v_type == ely_VALUE_OBJECT && idx_type == ely_VALUE_STRING) {
        dict* d = (dict*)ely_unbox_ptr(v);
        char buf[64];
        const char* k = ely_is_immediate_str(index) ? (ely_unbox_inline_str(index, buf), buf) : (const char*)ely_unbox_ptr(index);
        return dict_get_str(d, k);
    }
    return ELY_VAL_NULL;
}

ely_value ely_value_get_key(ely_value v, const char* key) {
    if (ely_get_type(v) != ely_VALUE_OBJECT) return ELY_VAL_NULL;
    return dict_get_str((dict*)ely_unbox_ptr(v), key);
}

void ely_value_set_key(ely_value v, const char* key, ely_value value) {
    if (ely_get_type(v) == ely_VALUE_OBJECT) {
        dict_set_str((dict*)ely_unbox_ptr(v), key, value);
    }
}

void ely_value_set_index(ely_value v, ely_value index, ely_value value) {
    int v_type = ely_get_type(v);
    int idx_type = ely_get_type(index);

    if (v_type == ely_VALUE_ARRAY && idx_type == ely_VALUE_INT) {
        size_t i = (size_t)ely_unbox_int(index);
        arr* a = (arr*)ely_unbox_ptr(v);
        if (i < arr_len(a)) arr_set(a, i, value);
    } else if (v_type == ely_VALUE_OBJECT && idx_type == ely_VALUE_STRING) {
        dict* d = (dict*)ely_unbox_ptr(v);
        char buf[64];
        const char* k = ely_is_immediate_str(index) ? (ely_unbox_inline_str(index, buf), buf) : (const char*)ely_unbox_ptr(index);
        dict_set_str(d, k, value);
    }
}

/* ===========================================================================
 *  Внутренний маппинг для Хэш-Таблиц Garbage Collector
 * =========================================================================== */
unsigned int ely_dict_str_hash(ely_value val) {
    char buf[64];
    if (ely_is_immediate_str(val)) { ely_unbox_inline_str(val, buf); return ely_str_hash(buf); }
    if (ely_is_ptr(val)) {
        void* p = ely_unbox_ptr(val);
        if (get_heap_obj_type(p) == GC_OBJ_STRING) return ely_str_hash((const char*)p);
    }
    return 0;
}

int ely_dict_str_cmp(ely_value a, ely_value b) {
    char buf_a[64] = {0}, buf_b[64] = {0};
    const char* sa = ely_is_immediate_str(a) ? (ely_unbox_inline_str(a, buf_a), buf_a) : (const char*)ely_unbox_ptr(a);
    const char* sb = ely_is_immediate_str(b) ? (ely_unbox_inline_str(b, buf_b), buf_b) : (const char*)ely_unbox_ptr(b);
    return strcmp(sa ? sa : "", sb ? sb : "");
}