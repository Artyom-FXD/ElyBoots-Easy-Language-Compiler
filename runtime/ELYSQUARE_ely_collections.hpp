#pragma once

#include "ELYSQUARE_ely_str.hpp"
#include "ely_dynamic.hpp"
#include "ELYSQUARE_ely_any.hpp"
#include <stdexcept>
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
        if (!raw_) throw std::runtime_error("GC: Failed to allocate array");
    }

    explicit array(::arr* a) : raw_(a) {
        if (!raw_) throw std::invalid_argument("Array pointer cannot be null");
    }

    explicit array(ely_value val) {
        if (!ely_is_ptr(val)) throw std::invalid_argument("Expected GC pointer");
        auto* obj = static_cast<ElyHeapObject*>(ely_as_ptr(val));
        if (!obj || static_cast<uint8_t>(obj->type) != ELY_HEAP_ARRAY) {
            throw std::invalid_argument("Passed ely_value is not an Array!");
        }
        raw_ = reinterpret_cast<::arr*>(obj);
    }

    ely_value raw() const noexcept { return ely_box_ptr(raw_); }
    size_t size() const noexcept { return ::arr_len(raw_); }
    bool empty() const noexcept { return size() == 0; }

    void push(const any& val) { ::arr_push(raw_, val.raw()); }
    
    any pop() {
        if (empty()) throw std::underflow_error("Array underflow");
        return any(::arr_pop_value(raw_));
    }

    any get(size_t index) const {
        if (index >= size()) throw std::out_of_range("Array index out of range");
        return any(::arr_get(raw_, index));
    }

    void set(size_t index, const any& val) {
        if (index >= size()) throw std::out_of_range("Array index out of range");
        ::arr_set(raw_, index, val.raw());
    }

    void insert(size_t index, const any& val) {
        if (::arr_insert(raw_, index, val.raw()) != 0) {
            throw std::out_of_range("Array insert out of range");
        }
    }

    void remove(size_t index) {
        if (::arr_remove_index(raw_, index) != 0) {
            throw std::out_of_range("Array remove index out of range");
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
        if (index >= size()) throw std::out_of_range("Array index out of range");
        return Proxy(raw_, index);
    }

    any operator[](size_t index) const {
        return get(index);
    }

    // template

    template <typename T>
    std::vector<T> to_static_vector() const {
        std::vector<T> result;
        result.reserve(size());

        for (size_t i = 0; i < size(); ++i) {
            ely::any item = get(i);

            // Проверяем типы и кошмарим рантайм, если подсунули не то
            if constexpr (std::is_same_v<T, int64_t> || std::is_same_v<T, int>) {
                if (!item.is_number()) {
                    throw std::runtime_error("TypeError: Запытался впихнуть не-число в статический массив целых чисел!");
                }
                result.push_back(static_cast<T>(item.as_int()));
            } 
            else if constexpr (std::is_same_v<T, double> || std::is_same_v<T, float>) {
                if (!item.is_number()) {
                    throw std::runtime_error("TypeError: Попытка привести не-число к статическому числу с плавающей точкой!");
                }
                result.push_back(static_cast<T>(item.as_double()));
            } 
            else if constexpr (std::is_same_v<T, std::string>) {
                if (!item.is_string()) {
                    throw std::runtime_error("TypeError: Ожидалась строка для статического массива, но прилетело что-то другое!");
                }
                result.push_back(item.as_string());
            } 
            else if constexpr (std::is_same_v<T, bool>) {
                if (!item.is_bool()) {
                    throw std::runtime_error("TypeError: Ожидался bool!");
                }
                result.push_back(item.as_bool());
            } 
            else {
                // Если T — это другой ely::array или ely::dict (вложенные структуры)
                result.push_back(item.as<T>());
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
        if (!raw_) throw std::runtime_error("GC: Failed to allocate dict");
    }

    explicit dict(::dict* d) : raw_(d) {
        if (!raw_) throw std::invalid_argument("Dict pointer cannot be null");
    }

    explicit dict(ely_value val) {
        if (!ely_is_ptr(val)) throw std::invalid_argument("Expected GC pointer");
        auto* obj = static_cast<ElyHeapObject*>(ely_as_ptr(val));
        if (!obj || static_cast<uint8_t>(obj->type) != ELY_HEAP_DICT) {
            throw std::invalid_argument("Passed ely_value is not a Dict!");
        }
        raw_ = reinterpret_cast<::dict*>(obj);
    }

    ely_value raw() const noexcept { return ely_box_ptr(raw_); }
    size_t size() const noexcept { return ::dict_size(raw_); }
    bool empty() const noexcept { return size() == 0; }

    bool has(const any& key) const { return ::dict_has(raw_, key.raw()) != 0; }
    
    any get(const any& key) const {
        return any(::dict_get(raw_, key.raw()));
    }

    void set(const any& key, const any& val) {
        ::dict_set(raw_, key.raw(), val.raw());
    }

    void remove(const any& key) {
        ::dict_delete(raw_, key.raw());
    }

    // ==========================================
    // НАСТОЯЩИЙ ИТЕРАТОР БЕЗ АЛЛОКАЦИЙ
    // ==========================================
    class Iterator {
    private:
        const ::dict* dict_;       // Ссылка на родительский словарь
        size_t bucket_idx_;        // Текущий индекс в массиве buckets
        ::dict_entry* current_;    // Текущая нода в связном списке коллизий

        // Вспомогательный метод для поиска следующего непустого бакета
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

        // Префиксный инкремент (++it)
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

        // Возвращаем пару, поддерживающую structured binding (C++17 auto [k, v])
        std::pair<ely::any, ely::any> operator*() const {
            if (!current_) {
                throw std::out_of_range("Dict iterator out of bounds");
            }
            return { ely::any(current_->key), ely::any(current_->value) };
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
    // СТАТИЧЕСКАЯ КОНВЕРТАЦИЯ С ВАЛИДАЦИЕЙ
    // ==========================================
    template <typename K, typename V>
    std::unordered_map<K, V> to_static_map() const {
        std::unordered_map<K, V> result;

        for (auto [key, val] : *this) {
            K safe_key;
            V safe_value;

            // 1. Валидация и парсинг ключа K
            if constexpr (std::is_same_v<K, std::string>) {
                if (!key.is_string()) throw std::runtime_error("TypeError: Key is not a string!");
                safe_key = key.as_string(); // Твоя C++ строка!
            } else if constexpr (std::is_same_v<K, ely::str>) {
                if (!key.is_string()) throw std::runtime_error("TypeError: Key is not a string!");
                safe_key = key.as_str();    // Твоя Ely строка!
            } else if constexpr (std::is_same_v<K, int64_t> || std::is_same_v<K, int>) {
                if (!key.is_int()) throw std::runtime_error("TypeError: Key is not an integer!");
                safe_key = static_cast<K>(key.as_int());
            } else {
                static_assert(false, "Unsupported key type for static map conversion");
            }

            // 2. Валидация и парсинг значения V (с автокастами int <-> float)
            if constexpr (std::is_same_v<V, int64_t> || std::is_same_v<V, int>) {
                if (!val.is_number()) throw std::runtime_error("TypeError: Expected numeric value!");
                safe_value = static_cast<V>(val.as_int());
            } else if constexpr (std::is_same_v<V, double> || std::is_same_v<V, float>) {
                if (!val.is_number()) throw std::runtime_error("TypeError: Expected numeric value!");
                safe_value = static_cast<V>(val.as_double());
            } else if constexpr (std::is_same_v<V, std::string>) {
                if (!val.is_string()) throw std::runtime_error("TypeError: Expected string value!");
                safe_value = val.as_string();
            } else if constexpr (std::is_same_v<V, ely::str>) {
                if (!val.is_string()) throw std::runtime_error("TypeError: Expected string value!");
                safe_value = val.as_str();
            } else if constexpr (std::is_same_v<V, bool>) {
                if (!val.is_bool()) throw std::runtime_error("TypeError: Expected boolean value!");
                safe_value = val.as_bool();
            } else {
                safe_value = val.as<V>();
            }

            result[safe_key] = safe_value;
        }

        return result;
    }

    // Proxy для []
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