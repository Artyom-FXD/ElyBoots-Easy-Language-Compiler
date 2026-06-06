import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from parser import *
from typing import List, Optional, Dict


from collections import namedtuple
CallSignature = namedtuple('CallSignature', ['name', 'return_type', 'param_types', 'is_method'])
class CCodeGen:
    def __init__(self, debug=False, is_module=False):
        self.debug = debug
        self.is_module = is_module
        self.code = []
        self.specializations = []
        self.main_code = []
        self.indent = 0
        self.var_types = {}
        self.global_types = {}
        self.scopes = []
        self.scope_roots = []
        self.func_name = None
        self.inside_func = False
        self.used_modules = []
        self.global_vars_to_init = []
        self.temp_counter = 0
        self.type_aliases = {}
        self.generic_instances = {}
        self.original_functions = {}
        self.structs = set()
        self.struct_fields = {}
        self.in_asafe = False
        self.hoisted_functions = []
        self.extern_functions = {}
        self.builtin_signatures = {}
        self._init_builtins()
        self.current_class_name = None
        self.current_function = None
        self.classes_ast = {}
        self.classes = {}
        self.class_structs = {}
        self.class_vtables = {}
        self.current_class_name = None
        self.current_namespace = None
        self.interface_vtables = {}
        # Кэш строковых литералов для функции
        self._str_lit_cache: Dict[str, str] = {}
        self._str_lit_counter: int = 0
        self._str_lit_decls: List[str] = []

    def _init_builtins(self):
        builtins = {
            # Console
            'print':     ('ely_print',    'void', ['str']),
            'println':   ('ely_println', 'void', ['str']),
            'print_old': ('ely_print',   'void', ['str']),

            # Time module
            'timeNow':     ('ely_time_now',      'more', []),
            'timeNowMs':   ('ely_time_now_ms',   'more', []),
            'timeDiff':    ('ely_time_diff',     'double', ['more', 'more']),
            'formatTime':  ('ely_format_time',   'str',   ['any', 'str']),
            'parseTime':   ('ely_parse_time',    'more',  ['str', 'str']),
            'sleep':       ('ely_sleep',         'void',  ['more']),

            # Random module
            'randInt':       ('ely_rand_int',        'int',  []),
            'randIntRange':  ('ely_rand_int_range',  'int',  ['int', 'int']),
            'randBool':      ('ely_rand_bool',       'bool', []),
            'srand':         ('ely_srand',           'void', ['uint']),
            'rand':          ('ely_rand',            'int',  []),
            'randDouble':    ('ely_rand_double',     'double', []),

            # File module
            'fileWrite':    ('ely_file_write',    'int',  ['str', 'str']),
            'fileRead':     ('ely_file_read',     'str',  ['str']),
            'fileExists':   ('ely_file_exists',   'bool', ['str']),
            'fileReadAll':  ('ely_file_read_all', 'str',  ['str']),
            'fileClose':    ('ely_file_close',    'void', ['int']),
            'fileRemove':   ('ely_file_remove',   'int',  ['str']),
            'fileRename':   ('ely_file_rename',   'int',  ['str', 'str']),

            # Path module
            'pathJoin':        ('ely_path_join',        'str', ['str', 'str']),
            'pathBasename':    ('ely_path_basename',    'str', ['str']),
            'pathDirname':     ('ely_path_dirname',     'str', ['str']),
            'pathIsAbsolute':  ('ely_path_is_absolute', 'bool', ['str']),

            # DinLibs module
            'loadLibrary':      ('ely_load_library',      'any',  ['str']),
            'getFunction':      ('ely_get_function',      'any',  ['any', 'str']),
            'callIntInt':       ('ely_call_int_int',      'int',  ['any', 'int']),
            'callDoubleDouble': ('ely_call_double_double','double',['any', 'double']),
            'callDoubleDoubleDouble': ('ely_call_double_double_double', 'double', ['any', 'double', 'double']),
            'callStrVoid':      ('ely_call_str_void',     'str',  ['any', 'str']),
            'closeLibrary':     ('ely_close_library',     'void', ['any']),

            # JSON
            'jsonify':  ('ely_dict_to_json', 'str', ['dict']),
            'dictify':  ('ely_dictify',      'dict', ['str']),

            # Dicts
            'keys': ('ely_dict_keys', 'arr<str>', ['dict']),
            'has':  ('ely_dict_has',  'bool',     ['dict', 'any']),
            'del':  ('ely_dict_del',  'void',     ['dict', 'any']),

            # Strs
            'len':      ('ely_str_len',       'int',   ['str']),
            'concat':   ('ely_str_concat',    'str',   ['str', 'str']),
            'dup':      ('ely_str_dup',       'str',   ['str']),
            'cmp':      ('ely_str_cmp',       'int',   ['str', 'str']),
            'substr':   ('ely_str_substr',    'str',   ['str', 'int', 'int']),
            'trim':     ('ely_str_trim',      'str',   ['str']),
            'replace':  ('ely_str_replace',   'str',   ['str', 'str', 'str']),
            'intToStr': ('ely_int_to_str',    'str',   ['int']),
            'strToInt': ('ely_str_to_int',    'int',   ['str']),

            # Nums
            'abs':      ('ely_abs_int',       'int',   ['int']),
            'absMore':  ('ely_abs_more',      'more',  ['more']),
            'fabs':     ('ely_fabs',          'double',['double']),
            'min':      ('ely_min_int',       'int',   ['int', 'int']),
            'max':      ('ely_max_int',       'int',   ['int', 'int']),
            'pow':      ('ely_pow',           'double',['double', 'double']),
            'sqrt':     ('ely_sqrt',          'double',['double']),
            'sin':      ('ely_sin',           'double',['double']),
            'cos':      ('ely_cos',           'double',['double']),
            'tan':      ('ely_tan',           'double',['double']),

            # Reflection
            'typeof':  ('ely_typeof',         'str',   ['any']),
            'fields':  ('ely_value_get_fields', 'arr<str>', ['any']),
            'methods': ('ely_value_get_methods','arr<str>', ['any']),
            'isType': ('isType', 'bool', ['any', 'str']),
            'classInfoName': ('ely_get_class_info_name', 'str', ['str']),
        }
        for name, (c_name, ret, params) in builtins.items():
            self.builtin_signatures[name] = (c_name, ret, params)

    # SCOPES
    def _push_scope(self):
        self.scopes.append(self.var_types)
        self.var_types = {}
        self.scope_roots.append([])

    def _ensure_identifier(self, name: str, line: int, col: int):
        if name in self.var_types:
            return
        for scope in reversed(self.scopes):
            if name in scope:
                return
        if name in self.global_types:
            return

        self.emit_to_main(f"ely_value* {name} = ely_value_new_null();")
        self.emit_to_main(f"gc_add_root((void**)&{name});")
        self.var_types[name] = 'any'
        if self.scope_roots:
            self.scope_roots[-1].append(name)

    def _pop_scope(self):
        if self.scopes:
            self.var_types = self.scopes.pop()
        if self.scope_roots:
            roots = self.scope_roots.pop()
            for name in reversed(roots):
                if name not in ('None', 'NULL'):
                    self.emit_to_main(f"gc_remove_root((void**)&{name});")

    # TYPES
    def _get_expression_type(self, expr: Expression) -> str:
        # Если тип уже закэширован в семантическом анализаторе — используем его
        if expr.cached_type is not None:
            return expr.cached_type
        if isinstance(expr, Literal):
            val = expr.value
            if isinstance(val, bool):
                return 'bool'
            if isinstance(val, int):
                return 'int'
            if isinstance(val, float):
                return 'flt'
            if isinstance(val, str):
                return 'str'
            return 'any'
        elif isinstance(expr, Identifier):
            if expr.name in self.var_types:
                return self._resolve_type_alias(self.var_types[expr.name])
            if expr.name in self.global_types:
                return self._resolve_type_alias(self.global_types[expr.name])
            for scope in reversed(self.scopes):
                if expr.name in scope:
                    return self._resolve_type_alias(scope[expr.name])
            return 'any'
        elif isinstance(expr, BinaryOp):
            return self._get_expression_type(expr.left)
        elif isinstance(expr, UnaryOp):
            return self._get_expression_type(expr.operand)
        elif isinstance(expr, ArrayLiteral):
            return 'arr<any>'
        elif isinstance(expr, DictLiteral):
            return 'dict<any, any>'
        elif isinstance(expr, IndexExpression):
            return 'any'
        elif isinstance(expr, MemberAccess):
            return 'any'
        elif isinstance(expr, TypeOfExpression):
            arg_code = self.gen_expression(expr.argument)
            return f"ely_value_new_string(ely_typeof({arg_code}))"
        elif isinstance(expr, FieldsExpression):
            arg_code = self.gen_expression(expr.argument)
            return f"ely_value_get_fields({arg_code})"
        elif isinstance(expr, MethodsExpression):
            arg_code = self.gen_expression(expr.argument)
            return f"ely_value_get_methods({arg_code})"
        elif isinstance(expr, Call):
            if isinstance(expr.callee, Identifier):
                if expr.callee.name.endswith('_constructor'):
                    class_name = expr.callee.name[:-len('_constructor')]
                    if class_name in self.classes_ast:
                        return class_name
                if expr.callee.name in self.original_functions:
                    ret = self.original_functions[expr.callee.name].return_type
                    if ret:
                        return self._resolve_type_alias(ret)
            elif isinstance(expr, MemberAccess):
                obj_type = self._get_expression_type(expr.object)
                if obj_type in self.classes_ast:
                    cls = self.classes_ast[obj_type]
                    # ищем поле в иерархии
                    def find_field(c):
                        for f in c.fields:
                            if f.name == expr.member:
                                return f.type
                        if c.extends and c.extends in self.classes_ast:
                            return find_field(self.classes_ast[c.extends])
                        return None
                    field_type = find_field(cls)
                    if field_type:
                        return self._resolve_type_alias(field_type)
                return 'any'
            elif isinstance(expr.callee, Identifier):
                func_name = expr.callee.name
                if func_name in self.original_functions:
                    ret = self.original_functions[func_name].return_type
                    if ret:
                        return self._resolve_type_alias(ret)
                if func_name == 'time_now':
                    return 'more'
                if func_name == 'time_diff':
                    return 'double'
                if func_name in ('print', 'println', 'sleep'):
                    return 'void'
            return 'any'
        return 'any'

    def _type_to_c(self, ely_type: str, for_signature=False, is_param=False,
                is_self=False, is_field=False) -> str:
        ely_type = self._resolve_type_alias(ely_type)
        # если это имя класса и используется как параметр/поле/self
        if ely_type in self.classes_ast:
            if is_param or is_self or is_field:
                return f"struct {ely_type}*"
            return 'ely_value*'
        mapping = {
            'void': 'void', 'bool': 'int', 'byte': 'signed char', 'ubyte': 'unsigned char',
            'int': 'int', 'uint': 'unsigned int', 'more': 'long long', 'umore': 'unsigned long long',
            'flt': 'float', 'double': 'double', 'str': 'char*', 'any': 'ely_value*', 'char': 'char',
        }
        if ely_type in self.classes_ast:
            if is_self or is_field:
                return f"struct {ely_type}*"
            return 'ely_value*'
        if ely_type.startswith('arr<') or ely_type.startswith('dict<'):
            return 'ely_value*'
        if ely_type in mapping:
            if for_signature and not is_param and ely_type != 'void':
                return 'ely_value*'
            return mapping[ely_type]
        if ely_type in self.structs:
            return f"struct {ely_type}"
        if ely_type.endswith('*'):
            inner = ely_type[:-1].strip()
            return f"{self._type_to_c(inner, for_signature, is_param, is_self, is_field)}*"
        return 'ely_value*'

    def _type_to_tag(self, ely_type: str) -> int:
        tags = {
            'int': 1, 'uint': 2, 'more': 3, 'umore': 4,
            'flt': 5, 'double': 6, 'bool': 7, 'str': 8,
            'byte': 9, 'ubyte': 10
        }
        return tags.get(ely_type, 1)

    # ------------------- Генерация кода -------------------
    def emit(self, line: str):
        self.code.append("    " * self.indent + line)

    def emit_to_main(self, line: str):
        self.main_code.append("    " * self.indent + line)

    def generate(self, program: Program) -> str:
        self.code = []
        self.specializations = []
        self.main_code = []
        self.used_modules = []
        self.global_vars_to_init = []
        self.type_aliases = {}
        self.generic_instances = {}
        self.original_functions = {}
        self.structs = set()
        self.struct_fields = {}
        self.classes_ast.clear()
        self.current_class_name = None

        self.code.append('#include "ely_runtime.h"\n')
        self.code.append('#include "ely_gc.h"\n')
        self.code.append('#include <stdio.h>\n')
        self.code.append('#include <stdlib.h>\n')
        self.code.append('#include <setjmp.h>\n')
        self.code.append('#include <stdint.h>\n')
        self.code.append('#include <string.h>\n')
        for mod in self.used_modules:
            self.code.append(f'#include "{mod}.h"\n')
        self.code.append('\n')
        self.code.append('static jmp_buf __ex_buf;\n')
        self.code.append('static ely_value* __ex_value = NULL;\n')
        self.code.append('')

        # Первичный проход: регистрируем все сущности
        for stmt in program.statements:
            if isinstance(stmt, GlobalCBlock):
                self.code.append(stmt.code)
            elif isinstance(stmt, TypeAlias):
                self.type_aliases[stmt.name] = stmt.target_type
            elif isinstance(stmt, StructDeclaration):
                self.structs.add(stmt.name)
                fields = {}
                for field in stmt.fields:
                    fields[field.name] = field.type
                self.struct_fields[stmt.name] = fields
            elif isinstance(stmt, ExternFunction):
                self.extern_functions[stmt.name] = stmt
            elif isinstance(stmt, ClassDeclaration):
                self.classes_ast[stmt.name] = stmt
                # собираем all_methods (с учётом свойств)
                all_methods = []
                if stmt.extends:
                    parent = self.classes_ast.get(stmt.extends)
                    if parent:
                        all_methods.extend(parent.all_methods)
                all_methods.extend(stmt.methods)
                for prop in stmt.properties:
                    if prop.getter:
                        all_methods.append(prop.getter)
                    if prop.setter:
                        all_methods.append(prop.setter)
                stmt.all_methods = all_methods
                # регистрируем методы в original_functions для кодогенерации
                for method in stmt.methods:
                    full_name = f"{stmt.name}_{method.name}"
                    self.original_functions[full_name] = method
                # конструктор регистрируем (пока формально)
                self.original_functions[f"{stmt.name}_constructor"] = MethodDeclaration(
                    line=stmt.line, col=stmt.col,
                    return_type=stmt.name,
                    name=f"{stmt.name}_constructor",
                    parameters=[Parameter(type=f.type, name=f.name) for f in stmt.wait_fields],
                    body=[],
                    modifier='public'
                )
            elif isinstance(stmt, MethodDeclaration):
                # глобальные функции
                self.original_functions[stmt.name] = stmt

        # 1. Структуры классов
        for cls in self.classes_ast.values():
            self._gen_class_struct(cls)
        self.code.append('')

        # 2. Объявления vtable
        for cls in self.classes_ast.values():
            self._gen_vtable_decl(cls)
        self.code.append('')

        # 3. Глобальные переменные и статические поля классов
        for stmt in program.statements:
            if isinstance(stmt, VariableDeclaration):
                self._gen_global_variable(stmt)
        for cls in self.classes_ast.values():
            for f in cls.static_fields:
                self.emit(f"static ely_value* {self._ns_prefix()}{cls.name}_{f.name};")

        # 4. Forward-объявления методов (экземпляра)
        global_methods = []
        class_methods = {}
        for stmt in program.statements:
            if isinstance(stmt, MethodDeclaration):
                global_methods.append(stmt)
        for cls_name, cls in self.classes_ast.items():
            class_methods[cls_name] = [m for m in cls.methods if not m.name.endswith('_constructor')]

        for method in global_methods:
            self.current_class_name = None
            self._forward_declare(method)
        for cls_name, methods in class_methods.items():
            self.current_class_name = cls_name
            for method in methods:
                self._forward_declare(method)

        # 5. Forward-объявления статических методов
        for cls in self.classes_ast.values():
            for sm in cls.static_methods:
                self._forward_declare_static(cls, sm)

        # 6. Forward-объявления конструкторов
        for cls in self.classes_ast.values():
            params = self._collect_constructor_params(cls)
            param_str = ', '.join([f"struct {cls.name}* self"] +
                                [f"{self._type_to_c(p.type, is_param=True)} {p.name}" for p in params])
            self.code.append(f"void {cls.name}_constructor({param_str});")

        # 7. Vtable-экземпляры и недостающие заглушки наследования
        for cls in self.classes_ast.values():
            self._gen_vtable_impl(cls)

        # 8. Конструкторы
        for cls in self.classes_ast.values():
            self._gen_class_constructor(cls)

        # 9. Глобальные функции
        for method in global_methods:
            self.current_class_name = None
            self._gen_function(method)

        # 10. Методы экземпляров
        for cls_name, methods in class_methods.items():
            self.current_class_name = cls_name
            for method in methods:
                self._gen_function(method)

        # 11. Статические методы
        for cls in self.classes_ast.values():
            for sm in cls.static_methods:
                self._gen_static_method(cls, sm)

        # 12. Класс-инфо для рефлексии
        for cls in self.classes_ast.values():
            self._gen_class_info(cls)

        # 13. Интерфейсные vtable (если есть)
        for stmt in program.statements:
            if isinstance(stmt, InterfaceDeclaration):
                self._gen_interface_vtable(stmt)

        # 14. Глобальная инициализация
        self._emit_global_init()

        # 15. Реестр классов
        self.code.append("static ely_class_info* class_registry[] = {")
        for cls in self.classes_ast.values():
            self.code.append(f"    &{self._ns_prefix()}{cls.name}_class_info,")
        self.code.append("    NULL")
        self.code.append("};")
        self.code.append("""
    ely_class_info* ely_get_class_info(const char* name) {
        for (int i = 0; class_registry[i] != NULL; i++) {
            if (strcmp(class_registry[i]->name, name) == 0)
                return class_registry[i];
        }
        return NULL;
    }
    """)

        final_code = self.code + self.specializations + self.main_code
        return "\n".join(final_code)

    def _method_full_name(self, method_name: str) -> str:
        ns = self._ns_prefix()
        if self.current_class_name:
            return f"{ns}{self.current_class_name}_{method_name}"
        return f"{ns}{method_name}"

    def _resolve_type_alias(self, type_name: str) -> str:
        while type_name in self.type_aliases:
            type_name = self.type_aliases[type_name]
        return type_name

    def _declare_function(self, node: MethodDeclaration):
        pass

    def _gen_global_variable(self, node: VariableDeclaration):
        resolved_type = self._resolve_type_alias(node.type)
        ctype = self._type_to_c(resolved_type)
        self.emit(f"{ctype} {node.name};")
        self.global_types[node.name] = node.type
        if node.initializer:
            self.global_vars_to_init.append((node.name, node.type, node.initializer))
        self.global_types[node.name] = resolved_type

    def _create_global_init(self):
        self.emit("void _global_init(void) {")
        self.indent += 1
        for name, typ, init_node in self.global_vars_to_init:
            if isinstance(init_node, ArrayLiteral):
                self._gen_global_array_init(name, typ, init_node)
            elif isinstance(init_node, DictLiteral):
                self._gen_global_dict_init(name, typ, init_node)
            else:
                init_code = self.gen_expression(init_node)
                self.emit(f"{name} = {init_code};")
        for cls in self.classes_ast.values():
            for f in cls.static_fields:
                init_val = "ely_value_new_int(0)"
                if f.initializer:
                    init_val = self.gen_expression(f.initializer)
                self.emit(f"{self._ns_prefix()}{cls.name}_{f.name} = {init_val};")
        self.indent -= 1
        self.emit("}")

    def _gen_global_array_init(self, name: str, typ: str, node: ArrayLiteral):
        self.emit(f"arr* __tmp_arr = arr_new();")
        self.emit(f"{name} = ely_value_new_array(__tmp_arr);")
        for elem in node.elements:
            elem_code = self.gen_expression(elem)
            tmp_var = f"__tmp_global_{self.temp_counter}"
            self.temp_counter += 1
            self.emit(f"ely_value* {tmp_var} = {elem_code};")
            self.emit(f"arr_push({name}->u.array_val, {tmp_var});")

    def _gen_global_dict_init(self, name: str, typ: str, node: DictLiteral):
        self.emit(f"dict* __tmp_dict = dict_new_str();")
        self.emit(f"{name} = ely_value_new_object(__tmp_dict);")
        for pair in node.pairs:
            key_code = self.gen_expression(pair.key)
            val_code = self.gen_expression(pair.value)
            key_tmp = f"__tmp_key_{self.temp_counter}"
            self.temp_counter += 1
            val_tmp = f"__tmp_val_{self.temp_counter}"
            self.temp_counter += 1
            self.emit(f"ely_value* {key_tmp} = {key_code};")
            self.emit(f"ely_value* {val_tmp} = {val_code};")
            self.emit(f"dict_set({name}->u.object_val, {key_tmp}, {val_tmp});")

    def _gen_struct(self, node: StructDeclaration):
        self.emit(f"struct {node.name} {{")
        self.indent += 1
        for field in node.fields:
            ctype = self._type_to_c(field.type)
            self.emit(f"{ctype} {field.name};")
        self.indent -= 1
        self.emit("};")

    # STATEMENTS GENERATION
    def gen_statement(self, stmt: Statement):
        if isinstance(stmt, GlobalCBlock):
            return
        if isinstance(stmt, ExpressionStatement):
            expr = self.gen_expression(stmt.expression)
            if expr:
                self.emit_to_main(f"{expr};")
        elif isinstance(stmt, VariableDeclaration):
            self._gen_local_variable(stmt)
        elif isinstance(stmt, MethodDeclaration):
            self._gen_function(stmt)
        elif isinstance(stmt, IfStatement):
            self._gen_if(stmt)
        elif isinstance(stmt, WhileLoop):
            self._gen_while(stmt)
        elif isinstance(stmt, ForLoop):
            self._gen_for(stmt)
        elif isinstance(stmt, ForEachLoop):
            self._gen_foreach(stmt)
        elif isinstance(stmt, ThrowStatement):
            self._gen_throw(stmt)
        elif isinstance(stmt, MatchStatement):
            self._gen_match(stmt)
        elif isinstance(stmt, AsafeBlock):
            self._gen_asafe(stmt)
        elif isinstance(stmt, GivebackStatement):
            self._gen_giveback(stmt)
        elif isinstance(stmt, ReturnStatement):
            self._gen_return(stmt)
        elif isinstance(stmt, CollapseStatement):
            self._gen_collapse(stmt)
        elif isinstance(stmt, BreakStatement):
            self._gen_break(stmt)
        elif isinstance(stmt, Assignment):
            expr = self.gen_expression(stmt)
            if expr:
                self.emit_to_main(f"{expr};")

    def _is_primitive_type(self, ely_type: str) -> bool:
        return ely_type == 'void'

    def _gen_local_variable(self, node: VariableDeclaration):
        resolved_type = self._resolve_type_alias(node.type)
        if resolved_type == 'void':
            self.error("Cannot declare variable of type void", node)
            return

        # Определяем C-тип и флаг, является ли тип классом (структурой)
        is_class = resolved_type in self.classes_ast
        ctype = f"struct {resolved_type}*" if is_class else self._type_to_c(resolved_type)

        # Инициализатор
        init_code = None
        if node.initializer:
            init_code = self.gen_expression(node.initializer)
            # Если класс, конструктор уже вернул указатель – используем как есть
            # иначе приводим к нужному типу
            if not is_class:
                source_type = self._get_expression_type(node.initializer)
                if source_type != resolved_type:
                    init_code = self._convert_value(init_code, source_type, resolved_type)

        # Объявление и инициализация
        if init_code:
            self.emit_to_main(f"{ctype} {node.name} = {init_code};")
        else:
            # Значение по умолчанию
            if is_class:
                self.emit_to_main(f"{ctype} {node.name} = NULL;")
            else:
                if resolved_type == 'int':
                    self.emit_to_main(f"{ctype} {node.name} = ely_value_new_int(0);")
                elif resolved_type in ('flt', 'double'):
                    self.emit_to_main(f"{ctype} {node.name} = ely_value_new_double(0.0);")
                elif resolved_type == 'bool':
                    self.emit_to_main(f"{ctype} {node.name} = ely_value_new_bool(0);")
                elif resolved_type == 'str':
                    self.emit_to_main(f"{ctype} {node.name} = ely_value_new_string(NULL);")
                else:
                    self.emit_to_main(f"{ctype} {node.name} = ely_value_new_null();")

        # Регистрируем переменную как корень, если она управляется сборщиком
        # (для ely_value* или struct*)
        if is_class or ctype == 'ely_value*' or ctype.startswith('ely_value*'):
            self.emit_to_main(f"gc_add_root((void**)&{node.name});")

        # Запоминаем тип переменной
        self.var_types[node.name] = resolved_type

        # Добавляем в список корней текущей области видимости для автоматического удаления
        if self.scope_roots and node.name not in ('None', 'NULL'):
            self.scope_roots[-1].append(node.name)

    def _gen_primitive_expression(self, expr: Expression) -> str:
        if isinstance(expr, Literal):
            val = expr.value
            if isinstance(val, bool):
                return '1' if val else '0'
            elif isinstance(val, int):
                return str(val)
            elif isinstance(val, float):
                return str(val)
            elif isinstance(val, str):
                return '""'
            else:
                return '0'
        elif isinstance(expr, Identifier):
            return expr.name
        elif isinstance(expr, BinaryOp):
            left = self._gen_primitive_expression(expr.left)
            right = self._gen_primitive_expression(expr.right)
            op = expr.operator
            if op in ('+', '-', '*', '/', '%', '<', '>', '<=', '>=', '==', '!=', '&&', '||'):
                return f"({left} {op} {right})"
            else:
                self.error(f"Unsupported primitive binary operator: {op}", expr)
                return "0"
        elif isinstance(expr, UnaryOp):
            operand = self._gen_primitive_expression(expr.operand)
            if expr.operator == '-':
                return f"(-{operand})"
            elif expr.operator == '!':
                return f"(!{operand})"
            else:
                return operand
        elif isinstance(expr, Call):
            self.error("Call in primitive expression not yet supported", expr)
            return "0"
        else:
            self.error(f"Cannot generate primitive expression for {type(expr).__name__}", expr)
            return "0"

    def _is_field_in_class_hierarchy(self, cls: ClassDeclaration, field_name: str) -> bool:
        if field_name in [f.name for f in cls.fields]:
            return True
        if cls.extends and cls.extends in self.classes_ast:
            parent = self.classes_ast[cls.extends]
            return self._is_field_in_class_hierarchy(parent, field_name)
        return False

    def _wrap_primitive_to_value(self, expr_code: str, ely_type: str) -> str:
        resolved = self._resolve_type_alias(ely_type)
        if resolved == 'int':
            return f"ely_value_new_int({expr_code})"
        elif resolved == 'bool':
            return f"ely_value_new_bool({expr_code})"
        elif resolved == 'flt' or resolved == 'double':
            return f"ely_value_new_double({expr_code})"
        elif resolved == 'str':
            return f"ely_value_new_string({expr_code})"
        else:
            return expr_code

    def _convert_to_ctype(self, expr_node: Expression, expr_code: str, target_type: str) -> str:
        if target_type == 'any' or target_type == 'ely_value*':
            source_type = self._get_expression_type(expr_node)
            if source_type in ('int', 'uint', 'more', 'umore', 'byte', 'ubyte'):
                return f"ely_value_new_int({expr_code})"
            if source_type in ('double', 'flt'):
                return f"ely_value_new_double({expr_code})"
            if source_type == 'bool':
                return f"ely_value_new_bool({expr_code})"
            if source_type == 'str':
                return f"ely_value_new_string({expr_code})"
            return expr_code
        if target_type in ('int', 'uint', 'more', 'umore', 'byte', 'ubyte'):
            return f"ely_value_as_int({expr_code})"
        if target_type in ('double', 'flt'):
            return f"ely_value_as_double({expr_code})"
        if target_type == 'bool':
            return f"ely_value_as_bool({expr_code})"
        if target_type == 'str':
            return f"ely_value_to_string({expr_code})"
        if target_type == 'char':
            return f"ely_value_as_char({expr_code})"
        return expr_code

    def _wrap_result(self, call_expr: str, return_type: str) -> str:
        if return_type == 'void':
            # Используем GCC statement expression: ({ stmt; expr; })
            return f"({{ {call_expr}; ely_value_new_null(); }})"
        if return_type in ('int', 'uint', 'more', 'umore', 'byte', 'ubyte'):
            return f"ely_value_new_int({call_expr})"
        if return_type in ('double', 'flt'):
            return f"ely_value_new_double({call_expr})"
        if return_type == 'bool':
            return f"ely_value_new_bool({call_expr})"
        if return_type == 'str':
            return f"ely_value_new_string({call_expr})"
        if return_type == 'char':
            return f"ely_value_new_char({call_expr})"
        return call_expr

    def _get_call_signature_for_func(self, node: Call, func_name: str):
        if func_name in self.extern_functions:
            ext = self.extern_functions[func_name]
            param_types = [p.type for p in ext.parameters]
            return_type = ext.return_type or 'void'
            return (func_name, return_type, param_types)
        if func_name in self.original_functions:
            func = self.original_functions[func_name]
            param_types = [p.type for p in func.parameters]
            return_type = func.return_type or 'void'
            return (func_name, return_type, param_types)
        if func_name in self.builtin_signatures:
            c_name, ret, params = self.builtin_signatures[func_name]
            return (c_name, ret, params)
        self.error(f"Unknown function '{func_name}'", node)
        return None

    def _convert_value(self, value_code: str, from_type: str, to_type: str) -> str:
        # Все значения уже ely_value* (кроме классовых приведений)
        if from_type in self.classes_ast and to_type in self.classes_ast:
            if not self._is_subclass(from_type, to_type):
                pass   # можно позже добавить приведение
        return value_code

    def is_numeric(self, ely_type: str) -> bool:
        return ely_type in ('int', 'uint', 'more', 'umore', 'flt', 'double', 'byte', 'ubyte')

    def _gen_if(self, node: IfStatement):
        cond = self.gen_expression(node.condition)
        self.emit_to_main(f"if (ely_value_as_bool({cond})) {{")
        self.indent += 1
        self._push_scope()
        for stmt in node.then_body:
            self.gen_statement(stmt)
        self._pop_scope()
        self.indent -= 1
        if node.else_body:
            self.emit_to_main("} else {")
            self.indent += 1
            self._push_scope()
            for stmt in node.else_body:
                self.gen_statement(stmt)
            self._pop_scope()
            self.indent -= 1
            self.emit_to_main("}")
        else:
            self.emit_to_main("}")

    def _gen_while(self, node: WhileLoop):
        cond = self.gen_expression(node.condition)
        self.emit_to_main(f"while (ely_value_as_bool({cond})) {{")
        self.indent += 1
        self._push_scope()
        for stmt in node.body:
            self.gen_statement(stmt)
        self._pop_scope()
        self.indent -= 1
        self.emit_to_main("}")

    def _gen_for(self, node: ForLoop):
        self._push_scope()
        
        init_part = ";"
        if node.init:
            if isinstance(node.init, VariableDeclaration):
                self._gen_local_variable(node.init)
                init_part = ";"
            elif isinstance(node.init, ExpressionStatement):
                expr_code = self.gen_expression(node.init.expression)
                init_part = expr_code + ";" if expr_code else ";"
            else:
                init_part = ";"

        cond_part = "1"
        if node.condition:
            cond_expr = self.gen_expression(node.condition)
            cond_part = f"ely_value_as_bool({cond_expr})"

        update_part = ""
        if node.update:
            update_expr = self.gen_expression(node.update)
            update_part = update_expr

        self.emit_to_main(f"for ({init_part} {cond_part}; {update_part}) {{")
        self.indent += 1

        for stmt in node.body:
            self.gen_statement(stmt)

        self.indent -= 1
        self.emit_to_main("}")
        self._pop_scope()

    def _gen_foreach(self, node: ForEachLoop):
        iterable_type = self._get_expression_type(node.iterable)
        iterable_code = self.gen_expression(node.iterable)
        
        # Генерируем уникальные имена для переменных цикла
        loop_counter = f"__i_{self.temp_counter}"
        self.temp_counter += 1

        if iterable_type.startswith('arr<'):
            self.emit_to_main(f"for (size_t {loop_counter} = 0; {loop_counter} < ely_array_len({iterable_code}); {loop_counter}++) {{")
            self.indent += 1
            elem_code = f"ely_array_get({iterable_code}, {loop_counter})"
            if isinstance(node.item_decl, VariableDeclaration):
                decl_type = node.item_decl.type or 'any'
                c_decl_type = self._type_to_c(decl_type)
                self.emit_to_main(f"{c_decl_type} {node.item_decl.name} = {elem_code};")
                self.var_types[node.item_decl.name] = decl_type
                if c_decl_type == 'ely_value*' or c_decl_type.startswith('ely_value*'):
                    self.emit_to_main(f"gc_add_root((void**)&{node.item_decl.name});")
                    if self.scope_roots and node.item_decl.name and node.item_decl.name not in ['None', 'NULL']:
                        self.scope_roots[-1].append(node.item_decl.name)
                self.var_types[node.item_decl.name] = decl_type
            else:
                self.emit_to_main(f"ely_value* {node.item_decl.name} = {elem_code};")
                self.var_types[node.item_decl.name] = 'any'
            for stmt in node.body:
                self.gen_statement(stmt)
            self.indent -= 1
            self.emit_to_main("}")

        elif iterable_type.startswith('dict<'):
            keys_var = f"__keys_{self.temp_counter}"
            self.temp_counter += 1
            self.emit_to_main(f"ely_value* {keys_var} = ely_dict_keys({iterable_code});")
            self.emit_to_main(f"for (size_t {loop_counter} = 0; {loop_counter} < ely_array_len({keys_var}); {loop_counter}++) {{")
            self.indent += 1
            self.emit_to_main(f"ely_value* __key = ely_array_get({keys_var}, {loop_counter});")
            self.emit_to_main(f"ely_value* __value = ely_dict_get({iterable_code}, __key);")
            if isinstance(node.item_decl, VariableDeclaration):
                decl_type = node.item_decl.type or 'any'
                c_decl_type = self._type_to_c(decl_type)
                self.emit_to_main(f"{c_decl_type} {node.item_decl.name} = __value;")
                self.var_types[node.item_decl.name] = decl_type
            else:
                self.emit_to_main(f"ely_value* {node.item_decl.name} = __value;")
                self.var_types[node.item_decl.name] = 'any'
            for stmt in node.body:
                self.gen_statement(stmt)
            self.indent -= 1
            self.emit_to_main("}")
            self.emit_to_main(f"ely_value_free({keys_var});")
        else:
            self.error(f"foreach not supported for type {iterable_type}", node.iterable)

    def _gen_match(self, node: MatchStatement):
        expr = self.gen_expression(node.expression)
        self.emit_to_main(f"switch ({expr}) {{")
        self.indent += 1
        for case in node.cases:
            case_val = self.gen_expression(case.value)
            self.emit_to_main(f"case {case_val}: {{")
            self.indent += 1
            for stmt in case.body:
                self.gen_statement(stmt)
            self.emit_to_main("break;")
            self.indent -= 1
            self.emit_to_main("}")
        if node.default_body:
            self.emit_to_main("default: {")
            self.indent += 1
            for stmt in node.default_body:
                self.gen_statement(stmt)
            self.indent -= 1
            self.emit_to_main("}")
        self.indent -= 1
        self.emit_to_main("}")

    def _gen_asafe(self, node: AsafeBlock):
        param = node.except_handler.parameter if node.except_handler else None
        if not param or param == 'None':
            param = '__ex'
        
        self.emit_to_main(f"ely_value* {param} = NULL;")
        self.var_types[param] = 'any'
        self.emit_to_main(f"gc_add_root((void**)&{param});")
        if self.scope_roots:
            self.scope_roots[-1].append(param)
        
        self.emit_to_main("int __ex_result = setjmp(__ex_buf);")
        self.emit_to_main("if (__ex_result == 0) {")
        self.indent += 1
        self._push_scope()
        for stmt in node.body:
            self.gen_statement(stmt)
        self._pop_scope()
        self.indent -= 1
        self.emit_to_main("} else {")
        self.indent += 1
        if node.except_handler:
            self.emit_to_main(f"{param} = __ex_value;")
            for stmt in node.except_handler.body:
                self.gen_statement(stmt)
            self.emit_to_main("__ex_value = NULL;")
        self.indent -= 1
        self.emit_to_main("}")

    def _gen_throw(self, node: ThrowStatement):
        val_code = self.gen_expression(node.value)
        self.emit_to_main(f"__ex_value = {val_code};")
        self.emit_to_main("longjmp(__ex_buf, 1);")

    def _gen_giveback(self, node: GivebackStatement):
        if node.value:
            val = self.gen_expression(node.value)
            self.emit_to_main(f"return {val};")
        else:
            self.emit_to_main("return;")

    def _gen_return(self, node: ReturnStatement):
        if not self.current_function and not self.current_method:
            self.error("return outside function/method", node)
            return
        if node.value:
            val = self.gen_expression(node.value)
            expected_type = self.func_return_type if self.current_function else 'void'
            if expected_type and expected_type != 'void':
                source_type = self._get_expression_type(node.value)
                val = self._convert_value(val, source_type, expected_type)
            if self.current_function == 'main':
                self.emit_to_main(f"return ely_value_as_int({val});")
            else:
                self.emit_to_main(f"return {val};")
        else:
            if self.current_function == 'main':
                self.emit_to_main("return 0;")
            else:
                self.emit_to_main("return;")

    def _gen_collapse(self, node: CollapseStatement):
        if node.name in self.var_types:
            del self.var_types[node.name]
        for scope in self.scopes:
            if node.name in scope:
                del scope[node.name]

    def _gen_break(self, node: BreakStatement):
        self.emit_to_main("break;")

    def gen_expression(self, expr: Expression) -> Optional[str]:
        if isinstance(expr, Literal):
            return self._gen_literal(expr)
        elif isinstance(expr, SuperCall):
            return self._gen_super_call(expr)
        elif isinstance(expr, Identifier):
            return self._gen_identifier(expr)
        elif isinstance(expr, BinaryOp):
            return self._gen_binary_op(expr)
        elif isinstance(expr, UnaryOp):
            return self._gen_unary_op(expr)
        elif isinstance(expr, Assignment):
            return self._gen_assignment(expr)
        elif isinstance(expr, Call):
            return self._gen_call(expr)
        elif isinstance(expr, MemberAccess):
            return self._gen_member_access(expr)
        elif isinstance(expr, Conditional):
            return self._gen_conditional(expr)
        elif isinstance(expr, FString):
            return self._gen_fstring(expr)
        elif isinstance(expr, ArrayLiteral):
            return self._gen_array_literal(expr)
        elif isinstance(expr, DictLiteral):
            return self._gen_dict_literal(expr)
        elif isinstance(expr, IndexExpression):
            return self._gen_index_expression(expr)
        elif isinstance(expr, TypeOfExpression):
            arg_code = self.gen_expression(expr.argument)
            return f"ely_value_new_string(ely_typeof({arg_code}))"
        elif isinstance(expr, FieldsExpression):
            arg_code = self.gen_expression(expr.argument)
            return f"ely_value_get_fields({arg_code})"
        elif isinstance(expr, MethodsExpression):
            arg_code = self.gen_expression(expr.argument)
            return f"ely_value_get_methods({arg_code})"
        else:
            self.error(f"Unknown expression type: {type(expr).__name__}", expr)
            return None

    def _gen_literal(self, node: Literal) -> str:
        if isinstance(node.value, bool):
            return f"ely_value_new_bool({1 if node.value else 0})"
        elif isinstance(node.value, int):
            return f"ely_value_new_int({node.value})"
        elif isinstance(node.value, float):
            return f"ely_value_new_double({node.value})"
        elif isinstance(node.value, str):
            escaped = node.value.replace('\\', '\\\\').replace('"', '\\"')
            escaped = escaped.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
            # Кэширование строковых литералов (только внутри функций)
            if self.inside_func and node.value not in self._str_lit_cache:
                var_name = f"__str_lit_{self._str_lit_counter}"
                self._str_lit_counter += 1
                self._str_lit_cache[node.value] = var_name
                # В C используем guard для безопасной инициализации
                self._str_lit_decls.append(
                    f'static ely_value* {var_name} = NULL;'
                )
                self._str_lit_decls.append(
                    f'if (!{var_name}) {{ {var_name} = ely_value_new_string("{escaped}"); gc_add_root((void**)&{var_name}); }}'
                )
            if node.value in self._str_lit_cache:
                return self._str_lit_cache[node.value]
            return f'ely_value_new_string("{escaped}")'
        elif node.value is None:
            return "ely_value_new_null()"
        return "ely_value_new_null()"

    def _gen_identifier(self, node: Identifier) -> str:
        if node.name == 'self' and self.current_class_name:
            return "self"

        if self.current_class_name:
            cls = self.classes_ast.get(self.current_class_name)
            if cls:
                # статические поля
                for sf in cls.static_fields:
                    if sf.name == node.name:
                        return f"{self._ns_prefix()}{self.current_class_name}_{sf.name}"
                # статические методы
                for sm in cls.static_methods:
                    if sm.name == node.name:
                        return f"{self._method_full_name(sm.name)}"
                # поля экземпляра (с учётом наследования)
                                # поля экземпляра (с учётом наследования)
                if self._is_field_in_class_hierarchy(cls, node.name):
                    owner = cls
                    parts = []          # цепочка классов-родителей
                    while owner:
                        for f in owner.fields:
                            if f.name == node.name:
                                access = "self"
                                if parts:
                                    # self — указатель, __parent — встроенная структура
                                    access += "->__parent"
                                    # если родительских уровней больше одного (пока нет), были бы ещё .__parent
                                access += f".{node.name}" if parts else f"->{node.name}"
                                # оборачиваем в ely_value*
                                if f.type == 'str':
                                    return f"ely_value_new_string({access})"
                                elif f.type in ('int','uint','more','umore','byte','ubyte'):
                                    return f"ely_value_new_int({access})"
                                elif f.type in ('flt','double'):
                                    return f"ely_value_new_double({access})"
                                elif f.type == 'bool':
                                    return f"ely_value_new_bool({access})"
                                else:
                                    return access   # объектный тип (указатель)
                        if owner.extends and owner.extends in self.classes_ast:
                            parts.append(owner.extends)
                            owner = self.classes_ast[owner.extends]
                        else:
                            break

        # Проверка на статическое поле/метод класса (Class_field, Class_method)
        if '_' in node.name and not node.name.startswith('__'):
            parts = node.name.split('_', 1)
            class_part = parts[0]
            field_part = parts[1]
            if class_part in self.classes_ast:
                cls = self.classes_ast[class_part]
                # статическое поле
                for sf in cls.static_fields:
                    if sf.name == field_part:
                        return f"{class_part}_{field_part}"
                # статический метод
                for sm in cls.static_methods:
                    if sm.name == field_part:
                        # если находимся внутри метода класса, даём полное имя, иначе просто имя
                        return self._method_full_name(sm.name) if self.current_class_name else f"{class_part}_{sm.name}"

        self._ensure_identifier(node.name, node.line, node.col)
        return node.name

    @staticmethod
    def _unwrap_primitive(expr_code: str, ely_type: str) -> str:
        """Распаковывает ely_value_new_*(...) и возвращает сырое значение."""
        prefix_map = {
            'str': 'ely_value_new_string(',
            'int': 'ely_value_new_int(',
            'uint': 'ely_value_new_int(',
            'more': 'ely_value_new_int(',
            'umore': 'ely_value_new_int(',
            'byte': 'ely_value_new_int(',
            'ubyte': 'ely_value_new_int(',
            'flt': 'ely_value_new_double(',
            'double': 'ely_value_new_double(',
            'bool': 'ely_value_new_bool(',
        }
        prefix = prefix_map.get(ely_type)
        if prefix and expr_code.startswith(prefix) and expr_code.endswith(')'):
            inner = expr_code[len(prefix):-1]
            if inner.count('(') == inner.count(')'):
                return inner
        return expr_code

    @staticmethod
    def _fold_constants(node: BinaryOp) -> Optional[str]:
        """Свёртка констант: если оба операнда — Literal, вычислить на месте."""
        from parser import Literal
        if not isinstance(node.left, Literal) or not isinstance(node.right, Literal):
            return None
        lv, rv = node.left.value, node.right.value
        op = node.operator

        # Целочисленные операции
        if isinstance(lv, int) and isinstance(rv, int):
            if op == '+':  return f"ely_value_new_int({lv + rv})"
            if op == '-':  return f"ely_value_new_int({lv - rv})"
            if op == '*':  return f"ely_value_new_int({lv * rv})"
            if op == '/':  return f"ely_value_new_int({lv // rv})" if rv != 0 else None
            if op == '%':  return f"ely_value_new_int({lv % rv})" if rv != 0 else None
            if op == '==': return f"ely_value_new_bool({1 if lv == rv else 0})"
            if op == '!=': return f"ely_value_new_bool({1 if lv != rv else 0})"
            if op == '<':  return f"ely_value_new_bool({1 if lv < rv else 0})"
            if op == '<=': return f"ely_value_new_bool({1 if lv <= rv else 0})"
            if op == '>':  return f"ely_value_new_bool({1 if lv > rv else 0})"
            if op == '>=': return f"ely_value_new_bool({1 if lv >= rv else 0})"

        # Операции с плавающей точкой
        if isinstance(lv, (int, float)) and isinstance(rv, (int, float)):
            lf, rf = float(lv), float(rv)
            if op == '+':  return f"ely_value_new_double({lf + rf})"
            if op == '-':  return f"ely_value_new_double({lf - rf})"
            if op == '*':  return f"ely_value_new_double({lf * rf})"
            if op == '/':  return f"ely_value_new_double({lf / rf})" if rf != 0.0 else None
            if op == '==': return f"ely_value_new_bool({1 if lf == rf else 0})"
            if op == '!=': return f"ely_value_new_bool({1 if lf != rf else 0})"
            if op == '<':  return f"ely_value_new_bool({1 if lf < rf else 0})"
            if op == '<=': return f"ely_value_new_bool({1 if lf <= rf else 0})"
            if op == '>':  return f"ely_value_new_bool({1 if lf > rf else 0})"
            if op == '>=': return f"ely_value_new_bool({1 if lf >= rf else 0})"

        # Логические операции
        if isinstance(lv, bool) and isinstance(rv, bool):
            if op == '&&': return f"ely_value_new_bool({1 if lv and rv else 0})"
            if op == '||': return f"ely_value_new_bool({1 if lv or rv else 0})"

        return None

    def _gen_binary_op(self, node: BinaryOp) -> str:
        # Свёртка констант
        folded = self._fold_constants(node)
        if folded is not None:
            return folded

        left = self.gen_expression(node.left)
        right = self.gen_expression(node.right)
        op = node.operator

        left_type = self._get_expression_type(node.left)
        right_type = self._get_expression_type(node.right)

        # Операторные методы классов
        if left_type in self.classes_ast:
            op_method_map = {
                '+': '__add', '-': '__sub', '*': '__mul', '/': '__div',
                '%': '__mod', '==': '__eq', '!=': '__ne',
                '<': '__lt', '<=': '__le', '>': '__gt', '>=': '__ge',
            }
            method_name = op_method_map.get(op)
            if method_name:
                cls = self.classes_ast[left_type]
                for m in cls.all_methods:
                    if m.name == method_name:
                        if len(m.parameters) >= 1:
                            expected_type = m.parameters[0].type
                            right = self._convert_to_c_type_expr(right, self._type_to_c(expected_type, is_param=True))
                        return f"({left}->__vtable->{method_name}({left}, {right}))"

        # ---- Оптимизация 1.2: нативная арифметика для примитивных числовых типов ----
        num_types = {'int','uint','more','umore','byte','ubyte','flt','double'}
        is_left_num = left_type in num_types
        is_right_num = right_type in num_types

        def _ensure_native(code, typ):
            """Извлекает нативное значение: unwrap ely_value_new_*() или через ely_value_as_*()."""
            unwrapped = self._unwrap_primitive(code, typ)
            if unwrapped != code:
                return unwrapped
            if typ in ('int', 'uint', 'more', 'umore', 'byte', 'ubyte'):
                return f"ely_value_as_int({code})"
            if typ in ('flt', 'double'):
                return f"ely_value_as_double({code})"
            if typ == 'bool':
                return f"ely_value_as_bool({code})"
            return code

        if is_left_num and is_right_num and op in '+-*/%':
            left_raw = _ensure_native(left, left_type)
            right_raw = _ensure_native(right, right_type)
            is_float_op = left_type in ('flt','double') or right_type in ('flt','double')
            raw_expr = f"({left_raw} {op} {right_raw})"
            if is_float_op:
                return f"ely_value_new_double{raw_expr}"
            else:
                return f"ely_value_new_int{raw_expr}"
        # Для логических операторов с числовыми типами
        if is_left_num and is_right_num and op in ('==','!=','<','>','<=','>='):
            left_raw = _ensure_native(left, left_type)
            right_raw = _ensure_native(right, right_type)
            raw_expr = f"({left_raw} {op} {right_raw})"
            return f"ely_value_new_bool{raw_expr}"
        # Для &&/|| с bool
        if left_type == 'bool' and right_type == 'bool' and op in ('&&','||'):
            left_raw = _ensure_native(left, 'bool')
            right_raw = _ensure_native(right, 'bool')
            c_op = '&&' if op == '&&' else '||'
            raw_expr = f"({left_raw} {c_op} {right_raw})"
            return f"ely_value_new_bool{raw_expr}"

        # Обычные runtime-операции
        op_map = {
            '+': 'add', '-': 'sub', '*': 'mul', '/': 'div',
            '%': 'mod', '==': 'eq', '!=': 'ne',
            '<': 'lt', '<=': 'le', '>': 'gt', '>=': 'ge',
            '&&': 'and', '||': 'or',
        }
        func = f"ely_value_{op_map.get(op, op)}"
        return f"{func}({left}, {right})"

    def _gen_unary_op(self, node: UnaryOp) -> str:
        operand = self.gen_expression(node.operand)
        op = node.operator
        if op == '!':
            return f"ely_value_not({operand})"
        elif op == '-':
            return f"ely_value_neg({operand})"
        elif op == '&':
            return f"(&{operand})"
        else:
            return f"{op}{operand}"

    def _is_lvalue(self, expr: Expression) -> bool:
        if isinstance(expr, Identifier):
            return True
        if isinstance(expr, IndexExpression):
            return True
        if isinstance(expr, MemberAccess):
            return True
        return False

    def _is_field_in_class_hierarchy(self, cls: ClassDeclaration, field_name: str) -> bool:
        if field_name in [f.name for f in cls.fields]:
            return True
        if cls.extends and cls.extends in self.classes_ast:
            return self._is_field_in_class_hierarchy(self.classes_ast[cls.extends], field_name)
        return False

    def _gen_assignment(self, node: Assignment) -> str:
        target_code = self.gen_expression(node.target)
        raw_value_code = self.gen_expression(node.value)
        op = node.operator

        if op != '=':
            binary_op = BinaryOp(
                line=node.line, col=node.col,
                left=node.target,
                operator=op[:-1],
                right=node.value
            )
            value_code = self.gen_expression(binary_op)
        else:
            value_code = raw_value_code

        target_ely_type = None
        if isinstance(node.target, Identifier):
            name = node.target.name
            if name in self.var_types:
                target_ely_type = self._resolve_type_alias(self.var_types[name])
            else:
                for scope in reversed(self.scopes):
                    if name in scope:
                        target_ely_type = self._resolve_type_alias(scope[name])
                        break
            if target_ely_type is None and name in self.global_types:
                target_ely_type = self._resolve_type_alias(self.global_types[name])

        if isinstance(node.target, Identifier):
            name = node.target.name
            found = (name in self.var_types) or (name in self.global_types)
            if not found:
                for scope in reversed(self.scopes):
                    if name in scope:
                        found = True
                        break
                # проверим статические поля классов (Class_field)
                if not found and '_' in name and not name.startswith('__'):
                    parts = name.split('_', 1)
                    class_part = parts[0]
                    field_part = parts[1]
                    if class_part in self.classes_ast:
                        cls = self.classes_ast[class_part]
                        for sf in cls.static_fields:
                            if sf.name == field_part:
                                found = True
                                break
            if not found:
                self.var_types[name] = 'any'
                self.emit_to_main(f"ely_value* {name};")
                self.emit_to_main(f"gc_add_root((void**)&{name});")
                if self.scope_roots and name and name not in ['None', 'NULL']:
                    self.scope_roots[-1].append(name)

        # Преобразование типа значения, если нужно
        if target_ely_type and target_ely_type not in ('any', 'void', 'arr', 'dict', '*'):
            source_type = self._get_expression_type(node.value)
            if source_type != target_ely_type:
                value_code = self._convert_value(value_code, source_type, target_ely_type)

        # 1. Присваивание полю текущего объекта (self.field)
        if isinstance(node.target, Identifier) and self.current_class_name:
            cls = self.classes_ast.get(self.current_class_name)
            if cls and self._is_field_in_class_hierarchy(cls, node.target.name):
                # строим путь до поля
                owner = cls
                parts = []
                field = None
                while owner:
                    for f in owner.fields:
                        if f.name == node.target.name:
                            field = f
                            break
                    if field:
                        break
                    if owner.extends and owner.extends in self.classes_ast:
                        parts.append(owner.extends)
                        owner = self.classes_ast[owner.extends]
                    else:
                        break
                access = "self"
                for p in parts:
                    access += ".__parent"
                if parts:
                    access += "->__parent"
                    access += f".{node.target.name}"
                else:
                    access += f"->{node.target.name}"
                # преобразование значения
                if field.type == 'str':
                    value_code = f"ely_str_dup({value_code})"
                elif field.type in ('int','uint','more','umore','byte','ubyte'):
                    value_code = f"ely_value_as_int({value_code})"
                elif field.type in ('flt','double'):
                    value_code = f"ely_value_as_double({value_code})"
                elif field.type == 'bool':
                    value_code = f"ely_value_as_bool({value_code})"
                return f"{access} = {value_code};"

        # 2. Присваивание свойству через сеттер (self.property или obj.property)
        if isinstance(node.target, MemberAccess):
            obj_type = self._get_expression_type(node.target.object)
            if obj_type in self.classes_ast:
                cls = self.classes_ast[obj_type]
                # Свойство (сеттер)
                for prop in cls.properties:
                    if prop.name == node.target.member and prop.setter:
                        obj_code = self.gen_expression(node.target.object)
                        # преобразуем значение в тип свойства
                        val_code = value_code
                        if prop.type == 'str':
                            val_code = f"ely_value_to_string({value_code})"
                        elif prop.type in ('int','uint','more','umore','byte','ubyte'):
                            val_code = f"ely_value_as_int({value_code})"
                        elif prop.type in ('flt','double'):
                            val_code = f"ely_value_as_double({value_code})"
                        elif prop.type == 'bool':
                            val_code = f"ely_value_as_bool({value_code})"
                        return f"{obj_code}->__vtable->{prop.setter.name}({obj_code}, {val_code});"
                # Обычное поле чужого объекта (прямой доступ, если это класс)
                if self._is_field_in_class_hierarchy(cls, node.target.member):
                    obj_code = self.gen_expression(node.target.object)
                    # преобразование типа поля
                    for f in cls.fields:
                        if f.name == node.target.member:
                            if f.type == 'str':
                                value_code = f"ely_value_to_string({value_code})"
                            elif f.type in ('int','uint','more','umore','byte','ubyte'):
                                value_code = f"ely_value_as_int({value_code})"
                            elif f.type in ('flt','double'):
                                value_code = f"ely_value_as_double({value_code})"
                            elif f.type == 'bool':
                                value_code = f"ely_value_as_bool({value_code})"
                            break
                    return f"{obj_code}->{node.target.member} = {value_code};"

            # Fallback: старый код для ely_value* (не-класс)
            obj = self.gen_expression(node.target.object)
            return f"ely_value_set_key({obj}, \"{node.target.member}\", {value_code})"

        # 3. Статическое поле класса
        if isinstance(node.target, Identifier) and target_ely_type in self.classes_ast:
            # Присваивание статическому полю вида `ClassName_field = val`
            # Уже сгенерировано через target_code, но можем оставить стандартное присваивание
            return f"{target_code} = {value_code};"

        # 4. Обычное присваивание переменной
        return f"{target_code} = {value_code};"

    def _gen_conditional(self, node: Conditional) -> str:
        cond = self.gen_expression(node.condition)
        then_expr = self.gen_expression(node.then_expr)
        else_expr = self.gen_expression(node.else_expr)
        return f"((ely_value_as_bool({cond})) ? {then_expr} : {else_expr})"

    def _gen_class_constructor_forward(self, cls: ClassDeclaration):
        own_wait = cls.wait_fields
        params = ', '.join([f"{self._type_to_c(f.type, is_param=True)} {f.name}" for f in own_wait])
        self.code.append(f"struct {cls.name}* {cls.name}_constructor({params});")

    def _gen_class_constructor(self, cls: ClassDeclaration):
        name = cls.name
        parent = cls.extends
        params = self._collect_constructor_params(cls)
        param_str = ', '.join([f"struct {name}* self"] + [f"{self._type_to_c(p.type, is_param=True)} {p.name}" for p in params])
        self.emit(f"void {name}_constructor({param_str}) {{")
        self.indent += 1
        # родительский конструктор (если есть) – ДО установки своего vtable
        if parent and parent in self.classes_ast:
            parent_wait = self.classes_ast[parent].wait_fields
            parent_self = f"(struct {parent}*)self" if parent != name else "self"
            parent_args = ', '.join([parent_self] + [p.name for p in params[:len(parent_wait)]])
            self.emit(f"{parent}_constructor({parent_args});")
        # Устанавливаем СВОЙ vtable (после родителя, чтобы не перезаписался)
        self.emit(f"self->__vtable = &{name}_vtable_inst;")
        # wait-поля
        own_wait = cls.wait_fields
        for i, f in enumerate(own_wait):
            param_name = params[i + (len(parent_wait) if parent and parent_wait else 0)].name
            if f.type == 'str':
                self.emit(f"self->{f.name} = ely_str_dup({param_name});")
            else:
                self.emit(f"self->{f.name} = {param_name};")
        # инициализация обычных полей
        for f in cls.fields:
            if f.modifier == 'static':
                continue
            if f in cls.wait_fields:
                continue
            # значение по умолчанию
            if f.type == 'str':
                default_val = "NULL"
            elif f.type in ('int', 'uint', 'more', 'umore', 'byte', 'ubyte'):
                default_val = "0"
            elif f.type in ('flt', 'double'):
                default_val = "0.0"
            elif f.type == 'bool':
                default_val = "0"
            else:
                default_val = "NULL"
            if f.initializer:
                # используем выражение инициализатора (упрощённо)
                init_code = self.gen_expression(f.initializer)
                # преобразуем к целевому C‑типу
                target_c = self._type_to_c(f.type, is_field=True)
                if target_c == 'char*':
                    init_code = f"ely_value_to_string({init_code})"
                elif target_c in ('int', 'long long', 'unsigned int', 'unsigned long long', 'signed char', 'unsigned char'):
                    init_code = f"ely_value_as_int({init_code})"
                elif target_c in ('float', 'double'):
                    init_code = f"ely_value_as_double({init_code})"
                default_val = init_code
            self.emit(f"self->{f.name} = {default_val};")
        self.indent -= 1
        self.emit("}")

    def _collect_wait_fields(self, cls: ClassDeclaration) -> List[VariableDeclaration]:
        fields = []
        if cls.extends and cls.extends in self.classes_ast:
            parent = self.classes_ast[cls.extends]
            fields.extend(self._collect_wait_fields(parent))
        fields.extend(cls.wait_fields)
        return fields

    def _gen_fstring(self, node: FString) -> str:
        if not node.parts:
            return 'ely_value_new_string("")'
        
        result = None
        for part in node.parts:
            if isinstance(part, str):
                escaped = part.replace('"', '\\"').replace('\n', '\\n')
                part_expr = f'ely_value_new_string("{escaped}")'
            else:
                part_expr = self.gen_expression(part)
            
            if result is None:
                result = part_expr
            else:
                result = f'ely_value_add({result}, {part_expr})'
        return result

    def _gen_array_literal(self, node: ArrayLiteral) -> str:
        if not node.elements:
            return "ely_value_new_array(arr_new())"
        elems = []
        for elem in node.elements:
            elem_code = self.gen_expression(elem)
            tmp = f"__tmp_ary_{self.temp_counter}"
            self.temp_counter += 1
            self.emit_to_main(f"ely_value* {tmp} = {elem_code};")
            elems.append(tmp)
        arr_var = f"__arr_{self.temp_counter}"
        self.temp_counter += 1
        self.emit_to_main(f"arr* {arr_var} = arr_new();")
        for e in elems:
            self.emit_to_main(f"arr_push({arr_var}, {e});")
        return f"ely_value_new_array({arr_var})"

    def _gen_dict_literal(self, node: DictLiteral) -> str:
        if not node.pairs:
            return "ely_value_new_object(dict_new_str())"
        pairs = []
        for pair in node.pairs:
            key_code = self.gen_expression(pair.key)
            val_code = self.gen_expression(pair.value)
            key_tmp = f"__tmp_key_{self.temp_counter}"
            self.temp_counter += 1
            val_tmp = f"__tmp_val_{self.temp_counter}"
            self.temp_counter += 1
            self.emit_to_main(f"ely_value* {key_tmp} = {key_code};")
            self.emit_to_main(f"ely_value* {val_tmp} = {val_code};")
            pairs.append((key_tmp, val_tmp))
        dict_var = f"__dict_{self.temp_counter}"
        self.temp_counter += 1
        self.emit_to_main(f"dict* {dict_var} = dict_new_str();")
        for key, val in pairs:
            self.emit_to_main(f"dict_set_str({dict_var}, {key}->u.string_val, {val});")
        return f"ely_value_new_object({dict_var})"

    def _gen_index_expression(self, node: IndexExpression) -> str:
        target = self.gen_expression(node.target)
        index = self.gen_expression(node.index)
        return f"ely_value_index({target}, {index})"

    def _gen_member_access(self, node: MemberAccess) -> str:
        obj = self.gen_expression(node.object)
        obj_type = self._get_expression_type(node.object)
        if obj_type in self.classes_ast:
            cls = self.classes_ast[obj_type]
            # статические поля
            for sf in cls.static_fields:
                if sf.name == node.member:
                    return f"{self._ns_prefix()}{obj_type}_{sf.name}"
            # поля экземпляра
            if self._is_field_in_class_hierarchy(cls, node.member):
                owner = cls
                parts = []
                while owner:
                    for f in owner.fields:
                        if f.name == node.member:
                            access = obj
                            if parts:
                                access += "->__parent"
                            access += f".{node.member}" if parts else f"->{node.member}"
                            # обёртка
                            if f.type == 'str':
                                return f"ely_value_new_string({access})"
                            elif f.type in ('int','uint','more','umore','byte','ubyte'):
                                return f"ely_value_new_int({access})"
                            elif f.type in ('flt','double'):
                                return f"ely_value_new_double({access})"
                            elif f.type == 'bool':
                                return f"ely_value_new_bool({access})"
                            else:
                                return access
                    if owner.extends and owner.extends in self.classes_ast:
                        parts.append(owner.extends)
                        owner = self.classes_ast[owner.extends]
                    else:
                        break
        return f"ely_value_get_key({obj}, \"{node.member}\")"

    def _gen_call(self, node: Call) -> str:
        if isinstance(node.callee, MemberAccess):
            obj = node.callee.object
            method = node.callee.member
            obj_type = self._get_expression_type(obj)
            obj_code = self.gen_expression(obj)
            if obj_code is None:
                return "ely_value_new_null()"

            if obj_type.startswith('arr<'):
                args = [self.gen_expression(a) for a in node.arguments]
                if method == 'push':
                    if len(args) != 1:
                        self.error("push expects 1 argument", node)
                        return ""
                    val = self._convert_to_ctype(node.arguments[0], args[0], 'any')
                    return f"ely_array_push({obj_code}, {val})"
                elif method == 'pop':
                    return f"ely_array_pop({obj_code})"
                elif method == 'len':
                    return self._wrap_result(f"ely_array_len({obj_code})", 'int')
                elif method == 'insert':
                    if len(args) != 2:
                        self.error("insert expects 2 arguments", node)
                        return ""
                    idx = self._convert_to_ctype(node.arguments[0], args[0], 'int')
                    val = self._convert_to_ctype(node.arguments[1], args[1], 'any')
                    return f"ely_array_insert({obj_code}, {idx}, {val})"
                elif method == 'remove':
                    if len(args) != 1:
                        self.error("remove expects 1 argument", node)
                        return ""
                    val = self._convert_to_ctype(node.arguments[0], args[0], 'any')
                    return f"ely_array_remove_value({obj_code}, {val})"
                elif method == 'index':
                    if len(args) != 1:
                        self.error("index expects 1 argument", node)
                        return ""
                    val = self._convert_to_ctype(node.arguments[0], args[0], 'any')
                    return self._wrap_result(f"ely_array_index({obj_code}, {val})", 'int')
                else:
                    self.error(f"Unknown array method '{method}'", node)
                    return ""

            if obj_type.startswith('dict<'):
                args = [self.gen_expression(a) for a in node.arguments]
                if method == 'keys':
                    return self._wrap_result(f"ely_dict_keys({obj_code})", 'arr<str>')
                elif method == 'del':
                    if len(args) != 1:
                        self.error("del expects 1 argument", node)
                        return ""
                    key = self._convert_to_ctype(node.arguments[0], args[0], 'any')
                    return f"ely_dict_del({obj_code}, {key})"
                elif method == 'has':
                    if len(args) != 1:
                        self.error("has expects 1 argument", node)
                        return ""
                    key = self._convert_to_ctype(node.arguments[0], args[0], 'any')
                    return self._wrap_result(f"ely_dict_has({obj_code}, {key})", 'bool')
                elif method == 'toJson':
                    return self._wrap_result(f"ely_dict_to_json({obj_code})", 'str')
                else:
                    self.error(f"Unknown dict method '{method}'", node)
                    return ""

            if obj_type == 'str':
                args = [self.gen_expression(a) for a in node.arguments]
                if method == 'len':
                    return self._wrap_result(f"ely_str_len(({obj_code})->u.string_val)", 'int')
                elif method == 'concat':
                    if len(args) != 1:
                        self.error("concat expects 1 argument", node)
                        return ""
                    other = self._convert_to_ctype(node.arguments[0], args[0], 'str')
                    return self._wrap_result(f"ely_str_concat(({obj_code})->u.string_val, {other})", 'str')
                elif method == 'substr':
                    if len(args) != 2:
                        self.error("substr expects 2 arguments", node)
                        return ""
                    start = self._convert_to_ctype(node.arguments[0], args[0], 'int')
                    length = self._convert_to_ctype(node.arguments[1], args[1], 'int')
                    return self._wrap_result(f"ely_str_substr(({obj_code})->u.string_val, {start}, {length})", 'str')
                elif method == 'trim':
                    return self._wrap_result(f"ely_str_trim(({obj_code})->u.string_val)", 'str')
                elif method == 'replace':
                    if len(args) != 2:
                        self.error("replace expects 2 arguments", node)
                        return ""
                    old = self._convert_to_ctype(node.arguments[0], args[0], 'str')
                    new = self._convert_to_ctype(node.arguments[1], args[1], 'str')
                    return self._wrap_result(f"ely_str_replace(({obj_code})->u.string_val, {old}, {new})", 'str')
                else:
                    self.error(f"Unknown string method '{method}'", node)
                    return ""

            if obj_type in ('int', 'uint', 'more', 'umore', 'flt', 'double'):
                if method == 'toStr':
                    return self._wrap_result(f"ely_value_to_string({obj_code})", 'str')
                elif method == 'abs':
                    return self._wrap_result(f"ely_value_abs({obj_code})", obj_type)
                else:
                    self.error(f"Unknown number method '{method}'", node)
                    return ""

            if obj_type in self.classes_ast:
                obj_code = self.gen_expression(obj)
                cls = self.classes_ast[obj_type]
                method_node = None
                for m in cls.all_methods:
                    if m.name == node.callee.member:
                        method_node = m
                        break
                if not method_node:
                    self.error(f"Method '{node.callee.member}' not found in class '{obj_type}'", node)
                    return "ely_value_new_null()"
                args = [obj_code]
                for i, arg_expr in enumerate(node.arguments):
                    arg_code = self.gen_expression(arg_expr)
                    if i < len(method_node.parameters):
                        param = method_node.parameters[i]
                        expected_c_type = self._type_to_c(param.type, is_param=True)
                        arg_code = self._convert_to_c_type_expr(arg_code, expected_c_type)
                    args.append(arg_code)
                return f"({obj_code}->__vtable->{node.callee.member}({', '.join(args)}))"

            # неявный вызов метода текущего класса
            if self.current_class_name:
                cls = self.classes_ast.get(self.current_class_name)
                if cls:
                    for m in cls.all_methods:
                        if m.name == func_name:
                            args_code = [self.gen_expression(a) for a in node.arguments]
                            # преобразование аргументов
                            for i, arg in enumerate(node.arguments):
                                if i < len(m.parameters):
                                    expected_c = self._type_to_c(m.parameters[i].type, is_param=True)
                                    args_code[i] = self._convert_to_c_type_expr(args_code[i], expected_c)
                            return f"(self->__vtable->{func_name}(self, {', '.join(args_code)}))"

            self.error(f"Unknown function '{func_name}'", node)
            return "ely_value_new_null()"

        if not isinstance(node.callee, Identifier):
            self.error("Call expression must be a function or method", node)
            return "ely_value_new_null()"

        func_name = node.callee.name

        # --- Обработка конструкторов ДО original_functions ---
        if func_name.endswith('_constructor'):
            class_name = func_name[:-len('_constructor')]
            cls = self.classes_ast.get(class_name)
            if not cls:
                self.error(f"Unknown class {class_name}", node)
                return "ely_value_new_null()"
            # выделяем память
            ctype = f"struct {class_name}*"
            obj_var = f"__obj_{self.temp_counter}"
            self.temp_counter += 1
            self.emit_to_main(f"{ctype} {obj_var} = gc_calloc(sizeof(struct {class_name}), GC_OBJ_OTHER);")
            self.emit_to_main(f"gc_add_root((void**)&{obj_var});")
            # собираем аргументы конструктора
            params = self._collect_constructor_params(cls)
            args_code = []
            for i, param in enumerate(params):
                arg = node.arguments[i] if i < len(node.arguments) else None
                if arg:
                    code = self.gen_expression(arg)
                    code = self._convert_to_c_type_expr(code, self._type_to_c(param.type, is_param=True))
                else:
                    code = "ely_value_new_null()"  # значение по умолчанию для ely_value*
                args_code.append(code)
            full_args = ', '.join([obj_var] + args_code)
            self.emit_to_main(f"{class_name}_constructor({full_args});")
            # удаляем временный корень, чтобы объект жил, пока есть другие корни
            self.emit_to_main(f"gc_remove_root((void**)&{obj_var});")
            return obj_var

        if func_name in self.original_functions:
            func_node = self.original_functions[func_name]
            if func_node.type_params:
                bindings = {}
                for arg, param in zip(node.arguments, func_node.parameters):
                    arg_type = self._get_expression_type(arg)
                    if param.type in func_node.type_params:
                        bindings[param.type] = arg_type
                missing = [tp for tp in func_node.type_params if tp not in bindings]
                if missing:
                    self.error(f"Could not infer type parameters: {missing}", node)
                    return "ely_value_new_null()"
                key = (func_name, tuple(bindings.values()))
                if key not in self.generic_instances:
                    spec_name = self._generate_specialization(func_node, bindings)
                    self.generic_instances[key] = spec_name
                else:
                    spec_name = self.generic_instances[key]
                args_code = [self.gen_expression(arg) for arg in node.arguments]
                call_expr = f"{spec_name}({', '.join(args_code)})"
                return call_expr
            else:
                args_code = [self.gen_expression(arg) for arg in node.arguments]
                call_expr = f"{func_name}({', '.join(args_code)})"
                return call_expr

        if func_name in self.builtin_signatures:
            c_func_name, return_type, param_types = self.builtin_signatures[func_name]

            # ---- Оптимизация: специализированные print/println ----
            if func_name in ('print', 'println', 'printOld') and len(node.arguments) == 1:
                arg_type = self._get_expression_type(node.arguments[0])
                # Выбираем мапу: println использует ely_println_*, print/printOld использует ely_print_*
                if func_name == 'println':
                    print_map = {
                        'int': 'ely_println_int',
                        'uint': 'ely_println_uint',
                        'more': 'ely_println_more',
                        'umore': 'ely_println_umore',
                        'flt': 'ely_println_flt',
                        'double': 'ely_println_double',
                        'bool': 'ely_println_bool',
                        'char': 'ely_println_char',
                        'byte': 'ely_println_byte',
                        'ubyte': 'ely_println_ubyte',
                        'str': 'ely_println_str',
                    }
                else:
                    print_map = {
                        'int': 'ely_print_int',
                        'uint': 'ely_print_uint',
                        'more': 'ely_print_more',
                        'umore': 'ely_print_umore',
                        'flt': 'ely_print_flt',
                        'double': 'ely_print_double',
                        'bool': 'ely_print_bool',
                        'char': 'ely_print_char',
                        'byte': 'ely_print_byte',
                        'ubyte': 'ely_print_ubyte',
                        'str': 'ely_print',
                    }
                if arg_type in print_map:
                    spec_func = print_map[arg_type]
                    arg_code = self.gen_expression(node.arguments[0])
                    if arg_code is None:
                        return "ely_value_new_null()"
                    # Распаковываем ely_value* в нативный тип, если кодогенератор уже обернул
                    if arg_type == 'str':
                        if arg_code.startswith('ely_value_new_string('):
                            arg_code = arg_code[len('ely_value_new_string('):-1]
                        else:
                            arg_code = self._convert_to_c_type_expr(arg_code, 'char*')
                    elif arg_type in ('int', 'uint', 'more', 'umore', 'byte', 'ubyte'):
                        if arg_code.startswith('ely_value_new_int('):
                            arg_code = arg_code[len('ely_value_new_int('):-1]
                        else:
                            arg_code = self._convert_to_c_type_expr(arg_code, 'int')
                    elif arg_type in ('flt', 'double'):
                        if arg_code.startswith('ely_value_new_double('):
                            arg_code = arg_code[len('ely_value_new_double('):-1]
                        else:
                            arg_code = self._convert_to_c_type_expr(arg_code, 'double')
                    elif arg_type == 'bool':
                        if arg_code.startswith('ely_value_new_bool('):
                            arg_code = arg_code[len('ely_value_new_bool('):-1]
                        else:
                            arg_code = f"ely_value_as_bool({arg_code})"
                    return f"{spec_func}({arg_code});"
                # Если тип не найден в мапе — падаем в общую обработку

            args_code = []
            for i, arg in enumerate(node.arguments):
                arg_code = self.gen_expression(arg)
                if arg_code is None:
                    return "ely_value_new_null()"
                if i < len(param_types):
                    expected = param_types[i]
                    arg_code = self._convert_to_ctype(arg, arg_code, expected)
                args_code.append(arg_code)
            call_expr = f"{c_func_name}({', '.join(args_code)})"
            return self._wrap_result(call_expr, return_type)

        if func_name in self.extern_functions:
            ext = self.extern_functions[func_name]
            return_type = ext.return_type or 'void'
            param_types = [p.type for p in ext.parameters]
            args_code = []
            for i, arg in enumerate(node.arguments):
                arg_code = self.gen_expression(arg)
                if arg_code is None:
                    return "ely_value_new_null()"
                if i < len(param_types):
                    expected = param_types[i]
                    arg_code = self._convert_to_ctype(arg, arg_code, expected)
                args_code.append(arg_code)
            call_expr = f"{func_name}({', '.join(args_code)})"
            return self._wrap_result(call_expr, return_type)

        self.error(f"Unknown function '{func_name}'", node)
        return "ely_value_new_null()"

    def _generate_specialization(self, func_node: MethodDeclaration, mapping: dict) -> str:
        def substitute(s: str) -> str:
            if s is None:
                return s
            for tp, ct in mapping.items():
                s = s.replace(tp, ct)
            return s

        new_params = []
        for p in func_node.parameters:
            new_type = substitute(p.type)
            new_params.append(Parameter(type=new_type, name=p.name))
        new_return_type = substitute(func_node.return_type)
        new_body = []
        for stmt in func_node.body:
            if isinstance(stmt, VariableDeclaration):
                new_type = substitute(stmt.type)
                new_body.append(VariableDeclaration(
                    line=stmt.line, col=stmt.col,
                    modifier=stmt.modifier, type=new_type, name=stmt.name,
                    initializer=stmt.initializer, tag=stmt.tag
                ))
            else:
                new_body.append(stmt)
        suffix = '_'.join(str(ct) for ct in mapping.values())
        spec_name = f"{func_node.name}_{suffix}"
        new_func = MethodDeclaration(
            line=func_node.line, col=func_node.col,
            return_type=new_return_type,
            name=spec_name,
            parameters=new_params,
            body=new_body,
            modifier=func_node.modifier,
            type_params=[]
        )
        old_main = self.main_code
        self.main_code = []
        self.indent = 0
        self._gen_function(new_func)
        spec_code = "\n".join(self.main_code)
        self.main_code = old_main
        self.specializations.append(spec_code)
        return spec_name

    def _gen_gc_roots(self):
        roots = []
        for name, typ in self.var_types.items():
            resolved = self._resolve_type_alias(typ)
            ctype = self._type_to_c(resolved)
            if ctype == 'ely_value*' or ctype.startswith('ely_value*'):
                roots.append(name)
        self.current_roots = roots
        for name in roots:
            self.emit_to_main(f"gc_add_root((void**)&{name});")

    def error(self, message: str, node: Expression):
        print(f"Code generation error: {message} at line {node.line}, col {node.col}")

    def _hoist_nested_functions(self, stmts: List[Statement]) -> List[Statement]:
        hoisted = []
        new_stmts = []
        for stmt in stmts:
            if isinstance(stmt, MethodDeclaration):
                if self.current_function:
                    new_name = f"{self.current_function}_{stmt.name}"
                else:
                    new_name = stmt.name
                stmt.name = new_name
                self.original_functions[new_name] = stmt
                hoisted.append(stmt)
            else:
                new_stmts.append(stmt)
        self.hoisted_functions.extend(hoisted)
        return new_stmts

    def _forward_declare(self, node: MethodDeclaration):
        if node.name == 'main':
            return
        if node.type_params:
            return
        is_static = (node.modifier == 'static')
        ret_type_c = self._type_to_c(node.return_type or 'void', for_signature=True)
        params = []
        if self.current_class_name and not is_static:
            params.append(f"struct {self.current_class_name}* self")
        for p in node.parameters:
            params.append(f"{self._type_to_c(p.type, for_signature=True, is_param=True)} {p.name}")
        full_name = self._method_full_name(node.name)
        self.code.append(f"{ret_type_c} {full_name}({', '.join(params)});")

    def _gen_function(self, node: MethodDeclaration):
        if node.name == '_global_init':
            return
        if node.type_params:
            return

        func_name = self._method_full_name(node.name)
        is_static = (node.modifier == 'static')
        is_main = (func_name == 'main')
        is_constructor = func_name.endswith('_constructor')

        ret_type_c = 'int' if is_main else self._type_to_c(node.return_type or 'void', for_signature=True)

        # Формируем сигнатуру функции
        sig_params = []
        if self.current_class_name and not is_static and not is_constructor:
            sig_params.append(f"struct {self.current_class_name}* self")
        for p in node.parameters:
            sig_params.append(f"{self._type_to_c(p.type, for_signature=True, is_param=True)} {p.name}")
        param_str = ", ".join(sig_params)

        old_main = self.main_code
        self.main_code = []
        self.indent = 0
        self.inside_func = True
        self.func_name = func_name
        old_function = self.current_function
        self.current_function = func_name
        self.func_return_type = node.return_type or 'void'
        self.hoisted_functions = []
        self.is_constructor = is_constructor
        # Сброс кэша строковых литералов для новой функции
        self._str_lit_cache.clear()
        self._str_lit_counter = 0
        self._str_lit_decls = []

        self.emit_to_main(f"{ret_type_c} {func_name}({param_str}) {{")
        self.indent += 1

        # Вставка кэшированных строковых литералов
        for decl in self._str_lit_decls:
            self.emit_to_main(decl)

        if is_main:
            self.emit_to_main("gc_init();")
            self.emit_to_main("_global_init();")
            self.emit_to_main("gc_set_enabled(0);")      # ← временно отключаем GC

        self._push_scope()

        # Регистрируем self в области видимости
        if self.current_class_name and not is_static and not is_constructor:
            self.var_types['self'] = self.current_class_name

        # Регистрируем параметры и добавляем корни для ely_value*
        for p in node.parameters:
            self.var_types[p.name] = p.type
            ctype = self._type_to_c(p.type, is_param=True)
            if ctype == 'ely_value*':
                self.emit_to_main(f"gc_add_root((void**)&{p.name});")
                if self.scope_roots:
                    self.scope_roots[-1].append(p.name)

        body_stmts = self._hoist_nested_functions(node.body)
        for stmt in body_stmts:
            self.gen_statement(stmt)

        self._pop_scope()
        self.indent -= 1
        self.emit_to_main("}")

        self.inside_func = False
        self.func_name = None
        self.current_function = old_function

        for hoisted in self.hoisted_functions:
            self._gen_function(hoisted)

        old_main.extend(self.main_code)
        self.main_code = old_main

    def _emit_temp_root(self, value_expr: str) -> str:
        tmp = f"__tmp_{self.temp_counter}"
        self.temp_counter += 1
        self.emit_to_main(f"ely_value* {tmp} = {value_expr};")
        self.emit_to_main(f"gc_add_root((void**)&{tmp});")
        if self.scope_roots:
            self.scope_roots[-1].append(tmp)
        return tmp

    def _temp_root(self, expr_code: str) -> str:
        tmp = f"__tmp_{self.temp_counter}"
        self.temp_counter += 1
        self.emit_to_main(f"ely_value* {tmp} = {expr_code};")
        self.emit_to_main(f"gc_add_root((void**)&{tmp});")
        if self.scope_roots:
            self.scope_roots[-1].append(tmp)
        return tmp

    def _emit_drop_root(self, var_name: str):
        self.emit_to_main(f"gc_remove_root((void**)&{var_name});")

    def _gen_class_struct(self, cls: ClassDeclaration):
        name = cls.name
        parent = cls.extends
        self.emit(f"struct {name};")  # forward объявление
        self.emit(f"struct {name} {{")
        self.emit(f"    const struct {name}_vtable* __vtable;")
        if parent and parent in self.classes_ast:
            self.emit(f"    struct {parent} __parent;")
        # Поля класса (не статические)
        for f in cls.fields:
            if f.modifier != 'static':
                ctype = self._type_to_c(f.type, is_field=True)
                self.emit(f"    {ctype} {f.name};")
        self.emit("};")

    def _gen_vtable_decl(self, cls: ClassDeclaration):
        name = cls.name
        vname = f"{name}_vtable"
        # Все нестатические неконструкторные методы из всей иерархии
        methods = []
        # Наследуем методы от родителя (если есть) и добавляем свои
        if cls.extends and cls.extends in self.classes_ast:
            parent = self.classes_ast[cls.extends]
            # Получаем список уникальных методов родителя
            parent_methods = []
            for m in parent.all_methods:
                if m.modifier != 'static' and not m.name.endswith('_constructor'):
                    parent_methods.append(m)
            # Убираем дубликаты по имени
            parent_names = {m.name for m in parent_methods}
            methods = parent_methods.copy()
            # Добавляем методы из cls, которых нет в родителе, или переопределённые
            for m in cls.methods:
                if m.modifier != 'static' and not m.name.endswith('_constructor'):
                    if m.name in parent_names:
                        # заменяем
                        for i, pm in enumerate(methods):
                            if pm.name == m.name:
                                methods[i] = m
                                break
                        else:
                            methods.append(m)
                    else:
                        methods.append(m)
        else:
            methods = [m for m in cls.methods if m.modifier != 'static' and not m.name.endswith('_constructor')]
        
        # Также учитываем сеттеры/геттеры свойств
        for prop in cls.properties:
            if prop.getter and prop.getter.modifier != 'static':
                methods.append(prop.getter)   # имена get_xxx уже уникальны
            if prop.setter and prop.setter.modifier != 'static':
                methods.append(prop.setter)
        
        if not methods:
            return
        self.emit(f"struct {vname} {{")
        for m in methods:
            ret = self._type_to_c(m.return_type or 'void', for_signature=True)
            params = ', '.join([f"{self._type_to_c(p.type, for_signature=True, is_param=True)} {p.name}" for p in m.parameters])
            self.emit(f"    {ret} (*{m.name})(struct {name}* self{', ' if params else ''}{params});")
        self.emit("};")

    def _gen_vtable_impl(self, cls: ClassDeclaration):
        name = cls.name
        vname = f"{name}_vtable"
        # Собираем список методов так же, как в vtable_decl
        methods = []
        if cls.extends and cls.extends in self.classes_ast:
            parent = self.classes_ast[cls.extends]
            parent_methods = [m for m in parent.all_methods if m.modifier != 'static' and not m.name.endswith('_constructor')]
            methods = parent_methods.copy()
            for m in cls.methods:
                if m.modifier != 'static' and not m.name.endswith('_constructor'):
                    if m.name in {pm.name for pm in parent_methods}:
                        for i, pm in enumerate(methods):
                            if pm.name == m.name:
                                methods[i] = m
                                break
                    else:
                        methods.append(m)
        else:
            methods = [m for m in cls.methods if m.modifier != 'static' and not m.name.endswith('_constructor')]
        
        # Добавляем методы свойств
        for prop in cls.properties:
            if prop.getter and prop.getter.modifier != 'static':
                methods.append(prop.getter)
            if prop.setter and prop.setter.modifier != 'static':
                methods.append(prop.setter)
        
        if not methods:
            return
        
        # Генерация недостающих функций (например, унаследованных от родителя)
        for m in methods:
            # Если метод объявлен в этом классе или переопределён, он уже будет сгенерирован как обычный метод
            # Если метод родительский и не переопределён, создаём заглушку
            if m in cls.methods:  # прямо объявлен в cls (оригинал)
                continue
            # Проверяем, есть ли уже функция с именем {name}_{m.name}
            # Сгенерируем заглушку, которая вызывает родительский метод
            self._gen_inherited_stub(cls, m)

        # Инициализация vtable
        self.emit(f"static const struct {vname} {vname}_inst = {{")
        for m in methods:
            # Имя указываемой функции
            func_name = f"{name}_{m.name}"
            self.emit(f"    {func_name},")
        self.emit("};")

    def _gen_super_call(self, node: SuperCall) -> str:
        if not self.current_class_name:
            self.error("super used outside class method", node)
            return "ely_value_new_null()"
        cls = self.classes_ast.get(self.current_class_name)
        if not cls or not cls.extends:
            self.error("class has no parent", node)
            return "ely_value_new_null()"
        parent = cls.extends
        parent_cls = self.classes_ast.get(parent)
        if not parent_cls:
            self.error(f"parent class {parent} not found", node)
            return "ely_value_new_null()"
        for m in parent_cls.all_methods:
            if m.name == node.method:
                args_code = [self.gen_expression(a) for a in node.arguments]
                args_code.insert(0, 'self')
                return f"{parent}_{m.name}({', '.join(args_code)})"
        self.error(f"Method {node.method} not found in parent {parent}", node)
        return "ely_value_new_null()"
    
    def _gen_expr_rooted(self, expr: Expression) -> str:
        code = self.gen_expression(expr)
        if isinstance(expr, Identifier):
            return code
        tmp = f"__tmp_{self.temp_counter}"
        self.temp_counter += 1
        self.emit_to_main(f"ely_value* {tmp} = {code};")
        self.emit_to_main(f"gc_add_root((void**)&{tmp});")
        return tmp

    def _ns_prefix(self) -> str:
        return self.current_namespace + "_" if self.current_namespace else ""

    def _gen_interface_vtable(self, iface: InterfaceDeclaration):
        name = iface.name
        vname = f"{name}_vtable"
        self.emit(f"struct {vname} {{")
        for m in iface.methods:
            ret = self._type_to_c(m.return_type or 'void', for_signature=True)
            params = ', '.join([f"{self._type_to_c(p.type, for_signature=True, is_param=True)}" for p in m.parameters])
            self.emit(f"    {ret} (*{m.name})(ely_value* self{', ' if params else ''}{params});")
        self.emit("};")

    def _gen_class_info(self, cls: ClassDeclaration):
        name = cls.name
        ns = self._ns_prefix()
        fields = [f.name for f in cls.fields if f.modifier != 'static']
        types = [f.type for f in cls.fields if f.modifier != 'static']
        self.emit(f"static const char* {ns}{name}_field_names[] = {{ {', '.join(f'"{f}"' for f in fields)} }};")
        self.emit(f"static const char* {ns}{name}_field_types[] = {{ {', '.join(f'"{t}"' for t in types)} }};")
        self.emit(f"static ely_class_info {ns}{name}_class_info = {{ \"{name}\", {len(fields)}, {ns}{name}_field_names, {ns}{name}_field_types }};")

    def _emit_global_init(self):
        self.code.append("static void _global_init(void);")
        has_init = bool(self.global_vars_to_init)
        if not has_init:
            for cls in self.classes_ast.values():
                if cls.static_fields:
                    has_init = True
                    break
        if has_init:
            self._create_global_init()
        else:
            self.code.append("static void _global_init(void) {}")

    def _gen_inherited_stub(self, cls: ClassDeclaration, method: MethodDeclaration):
        """Генерирует функцию-заглушку для метода, унаследованного от родителя."""
        name = cls.name
        parent = cls.extends
        ret = self._type_to_c(method.return_type or 'void', for_signature=True)
        params = ', '.join([f"{self._type_to_c(p.type, for_signature=True, is_param=True)} {p.name}" for p in method.parameters])
        full_params = f"struct {name}* self"
        if params:
            full_params += ", " + params
        
        self.emit(f"{ret} {name}_{method.name}({full_params}) {{")
        self.indent += 1
        # Вызов метода родителя с преобразованием self
        parent_func = f"{parent}_{method.name}"
        cast = f"(struct {parent}*)&self->__parent"
        call_args = ', '.join([f"{p.name}" for p in method.parameters])
        if call_args:
            call = f"{parent_func}({cast}, {call_args})"
        else:
            call = f"{parent_func}({cast})"
        if ret == 'void':
            self.emit(f"{call};")
        else:
            self.emit(f"return {call};")
        self.indent -= 1
        self.emit("}")

    def _collect_constructor_params(self, cls: ClassDeclaration) -> List[Parameter]:
        """Возвращает список параметров конструктора, начиная с родительских wait‑полей (super‑аргументов)."""
        params = []
        # Если есть extends и были переданы super_args, они соответствуют wait‑полям родителя
        if cls.extends and cls.extends in self.classes_ast:
            parent = self.classes_ast[cls.extends]
            # Берём wait‑поля родителя, если они есть
            if cls.super_args:
                for f in parent.wait_fields:
                    params.append(Parameter(type=f.type, name=f.name))
        # Свои wait‑поля
        for f in cls.wait_fields:
            params.append(Parameter(type=f.type, name=f.name))
        return params

    def _convert_to_c_type_expr(self, expr_code: str, target_c_type: str) -> str:
        # Оптимизация 1.1: если expr_code уже является ely_value_new_*(raw),
        # извлекаем raw напрямую, избегая лишней распаковки
        if target_c_type == 'char*':
            unwrapped = self._unwrap_primitive(expr_code, 'str')
            if unwrapped != expr_code:
                return unwrapped
            return f"ely_value_to_string({expr_code})"
        if target_c_type in ('int', 'long long', 'unsigned int', 'unsigned long long', 'signed char', 'unsigned char'):
            unwrapped = self._unwrap_primitive(expr_code, 'int')
            if unwrapped != expr_code:
                return unwrapped
            return f"ely_value_as_int({expr_code})"
        if target_c_type in ('float', 'double'):
            unwrapped = self._unwrap_primitive(expr_code, 'double')
            if unwrapped != expr_code:
                return unwrapped
            return f"ely_value_as_double({expr_code})"
        return expr_code

    def _forward_declare_static(self, cls: ClassDeclaration, method: MethodDeclaration):
        """Forward-объявление для статического метода (нет self)."""
        full_name = f"{self._method_full_name(method.name)}"
        ret_type_c = self._type_to_c(method.return_type or 'void', for_signature=True)
        params = ', '.join([f"{self._type_to_c(p.type, for_signature=True, is_param=True)} {p.name}" for p in method.parameters])
        self.code.append(f"{ret_type_c} {full_name}({params});")

    def _gen_static_method(self, cls: ClassDeclaration, method: MethodDeclaration):
        """Генерирует тело статического метода."""
        full_name = f"{self._method_full_name(method.name)}"
        ret_type_c = self._type_to_c(method.return_type or 'void', for_signature=True)
        params = ', '.join([f"{self._type_to_c(p.type, for_signature=True, is_param=True)} {p.name}" for p in method.parameters])
        param_str = params

        old_main = self.main_code
        self.main_code = []
        self.indent = 0
        self.inside_func = True
        self.func_name = full_name
        old_function = self.current_function
        self.current_function = full_name
        self.func_return_type = method.return_type or 'void'

        self.emit_to_main(f"{ret_type_c} {full_name}({param_str}) {{")
        self.indent += 1
        self._push_scope()
        # Параметры – в var_types
        for p in method.parameters:
            self.var_types[p.name] = p.type
            if self._type_to_c(p.type, is_param=True) == 'ely_value*':
                self.emit_to_main(f"gc_add_root((void**)&{p.name});")
            if self.scope_roots:
                self.scope_roots[-1].append(p.name)
        # Тело
        body_stmts = self._hoist_nested_functions(method.body)
        for stmt in body_stmts:
            self.gen_statement(stmt)
        self._pop_scope()
        self.indent -= 1
        self.emit_to_main("}")
        self.inside_func = False
        self.current_function = old_function
        old_main.extend(self.main_code)
        self.main_code = old_main

    def _promote_to_elyvalue(self, expr_code: str, ely_type: str) -> str:
        if ely_type == 'str':
            return f"ely_value_new_string({expr_code})"
        if ely_type in ('int', 'uint', 'more', 'umore', 'byte', 'ubyte'):
            return f"ely_value_new_int({expr_code})"
        if ely_type in ('flt', 'double'):
            return f"ely_value_new_double({expr_code})"
        if ely_type == 'bool':
            return f"ely_value_new_bool({expr_code})"
        return expr_code