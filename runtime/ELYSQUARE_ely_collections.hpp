#pragma once

#include "ELYSQUARE_ely_str.hpp"
#include "ely_dynamic.hpp"
#include "ELYSQUARE_ely_any.hpp"
#include "ELYSQUARE_ely_errors.hpp"

#include <string>
#include <vector>
#include <unordered_map>

extern "C" {
#include "collections.h"
}

namespace ely {

// ==========================================
// ДИНАМИЧЕСКИЙ МАССИВ (ely::array)
// ==========================================
class array {
private:
    ::arr* raw_;

public:
    array() {
        raw_ = ::arr_new();
        if (!raw_) {
            ely::raise(ErrorType::GCError, "GC allocation failed: Failed to allocate young array heap-object");
        }
    }

    explicit array(::arr* a) : raw_(a) {
        if (!raw_) {
            ely::raise(ErrorType::ValueError, "ValueError: Array initialization pointer cannot be null");
        }
    }

    explicit array(ely_value val) {
        if (!ely_is_ptr(val)) {
            ely::raise(ErrorType::TypeError, "TypeError: Expected GC heap-pointer for Array creation");
        }
        auto* obj = static_cast<ElyHeapObject*>(ely_as_ptr(val));
        if (!obj || static_cast<uint8_t>(obj->type) != ELY_HEAP_ARRAY) {
            ely::raise(ErrorType::TypeError, "TypeError: Passed ely_value is not a dynamic Array!");
        }
        raw_ = reinterpret_cast<::arr*>(obj);
    }

    ely_value raw() const noexcept { return ely_box_ptr(raw_); }
    size_t size() const noexcept { return ::arr_len(raw_); }
    bool empty() const noexcept { return size() == 0; }

    void push(const any& val) { ::arr_push(raw_, val.raw()); }
    
    any pop() {
        if (empty()) {
            ely::raise(ErrorType::IndexError, "IndexError: Pop from empty array");
        }
        return any(::arr_pop_value(raw_));
    }

    any get(size_t index) const {
        if (index >= size()) {
            ely::raise(ErrorType::IndexError, fstr("IndexError: Array index \'", ::std::to_string(index), "\' out of range (size is ", ::std::to_string(size()), ")").c_str());
        }
        return any(::arr_get(raw_, index));
    }

    void set(size_t index, const any& val) {
        if (index >= size()) {
            ely::raise(ErrorType::IndexError, fstr("IndexError: Cannot write to index \'", ::std::to_string(index), "\' (size is ", ::std::to_string(size()), ")").c_str());
        }
        ::arr_set(raw_, index, val.raw());
    }

    void insert(size_t index, const any& val) {
        if (::arr_insert(raw_, index, val.raw()) != 0) {
            ely::raise(ErrorType::IndexError, fstr("IndexError: Insertion index \'", ::std::to_string(index) , "\' is out of bounds").c_str());
        }
    }

    void remove(size_t index) {
        if (::arr_remove_index(raw_, index) != 0) {
            ely::raise(ErrorType::IndexError, fstr("IndexError: Deletion index '" + ::std::to_string(index) + "\' is out of bounds").c_str());
        }
    }

    class Proxy {
    private:
        ::arr* a_;
        size_t idx_;
    public:
        Proxy(::arr* a, size_t idx) : a_(a), idx_(idx) {}
        operator any() const { return any(::arr_get(a_, idx_)); }
        Proxy& operator=(const any& val) {
            ::arr_set(a_, idx_, val.raw());
            return *this;
        }
    };

    Proxy operator[](size_t index) {
        if (index >= size()) {
            ely::raise(ErrorType::IndexError, fstr("IndexError: Access index '", ::std::to_string(index), "' out of bounds").c_str());
        }
        return Proxy(raw_, index);
    }

    any operator[](size_t index) const {
        return get(index);
    }

    template <typename T>
    ::std::vector<T> to_static_vector() const {
        ::std::vector<T> result;
        result.reserve(size());

        for (size_t i = 0; i < size(); ++i) {
            ely::any item = get(i);

            if constexpr (std::is_same_v<T, int64_t> || ::std::is_same_v<T, int>) {
                if (!item.is_number()) {
                    ely::raise(ErrorType::TypeError, fstr("TypeError: Expected numeric element for static integer array conversion at index ", ::std::to_string(i)).c_str());
                }
                result.push_back(static_cast<T>(item.as_int()));
            } 
            else if constexpr (std::is_same_v<T, double> || ::std::is_same_v<T, float>) {
                if (!item.is_number()) {
                    ely::raise(ErrorType::TypeError, fstr("TypeError: Expected numeric element for static floating-point array conversion at index ", ::std::to_string(i)).c_str());
                }
                result.push_back(static_cast<T>(item.as_double()));
            } 
            else if constexpr (std::is_same_v<T, ::std::string>) {
                if (!item.is_string()) {
                    ely::raise(ErrorType::TypeError, fstr("TypeError: Expected string element at index ", ::std::to_string(i)).c_str());
                }
                result.push_back(::std::string(item.c_str()));
            } 
            else if constexpr (std::is_same_v<T, bool>) {
                if (!item.is_bool()) {
                    ely::raise(ErrorType::TypeError, fstr("TypeError: Expected boolean element at index " + ::std::to_string(i)).c_str());
                }
                result.push_back(item.as_bool());
            } 
            else {
                result.push_back(static_cast<T>(item));
            }
        }
        return result;
    }

    template <typename F>
    void foreach(F func) const {
        for (size_t i = 0; i < size(); ++i) {
            func(get(i));
        }
    }
};

// ==========================================
// ХЕШ-ТАБЛИЦА (ely::dict)
// ==========================================
class dict {
private:
    ::dict* raw_;

public:
    dict() {
        raw_ = ::dict_new(::dict_hash_str, ::dict_cmp_str);
        if (!raw_) {
            ely::raise(ErrorType::GCError, "GC allocation failed: Failed to allocate dictionary object in heap");
        }
    }

    explicit dict(::dict* d) : raw_(d) {
        if (!raw_) {
            ely::raise(ErrorType::ValueError, "ValueError: Dict initialization pointer cannot be null");
        }
    }

    explicit dict(ely_value val) {
        if (!ely_is_ptr(val)) {
            ely::raise(ErrorType::TypeError, "TypeError: Expected GC heap-pointer for Dict creation");
        }
        auto* obj = static_cast<ElyHeapObject*>(ely_as_ptr(val));
        if (!obj || static_cast<uint8_t>(obj->type) != ELY_HEAP_DICT) {
            ely::raise(ErrorType::TypeError, "TypeError: Passed ely_value is not a dynamic Dict!");
        }
        raw_ = reinterpret_cast<::dict*>(obj);
    }

    ely_value raw() const noexcept { return ely_box_ptr(raw_); }
    size_t size() const noexcept { return ::dict_size(raw_); }
    bool empty() const noexcept { return size() == 0; }

    bool has(const any& key) const { return ::dict_has(raw_, key.raw()) != 0; }
    
    any get(const any& key) const {
        // Если ключа нет — генерируем KeyError
        if (!has(key)) {
            ely::raise(ErrorType::KeyError, "KeyError: Key not found in dynamic dictionary");
        }
        return any(::dict_get(raw_, key.raw()));
    }

    void set(const any& key, const any& val) {
        ::dict_set(raw_, key.raw(), val.raw());
    }

    void remove(const any& key) {
        if (!has(key)) {
            ely::raise(ErrorType::KeyError, "KeyError: Cannot delete non-existent key from dictionary");
        }
        ::dict_delete(raw_, key.raw());
    }

    // ==========================================
    // ИТЕРАТОР
    // ==========================================
class Iterator {
    private:
        const ::dict* dict_;
        size_t bucket_idx_;
        ::dict_entry* current_;

        void advance_to_next_valid() {
            while (bucket_idx_ < dict_->capacity && current_ == nullptr) {
                bucket_idx_++;
                if (bucket_idx_ < dict_->capacity) {
                    current_ = dict_->buckets[bucket_idx_];
                }
            }
        }

    public:
        Iterator(const ::dict* d, size_t bucket_idx, ::dict_entry* entry)
            : dict_(d), bucket_idx_(bucket_idx), current_(entry) {
            if (d && current_ == nullptr) {
                advance_to_next_valid();
            }
        }

        Iterator& operator++() {
            if (current_) {
                current_ = current_->next;
            }
            if (current_ == nullptr) {
                advance_to_next_valid();
            }
            return *this;
        }

        bool operator!=(const Iterator& other) const {
            return current_ != other.current_ || bucket_idx_ != other.bucket_idx_;
        }

        // Явное приведение сырых данных ноды к ely_value гарантирует работу итератора
        ::std::pair<ely::any, ely::any> operator*() const {
            if (!current_) {
                ely::raise(ErrorType::IndexError, "IndexError: Dictionary iterator out of bounds");
            }
            return { 
                ely::any(static_cast<ely_value>(current_->key)), 
                ely::any(static_cast<ely_value>(current_->value)) 
            };
        }
    };

    Iterator begin() const {
        if (!raw_ || raw_->size == 0) return end();
        return Iterator(raw_, 0, raw_->buckets[0]);
    }

    Iterator end() const {
        return Iterator(raw_, raw_ ? raw_->capacity : 0, nullptr);
    }

    // ==========================================
    // КОНВЕРТЕР С ВАЛИДАЦИЕЙ
    // ==========================================
    template <typename K, typename V>
    ::std::unordered_map<K, V> to_static_map() const {
        ::std::unordered_map<K, V> result;

        for (auto [key, val] : *this) {
            K safe_key;
            V safe_value;

            // 1. Валидация ключа
            if constexpr (std::is_same_v<K, ::std::string>) {
                if (!key.is_string()) ely::raise(ErrorType::TypeError, "TypeError: Dictionary contains a non-string key where static ::std::string key was expected");
                safe_key = ::std::string(key.c_str()); // Replaced key.as_string()
            } else if constexpr (std::is_same_v<K, ely::str>) {
                if (!key.is_string()) ely::raise(ErrorType::TypeError, "TypeError: Dictionary contains a non-string key where static ely::str key was expected");
                safe_key = key.as_str();
            } else if constexpr (std::is_same_v<K, int64_t> || ::std::is_same_v<K, int>) {
                if (!key.is_int()) ely::raise(ErrorType::TypeError, "TypeError: Dictionary contains a non-integer key where static numeric key was expected");
                safe_key = static_cast<K>(key.as_int());
            } else {
                static_assert(false, "Unsupported key type for static map conversion");
            }

            // 2. Валидация значения
            if constexpr (std::is_same_v<V, int64_t> || ::std::is_same_v<V, int>) {
                if (!val.is_number()) ely::raise(ErrorType::TypeError, "TypeError: Value inside dictionary is not numeric");
                safe_value = static_cast<V>(val.as_int());
            } else if constexpr (std::is_same_v<V, double> || ::std::is_same_v<V, float>) {
                if (!val.is_number()) ely::raise(ErrorType::TypeError, "TypeError: Value inside dictionary is not numeric");
                safe_value = static_cast<V>(val.as_double());
            } else if constexpr (std::is_same_v<V, ::std::string>) {
                if (!val.is_string()) ely::raise(ErrorType::TypeError, "TypeError: Value inside dictionary is not a String");
                safe_value = val.as_string();
            } else if constexpr (std::is_same_v<V, ely::str>) {
                if (!val.is_string()) ely::raise(ErrorType::TypeError, "TypeError: Value inside dictionary is not an Ely-string");
                safe_value = val.as_str();
            } else if constexpr (std::is_same_v<V, bool>) {
                if (!val.is_bool()) ely::raise(ErrorType::TypeError, "TypeError: Value inside dictionary is not Boolean");
                safe_value = val.as_bool();
            } else {
                safe_value = val.as<V>();
            }

            result[safe_key] = safe_value;
        }

        return result;
    }

    class Proxy {
    private:
        ::dict* d_;
        ely_value key_;
    public:
        Proxy(::dict* d, ely_value k) : d_(d), key_(k) {}
        operator any() const { return any(::dict_get(d_, key_)); }
        Proxy& operator=(const any& val) {
            ::dict_set(d_, key_, val.raw());
            return *this;
        }
    };

    Proxy operator[](const any& key) {
        return Proxy(raw_, key.raw());
    }

    any operator[](const any& key) const {
        return get(key);
    }

    template <typename F>
    void foreach(F func) const {
        for (auto [key, val] : *this) {
            func(key, val);
        }
    }
};

// ===================================================================
// РАЗРЕШЕНИЕ КРУГОВОЙ ЗАВИСИМОСТИ: Тела отложенных методов ely::any
// ===================================================================
inline ely::array any::as_array() const {
    return ely::array(raw_);
}

inline ely::dict any::as_dict() const {
    return ely::dict(raw_);
}

} // namespace ely