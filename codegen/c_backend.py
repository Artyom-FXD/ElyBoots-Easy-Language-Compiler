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

    # ------------------- Управление областями видимости -------------------
    def _push_scope(self):
        self.scopes.append(self.var_types)
        self.var_types = {}

    def _pop_scope(self):
        if self.scopes:
            self.var_types = self.scopes.pop()

    # ------------------- Определение типов -------------------
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

    def _type_to_c(self, ely_type: str) -> str:
        ely_type = self._resolve_type_alias(ely_type)
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
        if not node.elements:
            self.emit(f"{name} = arr_new();")
            return
        self.emit(f"{name} = arr_new();")
        for elem in node.elements:
            elem_code = self.gen_expression(elem)
            tmp_var = f"__tmp_global_{self.temp_counter}"
            self.temp_counter += 1
            self.emit(f"ely_value* {tmp_var} = {elem_code};")
            self.emit(f"arr_push({name}, {tmp_var});")

    def _gen_global_dict_init(self, name: str, typ: str, node: DictLiteral):
        self.emit(f"{name} = dict_new_str();")
        for pair in node.pairs:
            key_code = self.gen_expression(pair.key)
            val_code = self.gen_expression(pair.value)
            key_tmp = f"__tmp_key_{self.temp_counter}"
            self.temp_counter += 1
            val_tmp = f"__tmp_val_{self.temp_counter}"
            self.temp_counter += 1
            self.emit(f"ely_value* {key_tmp} = {key_code};")
            self.emit(f"ely_value* {val_tmp} = {val_code};")
            self.emit(f"dict_set_str({name}, {key_tmp}->u.string_val, {val_tmp});")

    def _gen_struct(self, node: StructDeclaration):
        self.emit(f"struct {node.name} {{")
        self.indent += 1
        for field in node.fields:
            ctype = self._type_to_c(field.type)
            self.emit(f"{ctype} {field.name};")
        self.indent -= 1
        self.emit("};")

    # ------------------- Генерация утверждений -------------------
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

    def _gen_local_variable(self, node: VariableDeclaration):
        resolved_type = self._resolve_type_alias(node.type)
        ctype = self._type_to_c(resolved_type)
        if node.initializer:
            init = self.gen_expression(node.initializer)
            self.emit_to_main(f"{ctype} {node.name} = {init};")
        else:
            self.emit_to_main(f"{ctype} {node.name};")
        self.var_types[node.name] = node.type
        self.var_types[node.name] = resolved_type

    def _gen_function(self, node: MethodDeclaration):
        if node.name == '_global_init':
            return
        if node.type_params:
            return
        ret_type = self._type_to_c(node.return_type or 'void')
        params = [f"{self._type_to_c(p.type)} {p.name}" for p in node.parameters]
        param_str = ", ".join(params)
        func_name = node.name

        old_main = self.main_code
        self.main_code = []
        self.indent = 0

        self.emit_to_main(f"{ret_type} {func_name}({param_str}) {{")
        self.indent += 1
        self.inside_func = True
        self.func_name = node.name

        if func_name == 'main' and self.global_vars_to_init and not self.is_module:
            self.emit_to_main("_global_init();")

        self._push_scope()
        for p in node.parameters:
            self.var_types[p.name] = p.type
        for stmt in node.body:
            self.gen_statement(stmt)

        if ret_type != 'void':
            if not any(isinstance(s, (ReturnStatement, GivebackStatement)) for s in node.body):
                if ret_type in ('int', 'unsigned int', 'long long'):
                    self.emit_to_main("return 0;")
                elif ret_type in ('float', 'double'):
                    self.emit_to_main("return 0.0;")
                else:
                    self.emit_to_main("return NULL;")
        self._pop_scope()
        self.indent -= 1
        self.emit_to_main("}")
        self.inside_func = False
        self.func_name = None

        old_main.extend(self.main_code)
        self.main_code = old_main

    def _gen_if(self, node: IfStatement):
        cond = self.gen_expression(node.condition)
        self.emit_to_main(f"if ({cond}) {{")
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
        self.emit_to_main(f"while ({cond}) {{")
        self.indent += 1
        self._push_scope()
        for stmt in node.body:
            self.gen_statement(stmt)
        self._pop_scope()
        self.indent -= 1
        self.emit_to_main("}")

    def _gen_for(self, node: ForLoop):
        init = ""
        if node.init:
            if isinstance(node.init, VariableDeclaration):
                ctype = self._type_to_c(node.init.type)
                if node.init.initializer:
                    init = f"{ctype} {node.init.name} = {self.gen_expression(node.init.initializer)}"
                else:
                    init = f"{ctype} {node.init.name}"
                self.var_types[node.init.name] = node.init.type
            else:
                init = self.gen_expression(node.init.expression) if isinstance(node.init, ExpressionStatement) else ""
        cond = self.gen_expression(node.condition) if node.condition else ""
        update = self.gen_expression(node.update) if node.update else ""
        self.emit_to_main(f"for ({init}; {cond}; {update}) {{")
        self.indent += 1
        self._push_scope()
        for stmt in node.body:
            self.gen_statement(stmt)
        self._pop_scope()
        self.indent -= 1
        self.emit_to_main("}")

    def _gen_foreach(self, node: ForEachLoop):
        iterable_type = self._get_expression_type(node.iterable)
        iterable_code = self.gen_expression(node.iterable)

        if iterable_type.startswith('arr<'):
            counter_var = f"__i_{self.temp_counter}"
            self.temp_counter += 1
            self.emit_to_main(f"for (size_t {counter_var} = 0; {counter_var} < arr_len({iterable_code}); {counter_var}++) {{")
            self.indent += 1
            elem_code = f"arr_get({iterable_code}, {counter_var})"
            if isinstance(node.item_decl, VariableDeclaration):
                decl_type = node.item_decl.type or 'any'
                c_decl_type = self._type_to_c(decl_type)
                self.emit_to_main(f"{c_decl_type} {node.item_decl.name} = {elem_code};")
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
            self.emit_to_main(f"arr* {keys_var} = dict_keys({iterable_code});")
            counter_var = f"__i_{self.temp_counter}"
            self.temp_counter += 1
            self.emit_to_main(f"for (size_t {counter_var} = 0; {counter_var} < arr_len({keys_var}); {counter_var}++) {{")
            self.indent += 1
            self.emit_to_main(f"ely_value* __key = arr_get({keys_var}, {counter_var});")
            self.emit_to_main(f"ely_value* __value = dict_get({iterable_code}, __key);")
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
            self.emit_to_main(f"arr_free({keys_var});")
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
            escaped = node.value.replace('"', '\\"')
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
            return f"ely_value_set_key({obj}, \"{node.target.member}\", {value})"
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
        result = 'ely_str_dup("")'
        for part in node.parts:
            if isinstance(part, str):
                escaped = part.replace('"', '\\"')
                result = f'ely_str_concat({result}, "{escaped}")'
            else:
                expr_code = self.gen_expression(part)
                result = f'ely_str_concat({result}, ely_value_to_json({expr_code}))'
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
        if isinstance(node.callee, MemberAccess):
            obj = node.callee.object
            method = node.callee.member
            obj_type = self._get_expression_type(obj)
            obj_code = self.gen_expression(obj)
            if obj_type.startswith('arr<'):
                if method == 'append':
                    if len(node.arguments) != 1:
                        self.error("append expects one argument", node)
                        return ""
                    arg_expr = node.arguments[0]
                    arg_code = self.gen_expression(arg_expr)
                    return f"arr_push({obj_code}, {arg_code})"
                elif method == 'remove':
                    if len(node.arguments) != 1:
                        self.error("remove expects one argument (value)", node)
                        return ""
                    arg_expr = node.arguments[0]
                    arg_code = self.gen_expression(arg_expr)
                    return f"arr_remove_value({obj_code}, {arg_code})"
                elif method == 'insert':
                    if len(node.arguments) != 2:
                        self.error("insert expects two arguments (index, value)", node)
                        return ""
                    index_expr = node.arguments[0]
                    index_code = self.gen_expression(index_expr)
                    value_expr = node.arguments[1]
                    value_code = self.gen_expression(value_expr)
                    return f"arr_insert({obj_code}, {index_code}, {value_code})"
                elif method == 'index':
                    if len(node.arguments) != 1:
                        self.error("index expects one argument (value)", node)
                        return ""
                    arg_expr = node.arguments[0]
                    arg_code = self.gen_expression(arg_expr)
                    return f"arr_index({obj_code}, {arg_code})"
                elif method == 'pop':
                    if len(node.arguments) == 0:
                        return f"arr_pop_value({obj_code})"
                    elif len(node.arguments) == 1:
                        index_expr = node.arguments[0]
                        index_code = self.gen_expression(index_expr)
                        tmp_var = f"__tmp_{self.temp_counter}"
                        self.temp_counter += 1
                        self.emit_to_main(f"ely_value* {tmp_var} = arr_get({obj_code}, {index_code});")
                        self.emit_to_main(f"arr_remove_index({obj_code}, {index_code});")
                        return tmp_var
                    else:
                        self.error("pop expects 0 or 1 argument", node)
                        return ""
                elif method == 'len':
                    return f"ely_int_to_str((int)arr_len({obj_code}))"
            if obj_type.startswith('dict<'):
                if method == 'keys':
                    return f"dict_keys({obj_code})"
                elif method == 'del':
                    if len(node.arguments) != 1:
                        self.error("del expects one argument (key)", node)
                        return ""
                    key_expr = node.arguments[0]
                    key_code = self.gen_expression(key_expr)
                    return f"dict_delete({obj_code}, {key_code})"
                elif method == 'has':
                    if len(node.arguments) != 1:
                        self.error("has expects one argument (key)", node)
                        return ""
                    key_expr = node.arguments[0]
                    key_code = self.gen_expression(key_expr)
                    return f"dict_has({obj_code}, {key_code})"
                elif method == 'toJson':
                    return f"ely_dict_to_json({obj_code})"

        if not isinstance(node.callee, Identifier):
            return ""
        func_name = node.callee.name
        args = [self.gen_expression(arg) for arg in node.arguments]

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

        if func_name == 'print':
            if not node.arguments:
                return 'ely_print("")'
            arg = node.arguments[0]
            arg_code = self.gen_expression(arg)
            return f"ely_print(ely_value_to_json({arg_code}))"

        if func_name == 'println':
            if not node.arguments:
                return 'ely_println("")'
            arg = node.arguments[0]
            arg_code = self.gen_expression(arg)
            return f"ely_println(ely_value_to_json({arg_code}))"

        if func_name == 'jsonify':
            if not node.arguments:
                return 'ely_str_dup("")'
            arg_code = self.gen_expression(node.arguments[0])
            return f"ely_jsonify({arg_code})"
        if func_name == 'dictify':
            if not node.arguments:
                return "dict_new_str()"
            arg_code = self.gen_expression(node.arguments[0])
            return f"ely_dictify({arg_code})"

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
        }
        if func_name in stdlib:
            c_func = stdlib[func_name]
            return f"{c_func}({', '.join(args)})"

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

    def error(self, message: str, node: Expression):
        print(f"Code generation error: {message} at line {node.line}, col {node.col}")