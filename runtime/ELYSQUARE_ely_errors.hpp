#pragma once

// #include "ELYSQUARE_ely_context.hpp"
#include <csetjmp>
#include <cstdio>
#include <cstdlib>
#include <utility>
#include <ostream>

namespace ely {

// Forward declaration
class str;

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

// -------------------------------------------------------------------------
// Контекст ошибок (C-style Exception Runtime)
// -------------------------------------------------------------------------
struct ErrorData {
    ErrorType type;
    const char* message;
    const char* file;
    int line;
};

struct ExceptionFrame {
    ::std::jmp_buf env;
    ExceptionFrame* prev = nullptr;
};

inline thread_local ExceptionFrame* g_current_frame = nullptr;
inline thread_local ErrorData g_last_error{};

// Замена std::throw_exception / throw
[[noreturn]] inline void raise(ErrorType type, const char* msg, const char* file = nullptr, int line = 0) {
    g_last_error = { type, msg, file, line };

    if (g_current_frame) {
        ::std::longjmp(g_current_frame->env, 1);
    } else {
        ::std::fprintf(stderr,
            "\n--- [UNHANDLED ELY CRASH] ---\n"
            "  File \"%s\", line %d\n"
            "    %s: %s\n"
            "-----------------------------\n",
            file ? file : "unknown", line,
            error_type_to_string(type),
            msg ? msg : ""
        );
        ::std::abort();
    }
}

// -------------------------------------------------------------------------
// Шорткаты для возбуждения ошибок через raise(...)
// -------------------------------------------------------------------------
inline void raise_type_error(const char* msg, const char* file = nullptr, int line = 0) {
    raise(ErrorType::TypeError, msg, file, line);
}

inline void raise_value_error(const char* msg, const char* file = nullptr, int line = 0) {
    raise(ErrorType::ValueError, msg, file, line);
}

inline void raise_index_error(const char* msg, const char* file = nullptr, int line = 0) {
    raise(ErrorType::IndexError, msg, file, line);
}

inline void raise_syntax_error(const char* msg, const char* file = nullptr, int line = 0) {
    raise(ErrorType::SyntaxError, msg, file, line);
}

inline void raise_runtime_error(const char* msg, const char* file = nullptr, int line = 0) {
    raise(ErrorType::RuntimeError, msg, file, line);
}

inline ::std::ostream& operator<<(::std::ostream& os, const ErrorData& err) {
    return os << err.message; // или err.msg, в зависимости от имени поля
}

} // namespace ely

// -------------------------------------------------------------------------
// Макросы контроля выполнения: asafe / except
// -------------------------------------------------------------------------

// Безопасный блок (аналог try)
#define asafe \
    for (::ely::ExceptionFrame _frame{ {}, ::ely::g_current_frame }, *_once = (::ely::ExceptionFrame*)(::ely::g_current_frame = &_frame, (void*)1); \
         _once; \
         ::ely::g_current_frame = _frame.prev, _once = nullptr) \
        if (setjmp(_frame.env) == 0)

// Блок перехвата (аналог catch), возвращает структуру ::ely::ErrorData
#define except(err_var) \
        else for (::ely::ErrorData err_var = ::ely::g_last_error, *_once_c = (::ely::ErrorData*)1; _once_c; _once_c = nullptr)