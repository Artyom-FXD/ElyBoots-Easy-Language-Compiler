# ely Language

**ely Language** — a statically typed, compiled programming language with fast compilation, built-in collections, generics, and convenient syntax.

- Lightning-fast compilation (TCC)
- Safe static typing
- Dynamic arrays and dictionaries
- Generics (templates)
- Error handling (`asafe`/`except`/`throw`)
- F-strings with interpolation
- Modular system
- Built-in standard library
- JSON support via the DictServer module

---

## Table of Contents

1. [Features](#features)
2. [Syntax and Examples](#syntax-and-examples)
3. [Standard Library](#standard-library)
   - [Console](#console)
   - [Type Conversions](#type-conversions)
   - [String Functions](#string-functions)
   - [Mathematics](#mathematics)
   - [Time](#time)
   - [Files](#files)
   - [Paths](#paths)
   - [Dynamic Libraries](#dynamic-libraries)
   - [Array Methods](#array-methods)
4. [DictServer Module (JSON)](#dictserver-module-json)
5. [Modules and the elyBoots Compiler](#modules-and-the-elyboots-compiler)
6. [License](#license)

---

## Features

- **Static Typing** — type safety at compile time. Type inference via `var`.
- **Lightning-fast Compilation** — thanks to the Tiny C Compiler (TCC), compilation occurs at speeds of hundreds of thousands of lines per second.
- **Built-in Collections** — dynamic arrays (`arr<T>`) and dictionaries (`dict<K,V>`) with convenient methods: `push`, `pop`, `len`, index and key access.
- **Generics (Templates)** — write generic functions and structures. Types are inferred from arguments. Monomorphization is implemented — each specialization generates optimized code.
- **Error Handling** — `asafe` / `except` / `throw` blocks — a clear exception mechanism.
- **F-strings** — expression interpolation directly within a string: `f"Hello, {name}!"`. Automatic conversion to string of arrays, dictionaries, numbers.
- **Modularity** — project building via `manager.json`. Modules are compiled into dynamic libraries (`.dll`/`.so`) and can be reused.
- **Future Garbage Collector** — upcoming release — automatic memory management for strings, arrays, dictionaries, and objects.

---

## Syntax and Examples

```c
// Hello, World!
public func main() -> int {
    println("Hello, World!");
    return 0;
}
```

```c
// Generic function
func identity<T>(T x) -> T {
    return x;
}

// Arrays and dictionaries
int[] a = [1, 2, 3];
a.push(4);
println(a);          // [1,2,3,4]

dict<str, int> d = {"x": 10, "y": 20};
d.z = 30;
println(d);          // {"x":10,"y":20,"z":30}

// Error handling
asafe {
    throw "Something went wrong";
} except (str e) {
    println(e);
}

// F-string
str name = "World";
println(f"Hello, {name}!");   // Hello, World!
```

---

## Standard Library

All built-in functions are available without `using` and are written in **camelCase** style.

### Console

| Function               | Description                                     | Example                              |
|-----------------------|-------------------------------------------------|--------------------------------------|
| `print(str)`          | Prints a string without a newline              | `print("Hello")`                     |
| `println(str)`        | Prints a string with a newline                 | `println("World")`                   |
| `println(int)`        | Prints an integer                              | `println(42)`                        |
| `println(bool)`       | Prints true/false                              | `println(true)`                      |
| `println(arr<T>)`     | Prints an array in JSON format                 | `println([1,2,3])` → `[1,2,3]`       |
| `println(dict<K,V>)`  | Prints a dictionary in JSON format             | `println({"x":5})` → `{"x":5}`        |
| `input()`             | Reads a string from stdin                      | `str s = input()`                    |
| `inputPrompt(str)`    | Prints a prompt and reads a string             | `str name = inputPrompt("Name: ")`   |

### Type Conversions

| Function                   | Description                     | Example                                      |
|----------------------------|---------------------------------|----------------------------------------------|
| `strToInt(str)`           | String → int                    | `int x = strToInt("123")`                    |
| `strToUint(str)`          | String → uint                   | `uint u = strToUint("42")`                   |
| `strToMore(str)`          | String → more (long long)       | `more m = strToMore("9223372036854775807")`  |
| `strToUm(str)`            | String → umore                  | `umore um = strToUm("18446744073709551615")` |
| `strToFlt(str)`           | String → flt (float)            | `flt f = strToFlt("3.14")`                   |
| `strToDouble(str)`        | String → double                 | `double d = strToDouble("3.14159")`          |
| `intToStr(int)`           | int → string                    | `str s = intToStr(42)`                       |
| `uintToStr(uint)`         | uint → string                   | `str s = uintToStr(42u)`                     |
| `moreToStr(more)`         | more → string                   | `str s = moreToStr(123456789LL)`             |
| `umoreToStr(umore)`       | umore → string                  | `str s = umoreToStr(987654321ULL)`           |
| `fltToStr(flt)`           | flt → string                    | `str s = fltToStr(3.14f)`                    |
| `doubleToStr(double)`     | double → string                 | `str s = doubleToStr(2.71828)`               |
| `boolToStr(bool)`         | bool → "true"/"false"           | `str s = boolToStr(true)`                    |

### String Functions

| Function                      | Description                         | Example                                  |
|-------------------------------|-------------------------------------|------------------------------------------|
| `len(str)`                    | String length                       | `int n = len("hello")`                   |
| `dup(str)`                    | String copy                         | `str s = dup("text")`                    |
| `concat(str, str)`            | Concatenation                       | `str s = concat("Hello", "World")`       |
| `cmp(str, str)`               | Comparison (0 = equal)              | `int r = cmp("abc", "abd")`              |
| `substr(str, start, len)`     | Substring                           | `str s = substr("hello", 1, 2)` → `"el"` |
| `trim(str)`                   | Remove leading/trailing whitespace  | `str s = trim("  abc  ")` → `"abc"`      |
| `replace(str, old, new)`      | Replace substring                   | `str s = replace("ababa", "ab", "c")` → `"cba"` |

### Mathematics

| Function                       | Description                              |
|--------------------------------|------------------------------------------|
| `abs(int)`                     | Absolute value                           |
| `absMore(more)`                | Absolute value for more                  |
| `fabs(double)`                 | Absolute value for double                |
| `min(int, int)`                | Minimum                                  |
| `max(int, int)`                | Maximum                                  |
| `pow(double, double)`          | Power function                           |
| `sqrt(double)`                 | Square root                              |
| `sin(double), cos(double), tan(double)` | Trigonometry                    |
| `rand()`                       | Random integer (0..32767)                |
| `srand(uint)`                  | Set seed                                 |
| `randDouble()`                 | Random double [0..1)                     |

### Time

| Function                    | Description                              |
|-----------------------------|------------------------------------------|
| `sleep(uint)`               | Pause in milliseconds                    |
| `timeNow()`                 | Current time (seconds since epoch)       |
| `timeDiff(more, more)`      | Difference in seconds (double)           |

### Files

File operations using the `File` type (opaque pointer).

| Function                         | Description                                         |
|----------------------------------|---------------------------------------------------|
| `fileOpen(str, str)`             | Open a file (mode "r", "w", "rb", "wb")           |
| `fileClose(File)`                | Close a file                                      |
| `fileWrite(File, str, int)`      | Write data (string, length)                       |
| `fileRead(File, int*)`           | Read data (returns string, size via pointer)      |
| `fileExists(str)`                | Check existence                                   |
| `fileReadAll(str, int*)`         | Read entire file                                  |
| `fileRemove(str)`                | Delete a file                                     |
| `fileRename(str, str)`           | Rename                                          |

### Paths

| Function                | Description                     |
|-------------------------|---------------------------------|
| `pathJoin(str, str)`    | Join paths                      |
| `pathBasename(str)`     | File name from path             |
| `pathDirname(str)`      | Directory from path             |
| `pathIsAbsolute(str)`   | Check for absolute path         |

### Dynamic Libraries

| Function                              | Description                                      |
|---------------------------------------|--------------------------------------------------|
| `loadLibrary(str)`                    | Load DLL/so (returns pointer)                   |
| `getFunction(any, str)`               | Get function by name                            |
| `closeLibrary(any)`                   | Unload library                                  |
| `callIntInt(any, int, int)`           | Call function `int func(int, int)`              |
| `callDoubleDouble(any, double)`       | Call `double func(double)`                      |
| `callDoubleDoubleDouble(any, double, double)` | Call `double func(double, double)`      |
| `callStrVoid(any)`                    | Call `char* func(void)`                         |

### Array Methods `arr<T>`

| Method             | Description                                         | Example                |
|--------------------|-----------------------------------------------------|------------------------|
| `push(T)`          | Add element to the end                              | `a.push(10)`           |
| `pop()`            | Remove and return the last element                  | `int x = a.pop()`      |
| `len()`            | Array length                                        | `int n = a.len()`      |
| `insert(int, T)`   | Insert element at index                             | `a.insert(1, 99)`      |
| `remove(T)`        | Remove the first occurrence of a value              | `a.remove(42)`         |
| `index(T)`         | Find index of first occurrence (-1 if not found)    | `int i = a.index(5)`   |

---

## DictServer Module (JSON)

Import with `using DictServer;`. The `DictHost` type is an opaque pointer to a dictionary.

### Loading and Saving

| Function                | Description                                     |
|-------------------------|-------------------------------------------------|
| `load(str)`             | Loads JSON from a file, returns DictHost        |
| `save(DictHost, str)`   | Saves dictionary to a file                      |

### Getting Values

| Function                     | Description                          |
|------------------------------|------------------------------------|
| `getStr(DictHost, str)`      | Returns a string by key             |
| `getInt(DictHost, str)`      | Returns an int                      |
| `getBool(DictHost, str)`     | Returns a bool                      |
| `getDouble(DictHost, str)`   | Returns a double                    |
| `getObj(DictHost, str)`      | Returns a nested dictionary (DictHost) |

### Setting Values

| Function                         | Description                         |
|----------------------------------|-----------------------------------|
| `setStr(DictHost, str, str)`     | Sets a string                     |
| `setInt(DictHost, str, int)`     | Sets an integer                   |
| `setBool(DictHost, str, bool)`   | Sets a boolean                    |
| `setDouble(DictHost, str, double)` | Sets a double                   |
| `setObj(DictHost, str, DictHost)`  | Sets a nested dictionary        |

### Key Management and Serialization

| Function                | Description                                    |
|-------------------------|------------------------------------------------|
| `del(DictHost, str)`    | Deletes a key                                  |
| `has(DictHost, str)`    | Checks key existence                           |
| `keys(DictHost)`        | Returns an array of key strings                |
| `toJson(DictHost)`      | Returns the dictionary's JSON representation   |
| `parse(str)`            | Parses JSON into DictHost                      |
| `freeDict(DictHost)`    | Frees memory                                   |

---

## Modules and the elyBoots Compiler

### Project Structure

```json
{
    "name": "ProjectName",
    "libs": {},
    "modules": {
        "DictServer": "./modules/math.e"
    },
    "enter": "main.e",
    "stx": {
        "processType": "console"
    },
    "output": {
        "folder-modules": {
            "modules": "*"
        },
        "enter": {
            "name": "app.exe",
            "type": "exe"
        }
    }
}
```

### Building a Project

```bash
python ebt.py build
```

The executable file will appear in the `output/` folder.

### Creating a Module

```c
// math.e
public func add(a: int, b: int) -> int {
    return a + b;
}
```

Use `using math;` in your main code. The compiler will generate a header file and a dynamic library.
