import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from parser import *
from typing import List, Optional


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

    # SCOPES
    def _push_scope(self):
        self.scopes.append(self.var_types)
        self.var_types = {}
        self.scope_roots.append([])

    def _pop_scope(self):
        if self.scopes:
            self.var_types = self.scopes.pop()
        if self.scope_roots:
            roots = self.scope_roots.pop()
            for name in reversed(roots):
                self.emit_to_main(f"gc_remove_root((void**)&{name});")

    # TYPES
    def _get_expression_type(self, expr: Expression) -> str:
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
        elif isinstance(expr, Call):
            if isinstance(expr.callee, MemberAccess):
                obj = expr.callee.object
                method = expr.callee.member
                obj_type = self._get_expression_type(obj)
                if obj_type.startswith('arr<'):
                    if method == 'len':
                        return 'int'
                    elif method == 'pop':
                        return 'any'
                    elif method == 'push':
                        return 'void'
                elif obj_type.startswith('dict<'):
                    if method == 'keys':
                        return 'arr<str>'
            return 'any'
        return 'any'

    def _type_to_c(self, ely_type: str, for_signature: bool = False) -> str:
        ely_type = self._resolve_type_alias(ely_type)
        
        if for_signature and ely_type != 'void':
            return 'ely_value*'
        
        mapping = {
            'void': 'void',
            'bool': 'int',
            'byte': 'signed char',
            'ubyte': 'unsigned char',
            'int': 'int',
            'uint': 'unsigned int',
            'more': 'long long',
            'umore': 'unsigned long long',
            'flt': 'float',
            'double': 'double',
            'str': 'char*',
            'any': 'ely_value*',
            'char': 'char',
        }
        if ely_type.startswith('arr<') or ely_type.startswith('dict<'):
            return 'ely_value*'
        if ely_type in mapping:
            return mapping[ely_type]
        if ely_type in self.structs:
            return f"struct {ely_type}"
        if ely_type.endswith('*'):
            inner = ely_type[:-1].strip()
            return f"{self._type_to_c(inner)}*"
        return ely_type

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

        if not self.is_module:
            has_main = any(isinstance(s, MethodDeclaration) and s.name == 'main' for s in program.statements)
            if not has_main:
                self.main_code.append("int main() {")
                self.main_code.append("    gc_init();")
                self.main_code.append("    if (_global_init) _global_init();")
                self.main_code.append("    return 0;")
                self.main_code.append("}")

        for stmt in program.statements:
            if isinstance(stmt, TypeAlias):
                self.type_aliases[stmt.name] = stmt.target_type
            elif isinstance(stmt, MethodDeclaration):
                self.original_functions[stmt.name] = stmt
            elif isinstance(stmt, StructDeclaration):
                self.structs.add(stmt.name)
                fields = {}
                for field in stmt.fields:
                    fields[field.name] = field.type
                self.struct_fields[stmt.name] = fields

        for stmt in program.statements:
            if isinstance(stmt, UsingDirective):
                self.used_modules.append(stmt.module)

        self.code.append('#include "ely_runtime.h"\n')
        self.code.append('#include "ely_gc.h"\n')
        for mod in self.used_modules:
            self.code.append(f'#include "{mod}.h"\n')
        self.code.append('\n')

        for stmt in program.statements:
            if isinstance(stmt, StructDeclaration):
                self._gen_struct(stmt)

        for stmt in program.statements:
            if isinstance(stmt, ExternFunction):
                ret_type = self._type_to_c(stmt.return_type or 'void')
                params = []
                for p in stmt.parameters:
                    if p.type == '...':
                        params.append("...")
                    else:
                        param_type = self._type_to_c(p.type)
                        params.append(f"{param_type} {p.name}")
                param_str = ", ".join(params)
                self.emit(f"extern {ret_type} {stmt.name}({param_str});")
        self.code.append('\n')

        for stmt in program.statements:
            if isinstance(stmt, VariableDeclaration):
                self._gen_global_variable(stmt)
            elif isinstance(stmt, MethodDeclaration):
                self._declare_function(stmt)

        for stmt in program.statements:
            if isinstance(stmt, MethodDeclaration):
                self._gen_function(stmt)

        if self.global_vars_to_init:
            self._create_global_init()

        if not self.is_module:
            has_main = any(isinstance(s, MethodDeclaration) and s.name == 'main' for s in program.statements)
            if not has_main:
                self.main_code.append("int main() {")
                self.main_code.append("    if (_global_init) _global_init();")
                self.main_code.append("    return 0;")
                self.main_code.append("}")

        final_code = self.code + self.specializations + self.main_code
        return "\n".join(final_code)

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
        self.emit("static void _global_init(void) {")
        self.indent += 1
        for name, typ, init_node in self.global_vars_to_init:
            if isinstance(init_node, ArrayLiteral):
                self._gen_global_array_init(name, typ, init_node)
            elif isinstance(init_node, DictLiteral):
                self._gen_global_dict_init(name, typ, init_node)
            else:
                init_code = self.gen_expression(init_node)
                self.emit(f"{name} = {init_code};")
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

        ctype = 'ely_value*'
        if node.initializer:
            init_code = self.gen_expression(node.initializer)
            self.emit_to_main(f"{ctype} {node.name} = {init_code};")
        else:
            if resolved_type == 'int':
                self.emit_to_main(f"{ctype} {node.name} = ely_value_new_int(0);")
            elif resolved_type == 'bool':
                self.emit_to_main(f"{ctype} {node.name} = ely_value_new_bool(0);")
            elif resolved_type in ('flt', 'double'):
                self.emit_to_main(f"{ctype} {node.name} = ely_value_new_double(0.0);")
            else:
                self.emit_to_main(f"{ctype} {node.name} = ely_value_new_null();")
        self.var_types[node.name] = resolved_type

        self.emit_to_main(f"gc_add_root((void**)&{node.name});")
        if self.scope_roots:
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

    def _gen_function(self, node: MethodDeclaration):
        if node.name == '_global_init':
            return
        if node.type_params:
            return

        func_name = node.name
        ret_type = self._type_to_c(node.return_type or 'void', for_signature=True)
        params = [f"{self._type_to_c(p.type, for_signature=True)} {p.name}" for p in node.parameters]
        param_str = ", ".join(params)

        old_main = self.main_code
        self.main_code = []
        self.indent = 0

        self.emit_to_main(f"{ret_type} {func_name}({param_str}) {{")
        self.indent += 1
        self.inside_func = True
        self.func_name = node.name
        self.current_function = node.name
        self.func_return_type = node.return_type or 'void'

        if func_name == 'main':
            self.emit_to_main("gc_init();")
        
        if func_name == 'main' and self.global_vars_to_init and not self.is_module:
            self.emit_to_main("_global_init();")

        self._push_scope()
        
        for p in node.parameters:
            self.var_types[p.name] = p.type
            ctype = self._type_to_c(p.type)
            if ctype == 'ely_value*' or ctype.startswith('ely_value*'):
                self.emit_to_main(f"gc_add_root((void**)&{p.name});")
                if self.scope_roots:
                    self.scope_roots[-1].append(p.name)
        
        for stmt in node.body:
            self.gen_statement(stmt)

        self._pop_scope()
        self.indent -= 1
        self.emit_to_main("}")
        self.inside_func = False
        self.func_name = None

        old_main.extend(self.main_code)
        self.main_code = old_main

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
                init_part = ";"  # объявление уже добавлено отдельной строкой
            elif isinstance(node.init, ExpressionStatement):
                expr_code = self.gen_expression(node.init.expression)
                init_part = expr_code + ";" if expr_code else ";"
            else:
                init_part = ";"

        cond_part = "1"
        if node.condition:
            cond_expr = self.gen_expression(node.condition)
            cond_part = f"ely_value_as_bool({cond_expr})"   # уже есть, но убедитесь, что cond_expr обёрнут

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

        if iterable_type.startswith('arr<'):
            # Массив: итерируем по элементам
            self.emit_to_main(f"for (size_t __i = 0; __i < ely_array_len({iterable_code}); __i++) {{")
            self.indent += 1
            elem_code = f"ely_array_get({iterable_code}, __i)"
            if isinstance(node.item_decl, VariableDeclaration):
                decl_type = node.item_decl.type or 'any'
                c_decl_type = self._type_to_c(decl_type)
                self.emit_to_main(f"{c_decl_type} {node.item_decl.name} = {elem_code};")
                self.var_types[node.item_decl.name] = decl_type
                if c_decl_type == 'ely_value*' or c_decl_type.startswith('ely_value*'):
                    self.emit_to_main(f"gc_add_root((void**)&{node.item_decl.name});")
                    if self.scope_roots:
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
            # Словарь: итерируем по значениям (можно также по ключам, но по умолчанию по значениям)
            # Сначала получаем массив ключей
            keys_var = f"__keys_{self.temp_counter}"
            self.temp_counter += 1
            self.emit_to_main(f"ely_value* {keys_var} = ely_dict_keys({iterable_code});")
            self.emit_to_main(f"for (size_t __i = 0; __i < ely_array_len({keys_var}); __i++) {{")
            self.indent += 1
            # Получаем ключ и значение
            self.emit_to_main(f"ely_value* __key = ely_array_get({keys_var}, __i);")
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
            # Освобождаем временный массив ключей (не забыть)
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
        self.emit_to_main("int __error_flag = 0;")
        self.emit_to_main("void* __error_value = NULL;")
        self.emit_to_main("{")
        self.indent += 1
        for stmt in node.body:
            self.gen_statement(stmt)
        self.indent -= 1
        self.emit_to_main("}")
        self.emit_to_main("__except_label:")
        self.emit_to_main("if (__error_flag) {")
        self.indent += 1
        if node.except_handler:
            exc_type = node.except_handler.exception_type
            param = node.except_handler.parameter
            self.emit_to_main(f"{self._type_to_c(exc_type)}* __exc = ({self._type_to_c(exc_type)}*)__error_value;")
            if param:
                self.emit_to_main(f"{self._type_to_c(exc_type)} {param} = *__exc;")
                self.emit_to_main(f"ely_free(__exc);")
                self.var_types[param] = exc_type
            for stmt in node.except_handler.body:
                self.gen_statement(stmt)
        self.indent -= 1
        self.emit_to_main("}")

    def _gen_throw(self, node: ThrowStatement):
        val_expr = node.value
        val_code = self.gen_expression(val_expr)
        val_type = self._get_expression_type(val_expr)
        c_val_type = self._type_to_c(val_type)
        self.emit_to_main(f"{c_val_type}* __exc_ptr = ({c_val_type}*)ely_alloc(sizeof({c_val_type}));")
        self.emit_to_main(f"*__exc_ptr = {val_code};")
        self.emit_to_main("__error_flag = 1;")
        self.emit_to_main("__error_value = __exc_ptr;")
        self.emit_to_main("goto __except_label;")

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
            self.emit_to_main(f"return {val};")
        else:
            self.emit_to_main("return;")

    def _gen_collapse(self, node: CollapseStatement):
        if node.name in self.var_types:
            del self.var_types[node.name]

    def _gen_break(self, node: BreakStatement):
        self.emit_to_main("break;")

    # ------------------- Генерация выражений -------------------
    def gen_expression(self, expr: Expression) -> Optional[str]:
        if isinstance(expr, Literal):
            return self._gen_literal(expr)
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
            # Экранируем строку для C
            escaped = node.value.replace('\\', '\\\\').replace('"', '\\"')
            # Заменяем переводы строк на \n
            escaped = escaped.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
            return f'ely_value_new_string("{escaped}")'
        elif node.value is None:
            return "ely_value_new_null()"
        return "ely_value_new_null()"

    def _gen_identifier(self, node: Identifier) -> str:
        return node.name

    def _gen_binary_op(self, node: BinaryOp) -> str:
        left = self.gen_expression(node.left)
        right = self.gen_expression(node.right)
        op = node.operator
        op_map = {
            '+': 'add',
            '-': 'sub',
            '*': 'mul',
            '/': 'div',
            '%': 'mod',
            '==': 'eq',
            '!=': 'ne',
            '<': 'lt',
            '<=': 'le',
            '>': 'gt',
            '>=': 'ge',
            '&&': 'and',
            '||': 'or',
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

    def _gen_assignment(self, node: Assignment) -> str:
        if isinstance(node.target, MemberAccess):
            obj = self.gen_expression(node.target.object)
            value = self.gen_expression(node.value)
            # Write barrier: parent = obj, field = &obj->member, new_val = value
            self.emit_to_main(f"gc_write_barrier({obj}, (void**)&({obj}->{node.target.member}), {value});")
            return f"{obj}->{node.target.member} = {value}"
        if isinstance(node.target, IndexExpression):
            target = self.gen_expression(node.target.target)
            index = self.gen_expression(node.target.index)
            value = self.gen_expression(node.value)
            return f"ely_value_set_index({target}, {index}, {value})"
        target_code = self.gen_expression(node.target)
        value_code = self.gen_expression(node.value)
        return f"{target_code} = {value_code}"

    def _gen_conditional(self, node: Conditional) -> str:
        cond = self.gen_expression(node.condition)
        then_expr = self.gen_expression(node.then_expr)
        else_expr = self.gen_expression(node.else_expr)
        return f"((ely_value_as_bool({cond})) ? {then_expr} : {else_expr})"

    def _gen_fstring(self, node: FString) -> str:
        # Строим выражение как цепочку ely_value_add
        if not node.parts:
            return 'ely_value_new_string("")'
        
        # Накапливаем результат
        result = None
        for part in node.parts:
            if isinstance(part, str):
                # Строковая часть превращается в ely_value_new_string
                escaped = part.replace('"', '\\"').replace('\n', '\\n')
                part_expr = f'ely_value_new_string("{escaped}")'
            else:
                # Выражение
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
        return f"ely_value_get_key({obj}, \"{node.member}\")"

    def _gen_call(self, node: Call) -> str:
        # Обработка методов (obj.method(...))
        if isinstance(node.callee, MemberAccess):
            obj = node.callee.object
            method = node.callee.member
            obj_type = self._get_expression_type(obj)
            obj_code = self.gen_expression(obj)

            # Методы массивов arr<T>
            if obj_type.startswith('arr<'):
                if method == 'push':
                    if len(node.arguments) != 1:
                        self.error("push expects one argument", node)
                        return ""
                    arg_code = self.gen_expression(node.arguments[0])
                    return f"ely_array_push({obj_code}, {arg_code})"
                elif method == 'pop':
                    if len(node.arguments) == 0:
                        return f"ely_array_pop({obj_code})"
                    elif len(node.arguments) == 1:
                        index_code = self.gen_expression(node.arguments[0])
                        return f"ely_array_remove_index({obj_code}, {index_code})"
                    else:
                        self.error("pop expects 0 or 1 argument", node)
                        return ""
                elif method == 'len':
                    return f"ely_value_new_int(ely_array_len({obj_code}))"
                elif method == 'insert':
                    if len(node.arguments) != 2:
                        self.error("insert expects two arguments (index, value)", node)
                        return ""
                    index_code = self.gen_expression(node.arguments[0])
                    value_code = self.gen_expression(node.arguments[1])
                    return f"ely_array_insert({obj_code}, {index_code}, {value_code})"
                elif method == 'remove':
                    if len(node.arguments) != 1:
                        self.error("remove expects one argument (value)", node)
                        return ""
                    arg_code = self.gen_expression(node.arguments[0])
                    return f"ely_array_remove_value({obj_code}, {arg_code})"
                elif method == 'index':
                    if len(node.arguments) != 1:
                        self.error("index expects one argument (value)", node)
                        return ""
                    arg_code = self.gen_expression(node.arguments[0])
                    return f"ely_array_index({obj_code}, {arg_code})"
                else:
                    self.error(f"Unsupported array method '{method}'", node)
                    return ""

            # Методы словарей dict<K,V>
            elif obj_type.startswith('dict<'):
                if method == 'keys':
                    return f"ely_dict_keys({obj_code})"   # уже возвращает ely_value*
                elif method == 'del':
                    if len(node.arguments) != 1:
                        self.error("del expects one argument (key)", node)
                        return ""
                    key_code = self.gen_expression(node.arguments[0])
                    return f"ely_dict_del({obj_code}, {key_code})"
                elif method == 'has':
                    if len(node.arguments) != 1:
                        self.error("has expects one argument (key)", node)
                        return ""
                    key_code = self.gen_expression(node.arguments[0])
                    return f"ely_dict_has({obj_code}, {key_code})"
                elif method == 'toJson':
                    return f"ely_dict_to_json({obj_code})"
                else:
                    self.error(f"Unsupported dict method '{method}'", node)
                    return ""

            else:
                self.error(f"Method calls not supported for type {obj_type}", node)
                return ""

        # Обработка вызова обычной функции (не метода)
        if not isinstance(node.callee, Identifier):
            self.error("Call expression must be a function or method", node)
            return ""

        func_name = node.callee.name
        args = [self.gen_expression(arg) for arg in node.arguments]

        # Дженерики
        if func_name in self.original_functions:
            func_node = self.original_functions[func_name]
            if func_node.type_params:
                concrete_types = {}
                for arg, param in zip(node.arguments, func_node.parameters):
                    arg_type = self._get_expression_type(arg)
                    if param.type in func_node.type_params:
                        concrete_types[param.type] = arg_type
                missing = [tp for tp in func_node.type_params if tp not in concrete_types]
                if missing:
                    self.error(f"Could not infer type parameters: {missing}", node)
                    return ""
                key = (func_name, tuple(concrete_types.values()))
                if key not in self.generic_instances:
                    spec_name = self._generate_specialization(func_node, concrete_types)
                    self.generic_instances[key] = spec_name
                spec_name = self.generic_instances[key]
                return f"{spec_name}({', '.join(args)})"

        # Встроенные функции print/println
        if func_name == 'print':
            if not node.arguments:
                return 'ely_print("")'
            arg_code = self.gen_expression(node.arguments[0])
            return f"ely_print(ely_value_to_string({arg_code}))"
        if func_name == 'println':
            if not node.arguments:
                return 'ely_println("")'
            arg_code = self.gen_expression(node.arguments[0])
            return f"ely_println(ely_value_to_string({arg_code}))"

        # Стандартная библиотека (включая функции для словарей, если они вызываются как функции)
        stdlib = {
            'len': 'ely_str_len',
            'concat': 'ely_str_concat',
            'dup': 'ely_str_dup',
            'cmp': 'ely_str_cmp',
            'substr': 'ely_str_substr',
            'trim': 'ely_str_trim',
            'replace': 'ely_str_replace',
            'abs': 'ely_abs_int',
            'abs_more': 'ely_abs_more',
            'fabs': 'ely_fabs',
            'min': 'ely_min_int',
            'max': 'ely_max_int',
            'pow': 'ely_pow',
            'sqrt': 'ely_sqrt',
            'sin': 'ely_sin',
            'cos': 'ely_cos',
            'tan': 'ely_tan',
            'rand': 'ely_rand',
            'srand': 'ely_srand',
            'rand_double': 'ely_rand_double',
            'sleep': 'ely_sleep',
            'time_now': 'ely_time_now',
            'time_diff': 'ely_time_diff',
            'file_open': 'ely_file_open',
            'fileOpen': 'ely_file_open',
            'file_close': 'ely_file_close',
            'fileClose': 'ely_file_close',
            'file_write': 'ely_file_write',
            'fileWrite': 'ely_file_write',
            'file_read': 'ely_file_read',
            'fileRead': 'ely_file_read',
            'file_exists': 'ely_file_exists',
            'fileExists': 'ely_file_exists',
            'file_read_all': 'ely_file_read_all',
            'fileReadAll': 'ely_file_read_all',
            'file_remove': 'ely_file_remove',
            'remove': 'ely_file_remove',
            'file_rename': 'ely_file_rename',
            'path_join': 'ely_path_join',
            'path_basename': 'ely_path_basename',
            'path_dirname': 'ely_path_dirname',
            'path_is_absolute': 'ely_path_is_absolute',
            'load_library': 'ely_load_library',
            'get_function': 'ely_get_function',
            'close_library': 'ely_close_library',
            'call_int_int': 'ely_call_int_int',
            'call_double_double': 'ely_call_double_double',
            'call_double_double_double': 'ely_call_double_double_double',
            'call_str_void': 'ely_call_str_void',
            'jsonify': 'ely_dict_to_json',
            'dictify': 'ely_dictify',
            'keys': 'ely_dict_keys',
            'del': 'ely_dict_del',
            'has': 'ely_dict_has',
            'intToStr': 'ely_int_to_str',
            'strToInt': 'ely_str_to_int',
            'toJson': 'ely_value_to_string',
            'strToInt': 'ely_str_to_int',
            'intToStr': 'ely_int_to_str',
            'strLen': 'ely_str_len',
            'strCmp': 'ely_str_cmp',
            # Добавим псевдонимы для удобства
            'length': 'ely_str_len',
        }
        if func_name in stdlib:
            c_func = stdlib[func_name]
            call_expr = f"{c_func}({', '.join(args)})"
            wrappers = {
                # Преобразования чисел в строку
                'ely_int_to_str': 'ely_value_new_string',
                'ely_uint_to_str': 'ely_value_new_string',
                'ely_more_to_str': 'ely_value_new_string',
                'ely_umore_to_str': 'ely_value_new_string',
                'ely_flt_to_str': 'ely_value_new_string',
                'ely_double_to_str': 'ely_value_new_string',
                'ely_bool_to_str': 'ely_value_new_string',
                # Строковые функции, возвращающие числа
                'ely_str_len': 'ely_value_new_int',
                'ely_str_cmp': 'ely_value_new_int',
                # Математические функции, возвращающие числа
                'ely_abs_int': 'ely_value_new_int',
                'ely_abs_more': 'ely_value_new_int',
                'ely_fabs': 'ely_value_new_double',
                'ely_min_int': 'ely_value_new_int',
                'ely_min_more': 'ely_value_new_int',
                'ely_min_double': 'ely_value_new_double',
                'ely_max_int': 'ely_value_new_int',
                'ely_max_more': 'ely_value_new_int',
                'ely_max_double': 'ely_value_new_double',
                'ely_pow': 'ely_value_new_double',
                'ely_sqrt': 'ely_value_new_double',
                'ely_sin': 'ely_value_new_double',
                'ely_cos': 'ely_value_new_double',
                'ely_tan': 'ely_value_new_double',
                'ely_rand': 'ely_value_new_int',
                'ely_rand_double': 'ely_value_new_double',
                # Время
                'ely_time_now': 'ely_value_new_int',
                'ely_time_diff': 'ely_value_new_double',
            }
            if c_func in wrappers:
                return f"{wrappers[c_func]}({call_expr})"
            return call_expr

        # Обычный вызов пользовательской функции
        return f"{func_name}({', '.join(args)})"

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
        """Генерирует регистрацию корней для всех локальных переменных типа ely_value*"""
        roots = []
        for name, typ in self.var_types.items():
            resolved = self._resolve_type_alias(typ)
            ctype = self._type_to_c(resolved)
            # Проверяем, что тип является указателем на ely_value
            if ctype == 'ely_value*' or ctype.startswith('ely_value*'):
                roots.append(name)
        self.current_roots = roots
        for name in roots:
            self.emit_to_main(f"gc_add_root((void**)&{name});")

    def error(self, message: str, node: Expression):
        print(f"Code generation error: {message} at line {node.line}, col {node.col}")