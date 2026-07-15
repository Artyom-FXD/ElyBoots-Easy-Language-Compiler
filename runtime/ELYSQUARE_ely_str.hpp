#pragma once

#include "ely_dynamic.hpp"
#include <stdexcept>
#include <cstring>

namespace ely {

struct string_view {
private:
    const char* m_data;
    size_t m_size;

public:
    string_view() : m_data(""), m_size(0) {}
    string_view(const char* s) : m_data(s), m_size(s ? ::strlen(s) : 0) {}
    string_view(const char* s, size_t count) : m_data(s), m_size(count) {}

    const char* data() const { return m_data; }
    size_t size() const { return m_size; }
    bool empty() const { return m_size == 0; }
};

class str {
private:
    ely_value value;
    explicit str(ely_value val) : value(val) {}

public:
    str() : value(ely_box_inline_str("", 0)) {}

    str(const char* s, size_t len) {
        if (len <= 7) {
            value = ely_box_inline_str(s, len);
        } else {
            value = ely_value_new_string(s);
        }
    }
    
    str(const char* s) : str(s, ::strlen(s)) {}
    str(string_view sv) : str(sv.data(), sv.size()) {}

    ~str() = default;

    str(const str& other) = default;
    str& operator=(const str& other) = default;
    str(str&& other) noexcept = default;
    str& operator=(str&& other) noexcept = default;

    bool is_sso() const { return ely_is_immediate_str(value); }
    size_t length() const {
        if (is_sso()) return ely_immediate_str_len(value);
        return ely_str_len(c_str());
    }
    bool empty() const { return length() == 0; }

    const char* c_str() const {
        if (is_sso()) {
            return reinterpret_cast<const char*>(&value) + 1;
        }
        return ely_value_to_string(value);
    }

    // Декларируем оператор, реализация — в самом низу файла после ошибок!
    char operator[](size_t index) const;

    ely_value raw_value() const { return value; }

    str concat(const str& other) const {
        char* res = ely_str_concat_char(this->c_str(), other.c_str());
        str new_str(res);
        free(res);
        return new_str;
    }

    str operator+(const str& other) const {
        char* res = ely_str_concat_char(this->c_str(), other.c_str());
        str new_str(res);
        free(res);
        return new_str;
    }

    str& operator+=(const str& other) {
        *this = *this + other;
        return *this;
    }

    str operator-(int count) const {
        const char* original = this->c_str();
        int len = static_cast<int>(this->length());
        int new_len = len - count;

        if (new_len <= 0) {
            return str("", 0);
        }

        char* modified = new char[new_len + 1];
        std::memcpy(modified, original, new_len);
        modified[new_len] = '\0';

        str new_str(modified, new_len);
        delete[] modified;
        return new_str;
    }

    str& operator-=(int count) {
        *this = *this - count;
        return *this;
    }

    str operator*(int count) const {
        if (count <= 0 || this->length() == 0) return str("", 0);

        size_t len = length();
        size_t new_len = len * count;

        char* buf = static_cast<char*>(malloc(new_len + 1));
        for (int i = 0; i < count; i++) {
            memcpy(buf + (i * len), c_str(), len);
        }
        buf[new_len] = '\0';

        str new_str(buf, new_len);
        free(buf);
        return new_str;
    }

    str& operator*=(int count) {
        *this = *this * count;
        return *this;
    }

    bool operator==(const str& other) const { return ely_str_cmp(this->c_str(), other.c_str()) == 0; }
    bool operator!=(const str& other) const { return !(*this == other); }
    bool operator<(const str& other) const { return ely_str_cmp(this->c_str(), other.c_str()) < 0; }
    bool operator>(const str& other) const { return ely_str_cmp(this->c_str(), other.c_str()) > 0; }
    bool operator<=(const str& other) const { return ely_str_cmp(this->c_str(), other.c_str()) <= 0; }
    bool operator>=(const str& other) const { return ely_str_cmp(this->c_str(), other.c_str()) >= 0; }
};

inline str operator*(int count, const str& s) { return s * count; }
inline int len(str s) { return s.length(); }
inline int size(str s) { return s.length(); }

} // namespace ely

#include "ELYSQUARE_ely_errors.hpp"

namespace ely {
inline char str::operator[](size_t index) const {
    if (index >= length()) {
        throw ErrorException(ErrorType::IndexError, "String index out of range");
    }
    return c_str()[index];
}
} // namespace ely