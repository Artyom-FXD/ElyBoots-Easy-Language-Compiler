#pragma once

#include "ELYSQUARE_ely_str.hpp"
#include "ELYSQUARE_ely_any.hpp"
#include "ELYSQUARE_ely_errors.hpp" // Импортируем ошибки!

extern "C" {
#include "ely_value.h"
}

namespace ely {

class function {
private:
    ::ElyHeapFunction* raw_;

public:
    explicit function(::ElyHeapFunction* f) : raw_(f) {
        if (!raw_) {
            ely::raise(ErrorType::ValueError, "ValueError: Function initialization pointer cannot be null");
        }
    }

    explicit function(ely_value val) {
        if (!ely_is_ptr(val)) {
            ely::raise(ErrorType::TypeError, "TypeError: Expected GC pointer to load Function");
        }
        auto* obj = static_cast<ElyHeapObject*>(ely_as_ptr(val));
        if (!obj || static_cast<uint8_t>(obj->type) != ELY_HEAP_FUNCTION) {
            ely::raise(ErrorType::TypeError, "TypeError: Passed ely_value does not refer to a Function object!");
        }
        raw_ = reinterpret_cast<::ElyHeapFunction*>(obj);
    }

    ely_value raw() const noexcept { 
        return ely_box_ptr(raw_); 
    }

    ::std::string name() const { return raw_->name ? raw_->name : "<anonymous>"; }
    int arity() const { return raw_->arity; }
    
    template<typename FuncType>
    FuncType get_native() const {
        return reinterpret_cast<FuncType>(raw_->func_ptr);
    }
};

inline any::any(const function& fn) noexcept : raw_(fn.raw()) {}

inline any::operator ely::function() const {
    return as_function();
}

} // namespace ely