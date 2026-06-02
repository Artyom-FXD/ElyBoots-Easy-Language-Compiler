import sys, os
from typing import List, Optional, Any, Dict
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from parser import *
from codegen.utils_codegen import CodeGenUtils, ExprCode

class FuncCodeGen(CodeGenUtils):
    """Functions Generation. Second layer."""

    # Специализированные функции для print (без перевода строки)
    _PRINT_MAP = {
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

    # Специализированные функции для println (с переводом строки)
    _PRINTLN_MAP = {
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

    def __init__(self, debug=False, is_module=False):
        super().__init__(debug, is_module)
        self.current_function: Optional[str] = None
        self.current_function_is_method: bool = False
        self.func_return_type: Optional[str] = None
        self.interfaces_ast: Dict[str, InterfaceDeclaration] = {}

    # -------------------------------------------------------------------
    # Генерация выражений
    # -------------------------------------------------------------------
    def gen_expression(self, expr: Expression) -> ExprCode:
        if isinstance(expr, Literal):
            return self._gen_literal(expr)
        if isinstance(expr, Identifier):
            return self._gen_identifier(expr)
        if isinstance(expr, BinaryOp):
            return self._gen_binary_op(expr)
        if isinstance(expr, UnaryOp):
            return self._gen_unary_op(expr)
        if isinstance(expr, Call):
            return self._gen_call(expr)
        if isinstance(expr, MemberAccess):
            return self._gen_member_access(expr)
        if isinstance(expr, Assignment):
            return self._gen_assignment(expr)
        if isinstance(expr, ReturnStatement):
            return self._gen_return(expr)
        if isinstance(expr, VariableDeclaration):
            return self._gen_local_variable(expr)
        if isinstance(expr, Conditional):
            return self._gen_conditional(expr)
        if isinstance(expr, FString):
            return self._gen_fstring(expr)
        if isinstance(expr, ArrayLiteral):
            return self._gen_array_literal(expr)
        if isinstance(expr, DictLiteral):
            return self._gen_dict_literal(expr)
        if isinstance(expr, IndexExpression):
            return self._gen_index_expression(expr)
        if isinstance(expr, Literal) and expr.value is None:
            return ExprCode("ely_value_new_null()", "ely_value*", "any")
        if isinstance(expr, TypeOfExpression):
            arg = self.gen_expression(expr.argument)
            arg_ely = self.ensure_type(arg, 'ely_value*')
            return ExprCode(f"ely_typeof({arg_ely})", "char*", "str")
        if isinstance(expr, FieldsExpression):
            arg = self.gen_expression(expr.argument)
            arg_ely = self.ensure_type(arg, 'ely_value*')
            return ExprCode(f"ely_value_get_fields({arg_ely})", "ely_value*", "arr<str>")
        if isinstance(expr, MethodsExpression):
            arg = self.gen_expression(expr.argument)
            arg_ely = self.ensure_type(arg, 'ely_value*')
            return ExprCode(f"ely_value_get_methods({arg_ely})", "ely_value*", "arr<str>")
        if isinstance(expr, AwaitExpression):
            arg = self.gen_expression(expr.expression)
            # _gen_call уже добавляет .get() для асинхронных вызовов
            return ExprCode(f"{arg.code}", arg.raw_type, arg.ely_type)
        self.error(f"Unknown expression type: {type(expr).__name__}", expr)
        return ExprCode("ely_value_new_null()", "ely_value*", "any")

    # -------------------------------------------------------------------
    # Literal — всегда ely_value*
    # -------------------------------------------------------------------
    def _gen_literal(self, node: Literal) -> ExprCode:
        v = node.value
        if isinstance(v, bool):
            return ExprCode(f"ely_value_new_bool({1 if v else 0})", "ely_value*", "bool")
        if isinstance(v, int):
            return ExprCode(f"ely_value_new_int({v})", "ely_value*", "int")
        if isinstance(v, float):
            return ExprCode(f"ely_value_new_double({v})", "ely_value*", "flt")
        if isinstance(v, str):
            escaped = v.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\t', '\\t')
            return ExprCode(f'ely_value_new_string("{escaped}")', "ely_value*", "str")
        return ExprCode("ely_value_new_null()", "ely_value*", "any")

    # -------------------------------------------------------------------
    # Identifier — НЕ оборачиваем native переменные
    # -------------------------------------------------------------------
    def _gen_identifier(self, node: Identifier) -> ExprCode:
        name = node.name

        # self → this (указатель на класс)
        if name == 'self' and self.current_class_name:
            return ExprCode("this", f"{self.current_class_name}*", self.current_class_name)

        # Имя класса
        if name in self.classes_ast:
            return ExprCode(name, f"{name}*", name)

        # Параметры / локальные переменные
        if name in self.var_types:
            t = self.var_types[name]
            raw = self.type_to_cpp(t)
            return ExprCode(name, raw, t)

        # Глобальные переменные
        if name in self.global_types:
            t = self.global_types[name]
            raw = self.type_to_cpp(t)
            return ExprCode(name, raw, t)

        # Внешние области видимости
        for scope in reversed(self.scopes):
            if name in scope:
                t = scope[name]
                raw = self.type_to_cpp(t)
                return ExprCode(name, raw, t)

        # Поля и статические члены текущего класса
        if self.current_class_name:
            cls = self.classes_ast.get(self.current_class_name)
            if cls:
                for sf in cls.static_fields:
                    if sf.name == name:
                        return ExprCode(f"{self.current_class_name}::{sf.name}", "ely_value*", sf.type)
                for sm in cls.static_methods:
                    if sm.name == name:
                        return ExprCode(f"{self.current_class_name}::{sm.name}", "", "")

                # Поля экземпляра — возвращаем как есть (native)
                if self._is_field_in_hierarchy(cls, name):
                    field_type = self._get_field_type_in_hierarchy(cls, name)
                    raw = self.type_to_cpp(field_type, is_field=True)
                    return ExprCode(f"this->{name}", raw, field_type)

        # Импортированные пространства имён — это runtime-объект
        if name in self.imported_namespaces:
            return ExprCode(name, "ely_value*", "any")

        # auto-created GC root (any, ely_value*)
        self.ensure_identifier(name, node.line, node.col)
        return ExprCode(name, "ely_value*", "any")

    def _get_field_type_in_hierarchy(self, cls: ClassDeclaration, field: str) -> Optional[str]:
        for f in cls.fields:
            if f.name == field:
                return f.type
        if cls.extends and cls.extends in self.classes_ast:
            return self._get_field_type_in_hierarchy(self.classes_ast[cls.extends], field)
        return None

    # -------------------------------------------------------------------
    # Присваивание
    # -------------------------------------------------------------------
    def _gen_assignment(self, node: Assignment) -> ExprCode:
        # ---- Присваивание в индекс ----
        if isinstance(node.target, IndexExpression):
            target = self.gen_expression(node.target.target)
            index = self.gen_expression(node.target.index)
            index = self.ensure_type(index, 'ely_value*')
            val = self.ensure_type(self.gen_expression(node.value), 'ely_value*')
            return ExprCode(f"ely_value_set_index({target}, {index}, {val})", "void", "void")

        # ---- Прямое присваивание полю / переменной ----
        if isinstance(node.target, Identifier):
            target_name = node.target.name
            ttype = None
            if target_name in self.var_types:
                ttype = self.var_types[target_name]
            else:
                for scope in reversed(self.scopes):
                    if target_name in scope:
                        ttype = scope[target_name]
                        break

            if ttype is None and self.current_class_name:
                cls = self.classes_ast.get(self.current_class_name)
                if cls:
                    for sf in cls.static_fields:
                        if sf.name == target_name:
                            ttype = sf.type
                            break

            if ttype is not None:
                resolved = self.resolve_type_alias(ttype)

                if node.operator != '=':
                    binary = BinaryOp(node.line, node.col, node.target, node.operator[:-1], node.value)
                    val = self.gen_expression(binary)
                else:
                    val = self.gen_expression(node.value)

                # Статическое поле
                if self.current_class_name:
                    cls = self.classes_ast.get(self.current_class_name)
                    if cls and any(sf.name == target_name for sf in cls.static_fields):
                        val = self.ensure_type(val, 'ely_value*')
                        return ExprCode(f"{self.current_class_name}::{target_name} = {val}", "ely_value*", resolved)

                # Поле экземпляра
                if self.current_class_name:
                    cls = self.classes_ast.get(self.current_class_name)
                    if cls and self._is_field_in_hierarchy(cls, target_name):
                        field_raw = self.type_to_cpp(resolved, is_field=True)
                        if field_raw == 'char*':
                            val = self.ensure_type(val, 'char*')
                            val = ExprCode(f"ely_str_dup({val.code})", 'char*', resolved)
                        else:
                            val = self.ensure_type(val, field_raw)
                        return ExprCode(f"this->{target_name} = {val}", field_raw, resolved)

                # Локальная переменная
                target_raw = self.type_to_cpp(resolved)
                if target_raw == 'char*':
                    val = self.ensure_type(val, 'char*')
                    val = ExprCode(f"ely_str_dup({val.code})", 'char*', resolved)
                else:
                    val = self.ensure_type(val, target_raw)
                return ExprCode(f"{target_name} = {val}", target_raw, resolved)

        # ---- Присваивание MemberAccess ----
        if isinstance(node.target, MemberAccess):
            obj = self.gen_expression(node.target.object)
            obj_type = obj.ely_type if obj.ely_type != 'any' else self.get_expression_type(node.target.object)
            member = node.target.member

            if obj_type in self.classes_ast:
                cls = self.classes_ast[obj_type]

                # Статические поля
                for sf in cls.static_fields:
                    if sf.name == member:
                        if node.operator != '=':
                            binary = BinaryOp(node.line, node.col, node.target, node.operator[:-1], node.value)
                            val = self.gen_expression(binary)
                        else:
                            val = self.gen_expression(node.value)
                        val = self.ensure_type(val, 'ely_value*')
                        return ExprCode(f"{obj_type}::{sf.name} = {val}", "ely_value*", sf.type)

                # Свойства с сеттером
                for prop in cls.properties:
                    if prop.name == member and prop.setter:
                        param_type = prop.type
                        param_raw = self.type_to_cpp(param_type, is_param=True)
                        if node.operator != '=':
                            binary = BinaryOp(node.line, node.col, node.target, node.operator[:-1], node.value)
                            val = self.gen_expression(binary)
                        else:
                            val = self.gen_expression(node.value)
                        val = self.ensure_type(val, param_raw)
                        return ExprCode(f"{obj}->{prop.setter.name}({val})", param_raw, param_type)

                # Сеттер set<Name>
                setter_name = f"set{member[0].upper()}{member[1:]}"
                for m in cls.all_methods:
                    if m.name == setter_name and len(m.parameters) == 1:
                        param_type = m.parameters[0].type
                        param_raw = self.type_to_cpp(param_type, is_param=True)
                        if node.operator != '=':
                            binary = BinaryOp(node.line, node.col, node.target, node.operator[:-1], node.value)
                            val = self.gen_expression(binary)
                        else:
                            val = self.gen_expression(node.value)
                        val = self.ensure_type(val, param_raw)
                        return ExprCode(f"{obj}->{setter_name}({val})", param_raw, param_type)

                # Обычные поля экземпляра
                if self._is_field_in_hierarchy(cls, member):
                    field_type = self._get_field_type_in_hierarchy(cls, member)
                    field_raw = self.type_to_cpp(field_type, is_field=True)
                    if node.operator != '=':
                        binary = BinaryOp(node.line, node.col, node.target, node.operator[:-1], node.value)
                        val = self.gen_expression(binary)
                    else:
                        val = self.gen_expression(node.value)
                    if field_raw == 'char*':
                        val = self.ensure_type(val, 'char*')
                        val = ExprCode(f"ely_str_dup({val.code})", 'char*', field_type)
                    else:
                        val = self.ensure_type(val, field_raw)
                    return ExprCode(f"{obj}->{member} = {val}", field_raw, field_type)

            # Динамический доступ для any/неизвестного
            if node.operator != '=':
                binary = BinaryOp(node.line, node.col, node.target, node.operator[:-1], node.value)
                val = self.gen_expression(binary)
            else:
                val = self.gen_expression(node.value)
            val = self.ensure_type(val, 'ely_value*')
            return ExprCode(f"ely_value_set_key({obj}, \"{member}\", {val})", "void", "void")

        # ---- Общий случай (например, присваивание результату вызова) ----
        target = self.gen_expression(node.target)
        if node.operator != '=':
            binary = BinaryOp(node.line, node.col, node.target, node.operator[:-1], node.value)
            val = self.gen_expression(binary)
        else:
            val = self.gen_expression(node.value)
        return ExprCode(f"{target} = {val}", target.raw_type, target.ely_type)

    def _gen_member_access(self, node: MemberAccess) -> ExprCode:
        obj = self.gen_expression(node.object)
        obj_type = obj.ely_type if obj.ely_type != 'any' else self.get_expression_type(node.object)
        member = node.member

        # Пространства имён — obj.code это имя неймспейса
        ns_name = obj.code
        if ns_name in self.namespaces:
            ns_members = self.namespaces[ns_name]
            if member in ns_members:
                full_name = ns_members[member]
                # Для пространств имён возвращаем специальный код, 
                # который будет обрабатываться в _gen_method_call
                if full_name in self.classes_ast:
                    return ExprCode(f"{ns_name}_{member}", f"{full_name}*", f"namespace_{full_name}")
                return ExprCode(full_name, "ely_value*", "any")
            else:
                self.error(f"Namespace '{ns_name}' has no member '{member}'", node)
                return ExprCode("ely_value_new_null()", "ely_value*", "any")

        # Классы
        if obj_type in self.classes_ast:
            cls = self.classes_ast[obj_type]
            # Статические поля
            for sf in cls.static_fields:
                if sf.name == member:
                    return ExprCode(f"{obj_type}::{sf.name}", "ely_value*", sf.type)
            # Статические методы
            for sm in cls.static_methods:
                if sm.name == member:
                    return ExprCode(f"{obj_type}::{sm.name}", "", "")
            # Поля экземпляра
            if self._is_field_in_hierarchy(cls, member):
                field_type = self._get_field_type_in_hierarchy(cls, member)
                raw = self.type_to_cpp(field_type, is_field=True)
                return ExprCode(f"{obj}->{member}", raw, field_type)
            # Свойство через геттер
            getter_name = f"get{member[0].upper()}{member[1:]}"
            search_cls = cls
            found_getter = None
            while search_cls:
                for m in search_cls.all_methods:
                    if m.name == getter_name and len(m.parameters) == 0:
                        found_getter = m
                        break
                if found_getter:
                    break
                if search_cls.extends and search_cls.extends in self.classes_ast:
                    search_cls = self.classes_ast[search_cls.extends]
                else:
                    search_cls = None
            if found_getter:
                ret_raw = self.type_to_cpp(found_getter.return_type or 'any', for_signature=True)
                return ExprCode(f"({obj}->{getter_name}())", ret_raw, found_getter.return_type or 'any')
            self.error(f"Class '{obj_type}' has no member '{member}'", node)
            return ExprCode("ely_value_new_null()", "ely_value*", "any")

        # Для остальных – динамический доступ через ely_value
        return ExprCode(f"ely_value_get_key({obj}, \"{member}\")", "ely_value*", "any")

    def _is_field_in_hierarchy(self, cls: ClassDeclaration, field: str) -> bool:
        if cls is None:
            return False
        if field in [f.name for f in cls.fields]:
            return True
        if cls.extends and cls.extends in self.classes_ast:
            return self._is_field_in_hierarchy(self.classes_ast[cls.extends], field)
        return False

    # -------------------------------------------------------------------
    # Вызовы функций и методов
    # -------------------------------------------------------------------
    def _gen_call(self, node: Call) -> ExprCode:
        if isinstance(node.callee, MemberAccess):
            return self._gen_method_call(node)
        if isinstance(node.callee, AwaitExpression):
            arg = self.gen_expression(node.callee.expression)
            return ExprCode(f"({arg}).get()", "ely_value*", arg.ely_type)
        if not isinstance(node.callee, Identifier):
            self.error("Call target must be identifier", node)
            return ExprCode("ely_value_new_null()", "ely_value*", "any")

        func_name = node.callee.name

        # Конструктор
        if func_name.endswith('_constructor'):
            return self._gen_constructor_call(node, func_name)

        # Прямой вызов конструктора класса (например, File("path"))
        if func_name in self.classes_ast:
            return self._gen_constructor_call(node, func_name + '_constructor')

        # Старые статические методы (ClassName_method)
        if '_' in func_name and not func_name.startswith('__'):
            parts = func_name.split('_', 1)
            if parts[0] in self.classes_ast:
                cls = self.classes_ast[parts[0]]
                for sm in cls.static_methods:
                    if sm.name == parts[1]:
                        args = [self.gen_expression(a) for a in node.arguments]
                        for i, arg in enumerate(args):
                            if i < len(sm.parameters):
                                expected = self.type_to_cpp(sm.parameters[i].type, is_param=True)
                                args[i] = self.ensure_type(arg, expected)
                        ret_raw = self.type_to_cpp(sm.return_type or 'any', for_signature=True)
                        return ExprCode(f"{parts[0]}::{sm.name}({', '.join(a.code for a in args)})", ret_raw, sm.return_type or 'any')
                self.error(f"Static method '{func_name}' not found in class '{parts[0]}'", node)
                return ExprCode("ely_value_new_null()", "ely_value*", "any")

        # Оригинальные функции
        if func_name in self.original_functions:
            func_node = self.original_functions[func_name]
            ret_ely = func_node.return_type or 'any'
            is_method = getattr(self, 'current_function_is_method', False)

            if func_node.is_async:
                args = []
                for i, arg in enumerate(node.arguments):
                    code = self.gen_expression(arg)
                    if i < len(func_node.parameters):
                        expected_c = self.type_to_cpp(func_node.parameters[i].type, is_param=True)
                        code = self.ensure_type(code, expected_c)
                    args.append(code.code)
                args_code = ', '.join(args)
                call_expr = f"{func_name}({args_code})"
                # run() возвращает Task<T>, .get() возвращает T (нативный тип)
                # Но мы должны обернуть его в ely_value* для консистентности
                result_expr = f"ElyEventLoop::instance().run([&]() {{ return {call_expr}; }}).get()"
                raw_type = self.type_to_cpp(ret_ely)
                if raw_type in ('char*', 'int', 'long long', 'double', 'float'):
                    # Оборачиваем нативный результат в ely_value*
                    if ret_ely == 'str':
                        wrapper = "ely_value_new_string"
                    elif ret_ely in ('int','uint','more','umore','byte','ubyte'):
                        wrapper = "ely_value_new_int"
                    elif ret_ely in ('flt', 'double'):
                        wrapper = "ely_value_new_double"
                    elif ret_ely == 'bool':
                        wrapper = "ely_value_new_bool"
                    else:
                        wrapper = "ely_value_new_object"
                    result_expr = f"{wrapper}({result_expr})"
                # Асинхронные функции всегда возвращают ely_value*
                return ExprCode(result_expr, "ely_value*", ret_ely)
            if func_node.type_params:
                return self._gen_generic_call(node, func_node)
            args = []
            for i, arg in enumerate(node.arguments):
                code = self.gen_expression(arg)
                if i < len(func_node.parameters):
                    expected_c = self.type_to_cpp(func_node.parameters[i].type, is_param=True)
                    code = self.ensure_type(code, expected_c)
                args.append(code.code)
            # Определяем raw_type результата
            if is_method:
                raw = "ely_value*"
            elif ret_ely == 'str':
                raw = "char*"
            elif ret_ely in ('int','uint','more','umore','byte','ubyte','bool','flt','double'):
                raw = self.type_to_cpp(ret_ely)
            else:
                raw = "ely_value*"
            return ExprCode(f"{func_name}({', '.join(args)})", raw, ret_ely)

        # fields / methods
        if func_name == 'fields':
            if len(node.arguments) != 1:
                self.error("fields() expects 1 argument", node)
                return ExprCode("ely_value_new_null()", "ely_value*", "any")
            arg = self.gen_expression(node.arguments[0])
            return ExprCode(f"ely_value_get_fields({arg})", "ely_value*", "arr<str>")
        if func_name == 'methods':
            if len(node.arguments) != 1:
                self.error("methods() expects 1 argument", node)
                return ExprCode("ely_value_new_null()", "ely_value*", "any")
            arg = self.gen_expression(node.arguments[0])
            return ExprCode(f"ely_value_get_methods({arg})", "ely_value*", "arr<str>")

        return self._gen_builtin_or_extern_call(node, func_name)

    # Маппинг Ely-типов (как в builtin_signatures) → реальный C++ тип
    _ELY_TO_C_PARAM = {
        'str': 'char*', 'int': 'int', 'uint': 'unsigned int',
        'more': 'long long', 'umore': 'unsigned long long',
        'byte': 'signed char', 'ubyte': 'unsigned char',
        'flt': 'float', 'double': 'double', 'bool': 'int',
        'char': 'char', 'void': 'void',
        'size_t': 'size_t', 'char*': 'char*', 'const char*': 'char*',
        'long long': 'long long', 'unsigned int': 'unsigned int',
        'unsigned long long': 'unsigned long long',
        'float': 'float', 'signed char': 'signed char',
        'unsigned char': 'unsigned char',
        'ely_value*': 'ely_value*', 'void*': 'void*', 'any': 'ely_value*',
    }
    _ELY_TO_C_RET = {
        'str': 'char*', 'int': 'long long', 'uint': 'unsigned int',
        'more': 'long long', 'umore': 'unsigned long long',
        'byte': 'signed char', 'ubyte': 'unsigned char',
        'flt': 'float', 'double': 'double', 'bool': 'int',
        'char': 'char', 'void': 'void',
        'char*': 'char*', 'size_t': 'size_t', 'long long': 'long long',
        'unsigned int': 'unsigned int', 'float': 'float',
        'ely_value*': 'ely_value*', 'void*': 'void*',
    }

    def _gen_builtin_or_extern_call(self, node: Call, func_name: str) -> ExprCode:
        # ---- Builtin ----
        if func_name in self.builtin_signatures:
            c_name, ret_ely, param_ctypes = self.builtin_signatures[func_name]

            # Специализированные print/println
            if func_name in ('print', 'println', 'printOld') and len(node.arguments) == 1:
                arg_type = self.get_expression_type(node.arguments[0])
                print_map = self._PRINTLN_MAP if func_name != 'printOld' else self._PRINT_MAP
                if func_name == 'print':
                    print_map = self._PRINT_MAP
                if arg_type in print_map:
                    spec_func = print_map[arg_type]
                    arg_code = self.gen_expression(node.arguments[0])
                    native_raw = self.type_to_cpp(arg_type)
                    if native_raw in ('ely_value*',):
                        if arg_type == 'str':
                            arg_native = ExprCode(f"({arg_code.code})->u.string_val", 'char*', 'str')
                        else:
                            arg_native = arg_code
                    else:
                        arg_native = self.ensure_type(arg_code, native_raw)
                    return ExprCode(f"{spec_func}({arg_native})", "void", "void")

            args = []
            for i, arg in enumerate(node.arguments):
                code = self.gen_expression(arg)
                if i < len(param_ctypes):
                    ely_param = param_ctypes[i]
                    c_type = self._ELY_TO_C_PARAM.get(ely_param, 'ely_value*')
                    code = self.ensure_type(code, c_type)
                args.append(code.code)
            call_expr = f"{c_name}({', '.join(args)})"

            # Вычисляем правильный C++ raw_type для возврата
            c_ret = self._ELY_TO_C_RET.get(ret_ely, 'ely_value*')
            return ExprCode(call_expr, c_ret, ret_ely)

        # ---- Extern ----
        if func_name in self.extern_functions:
            ext = self.extern_functions[func_name]
            ret = ext.return_type or 'void'
            args = []
            for i, arg in enumerate(node.arguments):
                code = self.gen_expression(arg)
                if i < len(ext.parameters):
                    raw_type = ext.parameters[i].type.strip()
                    if raw_type in ('char*', 'const char*', 'char *', 'const char *'):
                        c_type = 'char*'
                    elif raw_type in ('int', 'long', 'long long', 'unsigned', 'unsigned int', 'size_t'):
                        c_type = 'long long'
                    elif raw_type in ('float', 'double'):
                        c_type = 'double'
                    elif raw_type == 'bool':
                        c_type = 'int'
                    else:
                        c_type = 'ely_value*'
                    code = self.ensure_type(code, c_type)
                args.append(code.code)
            call_expr = f"{func_name}({', '.join(args)})"
            if ret == 'char*' or ret == 'const char*':
                ely_ret = 'str'
            elif ret in ('int', 'long', 'long long', 'unsigned', 'unsigned int', 'size_t'):
                ely_ret = 'int'
            elif ret in ('float', 'double'):
                ely_ret = 'double'
            elif ret == 'bool':
                ely_ret = 'bool'
            else:
                ely_ret = 'any'
            is_method = getattr(self, 'current_function_is_method', False)
            if is_method:
                return self._wrap_result(call_expr, ely_ret)
            else:
                if ely_ret == 'str':
                    return ExprCode(call_expr, "char*", "str")
                elif ely_ret in ('int','uint','more','umore','byte','ubyte','bool','flt','double'):
                    return ExprCode(call_expr, self.type_to_cpp(ely_ret), ely_ret)
                else:
                    return ExprCode(call_expr, "ely_value*", ely_ret)

        # Методы текущего класса
        if self.current_class_name:
            cls = self.classes_ast.get(self.current_class_name)
            if cls:
                for m in cls.all_methods:
                    if m.name == func_name:
                        args = [self.gen_expression(a) for a in node.arguments]
                        for i, arg in enumerate(node.arguments):
                            if i < len(m.parameters):
                                expected = self.type_to_cpp(m.parameters[i].type, is_param=True)
                                args[i] = self.ensure_type(args[i], expected)
                        ret_raw = self.type_to_cpp(m.return_type or 'any', for_signature=True)
                        return ExprCode(f"this->{func_name}({', '.join(a.code for a in args)})", ret_raw, m.return_type or 'any')

        self.error(f"Unknown function '{func_name}'", node)
        return ExprCode("ely_value_new_null()", "ely_value*", "any")

    def _gen_method_call(self, node: Call) -> ExprCode:
        obj = node.callee.object
        method = node.callee.member
        obj_code = self.gen_expression(obj)
        obj_type = obj_code.ely_type if obj_code.ely_type != 'any' else self.get_expression_type(obj)

        # Обработка вызовов методов из пространств имён
        if obj_type.startswith('namespace_'):
            # Вызываем статический метод напрямую: ClassName::method(...)
            namespace_class = obj_type[len('namespace_'):]
            if namespace_class in self.classes_ast:
                cls = self.classes_ast[namespace_class]
                for sm in cls.static_methods:
                    if sm.name == method:
                        args = [self.gen_expression(a) for a in node.arguments]
                        for i, arg in enumerate(node.arguments):
                            if i < len(sm.parameters):
                                expected = self.type_to_cpp(sm.parameters[i].type, is_param=True)
                                args[i] = self.ensure_type(args[i], expected)
                        ret_raw = self.type_to_cpp(sm.return_type or 'any', for_signature=True)
                        return ExprCode(f"{namespace_class}::{sm.name}({', '.join(a.code for a in args)})", ret_raw, sm.return_type or 'any')
            self.error(f"Namespace class '{namespace_class}' not found or has no static method '{method}'", node)
            return ExprCode("ely_value_new_null()", "ely_value*", "any")

        if obj_type in self.classes_ast:
            cls = self.classes_ast[obj_type]
            # Статические методы
            for sm in cls.static_methods:
                if sm.name == method:
                    args = [self.gen_expression(a) for a in node.arguments]
                    for i, arg in enumerate(node.arguments):
                        if i < len(sm.parameters):
                            expected = self.type_to_cpp(sm.parameters[i].type, is_param=True)
                            args[i] = self.ensure_type(args[i], expected)
                    ret_raw = self.type_to_cpp(sm.return_type or 'any', for_signature=True)
                    return ExprCode(f"{obj_type}::{sm.name}({', '.join(a.code for a in args)})", ret_raw, sm.return_type or 'any')

        # Интерфейсы – виртуальный вызов
        if obj_type in self.interfaces_ast:
            iface = self.interfaces_ast[obj_type]
            method_exists = any(m.name == method for m in iface.methods)
            if not method_exists:
                self.error(f"Interface '{obj_type}' has no method '{method}'", node)
                return ExprCode("ely_value_new_null()", "ely_value*", "any")
            args = [self.gen_expression(a) for a in node.arguments]
            return ExprCode(f"({obj_code}->{method}({', '.join(a.code for a in args)}))", "ely_value*", "any")

        # Встроенные методы для конкретных типов
        if obj_type.startswith('arr<'):
            return self._gen_array_method(obj_code, method, node.arguments)
        if obj_type.startswith('dict<'):
            return self._gen_dict_method(obj_code, method, node.arguments)
        if obj_type == 'str':
            return self._gen_str_method(obj_code, method, node.arguments)
        if obj_type in ('int','uint','more','umore','flt','double'):
            return self._gen_num_method(obj_code, method, obj_type)

        # Методы экземпляров классов
        if obj_type in self.classes_ast:
            cls = self.classes_ast[obj_type]
            method_node = None
            search_cls = cls
            while search_cls:
                for m in search_cls.all_methods:
                    if m.name == method:
                        method_node = m
                        break
                if method_node:
                    break
                if search_cls.extends and search_cls.extends in self.classes_ast:
                    search_cls = self.classes_ast[search_cls.extends]
                else:
                    search_cls = None
            if method_node:
                args = []
                for i, arg in enumerate(node.arguments):
                    code = self.gen_expression(arg)
                    if i < len(method_node.parameters):
                        expected = self.type_to_cpp(method_node.parameters[i].type, is_param=True)
                        code = self.ensure_type(code, expected)
                    args.append(code)
                ret_type = method_node.return_type or 'any'
                return ExprCode(f"({obj_code}->{method}({', '.join(a.code for a in args)}))", "ely_value*", ret_type)
            else:
                self.error(f"Class '{obj_type}' has no method '{method}'", node)
                return ExprCode("ely_value_new_null()", "ely_value*", "any")

        # Динамическая диспетчеризация для any/неизвестного типа
        args_code = [self.gen_expression(a) for a in node.arguments]
        for i, a in enumerate(args_code):
            args_code[i] = self.ensure_type(a, 'ely_value*')
        argc = len(args_code)
        if argc == 0:
            return ExprCode(f"ely_value_call_method({obj_code}, \"{method}\", NULL, 0)", "ely_value*", "any")
        arr_name = f"__args_{self.temp_counter}"
        self.temp_counter += 1
        self.emit_to_method(f"ely_value* {arr_name}[] = {{ {', '.join(a.code for a in args_code)} }};")
        return ExprCode(f"ely_value_call_method({obj_code}, \"{method}\", {arr_name}, {argc})", "ely_value*", "any")

    def _gen_constructor_call(self, node: Call, func_name: str) -> ExprCode:
        class_name = func_name[:-len('_constructor')]
        cls = self.classes_ast.get(class_name)
        if not cls:
            self.error(f"Unknown class {class_name}", node)
            return ExprCode("ely_value_new_null()", "ely_value*", "any")
        args = [self.gen_expression(a) for a in node.arguments]
        params = self.collect_constructor_params(cls)
        for i, param in enumerate(params):
            if i < len(args):
                args[i] = self.ensure_type(args[i], self.type_to_cpp(param.type, is_param=True))
        # new ClassName(...) возвращает ClassName*, не ely_value*
        # ensure_type / _wrap_to_ely позаботятся о приведении к ely_value* если нужно
        return ExprCode(f"(new {class_name}({', '.join(a.code for a in args)}))", f"{class_name}*", class_name)

    # -------------------------------------------------------------------
    # Арифметика и сравнения (двоичные и унарные)
    # -------------------------------------------------------------------

    @staticmethod
    def _fold_constants(node: BinaryOp) -> Optional[ExprCode]:
        """Свёртка констант: если оба операнда — Literal, вычислить на месте."""
        from parser import Literal
        if not isinstance(node.left, Literal) or not isinstance(node.right, Literal):
            return None
        lv, rv = node.left.value, node.right.value
        op = node.operator

        # Целочисленные операции
        if isinstance(lv, int) and isinstance(rv, int):
            if op == '+':  return ExprCode(f"ely_value_new_int({lv + rv})", "ely_value*", "int")
            if op == '-':  return ExprCode(f"ely_value_new_int({lv - rv})", "ely_value*", "int")
            if op == '*':  return ExprCode(f"ely_value_new_int({lv * rv})", "ely_value*", "int")
            if op == '/':  return ExprCode(f"ely_value_new_int({lv // rv})", "ely_value*", "int") if rv != 0 else None
            if op == '%':  return ExprCode(f"ely_value_new_int({lv % rv})", "ely_value*", "int") if rv != 0 else None
            if op == '==': return ExprCode(f"ely_value_new_bool({1 if lv == rv else 0})", "ely_value*", "bool")
            if op == '!=': return ExprCode(f"ely_value_new_bool({1 if lv != rv else 0})", "ely_value*", "bool")
            if op == '<':  return ExprCode(f"ely_value_new_bool({1 if lv < rv else 0})", "ely_value*", "bool")
            if op == '<=': return ExprCode(f"ely_value_new_bool({1 if lv <= rv else 0})", "ely_value*", "bool")
            if op == '>':  return ExprCode(f"ely_value_new_bool({1 if lv > rv else 0})", "ely_value*", "bool")
            if op == '>=': return ExprCode(f"ely_value_new_bool({1 if lv >= rv else 0})", "ely_value*", "bool")
        # с плавающей точкой
        if isinstance(lv, (int, float)) and isinstance(rv, (int, float)):
            lf, rf = float(lv), float(rv)
            if op == '+':  return ExprCode(f"ely_value_new_double({lf + rf})", "ely_value*", "flt")
            if op == '-':  return ExprCode(f"ely_value_new_double({lf - rf})", "ely_value*", "flt")
            if op == '*':  return ExprCode(f"ely_value_new_double({lf * rf})", "ely_value*", "flt")
            if op == '/':  return ExprCode(f"ely_value_new_double({lf / rf})", "ely_value*", "flt") if rf != 0.0 else None
            if op == '==': return ExprCode(f"ely_value_new_bool({1 if lf == rf else 0})", "ely_value*", "bool")
            if op == '!=': return ExprCode(f"ely_value_new_bool({1 if lf != rf else 0})", "ely_value*", "bool")
            if op == '<':  return ExprCode(f"ely_value_new_bool({1 if lf < rf else 0})", "ely_value*", "bool")
            if op == '<=': return ExprCode(f"ely_value_new_bool({1 if lf <= rf else 0})", "ely_value*", "bool")
            if op == '>':  return ExprCode(f"ely_value_new_bool({1 if lf > rf else 0})", "ely_value*", "bool")
            if op == '>=': return ExprCode(f"ely_value_new_bool({1 if lf >= rf else 0})", "ely_value*", "bool")
        # логические
        if isinstance(lv, bool) and isinstance(rv, bool):
            if op == '&&': return ExprCode(f"ely_value_new_bool({1 if lv and rv else 0})", "ely_value*", "bool")
            if op == '||': return ExprCode(f"ely_value_new_bool({1 if lv or rv else 0})", "ely_value*", "bool")
        return None

    def _gen_binary_op(self, node: BinaryOp) -> ExprCode:
        folded = self._fold_constants(node)
        if folded is not None:
            return folded

        left = self.gen_expression(node.left)
        right = self.gen_expression(node.right)
        op = node.operator
        left_type = self.get_expression_type(node.left)
        right_type = self.get_expression_type(node.right)

        # Операторные методы классов
        if left_type in self.classes_ast:
            ops = {'+':'__add','-':'__sub','*':'__mul','/':'__div','%':'__mod',
                '==':'__eq','!=':'__ne','<':'__lt','<=':'__le','>':'__gt','>=':'__ge'}
            method_name = ops.get(op)
            if method_name:
                cls = self.classes_ast[left_type]
                for m in cls.all_methods:
                    if m.name == method_name and len(m.parameters) >= 1:
                        expected = m.parameters[0].type
                        right = self.ensure_type(right, self.type_to_cpp(expected, is_param=True))
                        return ExprCode(f"({left}->{method_name}({right}))", "ely_value*", left_type)

        # Нативная арифметика для примитивных числовых типов
        num_types = {'int','uint','more','umore','byte','ubyte','flt','double','long long'}
        is_left_num = left_type in num_types
        is_right_num = right_type in num_types

        if is_left_num and is_right_num and op in '+-*/%':
            is_float_op = left_type in ('flt','double') or right_type in ('flt','double')
            target_native = 'double' if is_float_op else 'long long'
            left_native = self.ensure_type(left, target_native)
            right_native = self.ensure_type(right, target_native)
            raw_expr = f"({left_native.code} {op} {right_native.code})"
            if is_float_op:
                return ExprCode(raw_expr, "double", "flt")
            else:
                return ExprCode(raw_expr, "long long", "int")

        # Сравнения с числовыми типами
        if is_left_num and is_right_num and op in ('==','!=','<','>','<=','>='):
            target_native = 'double' if (left_type in ('flt','double') or right_type in ('flt','double')) else 'long long'
            left_native = self.ensure_type(left, target_native)
            right_native = self.ensure_type(right, target_native)
            raw_expr = f"({left_native.code} {op} {right_native.code})"
            return ExprCode(raw_expr, "int", "bool")

        # Логические &&/|| с bool
        if left_type == 'bool' and right_type == 'bool' and op in ('&&','||'):
            left_native = self.ensure_type(left, 'int')
            right_native = self.ensure_type(right, 'int')
            c_op = '&&' if op == '&&' else '||'
            raw_expr = f"({left_native.code} {c_op} {right_native.code})"
            return ExprCode(f"ely_value_new_bool({raw_expr})", "ely_value*", "bool")

        # Строковая конкатенация
        if op == '+' and (left_type == 'str' or right_type == 'str'):
            # Если хотя бы один операнд не str (напр. str + int), используем ely_value_add
            if left_type != 'str' or right_type != 'str':
                left_ely = self.ensure_type(left, 'ely_value*')
                right_ely = self.ensure_type(right, 'ely_value*')
                return ExprCode(f"ely_value_add({left_ely}, {right_ely})", "ely_value*", "str")
            # Чистая str + str конкатенация
            is_method = getattr(self, 'current_function_is_method', False)
            if is_method:
                left_ely = self.ensure_type(left, 'ely_value*')
                right_ely = self.ensure_type(right, 'ely_value*')
                return ExprCode(f"ely_value_add({left_ely}, {right_ely})", "ely_value*", "str")
            else:
                left_str = self.ensure_type(left, 'char*')
                right_str = self.ensure_type(right, 'char*')
                return ExprCode(f"ely_str_concat({left_str}, {right_str})", "char*", "str")

        op_map = {'+':'add','-':'sub','*':'mul','/':'div','%':'mod',
                '==':'eq','!=':'ne','<':'lt','<=':'le','>':'gt','>=':'ge',
                '&&':'and','||':'or'}

        left = self.ensure_type(left, 'ely_value*')
        right = self.ensure_type(right, 'ely_value*')
        func = f"ely_value_{op_map.get(op, op)}"
        return ExprCode(f"{func}({left}, {right})", "ely_value*", "any")

    def _gen_unary_op(self, node: UnaryOp) -> ExprCode:
        operand = self.gen_expression(node.operand)
        op = node.operator
        t = self.get_expression_type(node.operand)
        if op == '!':
            operand_ely = self.ensure_type(operand, 'ely_value*')
            return ExprCode(f"ely_value_not({operand_ely})", "ely_value*", "bool")
        if op == '-':
            operand_ely = self.ensure_type(operand, 'ely_value*')
            return ExprCode(f"ely_value_neg({operand_ely})", "ely_value*", t)
        if op == '&':
            return ExprCode(f"(&{operand.code})", f"{operand.raw_type}*", t)
        return ExprCode(f"{op}{operand}", operand.raw_type, t)

    # -------------------------------------------------------------------
    # Условный оператор
    # -------------------------------------------------------------------
    def _gen_conditional(self, node: Conditional) -> ExprCode:
        cond = self.ensure_type(self.gen_expression(node.condition), 'ely_value*')
        then_expr = self.ensure_type(self.gen_expression(node.then_expr), 'ely_value*')
        else_expr = self.ensure_type(self.gen_expression(node.else_expr), 'ely_value*')
        return ExprCode(f"((ely_value_as_bool({cond})) ? {then_expr} : {else_expr})", "ely_value*", "any")

    # -------------------------------------------------------------------
    # F-строки, массивы, словари, индексация
    # -------------------------------------------------------------------
    def _gen_fstring(self, node: FString) -> ExprCode:
        if not node.parts:
            return ExprCode('ely_value_new_string("")', "ely_value*", "str")
        result = None
        for part in node.parts:
            if isinstance(part, str):
                escaped = part.replace('"','\\"').replace('\n','\\n')
                part_expr = ExprCode(f'ely_value_new_string("{escaped}")', "ely_value*", "str")
            else:
                part_expr = self.ensure_type(self.gen_expression(part), 'ely_value*')
            if result is None:
                result = part_expr
            else:
                result = ExprCode(f'ely_value_add({result}, {part_expr})', "ely_value*", "str")
        return result

    def _gen_array_literal(self, node: ArrayLiteral) -> ExprCode:
        if not node.elements:
            return ExprCode("ely_value_new_array(arr_new())", "ely_value*", "arr<any>")
        elems = []
        for elem in node.elements:
            tmp = f"__tmp_ary_{self.temp_counter}"
            self.temp_counter += 1
            elem_code = self.ensure_type(self.gen_expression(elem), 'ely_value*')
            self.emit_to_method(f"ely_value* {tmp} = {elem_code};")
            elems.append(tmp)
        arr_var = f"__arr_{self.temp_counter}"
        self.temp_counter += 1
        self.emit_to_method(f"arr* {arr_var} = arr_new();")
        for e in elems:
            self.emit_to_method(f"arr_push({arr_var}, {e});")
        return ExprCode(f"ely_value_new_array({arr_var})", "ely_value*", "arr<any>")

    def _gen_dict_literal(self, node: DictLiteral) -> ExprCode:
        if not node.pairs:
            return ExprCode("ely_value_new_object(dict_new_str())", "ely_value*", "dict<str, any>")
        pairs = []
        for pair in node.pairs:
            key_tmp = f"__tmp_key_{self.temp_counter}"
            self.temp_counter += 1
            val_tmp = f"__tmp_val_{self.temp_counter}"
            self.temp_counter += 1
            key_code = self.ensure_type(self.gen_expression(pair.key), 'ely_value*')
            val_code = self.ensure_type(self.gen_expression(pair.value), 'ely_value*')
            self.emit_to_method(f"ely_value* {key_tmp} = {key_code};")
            self.emit_to_method(f"ely_value* {val_tmp} = {val_code};")
            pairs.append((key_tmp, val_tmp))
        dict_var = f"__dict_{self.temp_counter}"
        self.temp_counter += 1
        self.emit_to_method(f"dict* {dict_var} = dict_new_str();")
        for key, val in pairs:
            self.emit_to_method(f"dict_set_str({dict_var}, {key}->u.string_val, {val});")
        return ExprCode(f"ely_value_new_object({dict_var})", "ely_value*", "dict<str, any>")

    def _gen_index_expression(self, node: IndexExpression) -> ExprCode:
        target = self.ensure_type(self.gen_expression(node.target), 'ely_value*')
        index = self.ensure_type(self.gen_expression(node.index), 'ely_value*')
        return ExprCode(f"ely_value_index({target}, {index})", "ely_value*", "any")

    # -------------------------------------------------------------------
    # Диспетчер инструкций
    # -------------------------------------------------------------------
    def gen_statement(self, stmt: Statement):
        """Диспетчер инструкций для методов класса и управляющих конструкций."""
        from parser.dtcs import (
            ExpressionStatement, VariableDeclaration, ReturnStatement,
            IfStatement, WhileLoop, ForLoop, ForEachLoop,
            BreakStatement, ThrowStatement, Assignment, CollapseStatement
        )

        if isinstance(stmt, ExpressionStatement):
            expr = self.gen_expression(stmt.expression)
            self.emit_to_method(f"{expr.code};")
        elif isinstance(stmt, Assignment):
            expr = self._gen_assignment(stmt)
            if expr.raw_type != 'void':
                self.emit_to_method(f"{expr.code};")
        elif isinstance(stmt, ReturnStatement):
            self._gen_return(stmt)
        elif isinstance(stmt, IfStatement):
            self._gen_if(stmt)
        elif isinstance(stmt, WhileLoop):
            self._gen_while(stmt)
        elif isinstance(stmt, ForLoop):
            self._gen_for(stmt)
        elif isinstance(stmt, ForEachLoop):
            self._gen_foreach(stmt)
        elif isinstance(stmt, VariableDeclaration):
            self._gen_local_variable(stmt)
        elif isinstance(stmt, BreakStatement):
            self.emit_to_method("break;")
        elif isinstance(stmt, ThrowStatement):
            val = self.gen_expression(stmt.value)
            val = self.ensure_type(val, 'ely_value*')
            self.emit_to_method(f"throw {val.code};")
        elif isinstance(stmt, CollapseStatement):
            name = stmt.name
            if name in self.var_types:
                ctype = self.var_types[name]
                if ctype == 'str':
                    self.emit_to_method(f"if ({name}) {{ ely_str_free({name}); }}");
                elif ctype in self.classes_ast:
                    self.emit_to_method(f"delete {name};");
                elif ctype == 'any' or self.type_to_cpp(ctype) == 'ely_value*':
                    # Только для ely_value* переменных нужно убирать GC-корень
                    self.emit_to_method(f"gc_remove_root((void**)&{name});");
                del self.var_types[name]
            for scope in self.scopes:
                if name in scope:
                    del scope[name]
            self.emit_to_method(f"// collapse {name}");
            # Открываем новый C++ блок, чтобы можно было переиспользовать имя с другим типом
            self.emit_to_method("{");
            self.collapse_depth += 1;
        elif isinstance(stmt, AsafeBlock):
            self._gen_asafe(stmt)
        else:
            # Для неизвестных типов: если есть expression — генерируем его
            if hasattr(stmt, 'expression'):
                expr = self.gen_expression(stmt.expression)
                if expr.raw_type != 'void':
                    self.emit_to_method(f"{expr.code};")
            else:
                self.error(f"Unknown statement type: {type(stmt).__name__}", stmt)

    # -------------------------------------------------------------------
    # AsafeBlock — безопасный блок с обработкой исключений
    # -------------------------------------------------------------------
    def _gen_asafe(self, node):
        """Генерирует try-catch блок для AsafeBlock."""
        self.emit_to_method("try {")
        self.indent += 1
        self.push_scope()
        for stmt in node.body:
            self.gen_statement(stmt)
        self.pop_scope()
        self.indent -= 1
        if node.except_handler:
            except_h = node.except_handler
            exc_type_ely = except_h.exception_type or ''
            # Преобразуем Ely-тип в C++ тип для catch
            if exc_type_ely == 'str':
                exc_type_cpp = 'const char*'
            elif exc_type_ely in ('int','uint','more','umore','byte','ubyte'):
                exc_type_cpp = 'long long'
            elif exc_type_ely in ('flt','double'):
                exc_type_cpp = 'double'
            elif exc_type_ely == 'bool':
                exc_type_cpp = 'int'
            else:
                exc_type_cpp = exc_type_ely if exc_type_ely else '...'
            exc_param = except_h.parameter or ''
            catch_clause = f"catch ({exc_type_cpp} {exc_param})" if (exc_param and exc_type_cpp) else f"catch (...)"
            self.emit_to_method(f"}} {catch_clause} {{")
            self.indent += 1
            self.push_scope()
            if exc_param:
                self.var_types[exc_param] = exc_type_ely
            for stmt in except_h.body:
                self.gen_statement(stmt)
            self.pop_scope()
            self.indent -= 1
        self.emit_to_method("}")

    # -------------------------------------------------------------------
    # Управляющие конструкции
    # -------------------------------------------------------------------
    def _gen_if(self, node: IfStatement):
        cond_expr = self.gen_expression(node.condition)
        cond_type = self.get_expression_type(node.condition)
        if cond_expr.is_native and cond_type in ('int','uint','more','umore','byte','ubyte','bool','flt','double','long long'):
            self.emit_to_method(f"if ({cond_expr.code}) {{")
        elif cond_expr.is_wrapped:
            self.emit_to_method(f"if (ely_value_as_bool({cond_expr.code})) {{")
        else:
            cond = self.ensure_type(cond_expr, 'ely_value*')
            self.emit_to_method(f"if (ely_value_as_bool({cond})) {{")
        self.indent += 1
        self.push_scope()
        for stmt in node.then_body: self.gen_statement(stmt)
        self.pop_scope()
        self.indent -= 1
        if node.else_body:
            self.emit_to_method("} else {")
            self.indent += 1
            self.push_scope()
            for stmt in node.else_body: self.gen_statement(stmt)
            self.pop_scope()
            self.indent -= 1
        self.emit_to_method("}")

    def _gen_while(self, node: WhileLoop):
        cond_expr = self.gen_expression(node.condition)
        cond_type = self.get_expression_type(node.condition)
        if cond_expr.is_native and cond_type in ('int','uint','more','umore','byte','ubyte','bool','flt','double','long long'):
            self.emit_to_method(f"while ({cond_expr.code}) {{")
        elif cond_expr.is_wrapped:
            self.emit_to_method(f"while (ely_value_as_bool({cond_expr.code})) {{")
        else:
            cond = self.ensure_type(cond_expr, 'ely_value*')
            self.emit_to_method(f"while (ely_value_as_bool({cond})) {{")
        self.indent += 1
        self.push_scope()
        for stmt in node.body: self.gen_statement(stmt)
        self.pop_scope()
        self.indent -= 1
        self.emit_to_method("}")

    def _gen_for(self, node: ForLoop):
        from parser.dtcs import VariableDeclaration
        self.push_scope()
        # init: VariableDeclaration → генерируем объявление в заголовке цикла
        # init: ExpressionStatement → "expr; cond; inc"
        init_for = ";"
        if node.init:
            from parser.dtcs import ExpressionStatement
            if isinstance(node.init, VariableDeclaration):
                # Для объявления переменной генерируем тип и имя в заголовке цикла
                resolved = self.resolve_type_alias(node.init.type)
                c_type = self.type_to_cpp(resolved)
                if node.init.initializer:
                    init_code = self.gen_expression(node.init.initializer)
                    # Убеждаемся, что тип совпадает
                    init_code = self.ensure_type(init_code, c_type)
                    init_for = f"{c_type} {node.init.name} = {init_code.code}"
                else:
                    init_for = f"{c_type} {node.init.name} = 0"
                # Добавляем переменную в таблицу типов для использования внутри цикла
                self.var_types[node.init.name] = resolved
            elif isinstance(node.init, ExpressionStatement):
                init_code = self.gen_expression(node.init.expression)
                init_for = f"{init_code.code};"
            else:
                init_code = self.gen_expression(node.init)
                init_for = f"{init_code.code};"
        cond_for = "1"
        if node.condition:
            cond_expr = self.gen_expression(node.condition)
            cond_type = self.get_expression_type(node.condition)
            if cond_expr.is_native and cond_type in ('int','uint','more','umore','byte','ubyte','bool','flt','double','long long'):
                cond_for = cond_expr.code
            elif cond_expr.is_wrapped:
                cond_for = f"ely_value_as_bool({cond_expr})"
            else:
                cond = self.ensure_type(cond_expr, 'ely_value*')
                cond_for = f"ely_value_as_bool({cond})"
        inc_for = ""
        if node.update:
            upd_code = self.gen_expression(node.update)
            inc_for = upd_code.code
        self.emit_to_method(f"for ({init_for}; {cond_for}; {inc_for}) {{")
        self.indent += 1
        self.push_scope()
        for stmt in node.body: self.gen_statement(stmt)
        self.pop_scope()
        self.indent -= 1
        self.emit_to_method("}")
        self.pop_scope()

    def _gen_foreach(self, node: ForEachLoop):
        from parser.dtcs import VariableDeclaration
        # node.iterable — выражение коллекции
        collection = self.ensure_type(self.gen_expression(node.iterable), 'ely_value*')
        # Генерируем уникальное имя для переменной цикла
        loop_counter = f"__i_{self.temp_counter}"
        self.temp_counter += 1
        self.emit_to_method(f"for (size_t {loop_counter} = 0; {loop_counter} < ely_array_len({collection}); {loop_counter}++) {{")
        self.indent += 1
        self.push_scope()
        # node.item_decl — VariableDeclaration для переменной итерации
        decl = node.item_decl
        item_type = 'any'
        if isinstance(decl, VariableDeclaration) and decl.type:
            item_type = decl.type
        var_name = decl.name if isinstance(decl, VariableDeclaration) else '__item'
        self.var_types[var_name] = item_type
        raw_type = self.type_to_cpp(item_type)
        if raw_type == 'ely_value*':
            self.emit_to_method(f"ely_value* {var_name} = ely_array_get({collection}, {loop_counter});")
            if self.use_raii_roots:
                self.emit_to_method(f"GC_AUTO_ROOT({var_name});")
            else:
                self.emit_to_method(f"gc_add_root((void**)&{var_name});")
        elif raw_type == 'char*':
            self.emit_to_method(f"char* {var_name} = ely_value_to_string(ely_array_get({collection}, {loop_counter}));")
        elif raw_type in ('int', 'long long'):
            self.emit_to_method(f"{raw_type} {var_name} = ely_value_as_int(ely_array_get({collection}, {loop_counter}));")
        else:
            self.emit_to_method(f"{raw_type} {var_name} = ely_value_as_{raw_type}(ely_array_get({collection}, {loop_counter}));")
        for stmt in node.body: self.gen_statement(stmt)
        self.pop_scope()
        self.indent -= 1
        self.emit_to_method("}")

    # -------------------------------------------------------------------
    # Return — единая логика
    # -------------------------------------------------------------------
    def _gen_return(self, node: ReturnStatement) -> ExprCode:
        if node.value is None:
            return ExprCode("return;", "void", "void")

        val = self.gen_expression(node.value)

        # Определяем ожидаемый raw_type возврата
        if self.func_return_type and self.func_return_type != 'void':
            # Используем for_signature=True чтобы получить ely_value* для методов
            if self.current_function_is_method:
                ret_raw = 'ely_value*'
            else:
                # Для глобальных функций используем for_signature=True (всегда ely_value*)
                # Но для функций, чей return type native, должны возвращать native
                ret_ely = self.resolve_type_alias(self.func_return_type)
                if ret_ely in self.classes_ast or ret_ely in getattr(self, 'interfaces_ast', {}):
                    ret_raw = 'ely_value*'
                elif ret_ely in ('str',):
                    ret_raw = 'char*'
                elif ret_ely in ('int','uint','more','umore','byte','ubyte','bool','flt','double'):
                    ret_raw = self.type_to_cpp(ret_ely)
                else:
                    ret_raw = 'ely_value*'
            val = self.ensure_type(val, ret_raw)
            self.emit_to_method(f"return {val.code};")
        else:
            self.emit_to_method(f"return {val.code};")

        return ExprCode(f"return {val.code};", val.raw_type, val.ely_type)

    # -------------------------------------------------------------------
    # Локальные переменные
    # -------------------------------------------------------------------
    def _gen_local_variable(self, node: VariableDeclaration) -> ExprCode:
        resolved = self.resolve_type_alias(node.type)
        c_type = self.type_to_cpp(resolved)
        is_native = resolved in ('int','uint','more','umore','byte','ubyte','str','bool','flt','double','char')

        if node.initializer:
            init = self.gen_expression(node.initializer)
            # Если переменная native и init это ely_value* — unwrap
            if is_native and init.is_wrapped:
                init = self.ensure_type(init, c_type)
            # Если переменная ely_value* и init это native — wrap
            elif not is_native and init.is_native:
                init = self.ensure_type(init, "ely_value*")

            if c_type == 'char*' and resolved == 'str':
                init = ExprCode(f"ely_str_dup({init.code})", 'char*', 'str')

            self.var_types[node.name] = resolved
            self.emit_to_method(f"{c_type} {node.name} = {init.code};")

            # GC-register для ely_value* переменных
            if c_type == 'ely_value*':
                if self.use_raii_roots:
                    self.emit_to_method(f"GC_AUTO_ROOT({node.name});")
                else:
                    self.emit_to_method(f"gc_add_root((void**)&{node.name});")
                if self.scope_roots:
                    self.scope_roots[-1].append(node.name)

            return ExprCode(f"{node.name}", c_type, resolved)
        else:
            self.var_types[node.name] = resolved
            if c_type == 'ely_value*':
                self.emit_to_method(f"{c_type} {node.name} = ely_value_new_null();")
                if self.use_raii_roots:
                    self.emit_to_method(f"GC_AUTO_ROOT({node.name});")
                else:
                    self.emit_to_method(f"gc_add_root((void**)&{node.name});")
                if self.scope_roots:
                    self.scope_roots[-1].append(node.name)
            elif c_type == 'char*':
                self.emit_to_method(f"{c_type} {node.name} = nullptr;")
            elif resolved == 'bool':
                self.emit_to_method(f"int {node.name} = 0;")
            else:
                self.emit_to_method(f"{c_type} {node.name} = 0;")
            return ExprCode(f"{node.name}", c_type, resolved)

    # -------------------------------------------------------------------
    # Вспомогательные
    # -------------------------------------------------------------------
    def _wrap_result(self, code_or_str, ely_type: str) -> ExprCode:
        """Оборачивает нативный результат в ely_value* для возврата из методов класса."""
        if isinstance(code_or_str, str):
            expr = ExprCode(code_or_str, self.type_to_cpp(ely_type), ely_type)
        else:
            expr = code_or_str

        if expr.is_wrapped:
            return expr

        return self._wrap_to_ely(expr)

    def _wrap_to_ely(self, expr: ExprCode) -> ExprCode:
        """Wrap native expression to ely_value*."""
        if expr.is_wrapped:
            return expr
        t = expr.ely_type
        if t in ('int','uint','more','umore','byte','ubyte'):
            return ExprCode(f"ely_value_new_int({expr.code})", "ely_value*", t)
        if t in ('flt', 'double'):
            return ExprCode(f"ely_value_new_double({expr.code})", "ely_value*", t)
        if t == 'bool':
            return ExprCode(f"ely_value_new_bool({expr.code})", "ely_value*", t)
        if t == 'str':
            # Для char* → ely_value* используем ely_value_new_string
            if expr.raw_type == 'char*':
                # Проверяем, если код уже содержит ely_value_new_string — не дублируем
                if expr.code.startswith('ely_value_new_string('):
                    return ExprCode(expr.code, "ely_value*", t)
                return ExprCode(f"ely_value_new_string({expr.code})", "ely_value*", t)
            # Если это уже объект-класс (указатель)
            if expr.raw_type.endswith('*') and not expr.raw_type.startswith('ely_'):
                return ExprCode(expr.code, "ely_value*", t)
            return ExprCode(f"ely_value_new_string({expr.code})", "ely_value*", t)
        if t in self.classes_ast or t in getattr(self, 'interfaces_ast', {}):
            return ExprCode(f"({t}*)({expr.code})", "ely_value*", t)
        return ExprCode(expr.code, "ely_value*", t)

    # -------------------------------------------------------------------
    # Встраиваемые методы для массивов, строк, словарей
    # -------------------------------------------------------------------
    def _gen_array_method(self, obj: ExprCode, method: str, args: List[Expression]) -> ExprCode:
        args_code = [self.ensure_type(self.gen_expression(a), 'ely_value*') for a in args]
        if method == 'len':
            return ExprCode(f"ely_value_call_method({obj}, \"len\", NULL, 0)", "ely_value*", "int")
        if method == 'push':
            if not args_code:
                return ExprCode(f"ely_value_call_method({obj}, \"push\", NULL, 0)", "void", "void")
            arg_arr = f"__args_{self.temp_counter}"
            self.temp_counter += 1
            self.emit_to_method(f"ely_value* {arg_arr}[] = {{ {args_code[0].code} }};")
            return ExprCode(f"ely_value_call_method({obj}, \"push\", {arg_arr}, 1)", "void", "void")
        if method == 'pop':
            return ExprCode(f"ely_value_call_method({obj}, \"pop\", NULL, 0)", "ely_value*", "any")
        if method == 'has':
            if not args_code:
                return ExprCode("ely_value_new_bool(0)", "ely_value*", "bool")
            arg_arr = f"__args_{self.temp_counter}"
            self.temp_counter += 1
            self.emit_to_method(f"ely_value* {arg_arr}[] = {{ {args_code[0].code} }};")
            return ExprCode(f"ely_value_call_method({obj}, \"has\", {arg_arr}, 1)", "ely_value*", "bool")
        return ExprCode(f"ely_value_call_method({obj}, \"{method}\", NULL, 0)", "ely_value*", "any")

    def _gen_dict_method(self, obj: ExprCode, method: str, args: List[Expression]) -> ExprCode:
        args_code = [self.ensure_type(self.gen_expression(a), 'ely_value*') for a in args]
        if method == 'keys':
            return ExprCode(f"ely_value_call_method({obj}, \"keys\", NULL, 0)", "ely_value*", "arr<any>")
        if method == 'has':
            if not args_code:
                return ExprCode("ely_value_new_bool(0)", "ely_value*", "bool")
            arg_arr = f"__args_{self.temp_counter}"
            self.temp_counter += 1
            self.emit_to_method(f"ely_value* {arg_arr}[] = {{ {args_code[0].code} }};")
            return ExprCode(f"ely_value_call_method({obj}, \"has\", {arg_arr}, 1)", "ely_value*", "bool")
        if method == 'del':
            if not args_code:
                return ExprCode("", "void", "void")
            arg_arr = f"__args_{self.temp_counter}"
            self.temp_counter += 1
            self.emit_to_method(f"ely_value* {arg_arr}[] = {{ {args_code[0].code} }};")
            return ExprCode(f"ely_value_call_method({obj}, \"del\", {arg_arr}, 1)", "void", "void")
        return ExprCode(f"ely_value_call_method({obj}, \"{method}\", NULL, 0)", "ely_value*", "any")

    def _gen_str_method(self, obj: ExprCode, method: str, args: List[Expression]) -> ExprCode:
        if method == 'len':
            if obj.is_wrapped:
                return ExprCode(f"ely_str_len(ely_value_to_string({obj}))", "size_t", "int")
            return ExprCode(f"ely_str_len({obj})", "size_t", "int")
        if method in ('concat', 'dup', 'trim'):
            obj_str = self.ensure_type(obj, 'char*')
            args_code = [self.ensure_type(self.gen_expression(a), 'char*') for a in args]
            func_name = f"ely_str_{method}"
            return ExprCode(f"{func_name}({', '.join([obj_str.code] + [a.code for a in args_code])})", "char*", "str")
        if method == 'substr':
            obj_str = self.ensure_type(obj, 'char*')
            args_code = [self.ensure_type(self.gen_expression(a), 'long long') for a in args]
            return ExprCode(f"ely_str_substr({obj_str}, {', '.join(a.code for a in args_code)})", "char*", "str")
        if method == 'replace':
            obj_str = self.ensure_type(obj, 'char*')
            args_code = [self.ensure_type(self.gen_expression(a), 'char*') for a in args]
            return ExprCode(f"ely_str_replace({obj_str}, {', '.join(a.code for a in args_code)})", "char*", "str")
        if method in ('cmp', 'equals'):
            obj_str = self.ensure_type(obj, 'char*')
            args_code = [self.ensure_type(self.gen_expression(a), 'char*') for a in args]
            return ExprCode(f"ely_str_cmp({obj_str}, {args_code[0].code})", "int", "bool")
        return self._gen_default_method(obj, method)

    def _gen_num_method(self, obj: ExprCode, method: str, t: str) -> ExprCode:
        if method == 'toStr':
            prefix = {'int':'ely_int_to_str','uint':'ely_uint_to_str',
                      'more':'ely_more_to_str','umore':'ely_umore_to_str',
                      'flt':'ely_flt_to_str','double':'ely_double_to_str'}
            if t in prefix:
                obj_native = self.ensure_type(obj, self.type_to_cpp(t))
                return ExprCode(f"{prefix[t]}({obj_native})", "char*", "str")
            return ExprCode(f"ely_int_to_str({obj})", "char*", "str")
        return self._gen_default_method(obj, method)


    def _gen_default_method(self, obj: ExprCode, method: str) -> ExprCode:
        return ExprCode(f"ely_value_call_method({obj}, \"{method}\", NULL, 0)", "ely_value*", "any")

    # -------------------------------------------------------------------
    # Генерация top-level функции (вызывается из CppCodeGen._gen_one_function)
    # -------------------------------------------------------------------
    def gen_function(self, method: MethodDeclaration):
        """Генерирует top-level функцию: сигнатура + тело.
        Вызывается из CppCodeGen._gen_one_function.
        Для глобальных функций используем нативные типы (без for_signature=True),
        чтобы совпадало с forward declaration в codegen.py.
        """
        ret_raw = self.type_to_cpp(method.return_type or 'void')
        params = ', '.join([f"{self.type_to_cpp(p.type, is_param=True)} {p.name}"
                            for p in method.parameters])
        self.emit_to_method(f"{ret_raw} {method.name}({params}) {{")
        self.indent += 1

        # Пролог для main: инициализация GC + chdir к папке exe
        if method.name == 'main':
            self.emit_to_method("gc_init();")
            self.emit_to_method("_global_init();")
            self.emit_to_method("gc_set_enabled(1);")

        old_func = self.current_function
        self.current_function = method.name
        old_func_ret = getattr(self, 'func_return_type', None)
        self.func_return_type = method.return_type or 'void'
        old_method_flag = getattr(self, 'current_function_is_method', False)
        self.current_function_is_method = False
        self.push_scope()

        for p in method.parameters:
            self.var_types[p.name] = p.type
            ctype = self.type_to_cpp(p.type, is_param=True)
            if ctype == 'ely_value*':
                self.emit_to_method(f"gc_add_root((void**)&{p.name});")
                if self.scope_roots:
                    self.scope_roots[-1].append(p.name)

        for stmt in method.body:
            self.gen_statement(stmt)

        # Закрываем все open collapse блоки перед закрытием функции
        for _ in range(self.collapse_depth):
            self.indent -= 1
            self.emit_to_method("}")
        self.collapse_depth = 0

        self.pop_scope()
        self.indent -= 1
        self.emit_to_method("}")
        self.current_function = old_func
        self.func_return_type = old_func_ret
        self.current_function_is_method = old_method_flag

    # -------------------------------------------------------------------
    # Статические методы (вызываются внутри функций, где is_method=False)
    # -------------------------------------------------------------------
    def gen_static_method_call(self, class_name: str, method_name: str, args: List[Expression]) -> ExprCode:
        """Генерирует вызов статического метода класса.
        ВСЕ методы классов в C++ всегда возвращают ely_value* (for_signature=True),
        поэтому НЕ оборачиваем результат в ely_value_new_*().
        """
        cls = self.classes_ast.get(class_name)
        if not cls:
            return ExprCode("ely_value_new_null()", "ely_value*", "any")
        for sm in cls.static_methods:
            if sm.name == method_name:
                args_code = [self.gen_expression(a) for a in args]
                for i, arg in enumerate(args_code):
                    if i < len(sm.parameters):
                        expected = self.type_to_cpp(sm.parameters[i].type, is_param=True)
                        args_code[i] = self.ensure_type(arg, expected)
                # Все методы классов генерируются с for_signature=True → всегда ely_value*
                ret_ely = sm.return_type or 'any'
                call_code = f"{class_name}::{sm.name}({', '.join(a.code for a in args_code)})"
                return ExprCode(call_code, "ely_value*", ret_ely)
        return ExprCode("ely_value_new_null()", "ely_value*", "any")
