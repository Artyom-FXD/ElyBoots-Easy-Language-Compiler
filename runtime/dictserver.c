#include "dictserver.h"
#include <string.h>
#include <stdlib.h>
#include <stdio.h>

struct DictServer {
    char* path;           // путь к файлу (для сохранения)
    dict* root;           // корневой объект (словарь из ely_value*)
};

static char* next_segment(char* path, char** next) {
    char* dot = strchr(path, '.');
    if (dot) {
        size_t len = dot - path;
        char* seg = ely_alloc(len + 1);
        memcpy(seg, path, len);
        seg[len] = '\0';
        *next = dot + 1;
        return seg;
    } else {
        char* seg = ely_str_dup(path);
        *next = NULL;
        return seg;
    }
}

// Получение узла по пути (создание, если create=1)
static ely_value* get_node(DictServer* ds, char* path, int create, int* is_array) {
    if (!path || !*path) return ely_value_new_object(ds->root);
    char* cur = path;
    ely_value* current = ely_value_new_object(ds->root);
    ely_value* parent = NULL;
    char* last_seg = NULL;
    int last_is_array = 0;

    while (cur) {
        char* seg = next_segment(cur, &cur);
        int index = -1;
        char* endptr;
        long idx = strtol(seg, &endptr, 10);
        if (*endptr == '\0') {
            index = (int)idx;
            // текущий узел должен быть массивом
            if (!current) {
                if (!create) { ely_free(seg); return NULL; }
                // создать массив
                arr* a = arr_new();
                current = ely_value_new_array(a);
                if (parent) {
                    if (last_is_array) {
                        // parent – массив, last_seg – индекс
                        arr_set(parent->u.array_val, (size_t)index, current);
                    } else {
                        // parent – словарь, last_seg – ключ
                        dict_set_str(parent->u.object_val, last_seg, current);
                    }
                } else {
                    ds->root = current->u.object_val;
                }
            }
            if (!current) { ely_free(seg); return NULL; }
            if (cur == NULL) {
                // последний сегмент – индекс, возвращаем элемент массива
                if (is_array) *is_array = 1;
                ely_value* elem = arr_get(current->u.array_val, (size_t)index);
                if (elem) return elem;
                if (create) {
                    ely_value* new_elem = ely_value_new_null();
                    arr_set(current->u.array_val, (size_t)index, new_elem);
                    return new_elem;
                }
                return NULL;
            } else {
                // переходим в элемент массива
                ely_value* elem_ptr = arr_get(current->u.array_val, (size_t)index);
                if (!elem_ptr && create) {
                    ely_value* new_elem = ely_value_new_null();
                    arr_set(current->u.array_val, (size_t)index, new_elem);
                    elem_ptr = new_elem;
                }
                parent = current;
                last_seg = seg;
                last_is_array = 1;
                current = elem_ptr;
                continue;
            }
        } else {
            // работаем со словарём
            if (!current) {
                if (!create) { ely_free(seg); return NULL; }
                // создать словарь
                dict* d = dict_new_str();
                current = ely_value_new_object(d);
                if (parent) {
                    if (last_is_array) {
                        arr_set(parent->u.array_val, (size_t)index, current);
                    } else {
                        dict_set_str(parent->u.object_val, last_seg, current);
                    }
                } else {
                    ds->root = current->u.object_val;
                }
            }
            if (!current) { ely_free(seg); return NULL; }
            if (cur == NULL) {
                // последний сегмент – ключ
                if (is_array) *is_array = 0;
                ely_value* val = dict_get_str(current->u.object_val, seg);
                if (val) return val;
                if (create) {
                    ely_value* new_val = ely_value_new_null();
                    dict_set_str(current->u.object_val, seg, new_val);
                    return new_val;
                }
                return NULL;
            } else {
                // переходим в словарь по ключу
                ely_value* val = dict_get_str(current->u.object_val, seg);
                if (!val && create) {
                    ely_value* new_val = ely_value_new_null();
                    dict_set_str(current->u.object_val, seg, new_val);
                    val = new_val;
                }
                parent = current;
                last_seg = seg;
                last_is_array = 0;
                current = val;
                continue;
            }
        }
        ely_free(seg);
    }
    return NULL;
}

// Создание нового пустого сервера
static DictServer* new_dictserver(char* path) {
    DictServer* ds = ely_alloc(sizeof(DictServer));
    ds->path = path ? ely_str_dup(path) : NULL;
    ds->root = dict_new_str();
    return ds;
}

void DictServer_save(DictServer* ds) {
    if (!ds || !ds->path) return;
    ely_str json = ely_dict_to_json(ds->root);
    FILE* f = fopen(ds->path, "w");
    if (f) {
        fputs(json, f);
        fclose(f);
    }
    ely_free(json);
}

// Реализация get-функций (возвращают сырые типы, извлекая из ely_value)
ely_str DictServer_get_str(DictServer* ds, char* path) {
    ely_value* node = get_node(ds, path, 0, NULL);
    if (!node || node->type != ely_VALUE_STRING) return NULL;
    return node->u.string_val ? ely_str_dup(node->u.string_val) : NULL;
}

ely_int DictServer_get_int(DictServer* ds, char* path) {
    ely_value* node = get_node(ds, path, 0, NULL);
    if (!node || node->type != ely_VALUE_INT) return 0;
    return (ely_int)node->u.int_val;
}

ely_bool DictServer_get_bool(DictServer* ds, char* path) {
    ely_value* node = get_node(ds, path, 0, NULL);
    if (!node || node->type != ely_VALUE_BOOL) return 0;
    return node->u.bool_val;
}

ely_double DictServer_get_double(DictServer* ds, char* path) {
    ely_value* node = get_node(ds, path, 0, NULL);
    if (!node || node->type != ely_VALUE_DOUBLE) return 0.0;
    return node->u.double_val;
}

dict* DictServer_get_dict(DictServer* ds, char* path) {
    ely_value* node = get_node(ds, path, 0, NULL);
    if (!node || node->type != ely_VALUE_OBJECT) return NULL;
    return node->u.object_val;
}

arr* DictServer_get_array(DictServer* ds, char* path) {
    ely_value* node = get_node(ds, path, 0, NULL);
    if (!node || node->type != ely_VALUE_ARRAY) return NULL;
    return node->u.array_val;
}

// Установка значений (создаёт путь)
void DictServer_set_str(DictServer* ds, char* path, ely_str value) {
    ely_value* node = get_node(ds, path, 1, NULL);
    if (!node) return;
    if (node->type != ely_VALUE_STRING) {
        // если узел был другого типа, заменяем
        ely_value* new_val = ely_value_new_string(value);
        // нужно обновить ссылку в родителе – здесь сложно, упрощаем: меняем тип напрямую
        node->type = ely_VALUE_STRING;
        if (node->u.string_val) ely_free(node->u.string_val);
        node->u.string_val = value ? ely_str_dup(value) : NULL;
        return;
    }
    if (node->u.string_val) ely_free(node->u.string_val);
    node->u.string_val = value ? ely_str_dup(value) : NULL;
}

void DictServer_set_int(DictServer* ds, char* path, ely_int value) {
    ely_value* node = get_node(ds, path, 1, NULL);
    if (!node) return;
    node->type = ely_VALUE_INT;
    node->u.int_val = value;
}

void DictServer_set_bool(DictServer* ds, char* path, ely_bool value) {
    ely_value* node = get_node(ds, path, 1, NULL);
    if (!node) return;
    node->type = ely_VALUE_BOOL;
    node->u.bool_val = value;
}

void DictServer_set_double(DictServer* ds, char* path, ely_double value) {
    ely_value* node = get_node(ds, path, 1, NULL);
    if (!node) return;
    node->type = ely_VALUE_DOUBLE;
    node->u.double_val = value;
}

void DictServer_set_dict(DictServer* ds, char* path, dict* value) {
    ely_value* node = get_node(ds, path, 1, NULL);
    if (!node) return;
    node->type = ely_VALUE_OBJECT;
    if (node->u.object_val && node->u.object_val != value) dict_free(node->u.object_val);
    node->u.object_val = value;
}

void DictServer_set_array(DictServer* ds, char* path, arr* value) {
    ely_value* node = get_node(ds, path, 1, NULL);
    if (!node) return;
    node->type = ely_VALUE_ARRAY;
    if (node->u.array_val && node->u.array_val != value) arr_free(node->u.array_val);
    node->u.array_val = value;
}

void DictServer_delete(DictServer* ds, char* path) {
    // удаление узла – не реализовано
}

arr* DictServer_query(DictServer* ds, char* filter) {
    return arr_new();
}

void DictServer_free(DictServer* ds) {
    if (ds) {
        if (ds->path) ely_free(ds->path);
        if (ds->root) dict_free(ds->root);
        ely_free(ds);
    }
}

// ======================== Экспортируемые функции для модуля ========================
ely_value* load(char* path) {
    DictServer* ds = new_dictserver(path);
    return ely_value_new_object(ds->root);
}

void save(ely_value* host, char* path) {
    if (!host || host->type != ely_VALUE_OBJECT) return;
    DictServer ds;
    ds.path = path ? ely_str_dup(path) : NULL;
    ds.root = host->u.object_val;
    DictServer_save(&ds);
    if (ds.path) ely_free(ds.path);
}

char* getStr(ely_value* host, char* key) {
    if (!host || host->type != ely_VALUE_OBJECT) return NULL;
    DictServer ds;
    ds.root = host->u.object_val;
    return DictServer_get_str(&ds, key);
}

int getInt(ely_value* host, char* key) {
    if (!host || host->type != ely_VALUE_OBJECT) return 0;
    DictServer ds;
    ds.root = host->u.object_val;
    return DictServer_get_int(&ds, key);
}

int getBool(ely_value* host, char* key) {
    if (!host || host->type != ely_VALUE_OBJECT) return 0;
    DictServer ds;
    ds.root = host->u.object_val;
    return DictServer_get_bool(&ds, key);
}

double getDouble(ely_value* host, char* key) {
    if (!host || host->type != ely_VALUE_OBJECT) return 0.0;
    DictServer ds;
    ds.root = host->u.object_val;
    return DictServer_get_double(&ds, key);
}

ely_value* getObj(ely_value* host, char* key) {
    if (!host || host->type != ely_VALUE_OBJECT) return NULL;
    DictServer ds;
    ds.root = host->u.object_val;
    dict* d = DictServer_get_dict(&ds, key);
    if (!d) return NULL;
    return ely_value_new_object(d);
}

void setStr(ely_value* host, char* key, char* value) {
    if (!host || host->type != ely_VALUE_OBJECT) return;
    DictServer ds;
    ds.root = host->u.object_val;
    DictServer_set_str(&ds, key, value);
}

void setInt(ely_value* host, char* key, int value) {
    if (!host || host->type != ely_VALUE_OBJECT) return;
    DictServer ds;
    ds.root = host->u.object_val;
    DictServer_set_int(&ds, key, value);
}

void setBool(ely_value* host, char* key, int value) {
    if (!host || host->type != ely_VALUE_OBJECT) return;
    DictServer ds;
    ds.root = host->u.object_val;
    DictServer_set_bool(&ds, key, value);
}

void setDouble(ely_value* host, char* key, double value) {
    if (!host || host->type != ely_VALUE_OBJECT) return;
    DictServer ds;
    ds.root = host->u.object_val;
    DictServer_set_double(&ds, key, value);
}

void setObj(ely_value* host, char* key, ely_value* value) {
    if (!host || host->type != ely_VALUE_OBJECT) return;
    if (!value || value->type != ely_VALUE_OBJECT) return;
    DictServer ds;
    ds.root = host->u.object_val;
    DictServer_set_dict(&ds, key, value->u.object_val);
}
