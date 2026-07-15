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
#include <sys/time.h>
#endif
#include "ely_value.h"

#ifndef _WIN32
#define my_strtoll strtoll
#define my_strtoull strtoull
#else
static long long my_strtoll(const char *nptr, char **endptr, int base) {
    return _strtoi64(nptr, endptr, base);
}
static unsigned long long my_strtoull(const char *nptr, char **endptr, int base) {
    return _strtoui64(nptr, endptr, base);
}
#endif

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
}
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
 *  Высокопроизводительный Потоковый Буфер Сериализации JSON
 * =========================================================================== */
typedef struct {
    char* data;
    size_t len;
    size_t cap;
} json_buf_t;

static void json_buf_init(json_buf_t* b) {
    b->cap = 256;
    b->data = (char*)malloc(b->cap);
    b->len = 0;
    b->data[0] = '\0';
}

static void json_buf_append(json_buf_t* b, const char* s, size_t len) {
    if (b->len + len >= b->cap) {
        b->cap = (b->len + len) * 2 + 128;
        b->data = (char*)realloc(b->data, b->cap);
    }
    memcpy(b->data + b->len, s, len);
    b->len += len;
    b->data[b->len] = '\0';
}

static void json_buf_append_str(json_buf_t* b, const char* s) {
    json_buf_append(b, s, strlen(s));
}

static void serialize_string(json_buf_t* b, const char* s) {
    json_buf_append(b, "\"", 1);
    while (*s) {
        if (*s == '"' || *s == '\\') {
            json_buf_append(b, "\\", 1);
            json_buf_append(b, s, 1);
        } else if (*s == '\n') json_buf_append(b, "\\n", 2);
        else if (*s == '\r') json_buf_append(b, "\\r", 2);
        else if (*s == '\t') json_buf_append(b, "\\t", 2);
        else json_buf_append(b, s, 1);
        s++;
    }
    json_buf_append(b, "\"", 1);
}

static void serialize_value(json_buf_t* b, ely_value v) {
    int type = ely_get_type(v);
    char tmp[64];
    
    switch (type) {
        case ely_VALUE_NULL:
            json_buf_append_str(b, "null");
            break;
        case ely_VALUE_BOOL:
            json_buf_append_str(b, ely_unbox_bool(v) ? "true" : "false");
            break;
        case ely_VALUE_INT:
            snprintf(tmp, sizeof(tmp), "%lld", (long long)ely_unbox_int(v));
            json_buf_append_str(b, tmp);
            break;
        case ely_VALUE_DOUBLE:
            snprintf(tmp, sizeof(tmp), "%g", ely_unbox_double(v));
            json_buf_append_str(b, tmp);
            break;
        case ely_VALUE_STRING: {
            if (ely_is_immediate_str(v)) {
                ely_unbox_inline_str(v, tmp);
                serialize_string(b, tmp);
            } else {
                serialize_string(b, (const char*)ely_unbox_ptr(v));
            }
            break;
        }
        case ely_VALUE_ARRAY: {
            arr* a = (arr*)ely_unbox_ptr(v);
            json_buf_append(b, "[", 1);
            size_t length = arr_len(a);
            for (size_t i = 0; i < length; i++) {
                if (i > 0) json_buf_append(b, ",", 1);
                serialize_value(b, arr_get(a, i));
            }
            json_buf_append(b, "]", 1);
            break;
        }
        case ely_VALUE_OBJECT: {
            dict* d = (dict*)ely_unbox_ptr(v);
            json_buf_append(b, "{", 1);
            int first = 1;
            for (size_t i = 0; i < d->capacity; i++) {
                dict_entry* e = d->buckets[i];
                while (e) {
                    if (!first) json_buf_append(b, ",", 1);
                    first = 0;
                    
                    if (ely_get_type(e->key) == ely_VALUE_STRING) {
                        serialize_value(b, e->key);
                    } else {
                        json_buf_append(b, "\"", 1);
                        char* key_str = ely_value_to_string(e->key);
                        json_buf_append_str(b, key_str);
                        free(key_str);
                        json_buf_append(b, "\"", 1);
                    }
                    json_buf_append(b, ":", 1);
                    serialize_value(b, e->value);
                    e = e->next;
                }
            }
            json_buf_append(b, "}", 1);
            break;
        }
        default:
            json_buf_append_str(b, "null");
            break;
    }
}

char* ely_value_to_json(ely_value v) {
    json_buf_t b;
    json_buf_init(&b);
    serialize_value(&b, v);
    return b.data;
}

char* ely_value_to_string(ely_value v) {
    int type = ely_get_type(v);
    char* buf = (char*)malloc(128);
    if (!buf) return NULL;

    switch (type) {
        case ely_VALUE_NULL:   strcpy(buf, "null"); return buf;
        case ely_VALUE_BOOL:   strcpy(buf, ely_unbox_bool(v) ? "true" : "false"); return buf;
        case ely_VALUE_INT:    snprintf(buf, 128, "%lld", (long long)ely_unbox_int(v)); return buf;
        case ely_VALUE_DOUBLE: snprintf(buf, 128, "%g", ely_unbox_double(v)); return buf;
        case ely_VALUE_STRING: {
            if (ely_is_immediate_str(v)) {
                ely_unbox_inline_str(v, buf);
                return buf;
            }
            free(buf);
            return strdup((const char*)ely_unbox_ptr(v));
        }
        case ely_VALUE_ARRAY:
        case ely_VALUE_OBJECT:
            free(buf);
            return ely_value_to_json(v);
        default:
            strcpy(buf, "[unknown]");
            return buf;
    }
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
        char* str = ely_value_to_string(index);
        ely_value res = dict_get_str(d, str);
        free(str);
        return res;
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
        char* str = ely_value_to_string(index);
        dict_set_str(d, str, value);
        free(str);
    }
}

/* ===========================================================================
 *  Парсер JSON
 * =========================================================================== */
typedef struct {
    const char* str;
    size_t pos;
    size_t len;
} json_parser_t;

static void json_skip_ws(json_parser_t* p) {
    while (p->pos < p->len && isspace((unsigned char)p->str[p->pos])) p->pos++;
}

static char json_peek(json_parser_t* p) {
    return p->pos >= p->len ? '\0' : p->str[p->pos];
}

static int json_consume(json_parser_t* p, char expected) {
    json_skip_ws(p);
    if (p->pos < p->len && p->str[p->pos] == expected) {
        p->pos++;
        return 1;
    }
    return 0;
}

static ely_value json_parse_value(json_parser_t* p);

static ely_value json_parse_string(json_parser_t* p) {
    if (!json_consume(p, '"')) return ELY_VAL_NULL;
    size_t start = p->pos;
    while (p->pos < p->len && p->str[p->pos] != '"') {
        if (p->str[p->pos] == '\\') p->pos++;
        p->pos++;
    }
    size_t end = p->pos;
    json_consume(p, '"');
    
    size_t length = end - start;
    char* tmp = (char*)malloc(length + 1);
    memcpy(tmp, p->str + start, length);
    tmp[length] = '\0';
    
    ely_value res = ely_value_new_string(tmp);
    free(tmp);
    return res;
}

static ely_value json_parse_number(json_parser_t* p) {
    json_skip_ws(p);
    const char* start = p->str + p->pos;
    char* endptr;
    double d = strtod(start, &endptr);
    size_t consumed = endptr - start;
    
    int is_double = 0;
    for (size_t i = 0; i < consumed; i++) {
        if (start[i] == '.' || start[i] == 'e' || start[i] == 'E') {
            is_double = 1; break;
        }
    }
    p->pos += consumed;
    if (is_double) return ely_box_double(d);
    return ely_box_int(strtoll(start, NULL, 10));
}

static ely_value json_parse_object(json_parser_t* p) {
    if (!json_consume(p, '{')) return ELY_VAL_NULL;
    dict* d = dict_new((dict_hash_func)ely_dict_str_hash, (dict_cmp_func)ely_dict_str_cmp);
    
    while (1) {
        json_skip_ws(p);
        if (json_peek(p) == '}') {
            json_consume(p, '}');
            break;
        }
        ely_value key_val = json_parse_string(p);
        json_skip_ws(p);
        json_consume(p, ':');
        ely_value val = json_parse_value(p);
        
        char key_buf[64];
        const char* key_ptr = ely_is_immediate_str(key_val) ? (ely_unbox_inline_str(key_val, key_buf), key_buf) : (const char*)ely_unbox_ptr(key_val);
        dict_set_str(d, key_ptr, val);
        
        json_skip_ws(p);
        if (json_peek(p) == ',') json_consume(p, ',');
        else if (json_peek(p) == '}') continue;
        else break;
    }
    return ely_value_new_object(d);
}

static ely_value json_parse_array(json_parser_t* p) {
    if (!json_consume(p, '[')) return ELY_VAL_NULL;
    arr* a = arr_new();
    while (1) {
        json_skip_ws(p);
        if (json_peek(p) == ']') {
            json_consume(p, ']');
            break;
        }
        arr_push(a, json_parse_value(p));
        json_skip_ws(p);
        if (json_peek(p) == ',') json_consume(p, ',');
        else if (json_peek(p) == ']') continue;
        else break;
    }
    return ely_value_new_array(a);
}

static ely_value json_parse_value(json_parser_t* p) {
    json_skip_ws(p);
    char c = json_peek(p);
    if (c == '"') return json_parse_string(p);
    if (c == '{') return json_parse_object(p);
    if (c == '[') return json_parse_array(p);
    if (c == '-' || isdigit((unsigned char)c)) return json_parse_number(p);
    if (strncmp(p->str + p->pos, "true", 4) == 0) { p->pos += 4; return ELY_VAL_TRUE; }
    if (strncmp(p->str + p->pos, "false", 5) == 0) { p->pos += 5; return ELY_VAL_FALSE; }
    if (strncmp(p->str + p->pos, "null", 4) == 0) { p->pos += 4; return ELY_VAL_NULL; }
    return ELY_VAL_NULL;
}

dict* ely_dictify(const char* json_str) {
    if (!json_str) return NULL;
    json_parser_t p = { json_str, 0, strlen(json_str) };
    ely_value v = json_parse_object(&p);
    return ELY_IS_NULL(v) ? NULL : (dict*)ely_unbox_ptr(v);
}

ely_value ely_value_from_json(const char* json, size_t* pos) {
    (void)pos;
    json_parser_t p = { json, 0, strlen(json) };
    return json_parse_value(&p);
}

/* ===========================================================================
 *  Слой обратной совместимости
 * =========================================================================== */
void del(ely_value dict_val, char *key) { ely_dict_del(dict_val, ely_value_new_string(key)); }
int has(ely_value dict_val, char *key) { return dict_has_str((dict*)ely_unbox_ptr(dict_val), key); }
char* toJson(ely_value dict_val) { return ely_value_to_json(dict_val); }
ely_value keys(ely_value dict_val) {
    dict* d = (dict*)ely_unbox_ptr(dict_val);
    arr* a = arr_new();
    if (d) {
        for (size_t i = 0; i < d->capacity; i++) {
            dict_entry* e = d->buckets[i];
            while (e) { arr_push(a, e->key); e = e->next; }
        }
    }
    return ely_value_new_array(a);
}

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

void ely_array_push(ely_value arr_val, ely_value elem) { arr_push((arr*)ely_unbox_ptr(arr_val), elem); }
ely_value ely_array_pop(ely_value arr_val) { return arr_pop_value((arr*)ely_unbox_ptr(arr_val)); }
size_t ely_array_len(ely_value arr_val) { return arr_len((arr*)ely_unbox_ptr(arr_val)); }
ely_value ely_array_get(ely_value arr_val, size_t index) { return arr_get((arr*)ely_unbox_ptr(arr_val), index); }
void ely_array_set(ely_value arr_val, size_t index, ely_value elem) { arr_set((arr*)ely_unbox_ptr(arr_val), index, elem); }

ely_value ely_dict_get(ely_value dict_val, ely_value key) {
    char buf[64];
    const char* k = ely_is_immediate_str(key) ? (ely_unbox_inline_str(key, buf), buf) : (const char*)ely_unbox_ptr(key);
    return dict_get_str((dict*)ely_unbox_ptr(dict_val), k);
}

void ely_dict_set(ely_value dict_val, ely_value key, ely_value value) {
    char buf[64];
    const char* k = ely_is_immediate_str(key) ? (ely_unbox_inline_str(key, buf), buf) : (const char*)ely_unbox_ptr(key);
    dict_set_str((dict*)ely_unbox_ptr(dict_val), k, value);
}

void ely_dict_del(ely_value dict_val, ely_value key) {
    char buf[64];
    const char* k = ely_is_immediate_str(key) ? (ely_unbox_inline_str(key, buf), buf) : (const char*)ely_unbox_ptr(key);
    dict_delete_str((dict*)ely_unbox_ptr(dict_val), k);
}

char* ely_array_to_json(ely_value arr_val) { return ely_value_to_json(arr_val); }

/* ===========================================================================
 *  Консоль и Строковые Утилиты
 * =========================================================================== */
void ely_println_str(const char* str) {
    if (str) fputs(str, stdout);
    putchar('\n'); fflush(stdout);
}

void ely_print_int(ely_value n)    { printf("%lld\n", (long long)ely_unbox_int(n)); fflush(stdout); }
void ely_print_byte(ely_value b)   { printf("%d\n", (int)(int8_t)ely_unbox_int(b)); fflush(stdout); }
void ely_print_char(ely_value c)   { putchar((char)ely_unbox_int(c)); putchar('\n'); fflush(stdout); }
void ely_print_bool(ely_value b)   { fputs(ely_unbox_bool(b) ? "true\n" : "false\n", stdout); fflush(stdout); }
void ely_print_double(ely_value d) { printf("%g\n", ely_unbox_double(d)); fflush(stdout); }

// Удалена функция ely_value_as_int во избежание конфликта (уже реализована в virtual_main.cpp:30)

ely_str ely_input(void) {
    char buffer[1024];
    if (fgets(buffer, sizeof(buffer), stdin)) {
        size_t len = strlen(buffer);
        if (len && buffer[len-1] == '\n') buffer[len-1] = '\0';
        char* res = (char*)gc_alloc(strlen(buffer) + 1, GC_OBJ_STRING);
        if (res) strcpy(res, buffer);
        return res;
    }
    return NULL;
}

ely_str ely_input_prompt(const char* prompt) { if (prompt) fputs(prompt, stdout); return ely_input(); }

ely_int ely_str_to_int(const char* str) { return str ? (ely_int)my_strtoll(str, NULL, 10) : 0; }
ely_uint ely_str_to_uint(const char* str) { return str ? (ely_uint)my_strtoull(str, NULL, 10) : 0; }
ely_more ely_str_to_more(const char* str) { return str ? my_strtoll(str, NULL, 10) : 0; }
ely_umore ely_str_to_umore(const char* str) { return str ? my_strtoull(str, NULL, 10) : 0; }
ely_flt ely_str_to_flt(const char* str) { return str ? (ely_flt)strtod(str, NULL) : 0.0f; }
ely_double ely_str_to_double(const char* str) { return str ? strtod(str, NULL) : 0.0; }

static ely_str _gc_alloc_str(const char* buf) {
    size_t len = strlen(buf);
    char* res = (char*)gc_alloc(len + 1, GC_OBJ_STRING);
    if (res) memcpy(res, buf, len + 1);
    return res;
}
ely_str ely_int_to_str(ely_int n) { char b[32]; snprintf(b, 32, "%d", n); return _gc_alloc_str(b); }
ely_str ely_uint_to_str(ely_uint n) { char b[32]; snprintf(b, 32, "%u", n); return _gc_alloc_str(b); }
ely_str ely_more_to_str(ely_more n) { char b[32]; snprintf(b, 32, "%lld", n); return _gc_alloc_str(b); }
ely_str ely_umore_to_str(ely_umore n) { char b[32]; snprintf(b, 32, "%llu", n); return _gc_alloc_str(b); }
ely_str ely_flt_to_str(ely_flt f) { char b[64]; snprintf(b, 64, "%g", (double)f); return _gc_alloc_str(b); }
ely_str ely_double_to_str(ely_double d) { char b[64]; snprintf(b, 64, "%g", d); return _gc_alloc_str(b); }
ely_str ely_bool_to_str(ely_bool b) { return _gc_alloc_str(b ? "true" : "false"); }

size_t      ely_str_len(const char* str) { return str ? strlen(str) : 0; }
ely_str     ely_str_dup(const char* str) { return str ? _gc_alloc_str(str) : NULL; }

ely_str ely_str_concat(const char* a, const char* b) {
    if (!a && !b) return NULL;
    size_t la = a ? strlen(a) : 0;
    size_t lb = b ? strlen(b) : 0;
    char* res = (char*)gc_alloc(la + lb + 1, GC_OBJ_STRING);
    if (la) memcpy(res, a, la);
    if (lb) memcpy(res + la, b, lb);
    res[la+lb] = '\0';
    return res;
}

int ely_str_cmp(const char* a, const char* b) { return strcmp(a ? a : "", b ? b : ""); }

ely_str ely_str_substr(const char* str, size_t start, size_t len) {
    if (!str) return NULL;
    size_t slen = strlen(str);
    if (start >= slen) return _gc_alloc_str("");
    if (start + len > slen) len = slen - start;
    char* res = (char*)gc_alloc(len + 1, GC_OBJ_STRING);
    memcpy(res, str + start, len);
    res[len] = '\0';
    return res;
}

ely_str ely_str_trim(const char* str) {
    if (!str) return NULL;
    while (*str && isspace((unsigned char)*str)) str++;
    size_t len = strlen(str);
    while (len > 0 && isspace((unsigned char)str[len-1])) len--;
    char* res = (char*)gc_alloc(len + 1, GC_OBJ_STRING);
    memcpy(res, str, len);
    res[len] = '\0';
    return res;
}

ely_str ely_str_replace(const char* str, const char* old, const char* new_str) {
    if (!str || !old || strlen(old) == 0) return ely_str_dup(str);
    size_t old_len = strlen(old);
    size_t new_len = new_str ? strlen(new_str) : 0;
    
    size_t count = 0;
    const char* pos = str;
    while ((pos = strstr(pos, old))) { count++; pos += old_len; }
    if (count == 0) return ely_str_dup(str);
    
    size_t r_len = strlen(str) + count * (new_len - old_len);
    char* res = (char*)gc_alloc(r_len + 1, GC_OBJ_STRING);
    char* out = res;
    pos = str;
    while (*pos) {
        char* found = (char*)strstr(pos, old);
        if (found) {
            size_t before = found - pos;
            memcpy(out, pos, before); out += before;
            if (new_str) { memcpy(out, new_str, new_len); out += new_len; }
            pos = found + old_len;
        } else {
            strcpy(out, pos); break;
        }
    }
    return res;
}

/* ===========================================================================
 *  Математика и Рандом
 * =========================================================================== */
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

static unsigned int rand_seed = 1;
void ely_srand(ely_uint seed) { rand_seed = seed; }
ely_int ely_rand(void) { rand_seed = rand_seed * 1103515245 + 12345; return (ely_int)((rand_seed >> 16) & 0x7FFF); }
ely_double ely_rand_double(void) { return (ely_double)ely_rand() / 32767.0; }
ely_int ely_rand_int(void) { return ely_rand(); }
ely_int ely_rand_int_range(ely_int min, ely_int max) { return min >= max ? min : min + (ely_rand() % (max - min + 1)); }
ely_bool ely_rand_bool(void) { return (ely_rand() % 2) != 0; }

/* ===========================================================================
 *  Время и Файловая Система
 * =========================================================================== */
void ely_sleep(ely_uint milliseconds) {
#ifdef _WIN32
    Sleep(milliseconds);
#else
    usleep(milliseconds * 1000);
#endif
}
ely_more ely_time_now(void) { return (ely_more)time(NULL); }
double ely_time_diff(ely_more start, ely_more end) { return (double)(end - start); }

long long ely_time_now_ms(void) {
#ifdef _WIN32
    FILETIME ft; GetSystemTimeAsFileTime(&ft);
    ULARGE_INTEGER uli; uli.LowPart = ft.dwLowDateTime; uli.HighPart = ft.dwHighDateTime;
    return (long long)((uli.QuadPart - 116444736000000000ULL) / 10000);
#else
    struct timeval tv; gettimeofday(&tv, NULL);
    return (long long)tv.tv_sec * 1000 + tv.tv_usec / 1000;
#endif
}

ely_value ely_format_time(ely_value seconds_val, ely_value fmt_val) {
    time_t t = (time_t)ely_unbox_int(seconds_val);
    char fmt_buf[64];
    const char* f = ely_is_immediate_str(fmt_val) ? (ely_unbox_inline_str(fmt_val, fmt_buf), fmt_buf) : (const char*)ely_unbox_ptr(fmt_val);
    
    struct tm* tm_info = localtime(&t);
    char out[256];
    strftime(out, sizeof(out), f ? f : "%Y-%m-%d %H:%M:%S", tm_info);
    return ely_value_new_string(out);
}

// Исправлена сигнатура — удалена утекшая разметка [source: 15]
long long ely_parse_time(const char* str, const char* fmt) {
    if (!str || !fmt) return 0;
    struct tm tm_info = {0};
#ifdef _WIN32
    int y, m, d, h, min, s;
    if (sscanf(str, "%d-%d-%d %d:%d:%d", &y, &m, &d, &h, &min, &s) == 6) {
        tm_info.tm_year = y - 1900; tm_info.tm_mon = m - 1; tm_info.tm_mday = d;
        tm_info.tm_hour = h; tm_info.tm_min = min; tm_info.tm_sec = s;
        return (long long)mktime(&tm_info);
    }
    return 0;
#else
    if (!strptime(str, fmt, &tm_info)) return 0;
    return (long long)mktime(&tm_info);
#endif
}

struct ely_file { FILE* fp; };
ely_file* ely_file_open(const char* path, const char* mode) {
    FILE* fp = fopen(path, mode);
    if (!fp) return NULL;
    ely_file* f = (ely_file*)gc_alloc(sizeof(ely_file), GC_OBJ_STRING);
    f->fp = fp;
    return f;
}
void ely_file_close(ely_file* f) { if (f && f->fp) fclose(f->fp); }
int ely_file_write(ely_file* f, const char* data, size_t len) { return (f && f->fp && fwrite(data, 1, len, f->fp) == len) ? 0 : -1; }

char* ely_file_read(ely_file* f, size_t* out_len) {
    if (!f || !f->fp) return NULL;
    size_t c = 1024, t = 0;
    char* buf = (char*)malloc(c);
    char tmp[1024];
    while (1) {
        size_t n = fread(tmp, 1, sizeof(tmp), f->fp);
        if (n == 0) break;
        if (t + n >= c) { c = (t + n) * 2; buf = (char*)realloc(buf, c); }
        memcpy(buf + t, tmp, n); t += n;
    }
    if (out_len) *out_len = t;
    buf[t] = '\0';
    return buf;
}

int ely_file_exists(const char* path) { FILE* f = fopen(path, "r"); if (f) { fclose(f); return 1; } return 0; }
char* ely_file_read_all(const char* path, size_t* out_len) {
    ely_file* f = ely_file_open(path, "rb"); if (!f) return NULL;
    char* d = ely_file_read(f, out_len); ely_file_close(f); return d;
}
int ely_file_remove(const char* path) { return remove(path); }
int ely_file_rename(const char* old, const char* new_path) { return rename(old, new_path); }
int ely_file_write_all(const char* path, const char* data, size_t len) {
    FILE* f = fopen(path, "wb"); if (!f) return -1;
    size_t w = fwrite(data, 1, len, f); fclose(f); return (w == len) ? 0 : -1;
}
int ely_file_write_all_simple(const char* path, const char* data) { return ely_file_write_all(path, data, strlen(data)); }
char* ely_file_read_all_simple(const char* path) { size_t l; return ely_file_read_all(path, &l); }

ely_str ely_path_join(const char* a, const char* b) {
    if (!a && !b) return NULL;
    char buf[4096]; snprintf(buf, sizeof(buf), "%s/%s", a ? a : "", b ? b : "");
    return _gc_alloc_str(buf);
}
ely_str ely_path_basename(const char* path) {
    if (!path) return NULL;
    const char* s = strrchr(path, '/'); if (!s) s = strrchr(path, '\\');
    return _gc_alloc_str(s ? s + 1 : path);
}
ely_str ely_path_dirname(const char* path) {
    if (!path) return NULL;
    const char* s = strrchr(path, '/'); if (!s) s = strrchr(path, '\\');
    if (!s) return _gc_alloc_str(".");
    size_t len = s - path;
    char* res = (char*)gc_alloc(len + 1, GC_OBJ_STRING);
    memcpy(res, path, len); res[len] = '\0';
    return res;
}
int ely_path_is_absolute(const char* path) {
    if (!path) return 0;
    if (path[0] == '/' || path[0] == '\\') return 1;
    if (path[0] && path[1] == ':') return 1;
    return 0;
}

void* ely_load_library(const char* path) { return path ? (void*)
#ifdef _WIN32
    LoadLibraryA(path)
#else
    dlopen(path, RTLD_LAZY)
#endif
    : NULL;
}
void* ely_get_function(void* lib, const char* name) { return (lib && name) ? (void*)
#ifdef _WIN32
    GetProcAddress((HMODULE)lib, name)
#else
    dlsym(lib, name)
#endif
    : NULL;
}
void ely_close_library(void* lib) { if (lib) { 
#ifdef _WIN32
    FreeLibrary((HMODULE)lib);
#else
    dlclose(lib);
#endif
}}

/* ===========================================================================
 *  Рефлексия и Метод-Диспетчеры
 * =========================================================================== */
ely_bool isType(ely_value value, const char* type_name) {
    if (!type_name) return 0;
    return strcmp(ely_typeof(value), type_name) == 0;
}
ely_bool isNull(ely_value value) { return ely_get_type(value) == ely_VALUE_NULL; }
ely_bool isIn(ely_value value, arr* in) {
    if (!in) return 0;
    for (size_t i = 0; i < arr_len(in); i++) {
        if (ely_value_eq(value, arr_get(in, i)) == ELY_VAL_TRUE) return 1;
    }
    return 0;
}

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
        dict* d = (dict*)ely_unbox_ptr(v);
        for (size_t i = 0; i < d->capacity; i++) {
            dict_entry* e = d->buckets[i];
            while (e) { arr_push(fields, e->key); e = e->next; }
        }
    }
    return ely_value_new_array(fields);
}

ely_value ely_value_get_methods(ely_value v) {
    arr* methods = arr_new();
    int t = ely_get_type(v);
    if (t == ely_VALUE_ARRAY) {
        const char* m[] = {"push", "pop", "len", "insert", "remove", "index"};
        for (int i = 0; i < 6; i++) arr_push(methods, ely_value_new_string(m[i]));
    } else if (t == ely_VALUE_STRING) {
        const char* m[] = {"len", "dup", "concat", "cmp", "substr", "trim", "replace"};
        for (int i = 0; i < 7; i++) arr_push(methods, ely_value_new_string(m[i]));
    }
    return ely_value_new_array(methods);
}

ely_value ely_value_call_method(ely_value obj, const char* method_name, ely_value* args, int argc) {
    int obj_type = ely_get_type(obj);
    void* raw_obj = ely_unbox_ptr(obj);

    if (obj_type == ely_VALUE_ARRAY) {
        arr* a = (arr*)raw_obj;
        if (strcmp(method_name, "push") == 0 && argc == 1) { arr_push(a, args[0]); return ELY_VAL_NULL; }
        if (strcmp(method_name, "pop") == 0 && argc == 0) return arr_pop_value(a);
        if (strcmp(method_name, "len") == 0 && argc == 0) return ely_box_int(arr_len(a));
    } else if (obj_type == ely_VALUE_STRING) {
        char buf[64];
        const char* s = ely_is_immediate_str(obj) ? (ely_unbox_inline_str(obj, buf), buf) : (const char*)raw_obj;
        if (strcmp(method_name, "len") == 0 && argc == 0) return ely_box_int(strlen(s));
    }
    return ELY_VAL_NULL;
}

void ely_chdir_to_exe_dir(void) {
    char p[4096];
#ifdef _WIN32
    DWORD len = GetModuleFileNameA(NULL, p, sizeof(p));
    // Приведение типов для безопасной компиляции в режиме C++
    if (len > 0) { char* s = (char*)strrchr(p, '\\'); if (s) { *s = '\0'; SetCurrentDirectoryA(p); } }
#else
    ssize_t len = readlink("/proc/self/exe", p, sizeof(p) - 1);
    if (len > 0) { p[len] = '\0'; char* s = (char*)strrchr(p, '/'); if (s) { *s = '\0'; chdir(p); } }
#endif
}

ely_value ely_make_arr(ely_value elem) { arr* a = arr_new(); arr_push(a, elem); return ely_box_ptr(a); }
ely_value ely_dyn_arr(ely_value elem) { return ely_value_new_array((arr*)ely_unbox_ptr(ely_make_arr(elem))); }
void ely_immediate_str_get_chars(ely_value val, char* out_buf) { ely_unbox_inline_str(val, out_buf); }