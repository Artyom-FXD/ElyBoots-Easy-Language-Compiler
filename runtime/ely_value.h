// ely_value.h
#ifndef ELY_VALUE_H
#define ELY_VALUE_H

#include <stdint.h>
#include <stdbool.h>
#include <string.h>

// Единый тип для всей системы
typedef uint64_t ely_value;

// Маски и теги
#define ELY_TAG_MASK        0x07ULL
#define ELY_TAG_PTR         0x00ULL  // 000 - Указатель на объект в куче GC
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
// ЕДИНЫЙ КЛАССИФИКАТОР ОБЪЕКТОВ КУЧИ (Доступен везде!)
// ===================================================================
#define ELY_HEAP_STRING     0
#define ELY_HEAP_DOUBLE     1
#define ELY_HEAP_ARRAY      2
#define ELY_HEAP_DICT       3

typedef struct ElyHeapObject {
    uint8_t type; // Определяет, кто лежит по адресу: String, Double, Array или Dict
} ElyHeapObject;

typedef struct ElyHeapString {
    ElyHeapObject base;
    size_t length;
    char data[1]; // Эластичный массив
} ElyHeapString;

typedef struct ElyHeapDouble {
    ElyHeapObject base;
    double value;
} ElyHeapDouble;

// Базовые проверки типов
static inline bool ely_is_ptr(ely_value v) { return (v & ELY_TAG_MASK) == ELY_TAG_PTR; }
static inline bool ely_is_int(ely_value v) { return (v & ELY_TAG_MASK) == ELY_TAG_INT; }
static inline bool ely_is_immediate_str(ely_value v) { return (v & ELY_TAG_MASK) == ELY_TAG_STR0; }
static inline bool ely_is_float(ely_value v) { return (v & ELY_TAG_MASK) == ELY_TAG_FLOAT; }
static inline bool ely_is_const(ely_value v) { return (v & ELY_TAG_MASK) == ELY_TAG_CONST; }
static inline bool ely_is_bool(ely_value v) { return v == ELY_VAL_TRUE || v == ELY_VAL_FALSE; }
static inline bool ely_is_null(ely_value v) { return v == ELY_VAL_NULL; }

static inline void* ely_as_ptr(ely_value val) {
    return (void*)(val & ~ELY_TAG_MASK);
}

static inline size_t ely_immediate_str_len(ely_value val) {
    return (size_t)((val >> 3) & 0x7ULL);
}

// Быстрое извлечение SSO-строки в плоский Си-буфер
static inline void ely_immediate_str_get_chars(ely_value val, char* buf) {
    size_t len = ely_immediate_str_len(val);
    uint64_t chars = val >> ELY_STR_DATA_SHIFT;
    memcpy(buf, &chars, len);
    buf[len] = '\0';
}

#endif // ELY_VALUE_H