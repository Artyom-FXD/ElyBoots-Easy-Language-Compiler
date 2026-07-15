#pragma once

#include "ELYSQUARE_ely_context.hpp"
#include "ELYSQUARE_ely_str.hpp"
#include <string>
#include <exception>
#include <sstream>

namespace ely {

// Categories
// =========================================================================
enum class ErrorType {
    RuntimeError,
    TypeError,
    ValueError,
    IndexError,
    KeyError,
    NameError,
    SyntaxError,
    StackOverflow,
    GCError
};


inline const char* error_type_to_string(ErrorType type) {
    switch (type) {
        case ErrorType::RuntimeError:   return "RuntimeError";
        case ErrorType::TypeError:     return "TypeError";
        case ErrorType::ValueError:    return "ValueError";
        case ErrorType::IndexError:     return "IndexError";
        case ErrorType::KeyError:       return "KeyError";
        case ErrorType::NameError:      return "NameError";
        case ErrorType::SyntaxError:    return "SyntaxError";
        case ErrorType::StackOverflow:  return "StackOverflow";
        case ErrorType::GCError:         return "GCError";
    }
    return "UnknownError";
}

// Errors
// =========================================================================
class Error {
private:
    ErrorType type_;
    std::string message_;
    std::string file_;
    int line_;
    
    // Возможность прикрепить к ошибке произвольный объект Ely (например, если кинули кастомный класс)
    ely_value custom_payload_ = 0; 

public:
    Error(ErrorType type, std::string msg) // default constructor
        : type_(type), 
          message_(std::move(msg)), 
          file_(Context::get().current_file()), 
          line_(Context::get().current_line()) {}

    Error(ErrorType type, std::string msg, std::string file, int line)
        : type_(type), message_(std::move(msg)), file_(std::move(file)), line_(line) {}

    // --- Перегрузки для ely::str ---
    Error(ErrorType type, const ely::str& msg)
        : Error(type, std::string(msg.c_str())) {}

    Error(ErrorType type, const ely::str& msg, const ely::str& file, int line)
        : Error(type, std::string(msg.c_str()), std::string(file.c_str()), line) {}

    // --- Перегрузки для const char* ---
    Error(ErrorType type, const char* msg)
        : Error(type, std::string(msg)) {}

    Error(ErrorType type, const char* msg, const char* file, int line)
        : Error(type, std::string(msg), std::string(file), line) {}

    // Getters
    ErrorType type() const { return type_; }
    const std::string& message() const { return message_; }
    const std::string& file() const { return file_; }
    int line() const { return line_; }

    // Custom payload
    void set_payload(ely_value payload) { custom_payload_ = payload; }
    ely_value payload() const { return custom_payload_; }
    bool has_payload() const { return custom_payload_ != 0; }

    // Форматирование красивого трейсбэка
    std::string format() const {
        std::ostringstream ss;
        ss << "\n--- [ELY RUNTIME CRASH] ---\n"
           << "  File \"" << file_ << "\", line " << line_ << "\n"
           << "    " << error_type_to_string(type_) << ": " << message_ << "\n"
           << "---------------------------\n";
        return ss.str();
    }
};

// =========================================================================
// Error Exception
// =========================================================================
class ErrorException : public std::exception {
private:
    Error error_;
    mutable std::string formatted_what_; // Кэш для std::exception::what()

public:
    explicit ErrorException(Error err) : error_(std::move(err)) {}

    template <typename StrT>
    ErrorException(ErrorType type, StrT&& msg)
        : error_(type, std::forward<StrT>(msg)) {}

    template <typename StrT, typename FileT>
    ErrorException(ErrorType type, StrT&& msg, FileT&& file, int line)
        : error_(type, std::forward<StrT>(msg), std::forward<FileT>(file), line) {}

    const Error& error() const noexcept { return error_; }

    const char* what() const noexcept override {
        try {
            if (formatted_what_.empty()) {
                formatted_what_ = error_.format();
            }
            return formatted_what_.c_str();
        } catch (...) {
            return "Ely Exception occurred (formatting failed)";
        }
    }
};

// =========================================================================
// shortcuts
// =========================================================================
inline void throw_type_error(const std::string& msg) {
    throw ErrorException(ErrorType::TypeError, msg);
}

inline void throw_value_error(const std::string& msg) {
    throw ErrorException(ErrorType::ValueError, msg);
}

inline void throw_index_error(const std::string& msg) {
    throw ErrorException(ErrorType::IndexError, msg);
}

inline void throw_key_error(const std::string& msg) {
    throw ErrorException(ErrorType::KeyError, msg);
}

inline void throw_name_error(const std::string& msg) {
    throw ErrorException(ErrorType::NameError, msg);
}

} // namespace ely