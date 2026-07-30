#include "ELYSQUARE_ely_str.hpp"
#include "ELYSQUARE_ely_any.hpp"
#include "ELYSQUARE_ely_collections.hpp"
#include <vector>
#include <string>
#include <type_traits>

namespace ely {

inline int64_t Int(any val)    { return val.as_int(); }
inline double Double(any val)  { return val.as_double(); }
inline float Float(any val)    { return val.as_float(); }
inline bool Bool(any val)      { return val.as_bool(); }
inline str Str(any val)        { return val.as_str(); }

// --- Universal static caster ---
// ELYSQUARE_ely_utils.hpp

// --- Universal static caster ---
template <typename T>
inline T As(any val) {
    if constexpr (::std::is_same_v<T, str>) {
        return val.as_str();
    } else if constexpr (::std::is_same_v<T, bool>) {
        return val.as_bool();
    } else if constexpr (::std::is_integral_v<T>) {
        return static_cast<T>(val.as_int());
    } else if constexpr (::std::is_same_v<T, double>) {
        return val.as_double();
    } else if constexpr (::std::is_same_v<T, float>) {
        return val.as_float();
    } else if constexpr (::std::is_same_v<T, array>) {
        return val.as_array();
    } else if constexpr (::std::is_same_v<T, dict>) {
        return val.as_dict();
    } else {
        static_assert(!sizeof(T*), "Unsupported type passed to ely::As<T>()");
    }
}

template <typename T>
::std::vector<T> ToVector(const ely::array& arr) {
    return arr.to_static_vector<T>();
}

template <typename K, typename V>
::std::unordered_map<K, V> ToMap(const ely::dict& dict) {
    return dict.to_static_map<K, V>();
}

}