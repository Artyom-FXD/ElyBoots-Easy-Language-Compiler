#pragma once

#include "ely_gc.h"                  // Твой заголовочный файл GC
#include "ELYSQUARE_ely_str.hpp"   // Наш собственный API класс ely::str
#include "ELYSQUARE_ely_collections.hpp"
#include "ELYSQUARE_ely_any.hpp"
#include <string>
#include <stdexcept>

namespace ely {

class Context {
private:
    // Глобальная область видимости (словарь)
    ely::dict globals_;

    // Локация для красивых стектрейсов
    ::std::string current_file_ = "main.ely";
    int current_line_ = 1;

    // Конструктор приватный (синглтон)
    Context() : globals_() {
        // Регистрируем наш глобальный словарь в GC
        ::gc_add_global_root(reinterpret_cast<void**>(&globals_));
    }

    // Внутренние DRY-хелперы для избежания дублирования логики поиска/записи
    any get_global_impl(const char* name) const {
        any key(name);
        if (globals_.has(key)) {
            return globals_.get(key);
        }
        ely::raise(ely::ErrorType::RuntimeError, fstr("NameError: Global variable '", ::std::string(name), "' not found!").c_str());
    }

    void set_global_impl(const char* name, const any& val) {
        globals_.set(any(name), val);
    }

public:
    ~Context() {
        ::gc_remove_global_root(reinterpret_cast<void**>(&globals_));
    }

    static Context& get() {
        static Context instance;
        return instance;
    }

    Context(const Context&) = delete;
    Context& operator=(const Context&) = delete;

    // --- Доступ к глобальному словарю напрямую ---
    ely::dict& globals() { return globals_; }

    // =========================================================================
    // 🌍 Геттеры глобальных переменных (Перегрузки под все типы строк)
    // =========================================================================
    
    // 1. Плюсовый std::string
    any get_global(const ::std::string& name) const {
        return get_global_impl(name.c_str());
    }

    // 2. Наш API-шный ely::str (Ex-boxing)
    any get_global(const ely::str& name) const {
        // Избегаем создания промежуточных std::string, если переменная уже есть в мапе
        any key(name.raw_value());
        if (globals_.has(key)) {
            return globals_.get(key);
        }
        ely::raise(ely::ErrorType::NameError, fstr("NameError: Global variable '", ::std::string(name.c_str()), "' not found!").c_str());
    }

    // 3. Быстрый сырой литерал const char* (без оверхеда на аллокации строк)
    any get_global(const char* name) const {
        return get_global_impl(name);
    }

    // =========================================================================
    // 📥 Сеттеры глобальных переменных (Перегрузки под все типы строк)
    // =========================================================================

    // 1. Плюсовый std::string
    void set_global(const ::std::string& name, const any& val) {
        set_global_impl(name.c_str(), val);
    }

    // 2. Наш API-шный ely::str (Ex-boxing)
    void set_global(const ely::str& name, const any& val) {
        // Оптимальный путь: сразу передаем готовое упакованное ely_value в качестве ключа
        globals_.set(any(name.raw_value()), val);
    }

    // 3. Сырой литерал const char*
    void set_global(const char* name, const any& val) {
        set_global_impl(name, val);
    }

    // =========================================================================
    // 📍 Локация в коде (Перегрузки для дебага и стектрейсов)
    // =========================================================================

    void update_location(const ::std::string& file, int line) {
        current_file_ = file;
        current_line_ = line;
    }

    void update_location(const ely::str& file, int line) {
        current_file_ = file.c_str();
        current_line_ = line;
    }

    void update_location(const char* file, int line) {
        current_file_ = file;
        current_line_ = line;
    }

    ::std::string current_file() const { return current_file_; }
    int current_line() const { return current_line_; }

    // --- Управление GC ---
    void collect() { ::gc_collect(); }
    void collect_young() { ::gc_collect_young(); }
    void collect_old() { ::gc_collect_old(); }
};

// =========================================================================
// 🌟 RAII-защита стековых переменных C++ от GC (LocalRoot)
// =========================================================================
template <typename T>
class LocalRoot {
private:
    T value_;

public:
    template <typename... Args>
    explicit LocalRoot(Args&&... args) : value_(std::forward<Args>(args)...) {
        ::gc_add_root(reinterpret_cast<uint64_t*>(&value_));
    }

    ~LocalRoot() {
        ::gc_remove_root(reinterpret_cast<uint64_t*>(&value_));
    }

    T& get() { return value_; }
    const T& get() const { return value_; }

    T* operator->() { return &value_; }
    const T* operator->() const { return &value_; }

    operator T() const { return value_; }

    LocalRoot& operator=(const T& other) {
        value_ = other;
        return *this;
    }
};

template <typename ParentT>
inline void write_barrier(ParentT* parent, ely_value* slot, ely_value new_val) {
    if (::is_gc_managed(parent) && ELY_IS_PTR(new_val)) {
        void* unboxed = ELY_UNBOX_PTR(new_val);
        void* dummy = unboxed;
        ::gc_write_barrier(parent, &dummy, unboxed);
    }
    *slot = new_val;
}

} // namespace ely