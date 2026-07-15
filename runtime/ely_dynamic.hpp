#pragma once

#include <string>
#include <stdexcept>
#include <iostream>
#include <cstdint>
#include <cstring>

extern "C" {
#include "ely_value.h" // Подтягиваем единую базу Си-рантайма
#include "ely_gc.h"    // Твой сборщик мусора
}

// Идентификаторы типов объектов в куче (для ELY_TAG_PTR)
enum class ElyHeapType : uint8_t {
    String,
    Double // Используется при оверфлоу INT61
};

// Базовый заголовок для объектов на куче
struct ElyHeapObject {
    ElyHeapType type;
};

// Тяжёлая строка на куче
struct ElyHeapString : public ElyHeapObject {
    size_t length;
    char data[1]; // Эластичный массив
};

// Вещественное число двойной точности на куче
struct ElyHeapDouble : public ElyHeapObject {
    double value;
};

// ==========================================
// БОКСИНГ / АНБОКСИНГ ЧИСЕЛ И УКАЗАТЕЛЕЙ
// ==========================================

// Указатели (Куча)
inline ely_value ely_box_ptr(void* ptr) {
    uint64_t addr = reinterpret_cast<uint64_t>(ptr);
    if ((addr & ELY_TAG_MASK) != 0) {
        throw std::runtime_error("GigaCage Alignment Violation: Указатель не выровнен по 8 байтам!");
    }
    return addr | ELY_TAG_PTR;
}

inline void* ely_unbox_ptr(ely_value v) {
    if (!ely_is_ptr(v)) throw std::invalid_argument("Ожидался ELY_TAG_PTR");
    return reinterpret_cast<void*>(v & ~ELY_TAG_MASK);
}

// Целые (INT61)
inline constexpr ely_value ely_box_int(int64_t val) {
    if (val > ELY_INT61_MAX || val < ELY_INT61_MIN) {
        throw std::overflow_error("Значение выходит за рамки INT61");
    }
    return (static_cast<uint64_t>(val) << 3) | ELY_TAG_INT;
}

inline constexpr int64_t ely_unbox_int(ely_value v) {
    if (!ely_is_int(v)) throw std::invalid_argument("Ожидался ELY_TAG_INT");
    return static_cast<int64_t>(v) >> 3;
}

// Вещественные (FLOAT 32-bit)
inline ely_value ely_box_float(float f) {
    uint32_t bits;
    std::memcpy(&bits, &f, sizeof(float));
    return (static_cast<uint64_t>(bits) << 3) | ELY_TAG_FLOAT;
}

inline float ely_unbox_float(ely_value v) {
    if (!ely_is_float(v)) throw std::invalid_argument("Ожидался ELY_TAG_FLOAT");
    uint32_t bits = static_cast<uint32_t>(v >> 3);
    float f;
    std::memcpy(&f, &bits, sizeof(float));
    return f;
}

// ==========================================
// СТРОКОВАЯ ПОДСИСТЕМА (Inline & Heap)
// ==========================================

inline size_t ely_str_len(const char* s) {
    return s ? std::strlen(s) : 0;
}

inline size_t ely_immediate_str_len(ely_value val) {
    return static_cast<size_t>((val >> 3) & 0x7ULL);
}

// Упаковка инлайн-строки (длина до 6 символов)
inline ely_value ely_box_inline_str(const char* content, size_t length) {
    if (length > 6) {
        throw std::invalid_argument("Inline str cannot be longer than 6 symbols!");
    }
    ely_value result = ELY_TAG_STR0;
    result |= (static_cast<uint64_t>(length) << 3); 

    uint64_t chars = 0;
    if (content && length > 0) {
        std::memcpy(&chars, content, length); 
    }
    result |= (chars << ELY_STR_DATA_SHIFT); // Символы ложатся со 1-го байта
    return result;
}

inline ely_value ely_value_new_double(double val) {
    auto* heap_double = static_cast<ElyHeapDouble*>(gc_alloc(sizeof(ElyHeapDouble), GC_OBJ_DOUBLE));
    heap_double->type = ElyHeapType::Double;
    heap_double->value = val;
    return ely_box_ptr(heap_double);
}

// Создание строки (SSO либо Куча)
inline ely_value ely_value_new_string(const char* content) {
    size_t len = ely_str_len(content);
    if (len <= 6) { 
        return ely_box_inline_str(content, len);
    }
    
    size_t total_size = sizeof(ElyHeapString) + len;
    auto* heap_str = static_cast<ElyHeapString*>(gc_alloc(total_size, GC_OBJ_STRING));
    heap_str->type = ElyHeapType::String;
    heap_str->length = len;
    
    if (content) {
        std::memcpy(heap_str->data, content, len);
    }
    heap_str->data[len] = '\0'; 
    
    return ely_box_ptr(heap_str);
}

inline const char* ely_value_to_string(ely_value val) {
    if (ely_is_immediate_str(val)) {
        thread_local char static_bufs[4][8];
        thread_local size_t buf_idx = 0;
        char* static_buf = static_bufs[buf_idx];
        buf_idx = (buf_idx + 1) % 4;

        size_t len = ely_immediate_str_len(val);
        uint64_t chars = val >> ELY_STR_DATA_SHIFT;
        std::memcpy(static_buf, &chars, len);
        static_buf[len] = '\0';
        return static_buf;
    } 
    
    if (ely_is_ptr(val)) {
        auto* obj = static_cast<ElyHeapObject*>(ely_unbox_ptr(val));
        if (obj && obj->type == ElyHeapType::String) {
            return static_cast<ElyHeapString*>(obj)->data; 
        }
    }
    throw std::invalid_argument("ely_value не является строковым типом");
}

inline ely_value ely_str_concat(const char* s1, const char* s2) {
    std::string lhs = s1 ? s1 : "";
    std::string rhs = s2 ? s2 : "";
    return ely_value_new_string((lhs + rhs).c_str());
}

// Безопасное объединение строк напрямую из ely_value
inline const char* ely_value_concat_to_c(ely_value a, ely_value b) {
    thread_local std::string result_buffer;
    result_buffer.clear();

    if (ely_is_immediate_str(a)) {
        size_t len = ely_immediate_str_len(a);
        uint64_t chars = a >> ELY_STR_DATA_SHIFT;
        result_buffer.append(reinterpret_cast<const char*>(&chars), len);
    } else if (ely_is_ptr(a)) {
        auto* obj = static_cast<ElyHeapObject*>(ely_unbox_ptr(a));
        if (obj && obj->type == ElyHeapType::String) {
            result_buffer.append(static_cast<ElyHeapString*>(obj)->data);
        }
    }

    if (ely_is_immediate_str(b)) {
        size_t len = ely_immediate_str_len(b);
        uint64_t chars = b >> ELY_STR_DATA_SHIFT; // ИСПРАВЛЕНО: Был ошибочный сдвиг на 6
        result_buffer.append(reinterpret_cast<const char*>(&chars), len);
    } else if (ely_is_ptr(b)) {
        auto* obj = static_cast<ElyHeapObject*>(ely_unbox_ptr(b));
        if (obj && obj->type == ElyHeapType::String) {
            result_buffer.append(static_cast<ElyHeapString*>(obj)->data);
        }
    }

    return result_buffer.c_str();
}

inline char* ely_str_concat_char(const char* s1, const char* s2) {
    size_t len1 = s1 ? std::strlen(s1) : 0;
    size_t len2 = s2 ? std::strlen(s2) : 0;
    
    // Выделяем память в куче (+1 байт под нуль-терминатор)
    char* res = new char[len1 + len2 + 1];
    
    // Копируем блоки памяти напрямую
    if (len1 > 0) {
        std::memcpy(res, s1, len1);
    }
    if (len2 > 0) {
        std::memcpy(res + len1, s2, len2);
    }
    
    // Жестко закрываем строку нулем
    res[len1 + len2] = '\0'; 
    
    return res;
}

inline int ely_str_cmp(const char* a, const char* b) {
    return std::strcmp(a ? a : "", b ? b : "");
}

// ==========================================
// СОВЕРШЕННАЯ АРИФМЕТИКА (Связность с GC)
// ==========================================

inline double ely_internal_cast_to_double(ely_value v) {
    if (ely_is_int(v))   return static_cast<double>(ely_unbox_int(v));
    if (ely_is_float(v)) return static_cast<double>(ely_unbox_float(v));
    if (ely_is_ptr(v)) {
        auto* obj = static_cast<ElyHeapObject*>(ely_unbox_ptr(v));
        if (obj && obj->type == ElyHeapType::Double) {
            return static_cast<ElyHeapDouble*>(obj)->value;
        }
    }
    throw std::invalid_argument("Попытка извлечь число из нечислового типа ely_value");
}

inline ely_value ely_value_add(ely_value a, ely_value b) {
    if (ely_is_int(a) && ely_is_int(b)) {
        ely_value sum = a + b - ELY_TAG_INT;

        // Битовый перехват знакового переполнения
        if (~(a ^ b) & (sum ^ a) & 0x8000000000000000ULL) {
            // ИСПРАВЛЕНО: Теперь безопасно выделяем на куче GC!
            double promoted = static_cast<double>(ely_unbox_int(a)) + static_cast<double>(ely_unbox_int(b));
            return ely_value_new_double(promoted);
        }
        return sum;
    }

    if (ely_is_float(a) && ely_is_float(b)) {
        return ely_box_float(ely_unbox_float(a) + ely_unbox_float(b));
    }

    // ИСПРАВЛЕНО: Любой фоллбек тоже выделяет через GC!
    double fallback_res = ely_internal_cast_to_double(a) + ely_internal_cast_to_double(b);
    return ely_value_new_double(fallback_res);
}