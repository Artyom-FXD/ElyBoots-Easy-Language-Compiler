#pragma once

#include <string>
#include <stdexcept>
#include <iostream>
#include <cstdint>
#include <cstring>

extern "C" {
#include "ely_value.h" // Unified C-runtime base
#include "ely_gc.h"    // Garbage Collector integration
}

// Heap object type identifiers (used with ELY_TAG_PTR)
enum class ElyHeapType : uint8_t {
    String,
    Double // Used when INT61 overflows
};

// Base header for all heap-allocated objects
struct ElyHeapObject {
    ElyHeapType type;
};

// Heavyweight heap-allocated string
struct ElyHeapString : public ElyHeapObject {
    size_t length;
    char data[1]; // Flexible array member
};

// Double-precision floating-point number on the heap
struct ElyHeapDouble : public ElyHeapObject {
    double value;
};

// ===========================================================================
//  BOXING / UNBOXING OF NUMBERS AND POINTERS (Ex-Boxing Lower Tag Scheme)
// ===========================================================================

// Pointers (Heap)
inline ely_value ely_box_ptr(void* ptr) {
    uint64_t addr = reinterpret_cast<uint64_t>(ptr);
    if ((addr & ELY_TAG_MASK) != 0) {
        throw std::runtime_error("GigaCage Alignment Violation: Pointer is not 8-byte aligned!");
    }
    return addr | ELY_TAG_PTR;
}

inline void* ely_unbox_ptr(ely_value v) {
    if (!ely_is_ptr(v)) throw std::invalid_argument("Expected ELY_TAG_PTR");
    return reinterpret_cast<void*>(v & ~ELY_TAG_MASK);
}

// Integers (INT61)
inline constexpr ely_value ely_box_int(int64_t val) {
    if (val > ELY_INT61_MAX || val < ELY_INT61_MIN) {
        throw std::overflow_error("Value exceeds INT61 limits");
    }
    return (static_cast<uint64_t>(val) << 3) | ELY_TAG_INT;
}

inline constexpr int64_t ely_unbox_int(ely_value v) {
    if (!ely_is_int(v)) throw std::invalid_argument("Expected ELY_TAG_INT");
    return static_cast<int64_t>(v) >> 3;
}

// Floating-point (FLOAT 32-bit)
inline ely_value ely_box_float(float f) {
    uint32_t bits;
    std::memcpy(&bits, &f, sizeof(float));
    return (static_cast<uint64_t>(bits) << 3) | ELY_TAG_FLOAT;
}

inline float ely_unbox_float(ely_value v) {
    if (!ely_is_float(v)) throw std::invalid_argument("Expected ELY_TAG_FLOAT");
    uint32_t bits = static_cast<uint32_t>(v >> 3);
    float f;
    std::memcpy(&f, &bits, sizeof(float));
    return f;
}

// ===========================================================================
//  STRING SUBSYSTEM (Inline SSO & Heap Strings)
// ===========================================================================

inline size_t ely_str_len(const char* s) {
    return s ? std::strlen(s) : 0;
}

inline size_t ely_immediate_str_len(ely_value val) {
    return static_cast<size_t>((val >> 3) & 0x7ULL);
}

// Packs an inline string (up to 6 characters long)
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
    result |= (chars << ELY_STR_DATA_SHIFT); // Character payload starts from the 1st byte
    return result;
}

inline ely_value ely_value_new_double(double val) {
    auto* heap_double = static_cast<ElyHeapDouble*>(gc_alloc(sizeof(ElyHeapDouble), GC_OBJ_DOUBLE));
    heap_double->type = ElyHeapType::Double;
    heap_double->value = val;
    return ely_box_ptr(heap_double);
}

// Allocates a string (SSO / Immediate or GC Heap)
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
    throw std::invalid_argument("ely_value is not a string type");
}

inline ely_value ely_str_concat(const char* s1, const char* s2) {
    std::string lhs = s1 ? s1 : "";
    std::string rhs = s2 ? s2 : "";
    return ely_value_new_string((lhs + rhs).c_str());
}

// Safe string concatenation directly from raw ely_values
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
        uint64_t chars = b >> ELY_STR_DATA_SHIFT; // FIXED: Used to have an incorrect shift of 6
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
    
    // Allocate on C++ heap (+1 byte for null-terminator)
    char* res = new char[len1 + len2 + 1];
    
    // Direct memory block copies
    if (len1 > 0) {
        std::memcpy(res, s1, len1);
    }
    if (len2 > 0) {
        std::memcpy(res + len1, s2, len2);
    }
    
    // Strict null-termination
    res[len1 + len2] = '\0'; 
    
    return res;
}

inline int ely_str_cmp(const char* a, const char* b) {
    return std::strcmp(a ? a : "", b ? b : "");
}

// ===========================================================================
//  ARITHMETIC SUBSYSTEM (GC-integrated safe math)
// ===========================================================================

inline double ely_internal_cast_to_double(ely_value v) {
    if (ely_is_int(v))   return static_cast<double>(ely_unbox_int(v));
    if (ely_is_float(v)) return static_cast<double>(ely_unbox_float(v));
    if (ely_is_ptr(v)) {
        auto* obj = static_cast<ElyHeapObject*>(ely_unbox_ptr(v));
        if (obj && obj->type == ElyHeapType::Double) {
            return static_cast<ElyHeapDouble*>(obj)->value;
        }
    }
    throw std::invalid_argument("Attempted to extract a number from a non-numeric ely_value");
}

inline ely_value ely_value_add(ely_value a, ely_value b) {
    if (ely_is_int(a) && ely_is_int(b)) {
        ely_value sum = a + b - ELY_TAG_INT;

        // Bitwise signed overflow interception
        if (~(a ^ b) & (sum ^ a) & 0x8000000000000000ULL) {
            // FIXED: Safely promote to heap double allocated via GC
            double promoted = static_cast<double>(ely_unbox_int(a)) + static_cast<double>(ely_unbox_int(b));
            return ely_value_new_double(promoted);
        }
        return sum;
    }

    if (ely_is_float(a) && ely_is_float(b)) {
        return ely_box_float(ely_unbox_float(a) + ely_unbox_float(b));
    }

    // FIXED: Fallbacks safely allocate double on GC heap
    double fallback_res = ely_internal_cast_to_double(a) + ely_internal_cast_to_double(b);
    return ely_value_new_double(fallback_res);
}