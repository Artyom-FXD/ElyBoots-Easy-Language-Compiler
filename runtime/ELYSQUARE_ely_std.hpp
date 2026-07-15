#pragma once

#include "ELYSQUARE_ely_context.hpp"
#include "ELYSQUARE_ely_str.hpp"
#include "ELYSQUARE_ely_any.hpp"
#include "ELYSQUARE_ely_collections.hpp"
#include "ELYSQUARE_ely_errors.hpp"

#include <iostream>
#include <chrono>
#include <thread>
#include <cmath>
#include <random>
#include <algorithm>
#include <vector>
#include <cstring>
#include <cctype>
#include <cstdlib>

#if defined(_WIN32) || defined(_WIN64)
    #ifndef WIN32_LEAN_AND_MEAN
        #define WIN32_LEAN_AND_MEAN
    #endif
    #ifndef NOMINMAX
        #define NOMINMAX
    #endif
    #include <windows.h>
#else
    #include <dlfcn.h>
    #include <unistd.h>
    #include <sys/stat.h>
#endif

namespace ely::std {

/*
 *  Vector-based strings build (like std::stringstream)
 * =========================================================================== */
class StrBuilder {
public:
    ::std::vector<char> buf;

    void append(char c) {
        buf.push_back(c);
    }
    void append(const char* s) {
        if (!s) return;
        buf.insert(buf.end(), s, s + ::std::strlen(s));
    }
    void append(const char* s, size_t len) {
        if (!s || len == 0) return;
        buf.insert(buf.end(), s, s + len);
    }
    void append(const ely::str& s) {
        buf.insert(buf.end(), s.c_str(), s.c_str() + s.length());
    }
    ely::str to_str() {
        if (buf.empty()) return ely::str("", 0);
        return ely::str(buf.data(), buf.size());
    }
};

/* ===========================================================================
 *  1. СИСТЕМНОЕ ОКРУЖЕНИЕ И ДИРЕКТОРИЯ (AOT / JIT)
 * =========================================================================== */

namespace detail {
    inline ely::str& get_mutable_root_dir() {
        static ely::str root_dir("");
        return root_dir;
    }
}

// Changes root to the path
inline void set_root_dir(const ely::str& path) {
    detail::get_mutable_root_dir() = path;
}

// Returns current path of executable
inline ely::str get_executable_directory() {
#if defined(_WIN32) || defined(_WIN64)
    char buffer[MAX_PATH];
    GetModuleFileNameA(NULL, buffer, MAX_PATH);
    char* pos = ::std::strrchr(buffer, '\\');
    if (!pos) pos = ::std::strrchr(buffer, '/');
    if (pos) *pos = '\0';
    return ely::str(buffer);
#else
    char buffer[1024];
    ssize_t len = readlink("/proc/self/exe", buffer, sizeof(buffer) - 1);
    if (len != -1) {
        buffer[len] = '\0';
        char* pos = ::std::strrchr(buffer, '/');
        if (pos) *pos = '\0';
        return ely::str(buffer);
    }
    return ely::str("", 0);
#endif
}

// Returns current root directory
inline ely::str get_root_dir() {
    auto& custom_path = detail::get_mutable_root_dir();
    if (!custom_path.empty()) {
        return custom_path;
    }
    return get_executable_directory();
}

/* ===========================================================================
 *  2. КРОСССПЛАТФОРМЕННЫЙ КЛАСС PATH (Полностью на ely::str)
 * =========================================================================== */

// Path
// ===========================================================================
class Path {
private:
    ely::str path_;

    // normalizes the given path for platform
    static inline ely::str normalize(const ely::str& p) {
        size_t len = p.length();
        if (len == 0) return p;
        ::std::vector<char> buf(p.c_str(), p.c_str() + len + 1);
        for (size_t i = 0; i < len; ++i) {
#if defined(_WIN32) || defined(_WIN64)
            if (buf[i] == '/') buf[i] = '\\';
#else
            if (buf[i] == '\\') buf[i] = '/';
#endif
        }
        return ely::str(buf.data(), len);
    }

public:
    Path() : path_("", 0) {}
    Path(ely::str p) : path_(normalize(p)) {}
    Path(const char* p) : path_(normalize(ely::str(p))) {}

    // Returns string representation of the path
    ely::str to_str() const { return path_; }
    // Returns string representation of the path
    const char* c_str() const { return path_.c_str(); }

    Path join(const ely::str& sub) const {
        if (path_.empty()) return Path(sub);
        char sep = '/';
#if defined(_WIN32) || defined(_WIN64)
        sep = '\\';
#endif
        size_t len = path_.length();
        if (path_[len - 1] == sep) return Path(path_ + sub);
        
        char sep_str[2] = { sep, '\0' };
        return Path(path_ + ely::str(sep_str, 1) + sub);
    }

    Path operator/(const ely::str& sub) const { return join(sub); }
    Path operator/(const char* sub) const { return join(ely::str(sub)); }

    // Checks if the path is valid
    bool exists() const {
#if defined(_WIN32) || defined(_WIN64)
        DWORD attribs = GetFileAttributesA(path_.c_str());
        return (attribs != INVALID_FILE_ATTRIBUTES);
#else
        struct stat buffer;
        return (stat(path_.c_str(), &buffer) == 0);
#endif
    }

    ely::str basename() const {
        const char* s = path_.c_str();
        const char* pos = ::std::strrchr(s, '/');
        if (!pos) pos = ::std::strrchr(s, '\\');
        if (!pos) return path_;
        return ely::str(pos + 1);
    }

    // Returns the parent directory of this file or path 
    Path parent() const {
        const char* s = path_.c_str();
        const char* pos = ::std::strrchr(s, '/');
        if (!pos) pos = ::std::strrchr(s, '\\');
        if (!pos) return Path("");
        return Path(ely::str(s, pos - s));
    }
};

// Returns the current working dir
#define CURRENT_DIR (ely::std::Path(ely::std::get_root_dir()))

/* ===========================================================================
 *  3. КОНСОЛЬ С ЦВЕТОВЫМИ ТЕГАМИ (Zero-allocation парсинг потока)
 * =========================================================================== */

// @brief console decorations
namespace detail {
    inline void stream_colors(const char* text) {
        if (!text) return;
        while (*text) {
            if (*text == '<') {
                if (::std::strncmp(text, "<red>", 5) == 0) { ::std::cout << "\033[31m"; text += 5; continue; }
                if (::std::strncmp(text, "<green>", 7) == 0) { ::std::cout << "\033[32m"; text += 7; continue; }
                if (::std::strncmp(text, "<yellow>", 8) == 0) { ::std::cout << "\033[33m"; text += 8; continue; }
                if (::std::strncmp(text, "<blue>", 6) == 0) { ::std::cout << "\033[34m"; text += 6; continue; }
                if (::std::strncmp(text, "<magenta>", 9) == 0) { ::std::cout << "\033[35m"; text += 9; continue; }
                if (::std::strncmp(text, "<cyan>", 6) == 0) { ::std::cout << "\033[36m"; text += 6; continue; }
                if (::std::strncmp(text, "<white>", 7) == 0) { ::std::cout << "\033[37m"; text += 7; continue; }
                if (::std::strncmp(text, "<bold>", 6) == 0) { ::std::cout << "\033[1m"; text += 6; continue; }
                if (::std::strncmp(text, "</red>", 6) == 0 || ::std::strncmp(text, "</green>", 8) == 0 || 
                    ::std::strncmp(text, "</yellow>", 9) == 0 || ::std::strncmp(text, "</blue>", 7) == 0 ||
                    ::std::strncmp(text, "</magenta>", 10) == 0 || ::std::strncmp(text, "</cyan>", 7) == 0 ||
                    ::std::strncmp(text, "</white>", 8) == 0 || ::std::strncmp(text, "</bold>", 7) == 0 ||
                    ::std::strncmp(text, "</>", 3) == 0 || ::std::strncmp(text, "<reset>", 7) == 0) {
                    ::std::cout << "\033[0m";
                    if (*(text + 1) == '/') {
                        while (*text && *text != '>') text++;
                        if (*text == '>') text++;
                    } else {
                        text += 7; // <reset>
                    }
                    continue;
                }
            }
            ::std::cout << *text;
            text++;
        }
        ::std::cout << "\033[0m\n";
    }
}

// @class console (terminal) representation
struct console {
    static inline void print(const char* fmt) {
        detail::stream_colors(fmt);
    }
    static inline void print(const ely::str& s) {
        detail::stream_colors(s.c_str());
    }
    // @brief prints a string to the terminal with "\\n"
    static inline void print(const any& val) {
        if (val.is_string()) {
            detail::stream_colors(val.c_str());
        } else {
            ::std::cout << val << "\n";
        }
    }

    // @brief prints a string to the terminal with "\\n"
    template<typename... Args>
    static inline void print(const char* fmt, Args&&... args) {
        int size_s = ::std::snprintf(nullptr, 0, fmt, ::std::forward<Args>(args)...);
        if (size_s <= 0) { ::std::cout << "\n"; return; }
        size_t size = static_cast<size_t>(size_s);
        ::std::vector<char> buf(size + 1);
        ::std::snprintf(buf.data(), buf.size(), fmt, ::std::forward<Args>(args)...);
        detail::stream_colors(buf.data());
    }

    // Returns user's text as a str
    static inline ely::str input(const char* prompt = nullptr) {
        if (prompt) {
            detail::stream_colors(prompt);
            ::std::cout.flush();
        }
        // Чтобы не тащить std::string для getline, читаем посимвольно из си-потока
        ::std::vector<char> input_buf;
        int ch;
        while ((ch = ::std::cin.get()) != '\n' && ch != EOF) {
            input_buf.push_back(static_cast<char>(ch));
        }
        return ely::str(input_buf.data(), input_buf.size());
    }
    
    static inline ely::str input(const ely::str& prompt) {
        return input(prompt.c_str());
    }
};

/* ===========================================================================
 *  4. JSON: ПАРСЕР И СЕРИАЛИЗАТОР (Полностью без std::string)
 * =========================================================================== */

namespace detail {
    class JsonParser {
    private:
        const char* src_;
        size_t pos_ = 0;

        void skip_whitespace() {
            while (src_[pos_] && (src_[pos_] == ' ' || src_[pos_] == '\t' || src_[pos_] == '\r' || src_[pos_] == '\n')) {
                pos_++;
            }
        }
        char peek() { skip_whitespace(); return src_[pos_]; }
        char get() { skip_whitespace(); return src_[pos_] ? src_[pos_++] : '\0'; }

        ely::str parse_string() {
            get(); // пропустить открывающую кавычку
            ::std::vector<char> buf;
            while (src_[pos_]) {
                char c = src_[pos_++];
                if (c == '"') {
                    return ely::str(buf.data(), buf.size());
                } else if (c == '\\') {
                    if (src_[pos_]) {
                        char next = src_[pos_++];
                        if (next == 'n') buf.push_back('\n');
                        else if (next == 't') buf.push_back('\t');
                        else if (next == 'r') buf.push_back('\r');
                        else if (next == '"') buf.push_back('"');
                        else if (next == '\\') buf.push_back('\\');
                        else buf.push_back(next);
                    }
                } else {
                    buf.push_back(c);
                }
            }
            throw ErrorException(ErrorType::SyntaxError, "JSON Parser Error: Unterminated string literal");
        }

        any parse_number() {
            skip_whitespace();
            const char* startptr = src_ + pos_;
            char* endptr = nullptr;
            
            bool is_double = false;
            size_t check_pos = pos_;
            while (src_[check_pos] && src_[check_pos] != ',' && src_[check_pos] != ']' && src_[check_pos] != '}' && !::std::isspace(static_cast<unsigned char>(src_[check_pos]))) {
                if (src_[check_pos] == '.' || src_[check_pos] == 'e' || src_[check_pos] == 'E') {
                    is_double = true;
                    break;
                }
                check_pos++;
            }

            if (is_double) {
                double val = ::std::strtod(startptr, &endptr);
                pos_ += (endptr - startptr);
                return any(val);
            } else {
                int64_t val = ::std::strtoll(startptr, &endptr, 10);
                pos_ += (endptr - startptr);
                return any(val);
            }
        }

    public:
        JsonParser(const char* src) : src_(src) {}

        any parse_value() {
            char c = peek();
            if (c == '"') return any(parse_string());
            if (c == '{') {
                get();
                ely::dict d;
                if (peek() == '}') { get(); return any(d); }
                while (true) {
                    if (peek() != '"') throw ErrorException(ErrorType::SyntaxError, "JSON Parser Error: Keys must be strings");
                    ely::str key = parse_string();
                    if (get() != ':') throw ErrorException(ErrorType::SyntaxError, "JSON Parser Error: Expected ':' separator");
                    any val = parse_value();
                    d.set(any(key.raw_value()), val);
                    char next = peek();
                    if (next == '}') { get(); break; }
                    if (next == ',') { get(); continue; }
                    throw ErrorException(ErrorType::SyntaxError, "JSON Parser Error: Expected ',' or '}'");
                }
                return any(d);
            }
            if (c == '[') {
                get();
                ely::array arr;
                if (peek() == ']') { get(); return any(arr); }
                while (true) {
                    arr.push(parse_value());
                    char next = peek();
                    if (next == ']') { get(); break; }
                    if (next == ',') { get(); continue; }
                    throw ErrorException(ErrorType::SyntaxError, "JSON Parser Error: Expected ',' or ']'");
                }
                return any(arr);
            }
            if (c == 't' && ::std::strncmp(src_ + pos_, "true", 4) == 0) { pos_ += 4; return any(true); }
            if (c == 'f' && ::std::strncmp(src_ + pos_, "false", 5) == 0) { pos_ += 5; return any(false); }
            if (c == 'n' && ::std::strncmp(src_ + pos_, "null", 4) == 0) { pos_ += 4; return any(nullptr); }
            if (::std::isdigit(static_cast<unsigned char>(c)) || c == '-') return parse_number();
            
            throw ErrorException(ErrorType::SyntaxError, "JSON Parser Error: Illegal character token");
        }
    };

    inline void stringify_impl(const any& val, StrBuilder& sb) {
        if (val.is_null()) { sb.append("null"); return; }
        if (val.is_bool()) { sb.append(val.as_bool() ? "true" : "false"); return; }
        if (val.is_int()) {
            char buf[32];
            ::std::snprintf(buf, sizeof(buf), "%lld", static_cast<long long>(val.as_int()));
            sb.append(buf);
            return;
        }
        if (val.is_float() || val.is_heap_double()) {
            char buf[64];
            ::std::snprintf(buf, sizeof(buf), "%g", val.as_double());
            sb.append(buf);
            return;
        }
        if (val.is_string()) {
            sb.append('"');
            const char* s = val.c_str();
            while (*s) {
                if (*s == '"') sb.append("\\\"");
                else if (*s == '\\') sb.append("\\\\");
                else if (*s == '\n') sb.append("\\n");
                else if (*s == '\t') sb.append("\\t");
                else if (*s == '\r') sb.append("\\r");
                else sb.append(*s);
                s++;
            }
            sb.append('"');
            return;
        }
        if (val.is_array()) {
            auto arr = val.as_array();
            sb.append('[');
            for (size_t i = 0; i < arr.size(); ++i) {
                stringify_impl(arr.get(i), sb);
                if (i + 1 < arr.size()) sb.append(',');
            }
            sb.append(']');
            return;
        }
        if (val.is_dict()) {
            auto d = val.as_dict();
            sb.append('{');
            size_t count = 0;
            
            // Фикс ошибки 420:32 — Прямой безопасный обход бакетов Си-структуры dict
            auto* raw_dict = reinterpret_cast<::dict*>(ely_unbox_ptr(d.raw()));
            if (raw_dict) {
                for (size_t i = 0; i < raw_dict->capacity; ++i) {
                    ::dict_entry* entry = raw_dict->buckets[i];
                    while (entry) {
                        any k(static_cast<ely_value>(entry->key));
                        any v(static_cast<ely_value>(entry->value));

                        sb.append('"');
                        sb.append(k.as_str());
                        sb.append("\":");
                        stringify_impl(v, sb);

                        if (++count < d.size()) sb.append(',');
                        entry = entry->next;
                    }
                }
            }
            sb.append('}');
            return;
        }
        sb.append("null");
    }
}

// JSON, yeah, bro...
struct json {
    // Makes a "any" value from JSON string
    static inline any parse(const ely::str& raw) {
        detail::JsonParser parser(raw.c_str());
        return parser.parse_value();
    }
    static inline any parse(const char* raw) {
        detail::JsonParser parser(raw);
        return parser.parse_value();
    }
    // Makes a JSON string from "any" value
    static inline ely::str stringify(const any& val) {
        StrBuilder sb;
        detail::stringify_impl(val, sb);
        return sb.to_str();
    }
};

/* ===========================================================================
 *  5. ВЫСОКОСКОРОСТНАЯ МАТЕМАТИКА С ПЕРЕГРУЗКОЙ
 * =========================================================================== */
struct math {
    // Returns the absolute value of val
    static inline int64_t abs(int64_t val) { return ::std::abs(val); }
    // Returns the absolute value of val
    static inline double abs(double val) { return ::std::fabs(val); }
    // Returns x to power y
    static inline double pow(double base, double exp) { return ::std::pow(base, exp); }
    // Returns square root of value
    static inline double sqrt(double val) { return ::std::sqrt(val); }
    // returns the smallest integer from two values
    static inline int64_t min(int64_t a, int64_t b) { return ::std::min(a, b); }
    // returns the smallest integer from two values
    static inline double min(double a, double b) { return ::std::min(a, b); }
    // returns the biggest integer from two values
    static inline int64_t max(int64_t a, int64_t b) { return ::std::max(a, b); }
    // returns the biggest integer from two values
    static inline double max(double a, double b) { return ::std::max(a, b); }
};

/* ===========================================================================
 *  6. TIME & ВЫСОКОТОЧНЫЙ ТАЙМЕР
 * =========================================================================== */

// Time
struct time {
    // Waits for (ms)
    static inline void sleep(int ms) {
        ::std::this_thread::sleep_for(::std::chrono::milliseconds(ms));
    }
};

// High-resolution timer
class Timer {
private:
    ::std::chrono::high_resolution_clock::time_point start_;

public:
    Timer() : start_(::std::chrono::high_resolution_clock::now()) {}
    // Resets the starting time to now
    inline void reset() { start_ = ::std::chrono::high_resolution_clock::now(); }
    // Returns seconds since construction or last call
    inline double elapsed() const {
        auto now = ::std::chrono::high_resolution_clock::now();
        return ::std::chrono::duration<double, ::std::milli>(now - start_).count();
    }
};

/* ===========================================================================
 *  7. БЕЗОПАСНАЯ И БЫСТРАЯ РАБОТА С ФАЙЛАМИ
 * =========================================================================== */

// File representation of the path
class File {
private:
    FILE* handle_ = nullptr;

public:
    File(const ely::str& path, const ely::str& mode) {
#if defined(_MSC_VER)
        fopen_s(&handle_, path.c_str(), mode.c_str());
#else
        handle_ = fopen(path.c_str(), mode.c_str());
#endif
        if (!handle_) {
            throw ErrorException(ErrorType::RuntimeError, "File I/O Error: Failed to open targeted path");
        }
    }

    ~File() { close(); }

    // Close the file
    void close() {
        if (handle_) {
            fclose(handle_);
            handle_ = nullptr;
        }
    }

    // Changes contents of a File
    void write(const ely::str& data) {
        if (!handle_) throw ErrorException(ErrorType::RuntimeError, "File I/O Error: Stream closed");
        fwrite(data.c_str(), 1, data.length(), handle_);
    }

    // Reads all the content from file
    ely::str read_all() {
        if (!handle_) throw ErrorException(ErrorType::RuntimeError, "File I/O Error: Stream closed");
        fseek(handle_, 0, SEEK_END);
        long size = ftell(handle_);
        fseek(handle_, 0, SEEK_SET);
        ::std::vector<char> buf(size);
        size_t read_bytes = fread(buf.data(), 1, size, handle_);
        return ely::str(buf.data(), read_bytes);
    }
};

/* ===========================================================================
 *  8. КРОССПЛАТФОРМЕННЫЙ ДИНАМИЧЕСКИЙ FFI (DYNLIB)
 * =========================================================================== */

// Dynamic library representation of the value
class Library {
private:
    void* handle_ = nullptr;

public:
    Library(const ely::str& path) {
#if defined(_WIN32) || defined(_WIN64)
        handle_ = (void*)LoadLibraryA(path.c_str());
#else
        handle_ = dlopen(path.c_str(), RTLD_NOW);
#endif
        if (!handle_) {
            throw ErrorException(ErrorType::RuntimeError, "FFI Error: Failed to bind external dynamic library");
        }
    }

    ~Library() { close(); }

    // closes the library
    void close() {
        if (handle_) {
#if defined(_WIN32) || defined(_WIN64)
            FreeLibrary((HMODULE)handle_);
#else
            dlclose(handle_);
#endif
            handle_ = nullptr;
        }
    }

    // Get a function pointer from this dynamic lib
    void* get_function(const ely::str& name) {
        if (!handle_) throw ErrorException(ErrorType::RuntimeError, "FFI Error: Library is closed");
#if defined(_WIN32) || defined(_WIN64)
        return (void*)GetProcAddress((HMODULE)handle_, name.c_str());
#else
        return dlsym(handle_, name.c_str());
#endif
    }
};

/* ===========================================================================
 *  9. ИНСПЕКЦИЯ И СИСТЕМНЫЕ ТИПЫ
 * =========================================================================== */

// additional utilities
namespace utils {
    // check if the value is in collection (ely array or dict)
    inline bool isIn(const any& val, const any& collection) {
        if (collection.is_array()) {
            auto arr = collection.as_array();
            for (size_t i = 0; i < arr.size(); ++i) {
                if (arr.get(i) == val) return true;
            }
        } else if (collection.is_dict()) {
            return collection.as_dict().has(val);
        } else if (collection.is_string() && val.is_string()) {
            return ::std::strstr(collection.c_str(), val.c_str()) != nullptr;
        }
        return false;
    }

    // Returns the string representation a type of the "any" value
    inline const char* typeOf(const any& val) {
        if (val.is_null()) return "null";
        if (val.is_bool()) return "bool";
        if (val.is_int()) return "int";
        if (val.is_float() || val.is_heap_double()) return "double";
        if (val.is_string()) return "string";
        if (val.is_array()) return "array";
        if (val.is_dict()) return "dict";
        if (val.is_function()) return "function";
        return "unknown";
    }

    // Check if the "any" value is of a specific type
    inline bool isType(const any& val, const ely::str& type_name) {
        char lower[32];
        size_t len = type_name.length();
        if (len >= 32) len = 31;
        for (size_t i = 0; i < len; ++i) {
            lower[i] = static_cast<char>(::std::tolower(static_cast<unsigned char>(type_name[i])));
        }
        lower[len] = '\0';

        if (::std::strcmp(lower, "int") == 0 || ::std::strcmp(lower, "integer") == 0) return val.is_int();
        if (::std::strcmp(lower, "double") == 0 || ::std::strcmp(lower, "float") == 0) return val.is_float() || val.is_heap_double();
        if (::std::strcmp(lower, "string") == 0 || ::std::strcmp(lower, "str") == 0) return val.is_string();
        if (::std::strcmp(lower, "bool") == 0 || ::std::strcmp(lower, "boolean") == 0) return val.is_bool();
        if (::std::strcmp(lower, "array") == 0 || ::std::strcmp(lower, "list") == 0) return val.is_array();
        if (::std::strcmp(lower, "dict") == 0 || ::std::strcmp(lower, "object") == 0) return val.is_dict();
        if (::std::strcmp(lower, "function") == 0 || ::std::strcmp(lower, "fn") == 0) return val.is_function();
        return false;
    }

    // Checks if a value is null
    inline bool isNull(const any& val) { return val.is_null(); }
    // Appends the value to the end of an array
    inline void append(ely::array& arr, const any& val) { arr.push(val); }
    // Appends the value to the end of an array
    inline void append(ely_value arr_val, const any& val) { ely::array(arr_val).push(val); }
    // Removes a specific element from its parent
    inline void remove(ely::array& arr, size_t index) { arr.remove(index); }
    // Removes a specific element from its parent
    inline void remove(ely::dict& d, const any& key) { d.remove(key); }
    
    // returns length of an array or dictionary
    inline size_t len(const any& val) {
        if (val.is_array()) return val.as_array().size();
        if (val.is_dict()) return val.as_dict().size();
        if (val.is_string()) return val.as_str().length();
        return 0;
    }

    // generate a random UUID
    inline ely::str uuid() {
        static ::std::random_device rd;
        static ::std::mt19937 gen(rd());
        static ::std::uniform_int_distribution<> dis(0, 15);
        static ::std::uniform_int_distribution<> dis2(8, 11);

        char buf[40];
        ::std::snprintf(buf, sizeof(buf), "%x%x%x%x%x%x%x%x-%x%x%x%x-4%x%x%x-%x%x%x%x-%x%x%x%x%x%x%x%x%x%x%x%x",
            dis(gen), dis(gen), dis(gen), dis(gen), dis(gen), dis(gen), dis(gen), dis(gen),
            dis(gen), dis(gen), dis(gen), dis(gen),
            dis(gen), dis(gen), dis(gen),
            dis2(gen), dis(gen), dis(gen), dis(gen),
            dis(gen), dis(gen), dis(gen), dis(gen), dis(gen), dis(gen), dis(gen), dis(gen), dis(gen), dis(gen), dis(gen), dis(gen));
        return ely::str(buf);
    }
}

/* ===========================================================================
 *  10. РЕКУРСИВНЫЙ ИНСПЕКТОР DUMP
 * =========================================================================== */

// An recursive inspector of the value
inline void dump(const any& val, int indent = 0) {
    for (int i = 0; i < indent * 4; ++i) ::std::cout << ' ';
    if (val.is_null()) {
        ::std::cout << "<null>\n";
    } else if (val.is_bool()) {
        ::std::cout << (val.as_bool() ? "true" : "false") << " (bool)\n";
    } else if (val.is_int()) {
        ::std::cout << val.as_int() << " (int)\n";
    } else if (val.is_float() || val.is_heap_double()) {
        ::std::cout << val.as_double() << " (double)\n";
    } else if (val.is_string()) {
        ::std::cout << "\"" << val.c_str() << "\" (string)\n";
    } else if (val.is_function()) {
        auto fn = val.as_function();
        ::std::cout << "<function '" << fn.name() << "' (arity=" << fn.arity() << ")>\n";
    } else if (val.is_array()) {
        auto arr = val.as_array();
        ::std::cout << "array (size=" << arr.size() << ") [\n";
        for (size_t i = 0; i < arr.size(); ++i) {
            dump(arr.get(i), indent + 1);
        }
        for (int i = 0; i < indent * 4; ++i) ::std::cout << ' ';
        ::std::cout << "]\n";
    } else if (val.is_dict()) {
        auto d = val.as_dict();
        ::std::cout << "dictionary (size=" << d.size() << ") {\n";
        
        // Фикс ошибки 680:28 — Безопасный прямой обход бакетов Си-структуры dict
        auto* raw_dict = reinterpret_cast<::dict*>(ely_unbox_ptr(d.raw()));
        if (raw_dict) {
            for (size_t i = 0; i < raw_dict->capacity; ++i) {
                ::dict_entry* entry = raw_dict->buckets[i];
                while (entry) {
                    any k(static_cast<ely_value>(entry->key));
                    any v(static_cast<ely_value>(entry->value));

                    for (int idx = 0; idx < (indent + 1) * 4; ++idx) ::std::cout << ' ';
                    ::std::cout << "Key: " << k.as_str().c_str() << " =>\n";
                    dump(v, indent + 2);

                    entry = entry->next;
                }
            }
        }
        for (int i = 0; i < indent * 4; ++i) ::std::cout << ' ';
        ::std::cout << "}\n";
    } else {
        ::std::cout << "Raw ely_value (" << val.raw() << ")\n";
    }
}

/* ===========================================================================
 *  11. ШИНА СОБЫТИЙ (EVENT EMITTER)
 * =========================================================================== */

// Event emitter
class EventEmitter {
private:
    ely::dict events_;

public:
    EventEmitter() : events_() {}

    void on(const ely::str& event_name, const any& callback) {
        any key(event_name.raw_value());
        if (!events_.has(key)) {
            events_.set(key, any(ely::array().raw()));
        }
        auto arr = events_.get(key).as_array();
        arr.push(callback);
    }

    void emit(const ely::str& event_name, const any& arg = nullptr) {
        any key(event_name.raw_value());
        if (!events_.has(key)) return;
        auto arr = events_.get(key).as_array();
        for (size_t i = 0; i < arr.size(); ++i) {
            any fn_any = arr.get(i);
            if (fn_any.is_function()) {
                auto fn = fn_any.as_function();
                auto raw_fn = fn.get_native<void(*)(ely_value)>();
                raw_fn(arg.raw());
            }
        }
    }
};

} // namespace ely::std