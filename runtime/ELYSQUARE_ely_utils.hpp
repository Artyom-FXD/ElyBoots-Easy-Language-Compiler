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
inline std::string String(any val) { return val.as_string(); } // std::string[cite: 11]
inline str Str(any val)        { return val.as_str(); }       // ely::str[cite: 13]

// --- Universal static caster ---
template <typename T>
inline T As(any val) {
    if constexpr (std::is_same_v<T, str>) {
        return val.as_str();
    } else {
        return val.as<T>();
    }
}

template <typename T>
std::vector<T> ToVector(const ely::array& arr) {
    return arr.to_static_vector<T>();
}

template <typename K, typename V>
std::unordered_map<K, V> ToMap(const ely::dict& dict) {
    return dict.to_static_map<K, V>();
}

}