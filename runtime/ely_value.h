// ely_value.h
#ifndef ELY_VALUE_H
#define ELY_VALUE_H

#include <stdint.h>
#include <stdbool.h>
#include <string.h>

// Единый тип для всей системы
typedef uint64_t ely_value;

// Маски и теги (Младшие 3 бита - Ex-Boxing)
#define ELY_TAG_MASK        0x07ULL
#define ELY_TAG_PTR         0x00ULL  // 000 - Указатель на объект в куче GC (8-byte aligned)
#define ELY_TAG_INT         0x01ULL  // 001 - 61-битное целое число
#define ELY_TAG_STR0        0x02ULL  // 010 - Инлайн-строка (SSO)
#define ELY_TAG_CONST       0x03ULL  // 011 - Константы (Bool, Null)
#define ELY_TAG_FLOAT       0x04ULL  // 100 - 32-битный Float

#define ELY_STR_DATA_SHIFT  8

// Константы
#define ELY_VAL_FALSE       ((0ULL << 3) | ELY_TAG_CONST)
#define ELY_VAL_TRUE        ((1ULL << 3) | ELY_TAG_CONST)
#define ELY_VAL_NULL        ((2ULL << 3) | ELY_TAG_CONST)

#define ELY_INT61_MAX       ((1LL << 60) - 1)
#define ELY_INT61_MIN       (-(1LL << 60))

// ===================================================================
// ЕДИНЫЙ КЛАССИФИКАТОР ОБЪЕКТОВ КУЧИ
// ===================================================================
#define ELY_HEAP_STRING     0
#define ELY_HEAP_DOUBLE     1
#define ELY_HEAP_ARRAY      2
#define ELY_HEAP_DICT       3
#define ELY_HEAP_FUNCTION   4

typedef struct ElyHeapObject {
    uint8_t type;
} ElyHeapObject;

typedef struct ElyHeapString {
    ElyHeapObject base;
    size_t length;
    char data[1];
} ElyHeapString;

typedef struct ElyHeapDouble {
    ElyHeapObject base;
    double value;
} ElyHeapDouble;

typedef struct {
    ElyHeapObject base;
    void* func_ptr;
    const char* name;
    int arity;   
} ElyHeapFunction;

// ===================================================================
// 1. БАЗОВЫЕ МАКРОСЫ И ПРОВЕРКИ
// ===================================================================
#define ELY_UNBOX_PTR(v)      ((void*)((uintptr_t)(v) & ~(uintptr_t)ELY_TAG_MASK))
#define ELY_BOX_PTR(ptr)      ((ely_value)((uintptr_t)(ptr) | ELY_TAG_PTR))

#define ELY_UNBOX_INT(v)      (((int64_t)(v)) >> 3)
#define ELY_BOX_INT(val)      ((((ely_value)(val)) << 3) | ELY_TAG_INT)

#ifndef ELY_UNBOX_BOOL
#define ELY_UNBOX_BOOL(v)     ((v) == ELY_VAL_TRUE)
#endif
#define ELY_BOX_BOOL(b)       ((b) ? ELY_VAL_TRUE : ELY_VAL_FALSE)

#define ELY_IS_PTR(v)         (((v) & ELY_TAG_MASK) == ELY_TAG_PTR)
#define ELY_IS_INT(v)         (((v) & ELY_TAG_MASK) == ELY_TAG_INT)
#define ELY_IS_FLOAT(v)       (((v) & ELY_TAG_MASK) == ELY_TAG_FLOAT)
#define ELY_IS_CONST(v)       (((v) & ELY_TAG_MASK) == ELY_TAG_CONST)
#define ELY_IS_STR0(v)        (((v) & ELY_TAG_MASK) == ELY_TAG_STR0)

static inline bool ely_is_ptr(ely_value v) { return ELY_IS_PTR(v); }
static inline bool ely_is_int(ely_value v) { return ELY_IS_INT(v); }
static inline bool ely_is_immediate_str(ely_value v) { return ELY_IS_STR0(v); }
static inline bool ely_is_float(ely_value v) { return ELY_IS_FLOAT(v); }
static inline bool ely_is_const(ely_value v) { return ELY_IS_CONST(v); }
static inline bool ely_is_bool(ely_value v) { return v == ELY_VAL_TRUE || v == ELY_VAL_FALSE; }
static inline bool ely_is_null(ely_value v) { return v == ELY_VAL_NULL; }

static inline void* ely_as_ptr(ely_value val) { return ELY_UNBOX_PTR(val); }

static inline size_t ely_immediate_str_len(ely_value val) {
    return (size_t)((val >> 3) & 0x7ULL);
}

static inline void ely_immediate_str_get_chars(ely_value val, char* buf) {
    size_t len = ely_immediate_str_len(val);
    uint64_t chars = val >> ELY_STR_DATA_SHIFT;
    memcpy(buf, &chars, len);
    buf[len] = '\0';
}

// ===================================================================
// 2. УНИВЕРСАЛЬНЫЕ УПАКОВЩИКИ / РАСПАКОВЩИКИ (C и C++)
// ===================================================================

// Указатели
static inline void* ely_unbox_ptr(ely_value v) {
    return ELY_UNBOX_PTR(v);
}

static inline ely_value ely_box_ptr(const void* ptr) {
    return ELY_BOX_PTR(ptr);
}

// Целые числа
static inline int64_t ely_unbox_int(ely_value v) {
    return ELY_UNBOX_INT(v);
}

static inline ely_value ely_box_int(int64_t val) {
    return ELY_BOX_INT(val);
}

// Булевы значения
static inline bool ely_unbox_bool(ely_value v) {
    return ELY_UNBOX_BOOL(v);
}

static inline ely_value ely_box_bool(bool b) {
    return ELY_BOX_BOOL(b);
}

// Float (32-bit inline)
static inline float ely_unbox_float(ely_value v) {
    uint32_t bits = (uint32_t)(v >> 3);
    float f;
    memcpy(&f, &bits, sizeof(float));
    return f;
}

static inline ely_value ely_box_float(float f) {
    uint32_t bits;
    memcpy(&bits, &f, sizeof(float));
    return (((ely_value)bits) << 3) | ELY_TAG_FLOAT;
}

static inline ely_value ely_box_double(double val) {
    ElyHeapDouble* hd = (ElyHeapDouble*)gc_alloc(sizeof(ElyHeapDouble), (gc_obj_type_t)GC_OBJ_DOUBLE);
    if (!hd) return ELY_VAL_NULL;
    
    hd->base.type = ELY_HEAP_DOUBLE;
    hd->value = val;
    
    return ELY_BOX_PTR(hd);
}

// Double (Распаковка из Heap Double, Float или Int)
static inline double ely_unbox_double(ely_value v) {
    if (ely_is_float(v)) {
        return (double)ely_unbox_float(v);
    }
    if (ely_is_ptr(v)) {
        const ElyHeapDouble* hd = (const ElyHeapDouble*)ELY_UNBOX_PTR(v);
        return hd ? hd->value : 0.0;
    }
    if (ely_is_int(v)) {
        return (double)ELY_UNBOX_INT(v);
    }
    return 0.0;
}

// Упаковка инлайн-строки (SSO) до 6 символов без выделения памяти в куче
static inline ely_value ely_box_inline_str(const char* content, size_t length) {
    if (length > 6) {
        return ELY_VAL_NULL; // Строка слишком длинная для SSO (должна выделяться в куче)
    }

    // 1. Устанавливаем тег ELY_TAG_STR0 (010) в младших 3 битах
    ely_value result = ELY_TAG_STR0;

    // 2. Укладываем длину (0..6) в биты 3..5
    result |= (((uint64_t)length & 0x07ULL) << 3);

    // 3. Записываем байты строки начиная с 8-го бита (ELY_STR_DATA_SHIFT)
    uint64_t chars = 0;
    if (content && length > 0) {
        memcpy(&chars, content, length);
    }
    result |= (chars << ELY_STR_DATA_SHIFT);

    return result;
}
// Инлайн-строка SSO в буфер
static inline void ely_unbox_inline_str(ely_value val, char* buf) {
    ely_immediate_str_get_chars(val, buf);
}

#endif // ELY_VALUE_H