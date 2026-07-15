#pragma once

#include "ely_dynamic.hpp"
#include <iostream>
#include <string>
#include <stdexcept>
#include <type_traits>

namespace ely {

// 1. Вперед-декларации (Forward declarations), чтобы разорвать круговую зависимость
class array;
class dict;

class any {
private:
    ely_value raw_;

public:    
    constexpr any() noexcept : raw_(ELY_VAL_NULL) {}
    constexpr any(ely_value raw) noexcept : raw_(raw) {}

    any(bool val) noexcept : raw_(val ? ELY_VAL_TRUE : ELY_VAL_FALSE) {}
    any(std::nullptr_t) noexcept : raw_(ELY_VAL_NULL) {}

    any(int64_t val) {
        if (val > ELY_INT61_MAX || val < ELY_INT61_MIN) {
            raw_ = ely_value_new_double(static_cast<double>(val));
        } else {
            raw_ = ely_box_int(val);
        }
    }
    any(int val) : any(static_cast<int64_t>(val)) {}
    any(unsigned int val) : any(static_cast<int64_t>(val)) {}

    any(float val)  : raw_(ely_box_float(val)) {}
    any(double val) : raw_(ely_value_new_double(val)) {}

    any(const char* str) : raw_(ely_value_new_string(str)) {}
    any(const std::string& str) : raw_(ely_value_new_string(str.c_str())) {}

    constexpr ely_value raw() const noexcept { return raw_; }

    bool is_ptr() const noexcept { return ely_is_ptr(raw_); }
    bool is_int() const noexcept { return ely_is_int(raw_); }
    bool is_float() const noexcept { return ely_is_float(raw_); }
    bool is_inline_string() const noexcept { return ely_is_immediate_str(raw_); }
    bool is_bool() const noexcept { return ely_is_bool(raw_); }
    bool is_null() const noexcept { return ely_is_null(raw_); }
    
    bool is_heap_string() const noexcept {
        if (!is_ptr()) return false;
        auto* obj = static_cast<ElyHeapObject*>(ely_unbox_ptr(raw_));
        return obj && static_cast<uint8_t>(obj->type) == ELY_HEAP_STRING;
    }

    bool is_heap_double() const noexcept {
        if (!is_ptr()) return false;
        auto* obj = static_cast<ElyHeapObject*>(ely_unbox_ptr(raw_));
        return obj && static_cast<uint8_t>(obj->type) == ELY_HEAP_DOUBLE;
    }

    bool is_array() const noexcept {
        if (!is_ptr()) return false;
        auto* obj = static_cast<ElyHeapObject*>(ely_unbox_ptr(raw_));
        return obj && static_cast<uint8_t>(obj->type) == ELY_HEAP_ARRAY;
    }

    bool is_dict() const noexcept {
        if (!is_ptr()) return false;
        auto* obj = static_cast<ElyHeapObject*>(ely_unbox_ptr(raw_));
        return obj && static_cast<uint8_t>(obj->type) == ELY_HEAP_DICT;
    }

    bool is_string() const noexcept { return is_inline_string() || is_heap_string(); }
    bool is_number() const noexcept { return is_int() || is_float() || is_heap_double(); }

    int64_t as_int() const {
        if (is_int()) return ely_unbox_int(raw_);
        if (is_heap_double()) return static_cast<int64_t>(static_cast<ElyHeapDouble*>(ely_unbox_ptr(raw_))->value);
        if (is_float()) return static_cast<int64_t>(ely_unbox_float(raw_));
        throw std::bad_cast();
    }

    float as_float() const {
        if (is_float()) return ely_unbox_float(raw_);
        if (is_int()) return static_cast<float>(ely_unbox_int(raw_));
        if (is_heap_double()) return static_cast<float>(static_cast<ElyHeapDouble*>(ely_unbox_ptr(raw_))->value);
        throw std::bad_cast();
    }

    double as_double() const {
        if (is_heap_double()) return static_cast<ElyHeapDouble*>(ely_unbox_ptr(raw_))->value;
        if (is_int()) return static_cast<double>(ely_unbox_int(raw_));
        if (is_float()) return static_cast<double>(ely_unbox_float(raw_));
        throw std::bad_cast();
    }

    bool as_bool() const {
        if (!is_bool()) throw std::bad_cast();
        return raw_ == ELY_VAL_TRUE;
    }

    ely::array as_array() const;
    ely::dict as_dict() const;

    const char* c_str() const {
        if (!is_string()) throw std::bad_cast();
        return ely_value_to_string(raw_);
    }

    // @brief Returns a C++ string representation of the value
    // @warning IT'S NOT THE SAME AS `as_str`
    std::string as_string() const { return std::string(c_str()); }
    // @brief Returns a ELY string representation of the value.
    // @warning IT'S NOT THE SAME AS `as_string`
    str as_str() const { return str(c_str()); }

    explicit operator int64_t() const { return as_int(); }
    explicit operator float() const   { return as_float(); }
    explicit operator double() const  { return as_double(); }
    explicit operator std::string() const { return as_string(); }
    explicit operator str() const { return as_str(); }

    explicit operator bool() const {
        return raw_ != ELY_VAL_FALSE && raw_ != ELY_VAL_NULL;
    }

    friend any operator+(const any& lhs, const any& rhs) {
        if (lhs.is_string() && rhs.is_string()) {
            return any(ely_str_concat(lhs.c_str(), rhs.c_str()));
        }
        return any(ely_value_add(lhs.raw(), rhs.raw()));
    }

    bool operator==(const any& other) const {
        if (is_string() && other.is_string()) {
            return ely_str_cmp(c_str(), other.c_str()) == 0;
        }
        if (is_number() && other.is_number()) {
            return as_double() == other.as_double();
        }
        return raw_ == other.raw_;
    }

    bool operator!=(const any& other) const { return !(*this == other); }

    friend std::ostream& operator<<(std::ostream& os, const any& val) {
        if (val.is_null()) {
            os << "null";
        } else if (val.is_bool()) {
            os << (val.as_bool() ? "true" : "false");
        } else if (val.is_int()) {
            os << val.as_int();
        } else if (val.is_float()) {
            os << val.as_float();
        } else if (val.is_heap_double()) {
            os << val.as_double();
        } else if (val.is_string()) {
            os << val.c_str();
        } else if (val.is_ptr()) {
            os << "Ptr(" << ely_unbox_ptr(val.raw_) << ")";
        } else {
            os << "Raw(" << val.raw_ << ")";
        }
        return os;
    }
};

} // namespace ely

// КРИТИЧЕСКИЙ СДВИГ: Включаем коллекции только тогда, когда класс any полностью известен компилятору!
#include "ELYSQUARE_ely_collections.hpp"