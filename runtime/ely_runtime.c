#include "ely_runtime.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <time.h>
#include <stdarg.h>
#include <ctype.h>

#ifdef _WIN32
#include <windows.h>
#else
#include <unistd.h>
#include <dlfcn.h>
#endif

//__attribute__((weak))
//ely_class_info* ely_get_class_info(const char* name) {
//    return NULL;
//}

#ifndef _WIN32
#define my_strtoll strtoll
#define my_strtoull strtoull
#else
static long long my_strtoll(const char *nptr, char **endptr, int base) {
    long long val = 0;
    int sign = 1;
    if (base == 0) {
        if (*nptr == '0') {
            if (nptr[1] == 'x' || nptr[1] == 'X') base = 16;
            else base = 8;
        } else base = 10;
    }
    while (*nptr == ' ' || *nptr == '\t') nptr++;
    if (*nptr == '-') { sign = -1; nptr++; }
    else if (*nptr == '+') nptr++;
    if (base == 16 && *nptr == '0' && (nptr[1] == 'x' || nptr[1] == 'X')) nptr += 2;
    while (*nptr) {
        int digit;
        if (*nptr >= '0' && *nptr <= '9') digit = *nptr - '0';
        else if (base == 16 && *nptr >= 'a' && *nptr <= 'f') digit = *nptr - 'a' + 10;
        else if (base == 16 && *nptr >= 'A' && *nptr <= 'F') digit = *nptr - 'A' + 10;
        else break;
        if (digit >= base) break;
        val = val * base + digit;
        nptr++;
    }
    if (endptr) *endptr = (char*)nptr;
    return sign * val;
}

static unsigned long long my_strtoull(const char *nptr, char **endptr, int base) {
    unsigned long long val = 0;
    if (base == 0) {
        if (*nptr == '0') {
            if (nptr[1] == 'x' || nptr[1] == 'X') base = 16;
            else base = 8;
        } else base = 10;
    }
    while (*nptr == ' ' || *nptr == '\t') nptr++;
    if (*nptr == '-') nptr++;
    else if (*nptr == '+') nptr++;
    if (base == 16 && *nptr == '0' && (nptr[1] == 'x' || nptr[1] == 'X')) nptr += 2;
    while (*nptr) {
        int digit;
        if (*nptr >= '0' && *nptr <= '9') digit = *nptr - '0';
        else if (base == 16 && *nptr >= 'a' && *nptr <= 'f') digit = *nptr - 'a' + 10;
        else if (base == 16 && *nptr >= 'A' && *nptr <= 'F') digit = *nptr - 'A' + 10;
        else break;
        if (digit >= base) break;
        val = val * base + digit;
        nptr++;
    }
    if (endptr) *endptr = (char*)nptr;
    return val;
}
#endif

typedef struct {
    double value;
} ely_boxed_double_t;

/* ===========================================================================
 *  Ely-boxing
 * =========================================================================== */

// Создание кучного double (Slow Path)
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
    ely_boxed_double_t* obj = (ely_boxed_double_t*)ely_unbox_ptr(v);
    return obj->value;
}

inline int ely_get_type(ely_value v) {
    uint64_t tag = v & ELY_TAG_MASK;
    if (v == ELY_TAG_NULL) return ely_VALUE_NULL;
    if (tag == ELY_TAG_INT) return ely_VALUE_INT;
    if (tag == ELY_TAG_BOOL) return ely_VALUE_BOOL;
    if (tag == ELY_TAG_STRING) return ely_VALUE_STRING;
    if (tag == ELY_TAG_PTR) {
        void* ptr = ELY_UNBOX_PTR(v);
        int gc_type = get_heap_obj_type(ptr);
        if (gc_type == GC_OBJ_ARR) return ely_VALUE_ARRAY;
        if (gc_type == GC_OBJ_DICT) return ely_VALUE_OBJECT;
    }
    return ely_VALUE_DOUBLE; // Float Self-Tagging: всё остальное — валидный double
}

// ------------------------ ely_value constructors ------------------------
ely_value ely_value_new_null(void) {
    return ELY_TAG_NULL;
}

ely_value ely_value_new_int(long long val) {
    return ELY_TAG_INT | (val & ELY_PAYLOAD_MASK);
}

ely_value ely_value_new_double(double val) {
    union { double d; uint64_t u; } cast;
    cast.d = val;
    if ((cast.u & 0x7FF0000000000000ULL) == 0x7FF0000000000000ULL && (cast.u & 0x000FFFFFFFFFFFFFULL) != 0) {
        return 0x7FF8000000000001ULL; 
    }
    return cast.u;
}

ely_value ely_value_new_bool(int val) {
    return ELY_TAG_BOOL | (val ? 1 : 0);
}

ely_value ely_value_new_array(arr* a) {
    return ELY_TAG_PTR | ((uint64_t)a & ELY_PAYLOAD_MASK);
}

ely_value ely_value_new_object(dict* d) {
    return ELY_TAG_PTR | ((uint64_t)d & ELY_PAYLOAD_MASK);
}

void ely_value_free(ely_value v) {
    int type = ely_get_type(v);
    void* ptr = ELY_UNBOX_PTR(v);
    if (!ptr) return;
    
    switch (type) {
        case ely_VALUE_ARRAY:  arr_free((arr*)ptr); break;
        case ely_VALUE_OBJECT: dict_free((dict*)ptr); break;
        default: break; 
    }
}

ely_value ely_value_from_json(const char* json, size_t* pos) {
    (void)pos;
    dict* d = ely_dictify(json);
    if (d) return ely_value_new_object(d);
    return ely_value_new_null();
}

ely_value ely_value_new_string(const char* s) {
    if (!s) return ELY_VAL_NULL;
    
    size_t len = strlen(s);
    
    // FAST PATH: Строка короткая? Пакуем прямо в регистр без аллокаций!
    if (len <= 7) {
        return ely_box_inline_str(s, len);
    }
    
    // SLOW PATH: Длинная строка — уходит в кучу GigaCage под управление GC
    char* heap_str = (char*)gc_alloc(len + 1, GC_OBJ_STRING); 
    if (!heap_str) {
        fprintf(stderr, "Fatal: Out of memory while allocating string.\n");
        abort();
    }
    
    memcpy(heap_str, s, len + 1);
    return ely_box_ptr(heap_str);
}

// ------------------------ Дополнительные функции ------------------------
ely_value ely_value_index(ely_value v, ely_value index) {
    int v_type = ely_get_type(v);
    int idx_type = ely_get_type(index);

    if (v_type == ely_VALUE_ARRAY) {
        if (idx_type == ely_VALUE_INT) {
            size_t i = (size_t)ELY_UNBOX_INT(index);
            arr* a = (arr*)ELY_UNBOX_PTR(v);
            if (i < arr_len(a)) {
                return arr_get(a, i);
            }
        }
    } else if (v_type == ely_VALUE_OBJECT) {
        if (idx_type == ely_VALUE_STRING) {
            dict* d = (dict*)ELY_UNBOX_PTR(v);
            // БЕЗОПАСНОЕ ИЗВЛЕЧЕНИЕ: Строка может быть инлайновой (SSO)
            char* str = ely_value_to_string(index);
            ely_value res = dict_get_str(d, str);
            free(str); // Освобождаем буфер, выделенный ely_value_to_string
            return res;
        }
    }
    return ely_value_new_null();
}

ely_value ely_value_get_key(ely_value v, const char* key) {
    if (ely_get_type(v) != ely_VALUE_OBJECT) return ely_value_new_null();
    dict* d = (dict*)ELY_UNBOX_PTR(v);
    return dict_get_str(d, key);
}

void ely_value_set_key(ely_value v, const char* key, ely_value value) {
    if (ely_get_type(v) != ely_VALUE_OBJECT) return;
    dict* d = (dict*)ELY_UNBOX_PTR(v);
    dict_set_str(d, key, value);
}

void ely_value_set_index(ely_value v, ely_value index, ely_value value) {
    int v_type = ely_get_type(v);
    int idx_type = ely_get_type(index);

    if (v_type == ely_VALUE_ARRAY && idx_type == ely_VALUE_INT) {
        size_t i = (size_t)ELY_UNBOX_INT(index);
        arr* a = (arr*)ELY_UNBOX_PTR(v);
        if (i < arr_len(a)) {
            arr_set(a, i, value);
        }
    } else if (v_type == ely_VALUE_OBJECT && idx_type == ely_VALUE_STRING) {
        dict* d = (dict*)ELY_UNBOX_PTR(v);
        char* str = ely_value_to_string(index);
        dict_set_str(d, str, value);
        free(str);
    }
}

// ------------------------ Базовые операции над ely_value ------------------------
int ely_value_as_bool(ely_value v) {
    switch (ely_get_type(v)) {
        case ely_VALUE_BOOL:   return ELY_UNBOX_BOOL(v);
        case ely_VALUE_INT:    return ELY_UNBOX_INT(v) != 0;
        case ely_VALUE_DOUBLE: return ely_unbox_double(v) != 0.0;
        case ely_VALUE_STRING: {
            char* s = (char*)ELY_UNBOX_PTR(v);
            return s && *s != '\0';
        }
        default:               return 0;
    }
}

ely_value ely_value_add(ely_value a, ely_value b) {
    // FAST PATH: Оба операнда — целые числа (Smi)
    if ((a & ELY_TAG_MASK) == ELY_TAG_INT && (b & ELY_TAG_MASK) == ELY_TAG_INT) {
        // Битовый трюк: сложение двух задвинутых чисел выдаст лишний тег 0x1. 
        // Просто вычитаем 1, чтобы восстановить тег ELY_TAG_INT (0x1)
        return a + b - 1; 
    }

    // FAST PATH: Оба операнда — нативные Double (Бит 2 горит у обоих)
    if (((a & 0x4ULL) != 0) && ((b & 0x4ULL) != 0)) {
        union { ely_value u; double d; } va, vb, vres;
        va.u = a; vb.u = b;
        vres.d = va.d + vb.d;
        if ((vres.u & 0x4ULL) != 0) return vres.u; // Результат тоже инлайновый double
        return ely_value_new_double_boxed(vres.d);
    }

    // SLOW PATH: Смешанные типы (Int + Double, кучные Double или строки)
    if (ely_is_double(a) || ely_is_double(b)) {
        double da = ely_is_double(a) ? ely_unbox_double(a) : (double)ely_unbox_int(a);
        double db = ely_is_double(b) ? ely_unbox_double(b) : (double)ely_unbox_int(b);
        return ely_box_double(da + db);
    }

    return ely_box_int(0);
}


ely_value ely_value_sub(ely_value a, ely_value b) {
    // FAST PATH: Оба операнда Int
    if ((a & ELY_TAG_MASK) == ELY_TAG_INT && (b & ELY_TAG_MASK) == ELY_TAG_INT) {
        // При вычитании теги аннулируются (1 - 1 = 0), поэтому прибавляем обратно 1
        return a - b + 1;
    }

    if (ely_is_double(a) || ely_is_double(b)) {
        double da = ely_is_double(a) ? ely_unbox_double(a) : (double)ely_unbox_int(a);
        double db = ely_is_double(b) ? ely_unbox_double(b) : (double)ely_unbox_int(b);
        return ely_box_double(da - db);
    }
    return ely_box_int(0);
}

ely_value ely_value_mul(ely_value a, ely_value b) {
    // Для умножения распаковываем аппаратно через сдвиг, так как биты перемножаются сложнее
    if (ely_is_int(a) && ely_is_int(b)) {
        return ely_box_int(ely_unbox_int(a) * ely_unbox_int(b));
    }
    if (ely_is_double(a) || ely_is_double(b)) {
        double da = ely_is_double(a) ? ely_unbox_double(a) : (double)ely_unbox_int(a);
        double db = ely_is_double(b) ? ely_unbox_double(b) : (double)ely_unbox_int(b);
        return ely_box_double(da * db);
    }
    return ely_box_int(0);
}

ely_value ely_value_div(ely_value a, ely_value b) {
    int type_a = ely_get_type(a);
    int type_b = ely_get_type(b);
    if ((type_a == ely_VALUE_INT || type_a == ely_VALUE_DOUBLE) &&
        (type_b == ely_VALUE_INT || type_b == ely_VALUE_DOUBLE)) {
        double da = (type_a == ely_VALUE_INT) ? (double)ELY_UNBOX_INT(a) : ely_unbox_double(a);
        double db = (type_b == ely_VALUE_INT) ? (double)ELY_UNBOX_INT(b) : ely_unbox_double(b);
        if (db == 0.0) return ely_value_new_null();
        if (type_a == ely_VALUE_INT && type_b == ely_VALUE_INT)
            return ely_value_new_int((long long)(da / db));
        else
            return ely_value_new_double(da / db);
    }
    return ely_value_new_null();
}

ely_value ely_value_mod(ely_value a, ely_value b) {
    if (ely_get_type(a) == ely_VALUE_INT && ely_get_type(b) == ely_VALUE_INT) {
        long long bv = ELY_UNBOX_INT(b);
        if (bv == 0) return ely_value_new_null();
        return ely_value_new_int(ELY_UNBOX_INT(a) % bv);
    }
    return ely_value_new_null();
}


ely_value ely_value_eq(ely_value a, ely_value b) {
    // Если битовые паттерны идентичны — они 100% равны (Int, Bool, Null, одинаковые указатели)
    if (a == b) return ELY_VAL_TRUE;

    // Сравнение строк (потенциально одна в куче, другая инлайновая)
    bool a_str = (ely_is_ptr(a) && get_heap_obj_type(ely_unbox_ptr(a)) == GC_OBJ_STRING) || ((a & ELY_TAG_MASK) == ELY_TAG_STR0);
    bool b_str = (ely_is_ptr(b) && get_heap_obj_type(ely_unbox_ptr(b)) == GC_OBJ_STRING) || ((b & ELY_TAG_MASK) == ELY_TAG_STR0);

    if (a_str && b_str) {
        char buf_a[64];
        char buf_b[64];
        
        if ((a & ELY_TAG_MASK) == ELY_TAG_STR0) ely_unbox_inline_str(a, buf_a);
        else strcpy(buf_a, (const char*)ely_unbox_ptr(a));

        if ((b & ELY_TAG_MASK) == ELY_TAG_STR0) ely_unbox_inline_str(b, buf_b);
        else strcpy(buf_b, (const char*)ely_unbox_ptr(b));

        return strcmp(buf_a, buf_b) == 0 ? ELY_VAL_TRUE : ELY_VAL_FALSE;
    }

    return ELY_VAL_FALSE;
}

ely_value ely_value_ne(ely_value a, ely_value b) {
    ely_value eq = ely_value_eq(a, b);
    int bval = ely_value_as_bool(eq);
    return ely_value_new_bool(!bval);
}

ely_value ely_value_lt(ely_value a, ely_value b) {
    int type_a = ely_get_type(a);
    int type_b = ely_get_type(b);
    if ((type_a == ely_VALUE_INT || type_a == ely_VALUE_DOUBLE) &&
        (type_b == ely_VALUE_INT || type_b == ely_VALUE_DOUBLE)) {
        double da = (type_a == ely_VALUE_INT) ? (double)ELY_UNBOX_INT(a) : ely_unbox_double(a);
        double db = (type_b == ely_VALUE_INT) ? (double)ELY_UNBOX_INT(b) : ely_unbox_double(b);
        return ely_value_new_bool(da < db);
    }
    if (type_a == ely_VALUE_STRING && type_b == ely_VALUE_STRING) {
        return ely_value_new_bool(strcmp((char*)ELY_UNBOX_PTR(a), (char*)ELY_UNBOX_PTR(b)) < 0);
    }
    return ely_value_new_bool(0);
}

ely_value ely_value_le(ely_value a, ely_value b) {
    int type_a = ely_get_type(a);
    int type_b = ely_get_type(b);
    if ((type_a == ely_VALUE_INT || type_a == ely_VALUE_DOUBLE) &&
        (type_b == ely_VALUE_INT || type_b == ely_VALUE_DOUBLE)) {
        double da = (type_a == ely_VALUE_INT) ? (double)ELY_UNBOX_INT(a) : ely_unbox_double(a);
        double db = (type_b == ely_VALUE_INT) ? (double)ELY_UNBOX_INT(b) : ely_unbox_double(b);
        return ely_value_new_bool(da <= db);
    }
    if (type_a == ely_VALUE_STRING && type_b == ely_VALUE_STRING) {
        return ely_value_new_bool(strcmp((char*)ELY_UNBOX_PTR(a), (char*)ELY_UNBOX_PTR(b)) <= 0);
    }
    return ely_value_new_bool(0);
}

ely_value ely_value_gt(ely_value a, ely_value b) {
    int type_a = ely_get_type(a);
    int type_b = ely_get_type(b);
    if ((type_a == ely_VALUE_INT || type_a == ely_VALUE_DOUBLE) &&
        (type_b == ely_VALUE_INT || type_b == ely_VALUE_DOUBLE)) {
        double da = (type_a == ely_VALUE_INT) ? (double)ELY_UNBOX_INT(a) : ely_unbox_double(a);
        double db = (type_b == ely_VALUE_INT) ? (double)ELY_UNBOX_INT(b) : ely_unbox_double(b);
        return ely_value_new_bool(da > db);
    }
    if (type_a == ely_VALUE_STRING && type_b == ely_VALUE_STRING) {
        return ely_value_new_bool(strcmp((char*)ELY_UNBOX_PTR(a), (char*)ELY_UNBOX_PTR(b)) > 0);
    }
    return ely_value_new_bool(0);
}

ely_value ely_value_ge(ely_value a, ely_value b) {
    int type_a = ely_get_type(a);
    int type_b = ely_get_type(b);
    if ((type_a == ely_VALUE_INT || type_a == ely_VALUE_DOUBLE) &&
        (type_b == ely_VALUE_INT || type_b == ely_VALUE_DOUBLE)) {
        double da = (type_a == ely_VALUE_INT) ? (double)ELY_UNBOX_INT(a) : ely_unbox_double(a);
        double db = (type_b == ely_VALUE_INT) ? (double)ELY_UNBOX_INT(b) : ely_unbox_double(b);
        return ely_value_new_bool(da >= db);
    }
    if (type_a == ely_VALUE_STRING && type_b == ely_VALUE_STRING) {
        return ely_value_new_bool(strcmp((char*)ELY_UNBOX_PTR(a), (char*)ELY_UNBOX_PTR(b)) >= 0);
    }
    return ely_value_new_bool(0);
}

ely_value ely_value_and(ely_value a, ely_value b) {
    return ely_value_new_bool(ely_value_as_bool(a) && ely_value_as_bool(b));
}

ely_value ely_value_or(ely_value a, ely_value b) {
    return ely_value_new_bool(ely_value_as_bool(a) || ely_value_as_bool(b));
}

ely_value ely_value_not(ely_value a) {
    return ely_value_new_bool(!ely_value_as_bool(a));
}

ely_value ely_value_neg(ely_value a) {
    int type = ely_get_type(a);
    if (type == ely_VALUE_INT)
        return ely_value_new_int(-ELY_UNBOX_INT(a));
    if (type == ely_VALUE_DOUBLE)
        return ely_value_new_double(-ely_unbox_double(a));
    return ely_value_new_null();
}

// ------------------------ Обёртки для массивов ------------------------
void ely_array_push(ely_value arr_val, ely_value elem) {
    if (ely_get_type(arr_val) != ely_VALUE_ARRAY) return;
    arr_push((arr*)ELY_UNBOX_PTR(arr_val), elem);
}

ely_value ely_array_pop(ely_value arr_val) {
    if (ely_get_type(arr_val) != ely_VALUE_ARRAY) return ely_value_new_null();
    return arr_pop_value((arr*)ELY_UNBOX_PTR(arr_val));
}

size_t ely_array_len(ely_value arr_val) {
    if (ely_get_type(arr_val) != ely_VALUE_ARRAY) return 0;
    return arr_len((arr*)ELY_UNBOX_PTR(arr_val));
}

ely_value ely_array_get(ely_value arr_val, size_t index) {
    if (ely_get_type(arr_val) != ely_VALUE_ARRAY) return ely_value_new_null();
    return arr_get((arr*)ELY_UNBOX_PTR(arr_val), index);
}

void ely_array_set(ely_value arr_val, size_t index, ely_value elem) {
    if (ely_get_type(arr_val) != ely_VALUE_ARRAY) return;
    arr_set((arr*)ELY_UNBOX_PTR(arr_val), index, elem);
}

// ------------------------ Обёртки для словарей ------------------------
ely_value ely_dict_get(ely_value dict_val, ely_value key) {
    if (ely_get_type(dict_val) != ely_VALUE_OBJECT) return ely_value_new_null();
    return dict_get((dict*)ELY_UNBOX_PTR(dict_val), key);
}

void ely_dict_set(ely_value dict_val, ely_value key, ely_value value) {
    if (ely_get_type(dict_val) != ely_VALUE_OBJECT) return;
    dict_set((dict*)ELY_UNBOX_PTR(dict_val), key, value);
}

void ely_dict_del(ely_value dict_val, ely_value key) {
    if (ely_get_type(dict_val) != ely_VALUE_OBJECT) return;
    dict* d = (dict*)ELY_UNBOX_PTR(dict_val);
    if (ely_get_type(key) == ely_VALUE_STRING) {
        dict_delete_str(d, (char*)ELY_UNBOX_PTR(key));
    } else {
        dict_delete(d, key);
    }
}

// ------------------ Reflection & Methods --------------------

// Извлечение сырых значений (вместо v->u.int_val)
static inline long long ely_as_int(ely_value v) {
    // Если используете 48-битное целое со знаком, может потребоваться sign-extension
    return (long long)(v & ELY_VAL_MASK); 
}

static inline void* ely_as_ptr(ely_value v) {
    return (void*)(uintptr_t)(v & ELY_VAL_MASK);
}

// ------------------------ Консоль ------------------------
void ely_print(const char* str) { if (str) fputs(str, stdout); }
void ely_println(const char* str) {
    if (str) fputs(str, stdout);
    putchar('\n');
    fflush(stdout);
}

// Быстрый внутренний хелпер для печати ely_value строк без лишних аллокаций памяти
static void ely_internal_print_str_value(ely_value str) {
    if (ely_is_null(str)) return;
    
    if (ELY_IS_STR0(str)) {
        char buf[16]; // Буфер для инлайн-строк
        ely_unbox_inline_str(str, buf);
        fputs(buf, stdout);
    } else if (ELY_IS_PTR(str)) {
        void* ptr = ELY_UNBOX_PTR(str);
        if (ptr && get_heap_obj_type(ptr) == GC_OBJ_STRING) {
            fputs((const char*)ptr, stdout);
        }
    }
}

// Исправленный вывод ely_value строк
void ely_println_str(ely_value str) {
    ely_internal_print_str_value(str);
    putchar('\n');
    fflush(stdout);
}

// Примитивы и числа (теперь строго с распаковкой)
void ely_print_int(ely_value n)    { printf("%d", (int)ELY_UNBOX_INT(n)); }
void ely_print_uint(ely_value n)   { printf("%u", (unsigned int)ELY_UNBOX_INT(n)); }
void ely_print_more(ely_value n)   { printf("%lld", (long long)ELY_UNBOX_INT(n)); }
void ely_print_umore(ely_value n)  { printf("%llu", (unsigned long long)ELY_UNBOX_INT(n)); }
void ely_print_flt(ely_value f)    { printf("%f", (float)ely_unbox_double(f)); }
void ely_print_double(ely_value d) { printf("%lf", ely_unbox_double(d)); }
void ely_print_bool(ely_value b)   { fputs(ELY_UNBOX_BOOL(b) ? "true" : "false", stdout); }
void ely_print_char(ely_value c)   { putchar((char)ELY_UNBOX_INT(c)); }
void ely_print_byte(ely_value b)   { printf("%d", (int)(int8_t)ELY_UNBOX_INT(b)); }
void ely_print_ubyte(ely_value b)  { printf("%u", (unsigned int)(uint8_t)ELY_UNBOX_INT(b)); }

void ely_println_int(ely_value n)    { printf("%d\n", (int)ELY_UNBOX_INT(n)); fflush(stdout); }
void ely_println_uint(ely_value n)   { printf("%u\n", (unsigned int)ELY_UNBOX_INT(n)); fflush(stdout); }
void ely_println_more(ely_value n)   { printf("%lld\n", (long long)ELY_UNBOX_INT(n)); fflush(stdout); }
void ely_println_umore(ely_value n)  { printf("%llu\n", (unsigned long long)ELY_UNBOX_INT(n)); fflush(stdout); }
void ely_println_flt(ely_value f)    { printf("%f\n", (float)ely_unbox_double(f)); fflush(stdout); }
void ely_println_double(ely_value d) { printf("%lf\n", ely_unbox_double(d)); fflush(stdout); }
void ely_println_bool(ely_value b)   { fputs(ELY_UNBOX_BOOL(b) ? "true" : "false", stdout); putchar('\n'); fflush(stdout); }
void ely_println_char(ely_value c)   { putchar((char)ELY_UNBOX_INT(c)); putchar('\n'); fflush(stdout); }
void ely_println_byte(ely_value b)   { printf("%d\n", (int)(int8_t)ELY_UNBOX_INT(b)); fflush(stdout); }
void ely_println_ubyte(ely_value b)  { printf("%u\n", (unsigned int)(uint8_t)ELY_UNBOX_INT(b)); fflush(stdout); }

ely_str ely_input(void) {
    static char buffer[1024];
    if (fgets(buffer, sizeof(buffer), stdin)) {
        size_t len = strlen(buffer);
        if (len && buffer[len-1] == '\n') buffer[len-1] = '\0';
        char* res = (char*)gc_alloc(len + 1, GC_OBJ_STRING);
        if (res) strcpy(res, buffer);
        return res;
    }
    return NULL;
}

ely_str ely_input_prompt(const char* prompt) {
    if (prompt) ely_print(prompt);
    return ely_input();
}

// ------------------------ Преобразования строк в числа ------------------------
ely_int ely_str_to_int(const char* str) {
    if (!str) return 0;
    long long v = my_strtoll(str, NULL, 10);
    return (ely_int)v;
}
ely_uint ely_str_to_uint(const char* str) {
    if (!str) return 0;
    unsigned long long v = my_strtoull(str, NULL, 10);
    return (ely_uint)v;
}
ely_more ely_str_to_more(const char* str) {
    if (!str) return 0;
    return my_strtoll(str, NULL, 10);
}
ely_umore ely_str_to_umore(const char* str) {
    if (!str) return 0;
    return my_strtoull(str, NULL, 10);
}
ely_flt ely_str_to_flt(const char* str) {
    if (!str) return 0.0f;
    return (ely_flt)strtod(str, NULL);
}
ely_double ely_str_to_double(const char* str) {
    if (!str) return 0.0;
    return strtod(str, NULL);
}

// ------------------------ Преобразования чисел в строки ------------------------
static ely_str _int_to_str(long long n) {
    char buf[32];
    int len = snprintf(buf, sizeof(buf), "%lld", n);
    if (len < 0) return NULL;
    char* res = (char*)gc_alloc(len + 1, GC_OBJ_STRING);
    if (res) memcpy(res, buf, len + 1);
    return res;
}
static ely_str _uint_to_str(unsigned long long n) {
    char buf[32];
    int len = snprintf(buf, sizeof(buf), "%llu", n);
    if (len < 0) return NULL;
    char* res = (char*)gc_alloc(len + 1, GC_OBJ_STRING);
    if (res) memcpy(res, buf, len + 1);
    return res;
}
ely_str ely_int_to_str(ely_int n) { return _int_to_str(n); }
ely_str ely_uint_to_str(ely_uint n) { return _uint_to_str(n); }
ely_str ely_more_to_str(ely_more n) { return _int_to_str(n); }
ely_str ely_umore_to_str(ely_umore n) { return _uint_to_str(n); }
ely_str ely_flt_to_str(ely_flt f) {
    char buf[64];
    int len = snprintf(buf, sizeof(buf), "%g", (double)f);
    if (len < 0) return NULL;
    char* res = (char*)gc_alloc(len + 1, GC_OBJ_STRING);
    if (res) memcpy(res, buf, len + 1);
    return res;
}
ely_str ely_double_to_str(ely_double d) {
    char buf[64];
    int len = snprintf(buf, sizeof(buf), "%g", d);
    if (len < 0) return NULL;
    char* res = (char*)gc_alloc(len + 1, GC_OBJ_STRING);
    if (res) memcpy(res, buf, len + 1);
    return res;
}
ely_str ely_bool_to_str(ely_bool b) {
    const char* s = b ? "true" : "false";
    char* res = (char*)gc_alloc(strlen(s) + 1, GC_OBJ_STRING);
    if (res) strcpy(res, s);
    return res;
}

// ------------------------ Строки ------------------------
size_t ely_str_len(const char* str) { return str ? strlen(str) : 0; }
ely_str ely_str_dup(const char* str) {
    return gc_strdup(str);
}
ely_str ely_str_concat(const char* a, const char* b) {
    if (!a && !b) return NULL;
    size_t la = a ? strlen(a) : 0;
    size_t lb = b ? strlen(b) : 0;
    char* res = (char*)gc_alloc(la + lb + 1, GC_OBJ_STRING);
    if (!res) return NULL;
    if (la) memcpy(res, a, la);
    if (lb) memcpy(res + la, b, lb);
    res[la+lb] = '\0';
    return res;
}
int ely_str_cmp(const char* a, const char* b) {
    if (a == b) return 0;
    if (!a) return -1;
    if (!b) return 1;
    return strcmp(a, b);
}
ely_str ely_str_substr(const char* str, size_t start, size_t len) {
    if (!str) return NULL;
    size_t slen = strlen(str);
    if (start >= slen) return ely_str_dup("");
    if (start + len > slen) len = slen - start;
    char* res = (char*)gc_alloc(len + 1, GC_OBJ_STRING);
    if (!res) return NULL;
    memcpy(res, str + start, len);
    res[len] = '\0';
    return res;
}
ely_str ely_str_trim(const char* str) {
    if (!str) return NULL;
    while (*str && (*str == ' ' || *str == '\t' || *str == '\n')) str++;
    size_t len = strlen(str);
    while (len > 0 && (str[len-1] == ' ' || str[len-1] == '\t' || str[len-1] == '\n')) len--;
    char* res = (char*)gc_alloc(len + 1, GC_OBJ_STRING);
    if (!res) return NULL;
    memcpy(res, str, len);
    res[len] = '\0';
    return res;
}
ely_str ely_str_replace(const char* str, const char* old, const char* new_str) {
    if (!str || !old) return ely_str_dup(str);
    size_t old_len = strlen(old);
    if (old_len == 0) return ely_str_dup(str);
    size_t new_len = new_str ? strlen(new_str) : 0;
    size_t count = 0;
    const char* pos = str;
    while ((pos = strstr(pos, old))) { count++; pos += old_len; }
    if (count == 0) return ely_str_dup(str);
    size_t result_len = strlen(str) + count * (new_len - old_len);
    char* res = (char*)gc_alloc(result_len + 1, GC_OBJ_STRING);
    if (!res) return NULL;
    char* out = res;
    pos = str;
    while (*pos) {
        char* found = (char*)strstr(pos, old);
        if (found) {
            size_t before = found - pos;
            memcpy(out, pos, before);
            out += before;
            if (new_str) { memcpy(out, new_str, new_len); out += new_len; }
            pos = found + old_len;
        } else {
            strcpy(out, pos);
            break;
        }
    }
    return res;
}

// ------------------------ Математика ------------------------
ely_int ely_abs_int(ely_int n) { return n < 0 ? -n : n; }
ely_more ely_abs_more(ely_more n) { return n < 0 ? -n : n; }
ely_double ely_fabs(ely_double x) { return fabs(x); }
ely_int ely_min_int(ely_int a, ely_int b) { return a < b ? a : b; }
ely_more ely_min_more(ely_more a, ely_more b) { return a < b ? a : b; }
ely_double ely_min_double(ely_double a, ely_double b) { return a < b ? a : b; }
ely_int ely_max_int(ely_int a, ely_int b) { return a > b ? a : b; }
ely_more ely_max_more(ely_more a, ely_more b) { return a > b ? a : b; }
ely_double ely_max_double(ely_double a, ely_double b) { return a > b ? a : b; }
ely_double ely_pow(ely_double base, ely_double exp) { return pow(base, exp); }
ely_double ely_sqrt(ely_double x) { return sqrt(x); }
ely_double ely_sin(ely_double x) { return sin(x); }
ely_double ely_cos(ely_double x) { return cos(x); }
ely_double ely_tan(ely_double x) { return tan(x); }

// ------------------------ Случайные числа ------------------------
static unsigned int rand_seed = 1;
void ely_srand(ely_uint seed) { rand_seed = seed; }
ely_int ely_rand(void) {
    rand_seed = rand_seed * 1103515245 + 12345;
    return (ely_int)((rand_seed >> 16) & 0x7FFF);
}
ely_double ely_rand_double(void) {
    return (ely_double)ely_rand() / 32767.0;
}

// ------------------------ Время ------------------------
void ely_sleep(ely_uint milliseconds) {
#ifdef _WIN32
    Sleep(milliseconds);
#else
    usleep(milliseconds * 1000);
#endif
}
ely_more ely_time_now(void) {
    return (ely_more)time(NULL);
}
double ely_time_diff(ely_more start, ely_more end) {
    return (double)(end - start);
}

// ------------------------ Файлы ------------------------
typedef struct ely_file {
    FILE* fp;
} ely_file;

ely_file* ely_file_open(const char* path, const char* mode) {
    FILE* fp = fopen(path, mode);
    if (!fp) return NULL;
    ely_file* f = (ely_file*)gc_alloc(sizeof(ely_file), GC_OBJ_STRING);
    if (!f) { fclose(fp); return NULL; }
    f->fp = fp;
    return f;
}
void ely_file_close(ely_file* f) {
    if (f) {
        if (f->fp) fclose(f->fp);
    }
}
int ely_file_write(ely_file* f, const char* data, size_t len) {
    if (!f || !f->fp) return -1;
    return (fwrite(data, 1, len, f->fp) == len) ? 0 : -1;
}
char* ely_file_read(ely_file* f, size_t* out_len) {
    if (!f || !f->fp) return NULL;
    char* result = NULL;
    size_t total = 0, cap = 0;
    char buf[4096];
    while (1) {
        size_t n = fread(buf, 1, sizeof(buf), f->fp);
        if (n == 0) break;
        if (total + n > cap) {
            cap = (total + n) * 2 + 1024;
            char* new_res = (char*)realloc(result, cap);
            if (!new_res) { free(result); return NULL; }
            result = new_res;
        }
        memcpy(result + total, buf, n);
        total += n;
    }
    if (out_len) *out_len = total;
    if (total == 0) {
        free(result);
        return NULL;
    }
    char* final = (char*)realloc(result, total + 1);
    if (final) result = final;
    result[total] = '\0';
    return result;
}
int ely_file_exists(const char* path) {
    FILE* f = fopen(path, "r");
    if (f) { fclose(f); return 1; }
    return 0;
}
char* ely_file_read_all(const char* path, size_t* out_len) {
    ely_file* f = ely_file_open(path, "rb");
    if (!f) return NULL;
    char* data = ely_file_read(f, out_len);
    ely_file_close(f);
    return data;
}
int ely_file_remove(const char* path) { return remove(path); }
int ely_file_rename(const char* old, const char* new_path) { return rename(old, new_path); }
int ely_file_write_all(const char* path, const char* data, size_t len) {
    FILE* f = fopen(path, "wb");
    if (!f) return -1;
    size_t written = fwrite(data, 1, len, f);
    fclose(f);
    return (written == len) ? 0 : -1;
}

// ------------------------ Пути ------------------------
ely_str ely_path_join(const char* a, const char* b) {
    if (!a && !b) return NULL;
    if (!a) return ely_str_dup(b);
    if (!b) return ely_str_dup(a);
    size_t la = strlen(a);
    size_t lb = strlen(b);
    char* res = (char*)gc_alloc(la + lb + 2, GC_OBJ_STRING);
    if (!res) return NULL;
    strcpy(res, a);
    if (la > 0 && res[la-1] != '/' && res[la-1] != '\\')
        strcat(res, "/");
    strcat(res, b);
    return res;
}
ely_str ely_path_basename(const char* path) {
    if (!path) return NULL;
    char* sep = (char*)strrchr(path, '/');
    if (!sep) sep = (char*)strrchr(path, '\\');
    if (!sep) return ely_str_dup(path);
    return ely_str_dup(sep + 1);
}
ely_str ely_path_dirname(const char* path) {
    if (!path) return NULL;
    char* sep = (char*)strrchr(path, '/');
    if (!sep) sep = (char*)strrchr(path, '\\');
    if (!sep) return ely_str_dup(".");
    size_t len = sep - path;
    if (len == 0) return ely_str_dup(".");
    char* res = (char*)gc_alloc(len + 1, GC_OBJ_STRING);
    if (!res) return NULL;
    memcpy(res, path, len);
    res[len] = '\0';
    return res;
}
int ely_path_is_absolute(const char* path) {
    if (!path) return 0;
    if (path[0] == '/' || path[0] == '\\') return 1;
#ifdef _WIN32
    if (path[0] && path[1] == ':') return 1;
#endif
    return 0;
}

// ------------------------ Динамические библиотеки ------------------------
#ifdef _WIN32
#define LIB_HANDLE HMODULE
#define LIB_LOAD(path) LoadLibraryA(path)
#define LIB_GET(lib, name) GetProcAddress((HMODULE)lib, name)
#define LIB_CLOSE(lib) FreeLibrary((HMODULE)lib)
#else
#define LIB_HANDLE void*
#define LIB_LOAD(path) dlopen(path, RTLD_LAZY)
#define LIB_GET(lib, name) dlsym(lib, name)
#define LIB_CLOSE(lib) dlclose(lib)
#endif

void* ely_load_library(const char* path) {
    if (!path) return NULL;
    return (void*)LIB_LOAD(path);
}
void* ely_get_function(void* lib, const char* name) {
    if (!lib || !name) return NULL;
    return (void*)LIB_GET(lib, name);
}
void ely_close_library(void* lib) {
    if (lib) LIB_CLOSE(lib);
}
int ely_call_int_int(void* func, int a, int b) {
    if (!func) return 0;
    int (*f)(int, int) = (int (*)(int, int))func;
    return f(a, b);
}
double ely_call_double_double(void* func, double a) {
    if (!func) return 0.0;
    double (*f)(double) = (double (*)(double))func;
    return f(a);
}
double ely_call_double_double_double(void* func, double a, double b) {
    if (!func) return 0.0;
    double (*f)(double, double) = (double (*)(double, double))func;
    return f(a, b);
}
char* ely_call_str_void(void* func) {
    if (!func) return NULL;
    char* (*f)(void) = (char* (*)(void))func;
    return f();
}

// ------------------------ Память ------------------------
// теперь за это отвечает GC

// ------------------------ JSON сериализация (внутренние статические функции) ------------------------
static char* _jsonify_string(const char* s) {
    if (!s) return ely_str_dup("null");
    size_t len = strlen(s);
    char* out = (char*)gc_alloc(len * 2 + 3, GC_OBJ_STRING);
    char* p = out;
    *p++ = '"';
    for (size_t i = 0; i < len; i++) {
        char c = s[i];
        if (c == '"' || c == '\\') {
            *p++ = '\\';
            *p++ = c;
        } else if (c == '\n') {
            *p++ = '\\';
            *p++ = 'n';
        } else if (c == '\r') {
            *p++ = '\\';
            *p++ = 'r';
        } else if (c == '\t') {
            *p++ = '\\';
            *p++ = 't';
        } else {
            *p++ = c;
        }
    }
    *p++ = '"';
    *p = '\0';
    char* result = ely_str_dup(out);
    return result;
}

static char* array_to_json(arr* a) {
    if (!a) return strdup("null");
    char* result = strdup("[");
    for (size_t i = 0; i < arr_len(a); i++) {
        if (i > 0) result = ely_str_concat(result, ",");
        ely_value elem = arr_get(a, i); // Получаем по значению!
        char* elem_json = ely_value_to_json(elem);
        result = ely_str_concat(result, elem_json);
    }
    result = ely_str_concat(result, "]");
    return result;
}

unsigned int ely_dict_str_hash(ely_value val) {
    char buf[64];
    if ((val & ELY_TAG_MASK) == ELY_TAG_STR0) {
        ely_immediate_str_get_chars(val, buf);
        return ely_str_hash(buf);
    } else if (ELY_IS_PTR(val)) {
        void* ptr = ELY_UNBOX_PTR(val);
        if (ptr && get_heap_obj_type(ptr) == GC_OBJ_STRING) {
            return ely_str_hash((const char*)ptr);
        }
    }
    return 0;
}

int ely_dict_str_cmp(ely_value a, ely_value b) {
    char buf_a[64] = {0};
    char buf_b[64] = {0};
    
    if ((a & ELY_TAG_MASK) == ELY_TAG_STR0) ely_immediate_str_get_chars(a, buf_a);
    else if (ELY_IS_PTR(a) && ELY_UNBOX_PTR(a)) strcpy(buf_a, (const char*)ELY_UNBOX_PTR(a));

    if ((b & ELY_TAG_MASK) == ELY_TAG_STR0) ely_immediate_str_get_chars(b, buf_b);
    else if (ELY_IS_PTR(b) && ELY_UNBOX_PTR(b)) strcpy(buf_b, (const char*)ELY_UNBOX_PTR(b));

    return strcmp(buf_a, buf_b);
}	
#undef dict_new_str
#define dict_new_str() dict_new(ely_dict_str_hash, ely_dict_str_cmp)

arr* dict_keys(dict* d) {
    arr* a = arr_new(); // Если есть возможность, используй пред-аллокацию на d->count элементов
    if (!d) return a;
    
    for (size_t i = 0; i < d->capacity; i++) {
        dict_entry* entry = d->buckets[i];
        while (entry) {
            arr_push(a, entry->key);
            entry = entry->next; // Идем по цепочке коллизий
        }
    }
    return a;
}

// Сбор всех значений словаря в один массив
arr* dict_values(dict* d) {
    arr* a = arr_new();
    if (!d) return a;
    
    for (size_t i = 0; i < d->capacity; i++) {
        dict_entry* entry = d->buckets[i];
        while (entry) {
            arr_push(a, entry->value);
            entry = entry->next;
        }
    }
    return a;
}

static char* dict_to_json(dict* d) {
    if (!d) return strdup("null");
    char* result = strdup("{");
    int first = 1;
    for (size_t i = 0; i < d->capacity; i++) {
        dict_entry* e = d->buckets[i]; // Используем buckets!
        while (e) {
            if (!first) result = ely_str_concat(result, ",");
            first = 0;
            char* key_json = ely_value_to_json(e->key);
            char* val_json = ely_value_to_json(e->value);
            result = ely_str_concat(result, key_json);
            result = ely_str_concat(result, ":");
            result = ely_str_concat(result, val_json);
            e = e->next;
        }
    }
    result = ely_str_concat(result, "}");
    return result;
}

#define ely_is_null(v)   ((v) == 0)
#define ely_is_bool(v)   (((v) & 0xFFFF000000000000ULL) == ELY_TAG_BOOL)

char* ely_value_to_string(ely_value v) {
    char* buf = (char*)malloc(64);
    if (!buf) return NULL;

    if (ely_is_null(v)) {
        free(buf);
        return strdup("null");
    } else if (ely_is_bool(v)) {
        free(buf);
        return strdup(ELY_UNBOX_BOOL(v) ? "true" : "false"); // Используем макрос из хедера
    } else if (ely_is_int(v)) {
        snprintf(buf, 64, "%lld", (long long)ELY_UNBOX_INT(v));
    } else if (ely_is_double(v)) {
        snprintf(buf, 64, "%g", ely_unbox_double(v));
    } else if (ELY_IS_STR0(v)) {
        ely_unbox_inline_str(v, buf);
    } else if (ELY_IS_PTR(v)) {
        void* ptr = ELY_UNBOX_PTR(v);
        uint8_t type = get_heap_obj_type(ptr);
        
        if (type == GC_OBJ_STRING) {
            free(buf);
            return strdup((const char*)ptr);
        } else if (type == GC_OBJ_ARR) {
            free(buf);
            return array_to_json((arr*)ptr);
        } else if (type == GC_OBJ_DICT) {
            free(buf);
            return dict_to_json((dict*)ptr);
        } else {
            snprintf(buf, 64, "[object]");
        }
    } else {
        snprintf(buf, 64, "[unknown]");
    }
    return buf;
}

// ------------------------ Главная функция сериализации ------------------------
char* ely_value_to_json(ely_value v) {
    if (ely_is_null(v))   return strdup("null");
    if (ely_is_bool(v))   return strdup(ely_unbox_bool(v) ? "true" : "false");
    
    if (ely_is_int(v)) {
        char buf[32];
        snprintf(buf, sizeof(buf), "%lld", (long long)ely_unbox_int(v));
        return strdup(buf);
    }
    if (ely_is_double(v)) {
        char buf[64];
        snprintf(buf, sizeof(buf), "%g", ely_unbox_double(v));
        return strdup(buf);
    }
    if ((v & ELY_TAG_MASK) == ELY_TAG_STR0) {
        char buf[8];
        ely_unbox_inline_str(v, buf);
        return _jsonify_string(buf);
    }
    if (ely_is_ptr(v)) {
        void* ptr = (void*)ely_unbox_ptr(v);
        uint8_t type = get_heap_obj_type(ptr);
        if (type == GC_OBJ_STRING) {
            return _jsonify_string((const char*)ptr);
        } else if (type == GC_OBJ_ARR) {
            return array_to_json((arr*)ptr);
        } else if (type == GC_OBJ_DICT) {
            return dict_to_json((dict*)ptr);
        }
    }
    return strdup("null");
}

// ------------------------ Парсинг JSON (ely_dictify) ------------------------
typedef struct json_parser {
    const char* str;
    size_t pos;
    size_t len;
} json_parser;

static void skip_whitespace(json_parser* p) {
    while (p->pos < p->len && isspace(p->str[p->pos])) p->pos++;
}
static int peek(json_parser* p) {
    if (p->pos >= p->len) return 0;
    return p->str[p->pos];
}
static int consume(json_parser* p, char expected) {
    skip_whitespace(p);
    if (p->pos < p->len && p->str[p->pos] == expected) {
        p->pos++;
        return 1;
    }
    return 0;
}
static char* parse_string(json_parser* p) {
    if (!consume(p, '"')) return NULL;
    size_t start = p->pos;
    while (p->pos < p->len && p->str[p->pos] != '"') {
        if (p->str[p->pos] == '\\') p->pos++;
        p->pos++;
    }
    if (p->pos >= p->len) return NULL;
    size_t end = p->pos;
    consume(p, '"');
    size_t len = end - start;
    char* buf = (char*)gc_alloc(len + 1, GC_OBJ_STRING);
    if (!buf) return NULL;
    memcpy(buf, p->str + start, len);
    buf[len] = '\0';
    return buf;
}
static char* parse_number(json_parser* p) {
    const char* start = p->str + p->pos;
    while (p->pos < p->len && (isdigit(p->str[p->pos]) || p->str[p->pos] == '.' || p->str[p->pos] == '-' || p->str[p->pos] == 'e' || p->str[p->pos] == 'E')) p->pos++;
    size_t len = p->pos - (start - p->str);
    char* buf = (char*)gc_alloc(len + 1, GC_OBJ_STRING);
    if (!buf) return NULL;
    memcpy(buf, start, len);
    buf[len] = '\0';
    return buf;
}
static char* parse_bool(json_parser* p) {
    if (strncmp(p->str + p->pos, "true", 4) == 0) {
        p->pos += 4;
        return ely_str_dup("true");
    } else if (strncmp(p->str + p->pos, "false", 5) == 0) {
        p->pos += 5;
        return ely_str_dup("false");
    }
    return NULL;
}
static char* parse_null(json_parser* p) {
    if (strncmp(p->str + p->pos, "null", 4) == 0) {
        p->pos += 4;
        return ely_str_dup("null");
    }
    return NULL;
}
static dict* parse_object(json_parser* p);
static arr* parse_array(json_parser* p);
static char* parse_value(json_parser* p);

dict* ely_dictify(const char* json_str) {
    if (!json_str) return NULL;
    json_parser parser = { json_str, 0, strlen(json_str) };
    skip_whitespace(&parser);
    if (!consume(&parser, '{')) return NULL;
    dict* d = dict_new_str();
    while (1) {
        skip_whitespace(&parser);
        if (peek(&parser) == '}') {
            consume(&parser, '}');
            break;
        }
        char* key = parse_string(&parser);
        if (!key) { dict_free(d); return NULL; }
        skip_whitespace(&parser);
        if (!consume(&parser, ':')) { dict_free(d); return NULL; }
        char* value = parse_value(&parser);
        if (!value) { dict_free(d); return NULL; }
        ely_value val = ely_value_new_string(value);
        dict_set_str(d, key, val);
        skip_whitespace(&parser);
        if (peek(&parser) == ',') consume(&parser, ',');
        else if (peek(&parser) == '}') continue;
        else { dict_free(d); return NULL; }
    }
    return d;
}

static char* parse_value(json_parser* p) {
    skip_whitespace(p);
    char c = peek(p);
    if (c == '"') {
        return parse_string(p);
    } else if (c == '-' || isdigit(c)) {
        return parse_number(p);
    } else if (c == 't' || c == 'f') {
        return parse_bool(p);
    } else if (c == 'n') {
        return parse_null(p);
    } else if (c == '{') {
        dict* obj = parse_object(p);
        if (!obj) return NULL;
        char* json = dict_to_json(obj);
        dict_free(obj);
        return json;
    } else if (c == '[') {
        arr* a = parse_array(p);
        if (!a) return NULL;
        char* json = array_to_json(a);
        arr_free(a);
        return json;
    }
    return NULL;
}

static dict* parse_object(json_parser* p) {
    if (!consume(p, '{')) return NULL;
    dict* d = dict_new_str();
    while (1) {
        skip_whitespace(p);
        if (peek(p) == '}') {
            consume(p, '}');
            break;
        }
        char* key = parse_string(p);
        if (!key) { dict_free(d); return NULL; }
        skip_whitespace(p);
        if (!consume(p, ':')) { dict_free(d); return NULL; }
        char* value = parse_value(p);
        if (!value) { dict_free(d); return NULL; }
        ely_value val = ely_value_new_string(value);
        dict_set_str(d, key, val);
        skip_whitespace(p);
        if (peek(p) == ',') consume(p, ',');
        else if (peek(p) == '}') continue;
        else { dict_free(d); return NULL; }
    }
    return d;
}

static arr* parse_array(json_parser* p) {
    if (!consume(p, '[')) return NULL;
    arr* a = arr_new();
    while (1) {
        skip_whitespace(p);
        if (peek(p) == ']') {
            consume(p, ']');
            break;
        }
        char* value = parse_value(p);
        if (!value) { arr_free(a); return NULL; }
        ely_value val = ely_value_new_string(value);
        arr_push(a, val);
        skip_whitespace(p);
        if (peek(p) == ',') consume(p, ',');
        else if (peek(p) == ']') continue;
        else { arr_free(a); return NULL; }
    }
    return a;
}

// -------------------------------------------------------------------
// Совместимость со старыми именами функций (для переходного периода)
// -------------------------------------------------------------------
void del(ely_value dict_val, char *key) {
    dict* d = (dict*)ELY_UNBOX_PTR(dict_val);
    if (d) {
        dict_delete_str(d, key); // Или твоя внутренняя функция удаления
    }
}

int has(ely_value dict_val, char *key) {
    dict* d = (dict*)ELY_UNBOX_PTR(dict_val);
    if (!d) return 0;
    return dict_has_str(d, key); 
}

ely_value keys(ely_value dict_val) {
    dict* d = (dict*)ELY_UNBOX_PTR(dict_val);
    if (!d) return ely_value_new_array(arr_new());
    
    arr* k_arr = dict_keys(d);
    return ely_value_new_array(k_arr);
}

char* toJson(ely_value dict_val) {
    int t = ely_get_type(dict_val);
    if (t == ely_VALUE_OBJECT) {
        return dict_to_json((dict*)ELY_UNBOX_PTR(dict_val));
    } else if (t == ely_VALUE_ARRAY) {
        return array_to_json((arr*)ELY_UNBOX_PTR(dict_val));
    }
    return ely_str_dup("null");
}

// -------------------------------------------------------------------
// Перевод оставшейся части рантайма на архитектуру Ely-boxing
// -------------------------------------------------------------------

char* ely_array_to_json(ely_value arr_val) {
    if (ely_get_type(arr_val) != ely_VALUE_ARRAY) return ely_str_dup("null");
    return array_to_json((arr*)ELY_UNBOX_PTR(arr_val));
}

// ------------------ OTHER --------------------
ely_bool isType(ely_value value, const char* type_name) {
    if (type_name == NULL) return 0;
    
    int t = ely_get_type(value);
    if (strcmp(type_name, "null") == 0)    return t == ely_VALUE_NULL;
    if (strcmp(type_name, "bool") == 0)    return t == ely_VALUE_BOOL;
    if (strcmp(type_name, "int") == 0)     return t == ely_VALUE_INT;
    if (strcmp(type_name, "double") == 0)  return t == ely_VALUE_DOUBLE;
    if (strcmp(type_name, "string") == 0)  return t == ely_VALUE_STRING;
    if (strcmp(type_name, "array") == 0)   return t == ely_VALUE_ARRAY;
    if (strcmp(type_name, "object") == 0)  return t == ely_VALUE_OBJECT;

    // Проверка цепочки прототипов/классов для пользовательских типов
    if (t == ely_VALUE_OBJECT) {
        dict* d = (dict*)ELY_UNBOX_PTR(value);
        
        ely_value chain = dict_get_str(d, "__class_chain");
        if (ely_get_type(chain) == ely_VALUE_ARRAY) {
            arr* chain_arr = (arr*)ELY_UNBOX_PTR(chain);
            for (size_t i = 0; i < arr_len(chain_arr); i++) {
                ely_value cls_name = arr_get(chain_arr, i);
                if (ely_get_type(cls_name) == ely_VALUE_STRING) {
                    if (strcmp((char*)ELY_UNBOX_PTR(cls_name), type_name) == 0)
                        return 1;
                }
            }
        }
        
        ely_value cls = dict_get_str(d, "__class");
        if (ely_get_type(cls) == ely_VALUE_STRING) {
            return strcmp((char*)ELY_UNBOX_PTR(cls), type_name) == 0;
        }
    }
    return 0;
}

ely_bool isNull(ely_value value) {
    return ely_get_type(value) == ely_VALUE_NULL;
}

ely_bool isIn(ely_value value, arr* in) {
    if (!in) return 0;
    for (int i = 0; i < arr_len(in); i++) {
        // ely_value_eq теперь принимает значения напрямую
        if (ely_value_as_bool(ely_value_eq(value, arr_get(in, i)))) {
            return 1;
        }
    }
    return 0;
}

// ------------------------ Reflection ------------------------
const char* ely_typeof(ely_value v) {
    switch (ely_get_type(v)) {
        case ely_VALUE_NULL:   return "null";
        case ely_VALUE_BOOL:   return "bool";
        case ely_VALUE_INT:    return "int";
        case ely_VALUE_DOUBLE: return "double";
        case ely_VALUE_STRING: return "string";
        case ely_VALUE_ARRAY:  return "array";
        case ely_VALUE_OBJECT: return "object";
        default:               return "unknown";
    }
}

ely_value ely_value_get_fields(ely_value v) {
    arr* fields = arr_new();
    if (ely_get_type(v) == ely_VALUE_OBJECT) {
        dict* d = (dict*)ELY_UNBOX_PTR(v);
        for (size_t i = 0; i < d->capacity; i++) {
            dict_entry* e = d->buckets[i];
            while (e) {
                // e->key теперь является упакованным ely_value (String)
                if (ely_get_type(e->key) == ely_VALUE_STRING) {
                    arr_push(fields, e->key);
                }
                e = e->next;
            }
        }
    }
    return ely_value_new_array(fields);
}

ely_value ely_value_get_methods(ely_value v) {
    arr* methods = arr_new();
    int t = ely_get_type(v);

    if (t == ely_VALUE_OBJECT) {
        dict* d = (dict*)ELY_UNBOX_PTR(v);
        for (size_t i = 0; i < d->capacity; i++) {
            dict_entry* e = d->buckets[i];
            while (e) {
                // Проверяем кастомные методы объекта (значение должно иметь тег функции)
                if (ely_get_type(e->value) == ely_VALUE_FUNCTION) {
                    if (ely_get_type(e->key) == ely_VALUE_STRING) {
                        arr_push(methods, e->key);
                    }
                }
                e = e->next;
            }
        }
    } else if (t == ely_VALUE_ARRAY) {
        const char* arr_methods[] = {"push", "pop", "len", "insert", "remove", "index"};
        for (int i = 0; i < 6; i++) {
            arr_push(methods, ely_value_new_string(gc_strdup(arr_methods[i])));
        }
    } else if (t == ely_VALUE_STRING) {
        const char* str_methods[] = {"len", "dup", "concat", "cmp", "substr", "trim", "replace"};
        for (int i = 0; i < 7; i++) {
            arr_push(methods, ely_value_new_string(gc_strdup(str_methods[i])));
        }
    } else if (t == ely_VALUE_INT || t == ely_VALUE_DOUBLE) {
        const char* num_methods[] = {"toStr", "abs", "toInt", "toDouble"};
        for (int i = 0; i < 4; i++) {
            arr_push(methods, ely_value_new_string(gc_strdup(num_methods[i])));
        }
    }
    return ely_value_new_array(methods);
}

ely_value ely_invoke(void* func_ptr, ely_value* args, int argc) {
    if (!func_ptr) return ely_value_new_null();
    switch (argc) {
        case 0: {
            ely_value (*f)(void) = (ely_value (*)(void))func_ptr;
            return f();
        }
        case 1: {
            ely_value (*f)(ely_value) = (ely_value (*)(ely_value))func_ptr;
            return f(args[0]);
        }
        case 2: {
            ely_value (*f)(ely_value, ely_value) = (ely_value (*)(ely_value, ely_value))func_ptr;
            return f(args[0], args[1]);
        }
        case 3: {
            ely_value (*f)(ely_value, ely_value, ely_value) = (ely_value (*)(ely_value, ely_value, ely_value))func_ptr;
            return f(args[0], args[1], args[2]);
        }
        case 4: {
            ely_value (*f)(ely_value, ely_value, ely_value, ely_value) = 
                (ely_value (*)(ely_value, ely_value, ely_value, ely_value))func_ptr;
            return f(args[0], args[1], args[2], args[3]);
        }
        default:
            fprintf(stderr, "ely_invoke: too many arguments (%d)\n", argc);
            return ely_value_new_null();
    }
}

ely_value ely_value_call_method(ely_value obj, const char* method_name, ely_value* args, int argc) {
    int obj_type = ely_get_type(obj);
    void* raw_obj = ELY_UNBOX_PTR(obj);

    if (obj_type == ely_VALUE_ARRAY) {
        arr* a = (arr*)raw_obj;
        if (strcmp(method_name, "push") == 0 && argc == 1) {
            arr_push(a, args[0]);
            return ely_value_new_null();
        }
        else if (strcmp(method_name, "pop") == 0) {
            if (argc == 0) {
                ely_value val = arr_pop_value(a);
                return val; // возвращает упакованный ely_value напрямую
            }
            else if (argc == 1 && ely_get_type(args[0]) == ely_VALUE_INT) {
                int idx = (int)ELY_UNBOX_INT(args[0]);
                int res = arr_remove_index(a, idx);
                return ely_value_new_int(res);
            }
        }
        else if (strcmp(method_name, "len") == 0 && argc == 0) {
            return ely_value_new_int(arr_len(a));
        }
        else if (strcmp(method_name, "insert") == 0 && argc == 2) {
            if (ely_get_type(args[0]) == ely_VALUE_INT) {
                int idx = (int)ELY_UNBOX_INT(args[0]);
                arr_insert(a, idx, args[1]);
                return ely_value_new_null();
            }
        }
        else if (strcmp(method_name, "remove") == 0 && argc == 1) {
            int res = arr_remove_value(a, args[0]);
            return ely_value_new_int(res);
        }
        else if (strcmp(method_name, "index") == 0 && argc == 1) {
            int res = arr_index(a, args[0]);
            return ely_value_new_int(res);
        }
    }

    else if (obj_type == ely_VALUE_STRING) {
        const char* s = (const char*)raw_obj;
        if (!s) return ely_value_new_null();

        if (strcmp(method_name, "len") == 0 && argc == 0)
            return ely_value_new_int(strlen(s));
        else if (strcmp(method_name, "dup") == 0 && argc == 0)
            return ely_value_new_string(ely_str_dup(s));
        else if (strcmp(method_name, "trim") == 0 && argc == 0)
            return ely_value_new_string(ely_str_trim(s));
        else if (strcmp(method_name, "concat") == 0 && argc == 1) {
            char* arg_str = ely_value_to_string(args[0]);
            return ely_value_new_string(ely_str_concat(s, arg_str));
        }
        else if (strcmp(method_name, "substr") == 0 && argc == 2) {
            if (ely_get_type(args[0]) == ely_VALUE_INT && ely_get_type(args[1]) == ely_VALUE_INT)
                return ely_value_new_string(ely_str_substr(s, (int)ELY_UNBOX_INT(args[0]), (int)ELY_UNBOX_INT(args[1])));
        }
        else if (strcmp(method_name, "replace") == 0 && argc == 2) {
            if (ely_get_type(args[0]) == ely_VALUE_STRING && ely_get_type(args[1]) == ely_VALUE_STRING) {
                char* target = (char*)ELY_UNBOX_PTR(args[0]);
                char* replacement = (char*)ELY_UNBOX_PTR(args[1]);
                return ely_value_new_string(ely_str_replace(s, target, replacement));
            }
        }
        else if (strcmp(method_name, "cmp") == 0 && argc == 1) {
            if (ely_get_type(args[0]) == ely_VALUE_STRING)
                return ely_value_new_int(ely_str_cmp(s, (char*)ELY_UNBOX_PTR(args[0])));
        }
    }

    else if (obj_type == ely_VALUE_OBJECT) {
        dict* d = (dict*)raw_obj;
        if (!d) return ely_value_new_null();

        if (strcmp(method_name, "keys") == 0 && argc == 0) {
            arr* keys_arr = dict_keys(d);
            return ely_value_new_array(keys_arr);
        }
        else if (strcmp(method_name, "values") == 0 && argc == 0) {
            arr* vals = dict_values(d);
            return ely_value_new_array(vals);
        }
        else if (strcmp(method_name, "has") == 0 && argc == 1) {
            int res = dict_has(d, args[0]);
            return ely_value_new_bool(res);
        }
        else if (strcmp(method_name, "del") == 0 && argc == 1) {
            int res = dict_delete(d, args[0]);
            return ely_value_new_int(res);
        }
        else if (strcmp(method_name, "size") == 0 && argc == 0) {
            return ely_value_new_int(dict_size(d));
        }
    }

    return ely_value_new_null();
}

// ------------------------ Расширенное время ------------------------
#include <time.h>
#ifndef _WIN32
#include <sys/time.h>
#else
#include <windows.h>
#endif

long long ely_time_now_ms(void) {
#ifdef _WIN32
    FILETIME ft;
    GetSystemTimeAsFileTime(&ft);
    ULARGE_INTEGER uli;
    uli.LowPart = ft.dwLowDateTime;
    uli.HighPart = ft.dwHighDateTime;
    const ULONGLONG EPOCH_DIFFERENCE = 116444736000000000ULL;
    uli.QuadPart -= EPOCH_DIFFERENCE;
    return (long long)(uli.QuadPart / 10000);
#else
    struct timeval tv;
    gettimeofday(&tv, NULL);
    return (long long)tv.tv_sec * 1000 + tv.tv_usec / 1000;
#endif
}

ely_value ely_format_time(ely_value seconds_val, ely_value fmt_val) {
    long long seconds = ely_value_as_int(seconds_val);
    char* fmt = ely_value_to_string(fmt_val);
    const char* actual_fmt = fmt ? fmt : "%Y-%m-%d %H:%M:%S";

    time_t t = (time_t)seconds;
    struct tm* tm_info = localtime(&t);
    if (!tm_info) {
        if (fmt) free(fmt);
        return ely_value_new_string("localtime error");
    }

    // Перенос буфера на стек во избежание фрагментации памяти кучи
    char result[1024];
    int ri = 0;
    for (int i = 0; actual_fmt[i] && ri < 1023; ) {
        if (actual_fmt[i] == 'Y' && actual_fmt[i+1] == 'Y' && actual_fmt[i+2] == 'Y' && actual_fmt[i+3] == 'Y') {
            strftime(result + ri, 5, "%Y", tm_info);
            ri += strlen(result + ri);
            i += 4;
        } else if (actual_fmt[i] == 'M' && actual_fmt[i+1] == 'M') {
            strftime(result + ri, 3, "%m", tm_info);
            ri += strlen(result + ri);
            i += 2;
        } else if (actual_fmt[i] == 'D' && actual_fmt[i+1] == 'D') {
            strftime(result + ri, 3, "%d", tm_info);
            ri += strlen(result + ri);
            i += 2;
        } else if (actual_fmt[i] == 'h' && actual_fmt[i+1] == 'h') {
            strftime(result + ri, 3, "%H", tm_info);
            ri += strlen(result + ri);
            i += 2;
        } else if (actual_fmt[i] == 'm' && actual_fmt[i+1] == 'm') {
            strftime(result + ri, 3, "%M", tm_info);
            ri += strlen(result + ri);
            i += 2;
        } else if (actual_fmt[i] == 's' && actual_fmt[i+1] == 's') {
            strftime(result + ri, 3, "%S", tm_info);
            ri += strlen(result + ri);
            i += 2;
        } else {
            result[ri++] = actual_fmt[i++];
        }
    }
    result[ri] = '\0';
    if (fmt) free(fmt);
    
    return ely_value_new_string(result);
}

long long ely_parse_time(const char* str, const char* fmt) {
    if (!str || !fmt) return 0;
    struct tm tm_info = {0};
#ifdef _WIN32
    if (strcmp(fmt, "%Y-%m-%d %H:%M:%S") == 0) {
        int year, month, day, hour, min, sec;
        if (sscanf(str, "%d-%d-%d %d:%d:%d", &year, &month, &day, &hour, &min, &sec) == 6) {
            tm_info.tm_year = year - 1900;
            tm_info.tm_mon  = month - 1;
            tm_info.tm_mday = day;
            tm_info.tm_hour = hour;
            tm_info.tm_min  = min;
            tm_info.tm_sec  = sec;
            tm_info.tm_isdst = -1;
            return (long long)mktime(&tm_info);
        }
    }
    return 0;
#else
    if (strptime(str, fmt, &tm_info) == NULL) return 0;
    return (long long)mktime(&tm_info);
#endif
}

/* ------------------------ Случайные числа ------------------------ */
ely_int ely_rand_int(void) {
    return (ely_int)ely_rand();
}

ely_int ely_rand_int_range(ely_int min, ely_int max) {
    if (min >= max) return min;
    return min + (ely_rand() % (max - min + 1));
}

ely_bool ely_rand_bool(void) {
    return (ely_rand() % 2) ? 1 : 0;
}

int ely_file_write_all_simple(const char* path, const char* data) {
    return ely_file_write_all(path, data, strlen(data));
}
char* ely_file_read_all_simple(const char* path) {
    size_t len;
    char* data = ely_file_read_all(path, &len);
    return data;
}

ely_value ely_to_int(ely_value v) {
    if (ely_is_int(v)) return v;
    
    if (ely_is_double(v)) {
        return ely_box_int((int64_t)ely_unbox_double(v));
    }
    
    if (ely_is_bool(v)) {
        return ely_box_int(ely_unbox_bool(v) ? 1 : 0);
    }
    
    // Если это строка из кучи
    if (ely_is_ptr(v) && get_heap_obj_type(ely_unbox_ptr(v)) == GC_OBJ_STRING) {
        const char* str = (const char*)ely_unbox_ptr(v);
        return ely_box_int((int64_t)strtoll(str, NULL, 10));
    }
    
    // Если это инлайновая строка Tier 0 (реализация ниже в п.3)
    if ((v & ELY_TAG_MASK) == ELY_TAG_STR0) {
        char buf[8];
        ely_unbox_inline_str(v, buf);
        return ely_box_int((int64_t)strtoll(buf, NULL, 10));
    }
    
    return ely_box_int(0);
}

ely_value ely_to_double(ely_value v) {
    if (ely_is_double(v)) return v;
    
    if (ely_is_int(v)) {
        return ely_box_double((double)ely_unbox_int(v));
    }
    
    if (ely_is_bool(v)) {
        return ely_box_double(ely_unbox_bool(v) ? 1.0 : 0.0);
    }
    
    if (ely_is_ptr(v) && get_heap_obj_type(ely_unbox_ptr(v)) == GC_OBJ_STRING) {
        const char* str = (const char*)ely_unbox_ptr(v);
        return ely_box_double(strtod(str, NULL));
    }
    
    if ((v & ELY_TAG_MASK) == ELY_TAG_STR0) {
        char buf[8];
        ely_unbox_inline_str(v, buf);
        return ely_box_double(strtod(buf, NULL));
    }
    
    return ely_box_double(0.0);
}

ely_value ely_make_arr(ely_value elem) {
    // Создаем внутреннюю структуру массива
    arr* a = arr_new(); 
    
    // Пушим элемент (теперь elem — это не указатель, а само 64-битное значение)
    arr_push(a, elem); 
    
    // Упаковываем указатель на массив в ely_value
    return ely_box_ptr(a);
}

ely_value ely_dyn_arr(ely_value elem) {
    arr* a = arr_new();
    arr_push(a, elem);
    return ely_value_new_array(a);
}

void ely_chdir_to_exe_dir(void) {
#ifdef _WIN32
    char exe_path[4096];
    DWORD len = GetModuleFileNameA(NULL, exe_path, sizeof(exe_path));
    if (len > 0 && len < sizeof(exe_path)) {
        char* last_slash = (char*)strrchr(exe_path, '\\');
        if (last_slash) {
            *last_slash = '\0';
            SetCurrentDirectoryA(exe_path);
        }
    }
#else
    char exe_path[4096];
    ssize_t len = readlink("/proc/self/exe", exe_path, sizeof(exe_path) - 1);
    if (len > 0 && len < (ssize_t)sizeof(exe_path)) {
        exe_path[len] = '\0';
        char* last_slash = (char*)strrchr(exe_path, '/');
        if (last_slash) {
            *last_slash = '\0';
            chdir(exe_path);
        }
    }
#endif
}

// SS0 =============================================================================
ely_value ely_immediate_str_encode(const char* str, size_t len) {
    if (len > 7) return 0; // Не влезает, нужно слать в кучу

    ely_value val = ELY_TAG_STR0;
    val |= ((ely_value)len << ELY_STR_LEN_SHIFT);

    for (size_t i = 0; i < len; i++) {
        val |= ((ely_value)(unsigned char)str[i] << (ELY_STR_DATA_SHIFT + (i * 8)));
    }
    return val;
}

void ely_immediate_str_get_chars(ely_value val, char* out_buf) {
    size_t len = ely_immediate_str_len(val);
    for (size_t i = 0; i < len; i++) {
        out_buf[i] = (char)((val >> (ELY_STR_DATA_SHIFT + (i * 8))) & 0xFF);
    }
    out_buf[len] = '\0';
}