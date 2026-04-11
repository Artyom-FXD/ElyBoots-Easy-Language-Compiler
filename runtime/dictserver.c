#include "dictserver.h"
#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include "ely_gc.h"          /* новый GC */

struct DictServer {
    char* path;             /* путь к файлу (для сохранения) */
    dict* root;             /* корневой объект (словарь из ely_value*) */
};

/* --------------------------------------------------------------------------
 * Вспомогательные функции для работы с путями через точку
 * -------------------------------------------------------------------------- */

/* Разбирает следующий сегмент пути (до точки) */
static char* next_segment(char* path, char** next) {
    char* dot = strchr(path, '.');
    if (dot) {
        size_t len = dot - path;
        char* seg = gc_alloc(len + 1, GC_OBJ_STRING);
        memcpy(seg, path, len);
        seg[len] = '\0';
        *next = dot + 1;
        return seg;
    } else {
        char* seg = ely_str_dup(path);   /* ely_str_dup теперь использует gc_alloc */
        *next = NULL;
        return seg;
    }
}

/* --------------------------------------------------------------------------
 * Получение узла по пути (с возможностью создания)
 * -------------------------------------------------------------------------- */
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
            /* Текущий узел должен быть массивом */
            if (!current) {
                if (!create) {
                    /* seg не освобождаем явно – GC соберёт */
                    return NULL;
                }
                /* Создать массив */
                arr* a = arr_new();
                current = ely_value_new_array(a);
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
            if (!current) {
                return NULL;
            }
            if (cur == NULL) {
                /* Последний сегмент – индекс, возвращаем элемент массива */
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
                /* Переходим в элемент массива */
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
            /* Работаем со словарём */
            if (!current) {
                if (!create) {
                    return NULL;
                }
                /* Создать словарь */
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
            if (!current) {
                return NULL;
            }
            if (cur == NULL) {
                /* Последний сегмент – ключ */
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
                /* Переходим в словарь по ключу */
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
        /* seg больше не нужен, GC освободит позже */
    }
    return NULL;
}

/* --------------------------------------------------------------------------
 * Создание нового экземпляра DictServer
 * -------------------------------------------------------------------------- */
static DictServer* new_dictserver(char* path) {
    DictServer* ds = gc_alloc(sizeof(DictServer), GC_OBJ_OTHER);
    ds->path = path ? ely_str_dup(path) : NULL;
    ds->root = dict_new_str();
    return ds;
}

/* --------------------------------------------------------------------------
 * Сохранение словаря в файл
 * -------------------------------------------------------------------------- */
void DictServer_save(DictServer* ds) {
    if (!ds || !ds->path) return;
    ely_str json = ely_dict_to_json(ds->root);
    FILE* f = fopen(ds->path, "w");
    if (f) {
        fputs(json, f);
        fclose(f);
    }
    /* json – временная строка, GC освободит */
}

/* --------------------------------------------------------------------------
 * Геттеры значений
 * -------------------------------------------------------------------------- */
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

/* --------------------------------------------------------------------------
 * Сеттеры значений (создают путь при необходимости)
 * -------------------------------------------------------------------------- */
void DictServer_set_str(DictServer* ds, char* path, ely_str value) {
    ely_value* node = get_node(ds, path, 1, NULL);
    if (!node) return;
    if (node->type != ely_VALUE_STRING) {
        /* Меняем тип узла на строку */
        node->type = ely_VALUE_STRING;
        /* Старое значение (если было) не освобождаем явно – GC */
        node->u.string_val = value ? ely_str_dup(value) : NULL;
        return;
    }
    /* Уже строка – заменяем содержимое */
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
    /* Старый словарь не освобождаем – GC */
    node->u.object_val = value;
}

void DictServer_set_array(DictServer* ds, char* path, arr* value) {
    ely_value* node = get_node(ds, path, 1, NULL);
    if (!node) return;
    node->type = ely_VALUE_ARRAY;
    /* Старый массив не освобождаем – GC */
    node->u.array_val = value;
}

/* --------------------------------------------------------------------------
 * Удаление узла (пока не реализовано)
 * -------------------------------------------------------------------------- */
void DictServer_delete(DictServer* ds, char* path) {
    (void)ds; (void)path;
    /* TODO: реализовать удаление */
}

/* --------------------------------------------------------------------------
 * Запрос (заглушка)
 * -------------------------------------------------------------------------- */
arr* DictServer_query(DictServer* ds, char* filter) {
    (void)ds; (void)filter;
    return arr_new();
}

/* --------------------------------------------------------------------------
 * Освобождение DictServer (теперь не нужно, GC всё уберёт)
 * -------------------------------------------------------------------------- */
void DictServer_free(DictServer* ds) {
    /* В новом GC явное освобождение не требуется.
       Можно оставить функцию пустой для совместимости. */
    (void)ds;
}

/* ==========================================================================
 * Экспортируемые функции для модуля Ely
 * ========================================================================== */

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
    /* ds.path будет освобождён GC */
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