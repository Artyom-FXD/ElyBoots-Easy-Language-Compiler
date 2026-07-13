import sys, os
from typing import List, Dict
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from parser import *
from codegen.classes_codegen import ClassCodeGen

class CppCodeGen(ClassCodeGen):
    def __init__(self, debug=False, is_module=False):
        super().__init__(debug, is_module)
        # C++ бэкенд использует RAII для GC-корней
        self.use_raii_roots = True
        self.header_code: List[str] = []
        self.global_code: List[str] = []
        self.main_code: List[str] = []
        self.specializations: List[str] = []
        self.extern_functions: Dict[str, ExternFunction] = {}
        self.interfaces_ast: Dict[str, InterfaceDeclaration] = {}
        self._init_builtins()

    def _init_builtins(self):
        builtins = {
            'print':     ('ely_println_str',   'void', ['char*']),
            'println':   ('ely_println_str', 'void', ['char*']),
            'printOld':  ('ely_print',   'void', ['char*']),
            'timeNow':     ('ely_time_now',      'more', []),
            'timeNowMs':   ('ely_time_now_ms',   'more', []),
            'timeDiff':    ('ely_time_diff',     'double', ['more', 'more']),
            'formatTime':  ('ely_format_time',   'ely_value',   ['ely_value', 'ely_value']),
            'parseTime':   ('ely_parse_time',    'more',  ['ely_value', 'ely_value']),
            'sleep':       ('ely_sleep',         'void',  ['unsigned int']),
            'randInt':       ('ely_rand_int',        'int',  []),
            'randIntRange':  ('ely_rand_int_range',  'int',  ['int', 'int']),
            'randBool':      ('ely_rand_bool',       'int', []),
            'srand':         ('ely_srand',           'void', ['unsigned int']),
            'rand':          ('ely_rand',            'int',  []),
            'randDouble':    ('ely_rand_double',     'double', []),
            'fileWriteAll': ('ely_file_write_all_simple', 'int', ['char*', 'char*']),
            'fileReadAll':  ('ely_file_read_all_simple', 'char*', ['char*']),
            'fileExists':   ('ely_file_exists',   'int', ['char*']),
            'fileRename':   ('ely_file_rename',   'int',  ['char*', 'char*']),
            'fileRemove':   ('ely_file_remove',   'int',  ['char*']),
            'pathJoin':        ('ely_path_join',        'str', ['str', 'str']),
            'pathBasename':    ('ely_path_basename',    'str', ['str']),
            'pathDirname':     ('ely_path_dirname',     'str', ['str']),
            'pathIsAbsolute':  ('ely_path_is_absolute', 'int', ['str']),
            'loadLibrary':      ('ely_load_library',      'void*',  ['char*']),
            'getFunction':      ('ely_get_function',      'void*',  ['void*', 'char*']),
            'callIntInt':       ('ely_call_int_int',      'int',  ['void*', 'int', 'int']),
            'callDoubleDouble': ('ely_call_double_double','double',['void*', 'double']),
            'callDoubleDoubleDouble': ('ely_call_double_double_double', 'double', ['void*', 'double', 'double']),
            'callStrVoid':      ('ely_call_str_void',     'char*',  ['void*']),
            'closeLibrary':     ('ely_close_library',     'void', ['void*']),
            'jsonify':  ('ely_dict_to_json', 'char*', ['ely_value']),
            'dictify':  ('ely_dictify',      'void*', ['char*']),
            'keys': ('ely_dict_keys', 'ely_value', ['ely_value']),
            'has':  ('ely_dict_has',  'int',     ['ely_value', 'ely_value']),
            'del':  ('ely_dict_del',  'void',     ['ely_value', 'ely_value']),
            'len':      ('ely_str_len',       'size_t',   ['char*']),
            'concat':   ('ely_str_concat',    'char*',   ['char*', 'char*']),
            'dup':      ('ely_str_dup',       'char*',   ['char*']),
            'cmp':      ('ely_str_cmp',       'int',   ['char*', 'char*']),
            'substr':   ('ely_str_substr',    'char*',   ['char*', 'size_t', 'size_t']),
            'trim':     ('ely_str_trim',      'char*',   ['char*']),
            'replace':  ('ely_str_replace',   'char*',   ['char*', 'char*', 'char*']),
            'intToStr': ('ely_int_to_str',    'char*',   ['int']),
            'uintToStr':('ely_uint_to_str',   'char*',   ['unsigned int']),
            'moreToStr':('ely_more_to_str',   'char*',   ['long long']),
            'umoreToStr':('ely_umore_to_str', 'char*',   ['unsigned long long']),
            'fltToStr': ('ely_flt_to_str',    'char*',   ['float']),
            'doubleToStr':('ely_double_to_str','char*',   ['double']),
            'boolToStr':('ely_bool_to_str',   'char*',   ['int']),
            'strToInt': ('ely_str_to_int',    'int',   ['char*']),
            'strToUint':('ely_str_to_uint',   'unsigned int', ['char*']),
            'strToMore':('ely_str_to_more',   'long long', ['char*']),
            'strToUm':  ('ely_str_to_umore',  'unsigned long long', ['char*']),
            'strToFlt': ('ely_str_to_flt',    'float', ['char*']),
            'strToDouble':('ely_str_to_double','double', ['char*']),
            'toInt':    ('ely_to_int',    'ely_value', ['ely_value']),
            'toFlt':    ('ely_to_double', 'ely_value', ['ely_value']),
            'toStr':    ('ely_to_string', 'ely_value', ['ely_value']),
            'makeArr':  ('ely_make_arr',  'ely_value', ['ely_value']),
            'dynArr':   ('ely_dyn_arr',   'ely_value', ['ely_value']),
            'abs':      ('ely_abs_int',       'int',   ['int']),
            'absMore':  ('ely_abs_more',      'long long',  ['long long']),
            'fabs':     ('ely_fabs',          'double',['double']),
            'min':      ('ely_min_int',       'int',   ['int', 'int']),
            'max':      ('ely_max_int',       'int',   ['int', 'int']),
            'pow':      ('ely_pow',           'double',['double', 'double']),
            'sqrt':     ('ely_sqrt',          'double',['double']),
            'sin':      ('ely_sin',           'double',['double']),
            'cos':      ('ely_cos',           'double',['double']),
            'tan':      ('ely_tan',           'double',['double']),
            'typeof':  ('ely_typeof',         'char*',   ['ely_value']),
            'fields':  ('ely_value_get_fields', 'ely_value', ['ely_value']),
            'methods': ('ely_value_get_methods','ely_value', ['ely_value']),
            'isType': ('isType', 'int', ['ely_value', 'char*']),
            'classInfoName': ('ely_get_class_info_name', 'char*', ['char*']),
        }
        self.set_builtins(builtins)

    def generate(self, program: Program) -> str:
        self.header_code = [
            'extern "C" {',
            '#include "ely_runtime.h"',
            '#include "ely_gc.h"',
            '}',
            '',
            '#include <stdio.h>',
            '#include <stdlib.h>',
            '#include <string.h>',
            '#include <setjmp.h>',
            '#include "ely_async.h"',
            '',
            '#ifdef _WIN32',
            '#include <windows.h>',
            '#else',
            '#include <unistd.h>',
            '#endif',
            '',
            'static jmp_buf __ex_buf;',
            'static ely_value volatile __ex_value = 0;',
            ''
        ]
        self.global_code = []
        self.main_code = []
        self.specializations = []
        self.type_aliases.clear()
        self.original_functions.clear()
        self.classes_ast.clear()
        self.namespaces.clear()
        self.imported_namespaces.clear()
        self.used_modules.clear()
        self.interfaces_ast.clear()
        pending_usings = []

        # ---- Первый проход: регистрация всех объявлений ----
        for stmt in program.statements:
            if isinstance(stmt, NamespaceDeclaration):
                old_ns = self.current_namespace
                self.current_namespace = stmt.name
                if stmt.name not in self.namespaces:
                    self.namespaces[stmt.name] = {}
                for inner in stmt.body:
                    if isinstance(inner, ClassDeclaration):
                        cls = inner
                        short_name = cls.name
                        full_name = self.method_full_name(cls.name)
                        cls.name = full_name
                        self.classes_ast[full_name] = cls
                        all_methods = []
                        if cls.extends and cls.extends in self.classes_ast:
                            parent = self.classes_ast[cls.extends]
                            all_methods.extend(parent.all_methods)
                        all_methods.extend(cls.methods)
                        for prop in cls.properties:
                            if prop.getter: all_methods.append(prop.getter)
                            if prop.setter: all_methods.append(prop.setter)
                        cls.all_methods = all_methods
                        cls.static_methods = [m for m in cls.methods if m.modifier == 'static']
                        cls.static_fields  = [f for f in cls.fields  if f.modifier == 'static']
                        for method in cls.methods:
                            self.original_functions[f"{full_name}_{method.name}"] = method
                        self.original_functions[f"{full_name}_constructor"] = MethodDeclaration(
                            line=cls.line, col=cls.col,
                            return_type=full_name,
                            name=f"{full_name}_constructor",
                            parameters=[Parameter(type=f.type, name=f.name) for f in cls.wait_fields],
                            body=[], modifier='public'
                        )
                        self.namespaces[stmt.name][short_name] = full_name
                    elif isinstance(inner, MethodDeclaration):
                        full_name = self.method_full_name(inner.name)
                        self.original_functions[full_name] = inner
                    elif isinstance(inner, InterfaceDeclaration):
                        self.interfaces_ast[inner.name] = inner
                    elif isinstance(inner, ImplDeclaration):
                        if inner.class_name in self.classes_ast:
                            cls = self.classes_ast[inner.class_name]
                            if inner.interface_name not in cls.impl_interfaces:
                                cls.impl_interfaces.append(inner.interface_name)
                            for method in inner.methods:
                                method.is_override = True
                                # Заменяем существующий метод с тем же именем (если есть)
                                existing_idx = next((i for i, m in enumerate(cls.methods) if m.name == method.name), None)
                                if existing_idx is not None:
                                    cls.methods[existing_idx] = method
                                else:
                                    cls.methods.append(method)
                                all_idx = next((i for i, m in enumerate(cls.all_methods) if m.name == method.name), None)
                                if all_idx is not None:
                                    cls.all_methods[all_idx] = method
                                else:
                                    cls.all_methods.append(method)
                                full_mname = f"{inner.class_name}_{method.name}"
                                self.original_functions[full_mname] = method
                self.current_namespace = old_ns
                continue

            if isinstance(stmt, ClassDeclaration):
                self.classes_ast[stmt.name] = stmt
                all_methods = []
                if stmt.extends and stmt.extends in self.classes_ast:
                    parent = self.classes_ast[stmt.extends]
                    all_methods.extend(parent.all_methods)
                all_methods.extend(stmt.methods)
                for prop in stmt.properties:
                    if prop.getter: all_methods.append(prop.getter)
                    if prop.setter: all_methods.append(prop.setter)
                stmt.all_methods = all_methods
                stmt.static_methods = [m for m in stmt.methods if m.modifier == 'static']
                stmt.static_fields  = [f for f in stmt.fields  if f.modifier == 'static']
                for method in stmt.methods:
                    self.original_functions[f"{stmt.name}_{method.name}"] = method
                self.original_functions[f"{stmt.name}_constructor"] = MethodDeclaration(
                    line=stmt.line, col=stmt.col,
                    return_type=stmt.name,
                    name=f"{stmt.name}_constructor",
                    parameters=[Parameter(type=f.type, name=f.name) for f in stmt.wait_fields],
                    body=[], modifier='public'
                )
            elif isinstance(stmt, InterfaceDeclaration):
                self.interfaces_ast[stmt.name] = stmt
            elif isinstance(stmt, ImplDeclaration):
                if stmt.class_name in self.classes_ast:
                    cls = self.classes_ast[stmt.class_name]
                    if stmt.interface_name not in cls.impl_interfaces:
                        cls.impl_interfaces.append(stmt.interface_name)
                    for method in stmt.methods:
                        method.is_override = True
                        # Заменяем существующий метод с тем же именем (если есть)
                        existing_idx = next((i for i, m in enumerate(cls.methods) if m.name == method.name), None)
                        if existing_idx is not None:
                            cls.methods[existing_idx] = method
                        else:
                            cls.methods.append(method)
                        all_idx = next((i for i, m in enumerate(cls.all_methods) if m.name == method.name), None)
                        if all_idx is not None:
                            cls.all_methods[all_idx] = method
                        else:
                            cls.all_methods.append(method)
                        full_name = f"{stmt.class_name}_{method.name}"
                        self.original_functions[full_name] = method
            elif isinstance(stmt, MethodDeclaration):
                self.original_functions[stmt.name] = stmt
                # Функции с пустым телом (из link.ely) — это extern-декларации
                if not stmt.body or len(stmt.body) == 0:
                    ext = ExternFunction(
                        line=stmt.line, col=stmt.col,
                        return_type=stmt.return_type or 'void',
                        name=stmt.name,
                        parameters=[Parameter(type=p.type, name=p.name) for p in stmt.parameters]
                    )
                    self.extern_functions[stmt.name] = ext
            elif isinstance(stmt, TypeAlias):
                self.type_aliases[stmt.name] = stmt.target_type
            elif isinstance(stmt, ExternFunction):
                self.extern_functions[stmt.name] = stmt
            elif isinstance(stmt, GlobalCBlock):
                # C++ code (with #include, templates, etc.) must not be wrapped in extern "C"
                is_cpp = any(line.strip().startswith('#') or '::' in line or '<' in line for line in stmt.code.split('\n'))
                if not is_cpp:
                    self.global_code.append('extern "C" {')
                self.global_code.append(stmt.code)
                if not is_cpp:
                    self.global_code.append('}')
                # Don't extract extern functions from C++ blocks (they have C++ linkage)
                if is_cpp:
                    continue
                import re
                # Pattern: C function declarations (not C++ code with ::, <, >, #)
                pattern = re.compile(r'\b((?:unsigned\s+)?(?:long\s+)?(?:long\s+)?[a-zA-Z_]\w*[\s\*]+)([a-zA-Z_]\w*)\s*\(([^)]*)\)\s*([{;])')
                for match in pattern.finditer(stmt.code):
                    full_match = match.group(0)
                    # Skip C++ specific lines: ::, <, >, #
                    if '::' in full_match or '<' in full_match or '>' in full_match or '#' in full_match:
                        continue
                    # Check context BEFORE match for C++ syntax (std::, <, etc.)
                    context_start = max(0, match.start() - 10)
                    context_before = stmt.code[context_start:match.start()]
                    if '::' in context_before or '<' in context_before:
                        continue
                    # Skip if match starts inside a C++ comment (// or /*)
                    line_start = stmt.code.rfind('\n', 0, match.start())
                    if line_start == -1:
                        line_start = 0
                    else:
                        line_start += 1
                    line_before = stmt.code[line_start:match.start()]
                    if '//' in line_before:
                        continue
                    ret_type = match.group(1).strip()
                    func_name = match.group(2)
                    params_str = match.group(3).strip()
                    parameters = []
                    if params_str:
                        for param in params_str.split(','):
                            param = param.strip()
                            if not param:
                                continue
                            parts = param.rsplit(None, 1)
                            if len(parts) == 2:
                                param_type, param_name = parts
                                parameters.append(Parameter(type=param_type, name=param_name))
                            else:
                                parameters.append(Parameter(type=param, name=''))
                    self.extern_functions[func_name] = ExternFunction(
                        line=stmt.line, col=stmt.col,
                        return_type=ret_type,
                        name=func_name,
                        parameters=parameters
                    )
            elif isinstance(stmt, UsingDirective):
                pending_usings.append(stmt)
            elif isinstance(stmt, VariableDeclaration):
                pass

        # Обработка using
        for using_stmt in pending_usings:
            self.used_modules.append(using_stmt.module)
            if using_stmt.module in self.namespaces:
                for short_name, full_name in self.namespaces[using_stmt.module].items():
                    self.imported_namespaces[short_name] = full_name

        # ---- Генерация кода ----
        old_code = self.code
        self.code = self.global_code
        try:
            self.global_code.append("void _global_init();")

            # --- Forward-декларации классов ---
            for cls_name in self.classes_ast:
                self.global_code.append(f"class {cls_name};")
            self.global_code.append('')

            # --- Прототипы extern-функций и глобальных функций (обёрнуты в extern "C" для ABI) ---
            self.global_code.append('extern "C" {')

            for ext in self.extern_functions.values():
                ret = ext.return_type or 'void'
                if ret == 'any' or ret == 'object':
                    ret_cpp = 'ely_value'
                elif ret == 'str':
                    ret_cpp = 'char*'
                elif ret in ('int','uint','more','umore','byte','ubyte','bool','flt','double'):
                    ret_cpp = self.type_to_cpp(ret)      # нативный
                elif ret in self.classes_ast:
                    ret_cpp = f'{ret}*'
                else:
                    ret_cpp = ret
                params = []
                for p in ext.parameters:
                    if p.type == 'str':
                        c_type = 'char*'
                    elif p.type == 'any' or p.type == 'object':
                        c_type = 'ely_value'
                    elif p.type in ('int','uint','more','umore','byte','ubyte','bool','flt','double'):
                        c_type = self.type_to_cpp(p.type, is_param=True)
                    elif p.type in self.classes_ast:
                        c_type = f'{p.type}*'
                    else:
                        c_type = p.type
                    params.append(f"{c_type} {p.name}")
                param_str = ', '.join(params)
                self.global_code.append(f"{ret_cpp} {ext.name}({param_str});")
            self.global_code.append('')

            # --- Прототипы обычных глобальных функций (нативные типы) ---
            for name, func_node in self.original_functions.items():
                if name in self.classes_ast:
                    continue
                if name.endswith('_constructor'):
                    continue
                if name in self.extern_functions:
                    continue
                if name == 'main':
                    continue

                ret = func_node.return_type or 'void'
                # Для глобальных функций возвращаем нативный тип
                if ret == 'void':
                    ret_cpp = 'void'
                elif ret == 'str':
                    ret_cpp = 'char*'
                elif ret == 'any' or ret == 'object':
                    ret_cpp = 'ely_value'
                elif ret in self.classes_ast:
                    ret_cpp = f'{ret}*'
                elif ret in ('int','uint','more','umore','byte','ubyte','bool','flt','double'):
                    ret_cpp = self.type_to_cpp(ret)   # нативный
                else:
                    ret_cpp = ret

                params = []
                for p in func_node.parameters:
                    if p.type == 'str':
                        c_type = 'char*'
                    elif p.type == 'any' or p.type == 'object':
                        c_type = 'ely_value'
                    elif p.type in ('int','uint','more','umore','byte','ubyte','bool','flt','double'):
                        c_type = self.type_to_cpp(p.type, is_param=True)
                    elif p.type in self.classes_ast:
                        c_type = f'{p.type}*'
                    else:
                        c_type = p.type
                    params.append(f"{c_type} {p.name}")
                param_str = ', '.join(params)
                self.global_code.append(f"{ret_cpp} {name}({param_str});")
            self.global_code.append('')
            self.global_code.append('}')  # конец extern "C"

            # Интерфейсы
            for iface in self.interfaces_ast.values():
                self.gen_interface_full(iface)
                self.global_code.append('')

            # Классы
            for cls in self.classes_ast.values():
                self.gen_class_full(cls)
                self.global_code.append('')

            # Статические поля
            self.gen_static_field_definitions()

            # Глобальные переменные
            for stmt in program.statements:
                if isinstance(stmt, VariableDeclaration):
                    self._gen_global_variable(stmt)

            # Глобальные функции (определения) — пропускаем extern
            for stmt in program.statements:
                if isinstance(stmt, MethodDeclaration) and stmt.name not in [c.name for c in self.classes_ast.values()]:
                    if stmt.name in self.extern_functions:
                        continue
                    self.current_class_name = None
                    self._gen_one_function(stmt)

            # Класс-инфо
            for cls in self.classes_ast.values():
                self.gen_class_info(cls)

            self.global_code.append("static ely_class_info* class_registry[] = {")
            for cls in self.classes_ast.values():
                self.global_code.append(f"    &{cls.name}_class_info,")
            self.global_code.append("    nullptr")
            self.global_code.append("};")
            self.global_code.append("""
    ely_class_info* ely_get_class_info(const char* name) {
        for (int i = 0; class_registry[i] != nullptr; ++i)
            if (strcmp(class_registry[i]->name, name) == 0)
                return class_registry[i];
        return nullptr;
    }
    """)
            self.global_code.append("void _global_init() {")
            self.global_code.append("    ely_chdir_to_exe_dir();")
            self.global_code.append("    // статические поля уже инициализированы")
            self.global_code.append("}")

        finally:
            self.code = old_code

        # Генерация main, если её нет в исходном коде
        if 'main' not in self.original_functions:
            self.main_code.append("int main() {")
            self.main_code.append("    gc_init();")
            self.main_code.append("    _global_init();")
            self.main_code.append("    gc_set_enabled(1);")
            self.main_code.append("    try {")
            self.main_code.append("        // пользовательский main будет вставлен сюда")
            self.main_code.append("    } catch (ely_value e) {")
            self.main_code.append("        ely_println_str(ely_value_to_cstr(e));")
            self.main_code.append("        return 1;")
            self.main_code.append("    }")
            self.main_code.append("    return 0;")
            self.main_code.append("}")

        return "\n".join(self.header_code + self.global_code + self.specializations + self.main_code)

    def _gen_one_function(self, method: MethodDeclaration):
        """Генерирует одну функцию и добавляет её в self.main_code."""
        old_main = self.main_code
        self.main_code = []          # временный буфер для тела функции
        # Перед генерацией очищаем method_code, чтобы gen_function записал туда код
        saved_method = self.method_code
        self.method_code = []
        self.gen_function(method)
        # Тело функции теперь находится в self.method_code
        self.main_code.extend(self.method_code)
        self.method_code = saved_method
        # Добавляем в общий main_code
        old_main.extend(self.main_code)
        self.main_code = old_main

    def _gen_global_variable(self, node: VariableDeclaration):
        resolved = self.resolve_type_alias(node.type)
        ctype = self.type_to_cpp(resolved)
        self.global_code.append(f"{ctype} {node.name};")
        self.global_types[node.name] = resolved
        if node.initializer:
            self.global_vars_to_init.append((node.name, resolved, node.initializer))