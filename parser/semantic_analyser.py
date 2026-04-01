import sys
import os
from typing import List, Dict, Optional, Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Импортируем всё из parser (включая новые классы)
from parser import *

class SemanticError(Exception):
    def __init__(self, message: str, node: Any):
        self.message = message
        self.node = node
        super().__init__(message)

class Symbol:
    def __init__(self, name: str, kind: str, type_info: Optional[str] = None):
        self.name = name
        self.kind = kind
        self.type = type_info
        self.parameters: Optional[List[Parameter]] = None
        self.is_defined: bool = False
        self.is_extern: bool = False
        self.is_variadic: bool = False
        self.type_params: List[str] = []
        self.fields: List[VariableDeclaration] = []  # добавлено

class Scope:
    def __init__(self, parent: Optional['Scope'] = None):
        self.parent = parent
        self.symbols: Dict[str, Symbol] = {}

    def declare(self, name: str, symbol: Symbol):
        if name in self.symbols:
            raise SemanticError(f"Duplicate declaration: {name}", None)
        self.symbols[name] = symbol

    def lookup(self, name: str) -> Optional[Symbol]:
        if name in self.symbols:
            return self.symbols[name]
        if self.parent:
            return self.parent.lookup(name)
        return None

    def lookup_local(self, name: str) -> Optional[Symbol]:
        return self.symbols.get(name)

class SemanticAnalyzer:
    def __init__(self):
        self.errors: List[str] = []
        self.current_scope = Scope()  # глобальный scope
        self.current_class: Optional[str] = None
        self.current_method: Optional[str] = None
        self.current_function: Optional[str] = None  # для глобальных функций
        self.loop_depth: int = 0
        self.match_depth: int = 0

    def analyze(self, program: Program) -> List[str]:
        try:
            self.visit_program(program)
        except SemanticError as e:
            self.errors.append(e.message)
        return self.errors

    def visit_program(self, node: Program):
        for stmt in node.statements:
            self.visit_statement(stmt)

    def visit_statement(self, node: Statement):
        if isinstance(node, VariableDeclaration):
            self.visit_variable_declaration(node)
        elif isinstance(node, UsingDirective):
            self.visit_using_directive(node)
        elif isinstance(node, ClassDeclaration):
            self.visit_class_declaration(node)
        elif isinstance(node, StructDeclaration):
            self.visit_struct_declaration(node)
        elif isinstance(node, TypeAlias):
            self.visit_type_alias(node)
        elif isinstance(node, NamespaceDeclaration):
            self.visit_namespace_declaration(node)
        elif isinstance(node, ExternFunction):
            self.visit_extern_function(node)
        elif isinstance(node, ConstDeclaration):
            self.visit_const_declaration(node)
        elif isinstance(node, StaticVariable):
            self.visit_static_variable(node)
        elif isinstance(node, MethodDeclaration):
            self.visit_method_declaration(node)  # для глобальных функций
        elif isinstance(node, IfStatement):
            self.visit_if_statement(node)
        elif isinstance(node, WhileLoop):
            self.visit_while_loop(node)
        elif isinstance(node, ForLoop):
            self.visit_for_loop(node)
        elif isinstance(node, ForEachLoop):
            self.visit_for_each_loop(node)
        elif isinstance(node, MatchStatement):
            self.visit_match_statement(node)
        elif isinstance(node, AsafeBlock):
            self.visit_asafe_block(node)
        elif isinstance(node, ThrowStatement):
            self.visit_throw_statement(node)
        elif isinstance(node, GivebackStatement):
            self.visit_giveback_statement(node)
        elif isinstance(node, ReturnStatement):
            self.visit_return_statement(node)
        elif isinstance(node, CollapseStatement):
            self.visit_collapse_statement(node)
        elif isinstance(node, BreakStatement):
            self.visit_break_statement(node)
        elif isinstance(node, ExpressionStatement):
            self.visit_expression(node.expression)
        else:
            self.error(f"Unknown statement type: {type(node).__name__}", node)

    def error(self, message: str, node: Any):
        self.errors.append(f"{message} at {node.line}:{node.col}")

    def visit_using_directive(self, node: UsingDirective):
        pass

    def visit_variable_declaration(self, node: VariableDeclaration):
        if node.type is None:
            self.error("Variable declaration missing type", node)
            return
        local = self.current_scope.lookup_local(node.name)
        if local:
            self.error(f"Variable '{node.name}' already declared in this scope", node)
            return
        # Раскрываем тип через псевдонимы
        resolved_type = self.resolve_type(node.type)
        if not self.is_valid_type(resolved_type):
            self.error(f"Invalid type '{node.type}' in variable declaration", node)
            return
        sym = Symbol(node.name, 'variable', resolved_type)
        self.current_scope.declare(node.name, sym)
        if node.initializer:
            expr_type = self.visit_expression(node.initializer)
            if expr_type and not self.is_type_compatible(resolved_type, expr_type):
                self.error(f"Cannot initialize {node.type} with {expr_type}", node)

    def visit_class_declaration(self, node: ClassDeclaration):
        existing = self.current_scope.lookup(node.name)
        if existing:
            self.error(f"Class '{node.name}' already declared", node)
            return
        class_sym = Symbol(node.name, 'class')
        self.current_scope.declare(node.name, class_sym)
        previous_scope = self.current_scope
        self.current_scope = Scope(previous_scope)
        self.current_class = node.name
        if node.extends:
            parent = previous_scope.lookup(node.extends)
            if not parent or parent.kind != 'class':
                self.error(f"Parent class '{node.extends}' not found or not a class", node)
        for method in node.methods:
            self.visit_method_declaration(method)
        self.current_scope = previous_scope
        self.current_class = None

    def visit_struct_declaration(self, node: StructDeclaration):
        existing = self.current_scope.lookup(node.name)
        if existing:
            self.error(f"Struct '{node.name}' already declared", node)
            return
        struct_sym = Symbol(node.name, 'struct')
        struct_sym.fields = node.fields  # сохраняем поля
        self.current_scope.declare(node.name, struct_sym)
        previous_scope = self.current_scope
        self.current_scope = Scope(previous_scope)
        for field in node.fields:
            self.visit_variable_declaration(field)
        self.current_scope = previous_scope

    def visit_type_alias(self, node: TypeAlias):
        existing = self.current_scope.lookup(node.name)
        if existing:
            self.error(f"Type alias '{node.name}' already declared", node)
            return
        # Проверяем целевой тип
        resolved_target = self.resolve_type(node.target_type)
        if not self.is_valid_type(resolved_target):
            self.error(f"Invalid target type '{node.target_type}' for type alias", node)
            return
        sym = Symbol(node.name, 'typealias', node.target_type)  # храним исходный
        self.current_scope.declare(node.name, sym)

    def visit_namespace_declaration(self, node: NamespaceDeclaration):
        existing = self.current_scope.lookup(node.name)
        if existing:
            self.error(f"Namespace '{node.name}' already declared", node)
            return
        namespace_sym = Symbol(node.name, 'namespace')
        self.current_scope.declare(node.name, namespace_sym)
        previous_scope = self.current_scope
        self.current_scope = Scope(previous_scope)
        for stmt in node.body:
            self.visit_statement(stmt)
        self.current_scope = previous_scope

    def visit_extern_function(self, node: ExternFunction):
        existing = self.current_scope.lookup(node.name)
        if existing:
            self.error(f"Extern function '{node.name}' already declared", node)
            return
        # Проверяем типы параметров, игнорируя вариативный параметр
        for param in node.parameters:
            if param.type == '...':
                continue
            if not self.is_valid_type(self.resolve_type(param.type)):
                self.error(f"Invalid type '{param.type}' for parameter '{param.name}'", node)
        if node.return_type and node.return_type != '...' and not self.is_valid_type(self.resolve_type(node.return_type)):
            self.error(f"Invalid return type '{node.return_type}' for extern function", node)
        sym = Symbol(node.name, 'function', node.return_type)
        sym.parameters = node.parameters
        sym.is_extern = True
        sym.is_defined = True
        sym.is_variadic = any(p.type == '...' for p in node.parameters)  # добавляем флаг
        self.current_scope.declare(node.name, sym)

    def visit_const_declaration(self, node: ConstDeclaration):
        existing = self.current_scope.lookup(node.name)
        if existing:
            self.error(f"Const '{node.name}' already declared", node)
            return
        resolved_type = self.resolve_type(node.type)
        if not self.is_valid_type(resolved_type):
            self.error(f"Invalid type '{node.type}' for const", node)
            return
        expr_type = self.visit_expression(node.value)
        if expr_type and not self.is_type_compatible(resolved_type, expr_type):
            self.error(f"Cannot assign {expr_type} to const {node.type}", node)
        sym = Symbol(node.name, 'const', resolved_type)
        self.current_scope.declare(node.name, sym)

    def visit_static_variable(self, node: StaticVariable):
        existing = self.current_scope.lookup(node.name)
        if existing:
            self.error(f"Static variable '{node.name}' already declared", node)
            return
        resolved_type = self.resolve_type(node.type)
        if not self.is_valid_type(resolved_type):
            self.error(f"Invalid type '{node.type}' for static variable", node)
            return
        if node.initializer:
            expr_type = self.visit_expression(node.initializer)
            if expr_type and not self.is_type_compatible(resolved_type, expr_type):
                self.error(f"Cannot initialize static {node.type} with {expr_type}", node)
        sym = Symbol(node.name, 'static', resolved_type)
        self.current_scope.declare(node.name, sym)

    def visit_method_declaration(self, node: MethodDeclaration):
        existing = self.current_scope.lookup(node.name)
        if existing:
            self.error(f"Function '{node.name}' already declared", node)
            return

        # Создаём символ (тип возврата пока не проверяем)
        sym = Symbol(node.name, 'function', node.return_type)
        sym.parameters = node.parameters
        sym.type_params = node.type_params
        sym.is_extern = False

        # Создаём новую область для тела функции
        previous_scope = self.current_scope
        self.current_scope = Scope(previous_scope)
        self.current_function = node.name

        # Добавляем параметры типов в область видимости
        for tp in node.type_params:
            self.current_scope.declare(tp, Symbol(tp, 'typevar', None))

        # Проверяем тип возврата (теперь видны параметры типов)
        if node.return_type and node.return_type != 'void':
            resolved_return = self.resolve_type(node.return_type)
            if not self.is_valid_type(resolved_return):
                self.error(f"Invalid return type '{node.return_type}'", node)

        # Проверяем типы параметров (тоже видны параметры типов)
        for param in node.parameters:
            if not self.is_valid_type(self.resolve_type(param.type)):
                self.error(f"Invalid type '{param.type}' for parameter '{param.name}'", node)

        # Регистрируем символ в родительской области
        previous_scope.declare(node.name, sym)

        # Добавляем параметры функции в текущую область
        for param in node.parameters:
            param_sym = Symbol(param.name, 'variable', param.type)
            self.current_scope.declare(param.name, param_sym)

        # Обрабатываем тело
        for stmt in node.body:
            self.visit_statement(stmt)

        self.current_scope = previous_scope
        self.current_function = None

    def visit_if_statement(self, node: IfStatement):
        cond_type = self.visit_expression(node.condition)
        if cond_type and cond_type != 'bool':
            self.error(f"If condition must be bool, got {cond_type}", node)
        previous_scope = self.current_scope
        self.current_scope = Scope(previous_scope)
        for stmt in node.then_body:
            self.visit_statement(stmt)
        self.current_scope = previous_scope

        if node.else_body:
            previous_scope = self.current_scope
            self.current_scope = Scope(previous_scope)
            for stmt in node.else_body:
                self.visit_statement(stmt)
            self.current_scope = previous_scope

    def visit_while_loop(self, node: WhileLoop):
        cond_type = self.visit_expression(node.condition)
        if cond_type and cond_type != 'bool':
            self.error(f"While condition must be bool, got {cond_type}", node)
        self.loop_depth += 1
        previous_scope = self.current_scope
        self.current_scope = Scope(previous_scope)
        for stmt in node.body:
            self.visit_statement(stmt)
        self.current_scope = previous_scope
        self.loop_depth -= 1

    def visit_for_loop(self, node: ForLoop):
        previous_scope = self.current_scope
        self.current_scope = Scope(previous_scope)
        if node.init:
            self.visit_statement(node.init)
        if node.condition:
            cond_type = self.visit_expression(node.condition)
            if cond_type and cond_type != 'bool':
                self.error(f"For condition must be bool, got {cond_type}", node)
        if node.update:
            self.visit_expression(node.update)
        self.loop_depth += 1
        for stmt in node.body:
            self.visit_statement(stmt)
        self.loop_depth -= 1
        self.current_scope = previous_scope

    def visit_for_each_loop(self, node: ForEachLoop):
        previous_scope = self.current_scope
        self.current_scope = Scope(previous_scope)

        # Получаем тип итерабеля
        iterable_type = self.visit_expression(node.iterable)
        if iterable_type is None:
            # ошибка уже зарегистрирована
            self.current_scope = previous_scope
            return

        # Выводим тип элемента
        if iterable_type.startswith('arr<'):
            # arr<T> -> T
            elem_type = iterable_type[4:-1].strip()
        elif iterable_type.startswith('dict<'):
            # dict<K,V> -> V (значение)
            inner = iterable_type[5:-1].strip()
            depth = 0
            comma_pos = -1
            for i, ch in enumerate(inner):
                if ch == '<':
                    depth += 1
                elif ch == '>':
                    depth -= 1
                elif ch == ',' and depth == 0:
                    comma_pos = i
                    break
            if comma_pos == -1:
                elem_type = 'any'
            else:
                elem_type = inner[comma_pos+1:].strip()
        else:
            self.error(f"For-each iterable must be array or dict, got {iterable_type}", node.iterable)
            self.current_scope = previous_scope
            return

        # Обрабатываем объявление элемента
        if isinstance(node.item_decl, VariableDeclaration):
            if node.item_decl.type is not None:
                declared_type = self.resolve_type(node.item_decl.type)
                if not self.is_type_compatible(declared_type, elem_type):
                    self.error(f"Cannot assign {elem_type} to {declared_type} in for-each", node.item_decl)
                # Используем объявленный тип
                final_type = declared_type
            else:
                final_type = elem_type
            # Создаём символ
            sym = Symbol(node.item_decl.name, 'variable', final_type)
            self.current_scope.declare(node.item_decl.name, sym)
        else:
            self.error("For-each item must be a variable declaration", node.item_decl)
            self.current_scope = previous_scope
            return

        self.loop_depth += 1
        for stmt in node.body:
            self.visit_statement(stmt)
        self.loop_depth -= 1
        self.current_scope = previous_scope

    def visit_match_statement(self, node: MatchStatement):
        expr_type = self.visit_expression(node.expression)
        self.match_depth += 1
        for case in node.cases:
            case_value_type = self.visit_expression(case.value)
            if expr_type and case_value_type and not self.is_type_compatible(expr_type, case_value_type):
                self.error(f"Case value type {case_value_type} does not match match expression type {expr_type}", case)
            previous_scope = self.current_scope
            self.current_scope = Scope(previous_scope)
            for stmt in case.body:
                self.visit_statement(stmt)
            self.current_scope = previous_scope
        if node.default_body:
            previous_scope = self.current_scope
            self.current_scope = Scope(previous_scope)
            for stmt in node.default_body:
                self.visit_statement(stmt)
            self.current_scope = previous_scope
        self.match_depth -= 1

    def visit_asafe_block(self, node: AsafeBlock):
        previous_scope = self.current_scope
        self.current_scope = Scope(previous_scope)
        for stmt in node.body:
            self.visit_statement(stmt)
        self.current_scope = previous_scope

        if node.except_handler:
            previous_scope = self.current_scope
            self.current_scope = Scope(previous_scope)
            if node.except_handler.parameter:
                param_sym = Symbol(node.except_handler.parameter, 'variable', node.except_handler.exception_type)
                self.current_scope.declare(node.except_handler.parameter, param_sym)
            for stmt in node.except_handler.body:
                self.visit_statement(stmt)
            self.current_scope = previous_scope

    def visit_throw_statement(self, node: ThrowStatement):
        # Проверяем, что значение имеет какой-то тип (можно позже проверить совместимость с типом except)
        self.visit_expression(node.value)

    def visit_giveback_statement(self, node: GivebackStatement):
        if not self.current_function and not self.current_method:
            self.error("giveback outside function/method", node)
            return
        expected = self.get_current_return_type()
        if node.value:
            val_type = self.visit_expression(node.value)
            if expected == 'void':
                self.error("giveback with value in void function", node)
            elif val_type and not self.is_type_compatible(expected, val_type):
                self.error(f"giveback value type {val_type} does not match expected {expected}", node)
        else:
            if expected != 'void':
                self.error(f"giveback without value in non-void function (expected {expected})", node)

    def visit_return_statement(self, node: ReturnStatement):
        if not self.current_function and not self.current_method:
            self.error("return outside function/method", node)
            return
        expected = self.get_current_return_type()
        if node.value:
            val_type = self.visit_expression(node.value)
            if expected == 'void':
                self.error("return with value in void function", node)
            elif val_type and not self.is_type_compatible(expected, val_type):
                self.error(f"return value type {val_type} does not match expected {expected}", node)
        else:
            if expected != 'void':
                self.error(f"return without value in non-void function (expected {expected})", node)

    def visit_collapse_statement(self, node: CollapseStatement):
        if node.name in self.current_scope.symbols:
            del self.current_scope.symbols[node.name]
        else:
            sym = self.current_scope.lookup(node.name)
            if sym:
                self.error(f"Cannot collapse variable '{node.name}' from outer scope", node)
            else:
                self.error(f"Variable '{node.name}' not declared", node)

    def visit_break_statement(self, node: BreakStatement):
        if self.loop_depth == 0 and self.match_depth == 0:
            self.error("break outside loop or match", node)

    def visit_expression(self, node: Expression) -> Optional[str]:
        if isinstance(node, Literal):
            return self._literal_type(node)
        elif isinstance(node, Identifier):
            return self._identifier_type(node)
        elif isinstance(node, BinaryOp):
            return self._binary_op_type(node)
        elif isinstance(node, UnaryOp):
            return self._unary_op_type(node)
        elif isinstance(node, Assignment):
            return self._assignment_type(node)
        elif isinstance(node, Call):
            return self._call_type(node)
        elif isinstance(node, MemberAccess):
            return self._member_access_type(node)
        elif isinstance(node, Conditional):
            return self._conditional_type(node)
        elif isinstance(node, TagAnnotation):
            return self.visit_expression(node.expression)
        elif isinstance(node, FString):
            return self._fstring_type(node)
        elif isinstance(node, ArrayLiteral):
            return self._array_literal_type(node)
        elif isinstance(node, DictLiteral):
            return self._dict_literal_type(node)
        elif isinstance(node, IndexExpression):
            return self._index_expression_type(node)
        else:
            self.error(f"Unknown expression type: {type(node).__name__}", node)
            return None

    def _literal_type(self, node: Literal) -> str:
        if isinstance(node.value, bool):
            return 'bool'
        elif isinstance(node.value, int):
            return 'int'
        elif isinstance(node.value, float):
            return 'flt'
        elif isinstance(node.value, str):
            return 'str'
        else:
            return 'any'

    def _identifier_type(self, node: Identifier) -> Optional[str]:
        sym = self.current_scope.lookup(node.name)
        if not sym:
            self.error(f"Undefined identifier '{node.name}'", node)
            return None
        if sym.kind in ('variable', 'parameter', 'const', 'static'):
            return sym.type
        elif sym.kind == 'function':
            return 'function'
        elif sym.kind == 'class':
            return 'class'
        elif sym.kind == 'struct':
            return 'struct'
        elif sym.kind == 'typealias':
            return self.resolve_type(sym.type)
        else:
            return None

    def _binary_op_type(self, node: BinaryOp) -> Optional[str]:
        left_type = self.visit_expression(node.left)
        right_type = self.visit_expression(node.right)
        if left_type is None or right_type is None:
            return None
        op = node.operator
        if op in ('+', '-', '*', '/', '%'):
            if self.is_numeric(left_type) and self.is_numeric(right_type):
                return left_type
            else:
                self.error(f"Operator '{op}' requires numeric types, got {left_type} and {right_type}", node)
                return None
        elif op in ('<', '>', '<=', '>=', '==', '!='):
            if self.is_comparable(left_type, right_type):
                return 'bool'
            else:
                self.error(f"Cannot compare {left_type} and {right_type} with '{op}'", node)
                return None
        elif op in ('&&', '||'):
            if left_type == 'bool' and right_type == 'bool':
                return 'bool'
            else:
                self.error(f"Logical operator '{op}' requires bool operands", node)
                return None
        else:
            self.error(f"Unknown binary operator '{op}'", node)
            return None

    def _unary_op_type(self, node: UnaryOp) -> Optional[str]:
        expr_type = self.visit_expression(node.operand)
        if expr_type is None:
            return None
        op = node.operator
        if op == '!':
            if expr_type == 'bool':
                return 'bool'
            else:
                self.error(f"Logical not requires bool operand, got {expr_type}", node)
                return None
        elif op == '-':
            if self.is_numeric(expr_type):
                return expr_type
            else:
                self.error(f"Unary minus requires numeric operand, got {expr_type}", node)
                return None
        elif op == '*':
            return expr_type
        else:
            self.error(f"Unknown unary operator '{op}'", node)
            return None

    def _assignment_type(self, node: Assignment) -> Optional[str]:
        target_type = self.visit_expression(node.target)
        value_type = self.visit_expression(node.value)
        if target_type is None or value_type is None:
            return None
        if not self.is_type_compatible(target_type, value_type):
            self.error(f"Cannot assign {value_type} to {target_type}", node)
        return target_type

    def _call_type(self, node: Call) -> Optional[str]:
        if isinstance(node.callee, Identifier):
            sym = self.current_scope.lookup(node.callee.name)
            if sym and sym.kind == 'function':
                # Если у функции есть параметры типов, выводим их из аргументов
                concrete_types = {}
                if sym.type_params:
                    # Простейший вывод: сопоставляем типы аргументов с параметрами
                    # Для каждого параметра функции, если его тип — один из type_params,
                    # связываем его с типом аргумента.
                    for arg, param in zip(node.arguments, sym.parameters):
                        arg_type = self.visit_expression(arg)
                        if arg_type is None:
                            continue
                        # Раскрываем тип параметра (может быть typevar)
                        param_type = param.type
                        if param_type in sym.type_params:
                            # связываем param_type с arg_type
                            concrete_types[param_type] = arg_type
                        # Если в параметре есть вложенные параметры (например, arr<T>),
                        # можно рекурсивно пройти, но для простоты пока не делаем.
                    # Проверяем, что все параметры типов определены
                    for tp in sym.type_params:
                        if tp not in concrete_types:
                            self.error(f"Could not infer type parameter '{tp}'", node)
                            return None
                    # Здесь нужно было бы создать экземпляр функции (мономорфизацию),
                    # но это уже задача бэкенда. Пока просто вернём тип (его тоже надо заменить).
                    # Для типа возврата заменим параметры на конкретные типы.
                    return_type = sym.type
                    for tp, ct in concrete_types.items():
                        # замена в строке типа (простая)
                        return_type = return_type.replace(tp, ct)
                    return return_type
                else:
                    # обычная функция
                    has_variadic = hasattr(sym, 'is_variadic') and sym.is_variadic
                    min_args = len(sym.parameters) - (1 if has_variadic else 0)
                    if has_variadic:
                        if len(node.arguments) < min_args:
                            self.error(f"Function '{node.callee.name}' expects at least {min_args} arguments, got {len(node.arguments)}", node)
                    else:
                        if len(node.arguments) != len(sym.parameters):
                            self.error(f"Function '{node.callee.name}' expects {len(sym.parameters)} arguments, got {len(node.arguments)}", node)
                    for i, (arg, param) in enumerate(zip(node.arguments, sym.parameters)):
                        if param.type == '...':
                            break
                        arg_type = self.visit_expression(arg)
                        if arg_type and not self.is_type_compatible(param.type, arg_type):
                            self.error(f"Argument {i+1} of call to '{node.callee.name}' expected {param.type}, got {arg_type}", node)
                    return sym.type
        elif isinstance(node.callee, MemberAccess):
            # можно добавить методы обобщённых типов
            pass
        return None

    def _member_access_type(self, node: MemberAccess) -> Optional[str]:
        obj_type = self.visit_expression(node.object)
        if obj_type is None:
            return None
        if obj_type.startswith('dict<'):
            # Извлекаем тип значения из dict<K,V>
            inner = obj_type[5:-1]  # dict<...>
            # Найдём запятую вне вложенных скобок
            depth = 0
            comma_pos = -1
            for i, ch in enumerate(inner):
                if ch == '<':
                    depth += 1
                elif ch == '>':
                    depth -= 1
                elif ch == ',' and depth == 0:
                    comma_pos = i
                    break
            if comma_pos == -1:
                self.error(f"Invalid dict type {obj_type}", node)
                return None
            key_type = inner[:comma_pos].strip()
            value_type = inner[comma_pos+1:].strip()
            # Ключ при dot-доступе всегда строка. Разрешаем key_type == 'str' или 'any'.
            if key_type not in ('str', 'any'):
                self.error(f"Dict key must be string for dot access, got {key_type}", node)
            return value_type
        else:
            # Для структур/классов – поиск поля
            sym = self.current_scope.lookup(obj_type)
            if sym and sym.kind == 'struct':
                for field in sym.fields:
                    if field.name == node.member:
                        # Возвращаем тип поля
                        return self.resolve_type(field.type)
                self.error(f"Struct '{obj_type}' has no field '{node.member}'", node)
                return None
            else:
                self.error(f"Member access not implemented for type {obj_type}", node)
                return None

    def _conditional_type(self, node: Conditional) -> Optional[str]:
        cond_type = self.visit_expression(node.condition)
        if cond_type and cond_type != 'bool':
            self.error(f"Condition in ternary must be bool, got {cond_type}", node)
        then_type = self.visit_expression(node.then_expr)
        else_type = self.visit_expression(node.else_expr)
        if then_type is None or else_type is None:
            return None
        if not self.is_type_compatible(then_type, else_type):
            self.error(f"Ternary branches have different types: {then_type} and {else_type}", node)
        return then_type

    def _fstring_type(self, node: FString) -> str:
        # Проверяем все вставки-выражения
        for part in node.parts:
            if isinstance(part, Expression):
                self.visit_expression(part)
        return 'str'

    def _array_literal_type(self, node: ArrayLiteral) -> str:
        if not node.elements:
            # Пустой массив – тип не определён, будем считать any
            return 'arr<any>'
        first_type = self.visit_expression(node.elements[0])
        for elem in node.elements[1:]:
            elem_type = self.visit_expression(elem)
            if not self.is_type_compatible(first_type, elem_type):
                self.error(f"Array literal elements must have same type: {first_type} vs {elem_type}", node)
        return f'arr<{first_type}>'

    def _dict_literal_type(self, node: DictLiteral) -> str:
        if not node.pairs:
            return 'dict<any, any>'
        first_key_type = self.visit_expression(node.pairs[0].key)
        first_val_type = self.visit_expression(node.pairs[0].value)
        # проверяем, что все ключи одного типа
        for pair in node.pairs[1:]:
            key_type = self.visit_expression(pair.key)
            if not self.is_type_compatible(first_key_type, key_type):
                # ключи разных типов – используем any
                first_key_type = 'any'
        # проверяем, что все значения одного типа
        val_type = first_val_type
        for pair in node.pairs[1:]:
            val_type2 = self.visit_expression(pair.value)
            if not self.is_type_compatible(val_type, val_type2):
                # значения разных типов – используем any
                val_type = 'any'
        return f'dict<{first_key_type}, {val_type}>'

    def _index_expression_type(self, node: IndexExpression) -> Optional[str]:
        target_type = self.visit_expression(node.target)
        index_type = self.visit_expression(node.index)
        if target_type is None or index_type is None:
            return None
        # Определяем тип элемента массива или словаря
        if target_type.startswith('arr<'):
            # Извлекаем внутренний тип
            inner = target_type[4:-1]  # arr<...>
            if not self.is_numeric(index_type):
                self.error(f"Array index must be numeric, got {index_type}", node)
            return inner
        elif target_type.startswith('dict<'):
            # dict<K,V>
            # Разбираем типы ключа и значения
            inner = target_type[5:-1]  # dict<...>
            # Найдём запятую вне вложенных скобок
            depth = 0
            comma_pos = -1
            for i, ch in enumerate(inner):
                if ch == '<':
                    depth += 1
                elif ch == '>':
                    depth -= 1
                elif ch == ',' and depth == 0:
                    comma_pos = i
                    break
            if comma_pos == -1:
                self.error(f"Invalid dict type {target_type}", node)
                return None
            key_type = inner[:comma_pos].strip()
            val_type = inner[comma_pos+1:].strip()
            if not self.is_type_compatible(key_type, index_type):
                self.error(f"Dict key type mismatch: expected {key_type}, got {index_type}", node)
            return val_type
        else:
            self.error(f"Indexing not supported for type {target_type}", node)
            return None

    def resolve_type(self, type_name: str) -> str:
        # Обработка указателей
        if type_name.endswith('*'):
            inner = type_name[:-1].strip()
            resolved_inner = self.resolve_type(inner)
            return f"{resolved_inner}*"
        # Если это параметризованный тип (arr<...>, dict<...>), раскрываем внутренние типы
        if type_name.startswith('arr<') and type_name.endswith('>'):
            inner = type_name[4:-1].strip()
            resolved_inner = self.resolve_type(inner)
            return f'arr<{resolved_inner}>'
        if type_name.startswith('dict<') and type_name.endswith('>'):
            inner = type_name[5:-1].strip()
            # Разделяем на ключ и значение с учётом вложенности
            depth = 0
            comma_pos = -1
            for i, ch in enumerate(inner):
                if ch == '<':
                    depth += 1
                elif ch == '>':
                    depth -= 1
                elif ch == ',' and depth == 0:
                    comma_pos = i
                    break
            if comma_pos == -1:
                # Может быть, это dict без параметров (уже обработано ранее)
                return type_name
            key_part = inner[:comma_pos].strip()
            val_part = inner[comma_pos+1:].strip()
            resolved_key = self.resolve_type(key_part)
            resolved_val = self.resolve_type(val_part)
            return f'dict<{resolved_key}, {resolved_val}>'
        # Простой тип
        sym = self.current_scope.lookup(type_name)
        if sym and sym.kind == 'typevar':
            return type_name
        if sym and sym.kind == 'typealias':
            return self.resolve_type(sym.type)
        return type_name

    def is_valid_type(self, type_name: str) -> bool:
        if type_name == '...':
            return True
        # Разбираем указатели
        if type_name.endswith('*'):
            inner = type_name[:-1].strip()
            return self.is_valid_type(inner)
        # Проверка typevar
        sym = self.current_scope.lookup(type_name)
        if sym and sym.kind == 'typevar':
            return True
        # Проверка примитивных типов
        if type_name in ('void', 'bool', 'int', 'uint', 'more', 'umore', 'flt', 'double', 'noised', 'str', 'char', 'byte', 'ubyte', 'any'):
            return True
        # Проверка параметризованных типов
        if type_name.startswith('arr<') and type_name.endswith('>'):
            inner = type_name[4:-1].strip()
            return self.is_valid_type(inner)
        if type_name.startswith('dict<') and type_name.endswith('>'):
            inner = type_name[5:-1].strip()
            depth = 0
            comma_pos = -1
            for i, ch in enumerate(inner):
                if ch == '<':
                    depth += 1
                elif ch == '>':
                    depth -= 1
                elif ch == ',' and depth == 0:
                    comma_pos = i
                    break
            if comma_pos == -1:
                return False
            key_part = inner[:comma_pos].strip()
            val_part = inner[comma_pos+1:].strip()
            return self.is_valid_type(key_part) and self.is_valid_type(val_part)
        # Пользовательские типы (классы, структуры, псевдонимы)
        sym = self.current_scope.lookup(type_name)
        if sym and sym.kind in ('class', 'struct', 'typealias'):
            return True
        return False

    def is_numeric(self, type_name: str) -> bool:
        # Примитивные числовые типы
        if type_name in ('int', 'uint', 'more', 'umore', 'flt', 'double', 'noised', 'byte', 'ubyte'):
            return True
        return False

    def is_comparable(self, left: str, right: str) -> bool:
        if self.is_numeric(left) and self.is_numeric(right):
            return True
        if left == 'bool' and right == 'bool':
            return True
        if left == 'str' and right == 'str':
            return True
        if left == 'any' or right == 'any':
            return True
        return False

    def is_type_compatible(self, target: str, source: str) -> bool:
        target_resolved = self.resolve_type(target)
        source_resolved = self.resolve_type(source)
        if target_resolved == source_resolved:
            return True
        if target_resolved == 'any' or source_resolved == 'any':
            return True
        if self.is_numeric(target_resolved) and self.is_numeric(source_resolved):
            return True
        # Если target – массив, а source – массив, сравниваем внутренние типы
        if target_resolved.startswith('arr<') and source_resolved.startswith('arr<'):
            t_inner = target_resolved[4:-1].strip()
            s_inner = source_resolved[4:-1].strip()
            return self.is_type_compatible(t_inner, s_inner)
        # Если target – словарь, сравниваем ключ и значение
        if target_resolved.startswith('dict<') and source_resolved.startswith('dict<'):
            t_inner = target_resolved[5:-1].strip()
            s_inner = source_resolved[5:-1].strip()
            t_key, t_val = self._split_dict_types(t_inner)
            s_key, s_val = self._split_dict_types(s_inner)
            if t_key is None or t_val is None:
                return False
            return self.is_type_compatible(t_key, s_key) and self.is_type_compatible(t_val, s_val)
        return False

    def _split_dict_types(self, inner: str):
        """Вспомогательная: разделяет строку dict<key,value> на key и value с учётом вложенности."""
        depth = 0
        comma_pos = -1
        for i, ch in enumerate(inner):
            if ch == '<':
                depth += 1
            elif ch == '>':
                depth -= 1
            elif ch == ',' and depth == 0:
                comma_pos = i
                break
        if comma_pos == -1:
            return None, None
        key = inner[:comma_pos].strip()
        val = inner[comma_pos+1:].strip()
        return key, val

    def get_current_return_type(self) -> Optional[str]:
        if self.current_method:
            sym = self.current_scope.lookup(self.current_method)
            if sym:
                return sym.type
        if self.current_function:
            sym = self.current_scope.lookup(self.current_function)
            if sym:
                return sym.type
        return 'void'