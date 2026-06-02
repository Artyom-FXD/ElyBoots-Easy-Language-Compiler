/**
 * file_native.c — Native C implementation for the File module.
 *
 * Wraps ely_runtime.h functions under file_* names.
 * Missing ely_* helpers are implemented directly.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <errno.h>

#ifdef _WIN32
#include <windows.h>
#include <direct.h>
#define stat _stat
#else
#include <unistd.h>
#include <limits.h>
#endif

#include "ely_runtime.h"

/* ---------------- Read / Write ---------------- */

char* file_read_all(char* path) {
    return ely_file_read_all(path, NULL);
}

void file_write_all(char* path, char* value) {
    ely_file_write_all(path, value, strlen(value));
}

/* ---------------- Existence & Remove ---------------- */

int file_exists(char* path) {
    return ely_file_exists(path);
}

void file_remove(char* path) {
    ely_file_remove(path);
}

void file_rename(char* path, char* newPath) {
    ely_file_rename(path, newPath);
}

/* ---------------- Path utilities ---------------- */

char* file_path_join(char* a, char* b) {
    return ely_path_join(a, b);
}

char* file_basename(char* path) {
    return ely_path_basename(path);
}

char* file_dirname(char* path) {
    return ely_path_dirname(path);
}

int file_is_absolute(char* path) {
    return ely_path_is_absolute(path);
}

/* ---------------- Metadata (direct impl, no ely_ wrappers) ---------------- */

long long file_size(char* path) {
    struct stat st;
    if (!path || stat(path, &st) != 0) return -1;
    return (long long)st.st_size;
}

int file_is_dir(char* path) {
    struct stat st;
    if (!path || stat(path, &st) != 0) return 0;
    return S_ISDIR(st.st_mode) ? 1 : 0;
}

int file_is_file(char* path) {
    struct stat st;
    if (!path || stat(path, &st) != 0) return 0;
    return S_ISREG(st.st_mode) ? 1 : 0;
}

int file_mkdir(char* path) {
#ifdef _WIN32
    return _mkdir(path);
#else
    return mkdir(path, 0755);
#endif
}

int file_rmdir(char* path) {
#ifdef _WIN32
    return _rmdir(path);
#else
    return rmdir(path);
#endif
}

long long file_mtime(char* path) {
    struct stat st;
    if (!path || stat(path, &st) != 0) return -1;
    return (long long)st.st_mtime;
}

char* file_list_dir(char* path) {
    /* Returns null-terminated concatenated file names separated by '\0',
       similar to ely_dict_join_keys style. For simplicity returns
       a JSON-like representation: ["a","b"].
       Actually, we use a simple allocation-based approach. */
    if (!path) return ely_str_dup("");

#ifdef _WIN32
    WIN32_FIND_DATAA fd;
    HANDLE h;
    char pattern[4096];
    snprintf(pattern, sizeof(pattern), "%s\\*", path);
    h = FindFirstFileA(pattern, &fd);
    if (h == INVALID_HANDLE_VALUE) return ely_str_dup("");
    size_t cap = 256, len = 0;
    char* buf = (char*)calloc(cap, 1);
    do {
        const char* name = fd.cFileName;
        if (strcmp(name, ".") == 0 || strcmp(name, "..") == 0) continue;
        int add = snprintf(NULL, 0, "%s%s", name, fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY ? "/" : "");
        size_t need = len + strlen(name) + add + 2;
        while (need > cap) { cap *= 2; buf = (char*)realloc(buf, cap); }
        strcpy(buf + len, name);
        if (fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) strcat(buf + len, "/");
        len += strlen(buf + len);
        buf[len++] = '\0';
    } while (FindNextFileA(h, &fd));
    FindClose(h);
    buf[len] = '\0';
    return buf;
#else
    DIR* d = opendir(path);
    if (!d) return ely_str_dup("");
    size_t cap = 256, len = 0;
    char* buf = (char*)calloc(cap, 1);
    struct dirent* e;
    while ((e = readdir(d)) != NULL) {
        const char* name = e->d_name;
        if (strcmp(name, ".") == 0 || strcmp(name, "..") == 0) continue;
        int is_dir = 0;
# ifdef _DIRENT_HAVE_D_TYPE
        is_dir = (e->d_type == DT_DIR);
# else
        {
            struct stat st;
            char sub[4096];
            snprintf(sub, sizeof(sub), "%s/%s", path, name);
            if (stat(sub, &st) == 0 && S_ISDIR(st.st_mode)) is_dir = 1;
        }
# endif
        int add = is_dir ? 1 : 0;
        size_t need = len + strlen(name) + add + 2;
        while (need > cap) { cap *= 2; buf = (char*)realloc(buf, cap); }
        strcpy(buf + len, name);
        if (is_dir) strcat(buf + len, "/");
        len += strlen(buf + len);
        buf[len++] = '\0';
    }
    closedir(d);
    buf[len] = '\0';
    return buf;
#endif
}