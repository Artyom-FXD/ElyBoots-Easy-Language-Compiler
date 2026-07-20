import sys
import os
from typing import List, Dict, Optional, Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from parser import *


class SemanticError(Exception):
    """
    Exception raised for semantic errors during analysis.

    Indicates violations of language semantics such as type mismatches,
    undefined identifiers, or incorrect usage of language constructs.

    Исключение, вызываемое при семантических ошибках во время анализа.
    Указывает на нарушения семантики языка, такие как несоответствие типов,
    неопределённые идентификаторы или неправильное использование конструкций языка.
    """

    def __init__(self, message: str, node: Any = None):
        self.message = message
        self.node = node
        super().__init__(message)


class Symbol:
    """
    Represents a symbol in the symbol table.

    Stores information about declared entities including variables, functions,
    classes, structs, and type aliases with their associated metadata.

    Представляет символ в таблице символов.
    Хранит информацию о объявленных сущностях, включая переменные, функции,
    классы, структуры и псевдонимы типов с соответствующими метаданными.
    """

    def __init__(self, name: str, kind: str, type_info: Optional[str] = None):
        self.name: str = name
        self.kind: str = kind  # 'variable', 'function', 'class', 'struct', 'typealias', 'namespace', 'interface', 'const', 'static', 'typevar'
        self.type: Optional[str] = type_info
        self.parameters: Optional[List[Any]] = None
        self.is_defined: bool = False
        self.is_extern: bool = False
        self.is_variadic: bool = False
        self.is_sealed: bool = False
        self.is_abstract: bool = False
        self.type_params: List[str] = []
        self.fields: List[Any] = []
        self.properties: List[Any] = []
        self.all_methods: List[Any] = []
        self.static_methods: List[Any] = []
        self.parent_class: Optional[str] = None
        self.methods: List[Any] = []
        self.scope: Optional['Scope'] = None


class Scope:
    """
    Manages a lexical scope with symbol declarations.

    Provides hierarchical symbol lookup where inner scopes can access
    symbols from outer scopes but not vice versa.

    Управляет лексической областью видимости с объявлениями символов.
    Обеспечивает иерархический поиск символов, где внутренние области видимости
    могут получать доступ к символам из внешних областей, но не наоборот.
    """

    def __init__(self, parent: Optional['Scope'] = None):
        self.parent: Optional['Scope'] = parent
        self.symbols: Dict[str, Symbol] = {}

    def declare(self, name: str, symbol: Symbol):
        """
        Declares a symbol in the current scope.

        Declares a new symbol, raising an error if a symbol with the same
        name already exists in this scope.

        Объявляет символ в текущей области видимости.
        Объявляет новый символ, вызывая ошибку, если символ с таким же
        именем уже существует в этой области видимости.
        """
        if name in self.symbols:
            raise SemanticError(f"Duplicate declaration: {name}", None)
        self.symbols[name] = symbol

    def lookup(self, name: str) -> Optional[Symbol]:
        """
        Looks up a symbol in the current scope and its parents.

        Searches for a symbol by name, traversing up the parent chain
        until found or until the global scope is reached.

        Ищет символ в текущей области видимости и её родителях.
        Выполняет поиск символа по имени, поднимаясь по цепочке родителей
        до тех пор, пока символ не будет найден или не будет достигнута глобальная область.
        """
        if name in self.symbols:
            return self.symbols[name]
        if self.parent:
            return self.parent.lookup(name)
        return None

    def lookup_local(self, name: str) -> Optional[Symbol]:
        """
        Looks up a symbol only in the current scope.

        Searches for a symbol by name without traversing to parent scopes.

        Ищет символ только в текущей области видимости.
        Выполняет поиск символа по имени без перехода к родительским областям.
        """
        return self.symbols.get(name)


class SemanticAnalyzer:
    """
    Performs semantic analysis on the AST.

    Validates type correctness, scope rules, inheritance relationships,
    and all other semantic constraints of the Ely language.

    Выполняет семантический анализ AST.
    Проверяет корректность типов, правила областей видимости, отношения наследования
    и все остальные семантические ограничения языка Ely.
    """

    def __init__(self):
        self.errors: List[str] = []
        self.current_scope: Scope = Scope()
        self.current_class: Optional[str] = None
        self.current_method: Optional[str] = None
        self.current_function: Optional[str] = None
        self.loop_depth: int = 0
        self.match_depth: int = 0
        self.classes_ast: Dict[str, ClassDeclaration] = {}
        self.namespace_names: set = set()
        self.namespace_scopes: Dict[str, Scope] = {}

    def analyze(self, program: Program) -> List[str]:
        """
        Analyzes the entire program AST.

        Entry point for semantic analysis that processes all statements
        and returns a list of detected errors.

        Анализирует всё AST программы.
        Точка входа для семантического анализа, которая обрабатывает все инструкции
        и возвращает список обнаруженных ошибок.
        """
        try:
            self.visit_program(program)
        except SemanticError as e:
            self.errors.append(e.message)
        return self.errors

    def visit_program(self, node: Program):
        """Visits and analyzes a program node."""
        for stmt in node.statements:
            self.visit_statement(stmt)

    def visit_statement(self, node: Statement):
        """Dispatches to the appropriate visit method for a statement."""
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
            self.visit_method_declaration(node)
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
        elif isinstance(node, GlobalCBlock):
            pass
        elif isinstance(node, InterfaceDeclaration):
            self.visit_interface_declaration(node)
        elif isinstance(node, ImplDeclaration):
            self.visit_impl_declaration(node)
        elif isinstance(node, Assignment):
            self.visit_expression(node.target)
            self.visit_expression(node.value)
        else:
            self.error(f"Unknown statement type: {type(node).__name__}", node)

    def error(self, message: str, node: Any = None):
        """Records a semantic error with location information."""
        if node and hasattr(node, 'line') and hasattr(node, 'col'):
            self.errors.append(f"{message} at {node.line}:{node.col}")
        else:
            self.errors.append(message)

    def visit_using_directive(self, node: UsingDirective):
        """
        Processes a using directive for namespace imports.

        Импортирует символы пространства имён в текущую область видимости.
        """
        ns_name = getattr(node, 'namespace', getattr(node, 'name', None))
        if ns_name in self.namespace_scopes:
            ns_scope = self.namespace_scopes[ns_name]
            for name, sym in ns_scope.symbols.items():
                if not self.current_scope.lookup_local(name):
                    self.current_scope.declare(name, sym)
        elif ns_name:
            self.error(f"Namespace '{ns_name}' not found in using directive", node)

    def visit_variable_declaration(self, node: VariableDeclaration):
        """
        Analyzes a variable declaration.

        Validates the type, checks for duplicate declarations,
        and processes the initializer if present.

        Анализирует объявление переменной.
        Проверяет тип, наличие дублирующихся объявлений
        и обрабатывает инициализатор, если он присутствует.
        """
        if node.type is None:
            self.error("Variable declaration missing type", node)
            return
        local = self.current_scope.lookup_local(node.name)
        if local:
            self.error(f"Variable '{node.name}' already declared in this scope", node)
            return
        resolved_type = self.resolve_type(node.type)
        if resolved_type in ('uint', 'umore', 'ubyte') and node.initializer:
            if isinstance(node.initializer, Literal) and isinstance(node.initializer.value, (int, float)):
                if node.initializer.value < 0:
                    self.error(f"Unsigned type '{resolved_type}' cannot be initialised with a negative value", node)
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
        """
        Analyzes a class declaration.

        Registers the class, processes inheritance, validates abstract methods,
        and analyzes all class members.

        Анализирует объявление класса.
        Регистрирует класс, обрабатывает наследование, проверяет абстрактные методы
        и анализирует все члены класса.
        """
        existing = self.current_scope.lookup(node.name)
        if existing:
            self.error(f"Class '{node.name}' already declared", node)
            return

        self.classes_ast[node.name] = node

        all_methods = []
        if node.extends:
            parent_sym = self.current_scope.lookup(node.extends)
            if not parent_sym or parent_sym.kind != 'class':
                self.error(f"Parent class '{node.extends}' not found or not a class", node)
            else:
                all_methods.extend(getattr(parent_sym, 'all_methods', []))
                if getattr(parent_sym, 'is_sealed', False):
                    self.error(f"Cannot inherit from sealed class '{node.extends}'", node)

        all_methods.extend(node.methods)
        for prop in getattr(node, 'properties', []):
            if hasattr(prop, 'getter') and prop.getter:
                all_methods.append(prop.getter)
            if hasattr(prop, 'setter') and prop.setter:
                all_methods.append(prop.setter)
        node.all_methods = all_methods

        has_abstract_methods = any(getattr(m, 'is_abstract', False) for m in node.methods)
        if has_abstract_methods and not getattr(node, 'is_abstract', False):
            self.error(f"Class '{node.name}' contains abstract methods but is not declared abstract", node)

        class_sym = Symbol(node.name, 'class')
        class_sym.all_methods = all_methods
        class_sym.properties = getattr(node, 'properties', [])
        class_sym.parent_class = node.extends
        class_sym.fields = getattr(node, 'fields', [])
        class_sym.static_methods = getattr(node, 'static_methods', [])
        class_sym.is_sealed = getattr(node, 'is_sealed', False)
        class_sym.is_abstract = getattr(node, 'is_abstract', False)
        self.current_scope.declare(node.name, class_sym)

        previous_scope = self.current_scope
        self.current_scope = Scope(previous_scope)
        self.current_class = node.name

        for f in getattr(node, 'fields', []):
            resolved = self.resolve_type(f.type)
            if not self.is_valid_type(resolved):
                self.error(f"Invalid type '{f.type}' for field '{f.name}'", f)
            field_sym = Symbol(f.name, 'variable', resolved)
            self.current_scope.declare(f.name, field_sym)

        # Валидация модификаторов unwait / wait
        for f in getattr(node, 'fields', []):
            if getattr(f, 'is_unwait', False):
                found = False
                cur = node.extends
                while cur:
                    parent_cls = self.classes_ast.get(cur)
                    if parent_cls:
                        wait_fields = getattr(parent_cls, 'wait_fields', [pf for pf in getattr(parent_cls, 'fields', []) if getattr(pf, 'is_wait', False)])
                        for pf in wait_fields:
                            if pf.name == f.name:
                                if not self.is_type_compatible(f.type, pf.type):
                                    self.error(f"unwait field '{f.name}' type '{f.type}' does not match parent wait field type '{pf.type}'", f)
                                found = True
                                break
                        if found:
                            break
                    cur = parent_cls.extends if parent_cls else None
                if not found:
                    self.error(f"unwait field '{f.name}' does not override any wait field in ancestors", f)

        for method in node.methods:
            self.visit_method_declaration(method)

        for smethod in getattr(node, 'static_methods', []):
            self.visit_method_declaration(smethod)

        for prop in getattr(node, 'properties', []):
            if hasattr(prop, 'getter') and prop.getter:
                self.visit_method_declaration(prop.getter)
            if hasattr(prop, 'setter') and prop.setter:
                self.visit_method_declaration(prop.setter)

        self.current_scope = previous_scope
        self.current_class = None

    def visit_struct_declaration(self, node: StructDeclaration):
        """
        Analyzes a struct declaration.

        Registers the struct and processes its fields.

        Анализирует объявление структуры.
        Регистрирует структуру и обрабатывает её поля.
        """
        existing = self.current_scope.lookup(node.name)
        if existing:
            self.error(f"Struct '{node.name}' already declared", node)
            return
        struct_sym = Symbol(node.name, 'struct')
        struct_sym.fields = getattr(node, 'fields', [])
        self.current_scope.declare(node.name, struct_sym)
        previous_scope = self.current_scope
        self.current_scope = Scope(previous_scope)
        for field in getattr(node, 'fields', []):
            self.visit_variable_declaration(field)
        self.current_scope = previous_scope

    def visit_type_alias(self, node: TypeAlias):
        """
        Analyzes a type alias declaration.

        Verifies the target type and creates an alias symbol.

        Анализирует объявление псевдонима типа.
        Проверяет целевой тип и создаёт символ-псевдоним.
        """
        existing = self.current_scope.lookup(node.name)
        if existing:
            self.error(f"Type alias '{node.name}' already declared", node)
            return
        resolved_target = self.resolve_type(node.target_type)
        if not self.is_valid_type(resolved_target):
            self.error(f"Invalid target type '{node.target_type}' for type alias", node)
            return
        sym = Symbol(node.name, 'typealias', node.target_type)
        self.current_scope.declare(node.name, sym)

    def visit_namespace_declaration(self, node: NamespaceDeclaration):
        """
        Analyzes a namespace declaration.

        Creates a namespace scope and processes all nested declarations.

        Анализирует объявление пространства имён.
        Создаёт область видимости пространства имён и обрабатывает все вложенные объявления.
        """
        existing = self.current_scope.lookup(node.name)
        if existing:
            self.error(f"Namespace '{node.name}' already declared", node)
            return
        namespace_sym = Symbol(node.name, 'namespace')
        self.current_scope.declare(node.name, namespace_sym)
        previous_scope = self.current_scope
        self.current_scope = Scope(previous_scope)
        for stmt in getattr(node, 'body', []):
            self.visit_statement(stmt)
        namespace_sym.scope = self.current_scope
        self.namespace_scopes[node.name] = self.current_scope
        self.current_scope = previous_scope

    def visit_extern_function(self, node: ExternFunction):
        """
        Analyzes an extern function declaration.

        Validates parameter and return types, marks the function as external.

        Анализирует объявление внешней функции.
        Проверяет типы параметров и возвращаемого значения, помечает функцию как внешнюю.
        """
        existing = self.current_scope.lookup(node.name)
        if existing:
            self.error(f"Extern function '{node.name}' already declared", node)
            return
        for param in getattr(node, 'parameters', []):
            if param.type == '...':
                continue
            if not self.is_valid_type(self.resolve_type(param.type)):
                self.error(f"Invalid type '{param.type}' for parameter '{param.name}'", node)
        if hasattr(node, 'return_type') and node.return_type and node.return_type != '...' and not self.is_valid_type(self.resolve_type(node.return_type)):
            self.error(f"Invalid return type '{node.return_type}' for extern function", node)
        sym = Symbol(node.name, 'function', getattr(node, 'return_type', 'void'))
        sym.parameters = getattr(node, 'parameters', [])
        sym.is_extern = True
        sym.is_defined = True
        sym.is_variadic = any(p.type == '...' for p in getattr(node, 'parameters', []))
        self.current_scope.declare(node.name, sym)

    def visit_const_declaration(self, node: ConstDeclaration):
        """
        Analyzes a constant declaration.

        Validates the type and checks that the initializer value is compatible.

        Анализирует объявление константы.
        Проверяет тип и совместимость значения инициализатора.
        """
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
        """
        Analyzes a static variable declaration.

        Validates the type and initializer for static storage duration.

        Анализирует объявление статической переменной.
        Проверяет тип и инициализатор для статической длительности хранения.
        """
        existing = self.current_scope.lookup(node.name)
        if existing:
            self.error(f"Static variable '{node.name}' already declared", node)
            return
        resolved_type = self.resolve_type(node.type)
        if not self.is_valid_type(resolved_type):
            self.error(f"Invalid type '{node.type}' for static variable", node)
            return
        if getattr(node, 'initializer', None):
            expr_type = self.visit_expression(node.initializer)
            if expr_type and not self.is_type_compatible(resolved_type, expr_type):
                self.error(f"Cannot initialize static {node.type} with {expr_type}", node)
        sym = Symbol(node.name, 'static', resolved_type)
        self.current_scope.declare(node.name, sym)

    def visit_method_declaration(self, node: MethodDeclaration):
        """
        Analyzes a method or function declaration.

        Processes parameters, return type, type parameters, and the function body.

        Анализирует объявление метода или функции.
        Обрабатывает параметры, возвращаемый тип, параметры типа и тело функции.
        """
        existing = self.current_scope.lookup_local(node.name)
        if existing and existing.kind == 'function':
            self.error(f"Function '{node.name}' already declared", node)
            return

        if getattr(node, 'is_abstract', False) and getattr(node, 'body', None):
            self.error("Abstract method cannot have a body", node)

        return_type = getattr(node, 'return_type', 'void')
        sym = Symbol(node.name, 'function', return_type)
        sym.parameters = getattr(node, 'parameters', [])
        sym.type_params = getattr(node, 'type_params', [])
        sym.is_extern = False

        old_function = self.current_function
        old_method = self.current_method
        previous_scope = self.current_scope

        self.current_scope = Scope(previous_scope)
        if self.current_class:
            self.current_method = node.name
        else:
            self.current_function = node.name

        for tp in getattr(node, 'type_params', []):
            self.current_scope.declare(tp, Symbol(tp, 'typevar', None))

        if return_type and return_type != 'void':
            resolved_return = self.resolve_type(return_type)
            if not self.is_valid_type(resolved_return):
                self.error(f"Invalid return type '{return_type}'", node)

        for param in getattr(node, 'parameters', []):
            if not self.is_valid_type(self.resolve_type(param.type)):
                self.error(f"Invalid type '{param.type}' for parameter '{param.name}'", node)

        previous_scope.declare(node.name, sym)

        if self.current_class:
            self_sym = Symbol('self', 'variable', self.current_class)
            self.current_scope.declare('self', self_sym)

        for param in getattr(node, 'parameters', []):
            param_sym = Symbol(param.name, 'variable', param.type)
            self.current_scope.declare(param.name, param_sym)

        for stmt in getattr(node, 'body', []):
            self.visit_statement(stmt)

        self.current_scope = previous_scope
        self.current_function = old_function
        self.current_method = old_method

    def visit_if_statement(self, node: IfStatement):
        """
        Analyzes an if-else statement.

        Validates that the condition is boolean and processes both branches.

        Анализирует инструкцию if-else.
        Проверяет, что условие является логическим, и обрабатывает обе ветви.
        """
        cond_type = self.visit_expression(node.condition)
        if cond_type and cond_type != 'bool':
            self.error(f"If condition must be bool, got {cond_type}", node)
        previous_scope = self.current_scope
        self.current_scope = Scope(previous_scope)
        for stmt in getattr(node, 'then_body', []):
            self.visit_statement(stmt)
        self.current_scope = previous_scope

        if getattr(node, 'else_body', None):
            previous_scope = self.current_scope
            self.current_scope = Scope(previous_scope)
            for stmt in node.else_body:
                self.visit_statement(stmt)
            self.current_scope = previous_scope

    def visit_while_loop(self, node: WhileLoop):
        """
        Analyzes a while loop.

        Validates the loop condition and processes the loop body.

        Анализирует цикл while.
        Проверяет условие цикла и обрабатывает тело цикла.
        """
        cond_type = self.visit_expression(node.condition)
        if cond_type and cond_type != 'bool':
            self.error(f"While condition must be bool, got {cond_type}", node)
        self.loop_depth += 1
        previous_scope = self.current_scope
        self.current_scope = Scope(previous_scope)
        for stmt in getattr(node, 'body', []):
            self.visit_statement(stmt)
        self.current_scope = previous_scope
        self.loop_depth -= 1

    def visit_for_loop(self, node: ForLoop):
        """
        Analyzes a for loop.

        Processes initialization, condition, update, and body.

        Анализирует цикл for.
        Обрабатывает инициализацию, условие, обновление и тело.
        """
        previous_scope = self.current_scope
        self.current_scope = Scope(previous_scope)
        if getattr(node, 'init', None):
            self.visit_statement(node.init)
        if getattr(node, 'condition', None):
            cond_type = self.visit_expression(node.condition)
            if cond_type and cond_type != 'bool':
                self.error(f"For condition must be bool, got {cond_type}", node)
        if getattr(node, 'update', None):
            self.visit_expression(node.update)
        self.loop_depth += 1
        for stmt in getattr(node, 'body', []):
            self.visit_statement(stmt)
        self.loop_depth -= 1
        self.current_scope = previous_scope

    def visit_for_each_loop(self, node: ForEachLoop):
        """
        Analyzes a for-each loop.

        Validates that the iterable is an array or dictionary and processes the iteration variable.

        Анализирует цикл for-each.
        Проверяет, что итерируемый объект является массивом или словарём,
        и обрабатывает переменную итерации.
        """
        previous_scope = self.current_scope
        self.current_scope = Scope(previous_scope)

        iterable_type = self.visit_expression(node.iterable)
        if iterable_type is None:
            self.current_scope = previous_scope
            return

        if iterable_type in self.classes_ast:
            cls = self.classes_ast[iterable_type]
            iter_method = None
            for m in getattr(cls, 'all_methods', cls.methods):
                if m.name == '__iter__' and len(getattr(m, 'parameters', [])) == 0:
                    iter_method = m
                    break
            if not iter_method:
                self.error(f"Class '{iterable_type}' has no __iter__ method without parameters", node.iterable)
                self.current_scope = previous_scope
                return
            ret_type = self.resolve_type(iter_method.return_type) if getattr(iter_method, 'return_type', None) else 'any'
            if not ret_type.startswith('arr<'):
                self.error(f"__iter__ of '{iterable_type}' must return an array", node.iterable)
                self.current_scope = previous_scope
                return
            elem_type = ret_type[4:-1].strip()

            if isinstance(node.item_decl, VariableDeclaration):
                if node.item_decl.type is not None:
                    declared_type = self.resolve_type(node.item_decl.type)
                    if not self.is_type_compatible(declared_type, elem_type):
                        self.error(f"Cannot assign {elem_type} to {declared_type} in for-each", node.item_decl)
                    final_type = declared_type
                else:
                    final_type = elem_type
                sym = Symbol(node.item_decl.name, 'variable', final_type)
                self.current_scope.declare(node.item_decl.name, sym)
            else:
                self.error("For-each item must be a variable declaration", node.item_decl)
                self.current_scope = previous_scope
                return

            self.loop_depth += 1
            for stmt in getattr(node, 'body', []):
                self.visit_statement(stmt)
            self.loop_depth -= 1
            self.current_scope = previous_scope
            return

        if iterable_type.startswith('arr<'):
            elem_type = iterable_type[4:-1].strip()
        elif iterable_type.startswith('dict<'):
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

        if isinstance(node.item_decl, VariableDeclaration):
            if node.item_decl.type is not None:
                declared_type = self.resolve_type(node.item_decl.type)
                if not self.is_type_compatible(declared_type, elem_type):
                    self.error(f"Cannot assign {elem_type} to {declared_type} in for-each", node.item_decl)
                final_type = declared_type
            else:
                final_type = elem_type
            sym = Symbol(node.item_decl.name, 'variable', final_type)
            self.current_scope.declare(node.item_decl.name, sym)
        else:
            self.error("For-each item must be a variable declaration", node.item_decl)
            self.current_scope = previous_scope
            return

        self.loop_depth += 1
        for stmt in getattr(node, 'body', []):
            self.visit_statement(stmt)
        self.loop_depth -= 1
        self.current_scope = previous_scope

    def visit_match_statement(self, node: MatchStatement):
        """
        Analyzes a match statement.

        Validates that case values are compatible with the matched expression.

        Анализирует инструкцию match.
        Проверяет, что значения вариантов совместимы с сопоставляемым выражением.
        """
        expr_type = self.visit_expression(node.expression)
        self.match_depth += 1
        for case in getattr(node, 'cases', []):
            case_value_type = self.visit_expression(case.value)
            if expr_type and case_value_type and not self.is_type_compatible(expr_type, case_value_type):
                self.error(f"Case value type {case_value_type} does not match match expression type {expr_type}", case)
            previous_scope = self.current_scope
            self.current_scope = Scope(previous_scope)
            for stmt in getattr(case, 'body', []):
                self.visit_statement(stmt)
            self.current_scope = previous_scope
        if getattr(node, 'default_body', None):
            previous_scope = self.current_scope
            self.current_scope = Scope(previous_scope)
            for stmt in node.default_body:
                self.visit_statement(stmt)
            self.current_scope = previous_scope
        self.match_depth -= 1

    def visit_asafe_block(self, node: AsafeBlock):
        """
        Analyzes an asafe block with exception handling.

        Processes the protected block and the exception handler.

        Анализирует блок asafe с обработкой исключений.
        Обрабатывает защищённый блок и обработчик исключений.
        """
        previous_scope = self.current_scope
        self.current_scope = Scope(previous_scope)
        for stmt in getattr(node, 'body', []):
            self.visit_statement(stmt)
        self.current_scope = previous_scope

        if getattr(node, 'except_handler', None):
            previous_scope = self.current_scope
            self.current_scope = Scope(previous_scope)
            handler = node.except_handler
            if getattr(handler, 'parameter', None):
                exc_type = getattr(handler, 'exception_type', 'any')
                param_sym = Symbol(handler.parameter, 'variable', exc_type)
                self.current_scope.declare(handler.parameter, param_sym)
            for stmt in getattr(handler, 'body', []):
                self.visit_statement(stmt)
            self.current_scope = previous_scope

    def visit_throw_statement(self, node: ThrowStatement):
        """Analyzes a throw statement."""
        if getattr(node, 'value', None):
            self.visit_expression(node.value)

    def visit_giveback_statement(self, node: GivebackStatement):
        """
        Analyzes a giveback statement (value return).

        Validates that the returned value matches the function's return type.

        Анализирует инструкцию giveback (возврат значения).
        Проверяет, что возвращаемое значение соответствует возвращаемому типу функции.
        """
        if not self.current_function and not self.current_method:
            self.error("giveback outside function/method", node)
            return
        expected = self.get_current_return_type()
        if getattr(node, 'value', None):
            val_type = self.visit_expression(node.value)
            if expected == 'void':
                self.error("giveback with value in void function", node)
            elif val_type and not self.is_type_compatible(expected, val_type):
                self.error(f"giveback value type {val_type} does not match expected {expected}", node)
        else:
            if expected != 'void':
                self.error(f"giveback without value in non-void function (expected {expected})", node)

    def visit_return_statement(self, node: ReturnStatement):
        """
        Analyzes a return statement.

        Validates that the returned value matches the function's return type.

        Анализирует инструкцию return.
        Проверяет, что возвращаемое значение соответствует возвращаемому типу функции.
        """
        if not self.current_function and not self.current_method:
            self.error("return outside function/method", node)
            return
        expected = self.get_current_return_type()
        if getattr(node, 'value', None):
            val_type = self.visit_expression(node.value)
            if expected == 'void':
                self.error("return with value in void function", node)
            elif val_type and not self.is_type_compatible(expected, val_type):
                self.error(f"return value type {val_type} does not match expected {expected}", node)
        else:
            if expected != 'void':
                self.error(f"return without value in non-void function (expected {expected})", node)

    def visit_collapse_statement(self, node: CollapseStatement):
        """
        Analyzes a collapse statement (variable removal).

        Removes a variable from the current scope or reports an error.

        Анализирует инструкцию collapse (удаление переменной).
        Удаляет переменную из текущей области видимости или сообщает об ошибке.
        """
        if node.name in self.current_scope.symbols:
            del self.current_scope.symbols[node.name]
        else:
            sym = self.current_scope.lookup(node.name)
            if sym:
                self.error(f"Cannot collapse variable '{node.name}' from outer scope", node)
            else:
                self.error(f"Variable '{node.name}' not declared", node)

    def visit_break_statement(self, node: BreakStatement):
        """
        Analyzes a break statement.

        Validates that break appears inside a loop or match construct.

        Анализирует инструкцию break.
        Проверяет, что break находится внутри цикла или конструкции match.
        """
        if self.loop_depth == 0 and self.match_depth == 0:
            self.error("break outside loop or match", node)

    def visit_interface_declaration(self, node: InterfaceDeclaration):
        """
        Analyzes an interface declaration.

        Registers the interface with its method signatures.

        Анализирует объявление интерфейса.
        Регистрирует интерфейс с сигнатурами его методов.
        """
        existing = self.current_scope.lookup(node.name)
        if existing:
            self.error(f"Interface '{node.name}' already declared", node)
            return
        sym = Symbol(node.name, 'interface')
        sym.methods = getattr(node, 'methods', [])
        for m in sym.methods:
            if getattr(m, 'return_type', None) and m.return_type != 'void':
                if not self.is_valid_type(self.resolve_type(m.return_type)):
                    self.error(f"Invalid return type '{m.return_type}' in interface method '{m.name}'", m)
            for p in getattr(m, 'parameters', []):
                if not self.is_valid_type(self.resolve_type(p.type)):
                    self.error(f"Invalid parameter type '{p.type}' for '{p.name}' in interface method '{m.name}'", m)
        self.current_scope.declare(node.name, sym)

    def visit_impl_declaration(self, node: ImplDeclaration):
        """
        Analyzes an implementation declaration.

        Validates that a class implements all methods of an interface and visits implementation methods.

        Анализирует объявление реализации.
        Проверяет, что класс реализует все методы интерфейса, и заходит в тела методов.
        """
        cls_sym = self.current_scope.lookup(node.class_name)
        if not cls_sym or cls_sym.kind != 'class':
            self.error(f"Class '{node.class_name}' not found", node)
            return
        iface_sym = self.current_scope.lookup(node.interface_name)
        if not iface_sym or iface_sym.kind != 'interface':
            self.error(f"Interface '{node.interface_name}' not found", node)
            return

        for im in getattr(iface_sym, 'methods', []):
            found = False
            for cm in getattr(node, 'methods', []):
                if cm.name == im.name:
                    found = True
                    break
            if not found:
                self.error(f"Missing implementation for '{im.name}' from interface '{node.interface_name}'", node)

        old_class = self.current_class
        self.current_class = node.class_name
        for cm in getattr(node, 'methods', []):
            self.visit_method_declaration(cm)
        self.current_class = old_class

    def visit_expression(self, node: Expression) -> Optional[str]:
        """
        Analyzes an expression and returns its type.

        Dispatches to specific expression handlers and returns the
        inferred type of the expression.

        Анализирует выражение и возвращает его тип.
        Перенаправляет к конкретным обработчикам выражений и возвращает
        выведенный тип выражения.
        """
        if node is None:
            return None

        # Если из парсера прилетел list
        if isinstance(node, list):
            if len(node) == 1:
                return self.visit_expression(node[0])
            elif len(node) == 5 and node[1] == '?' and node[3] == ':':
                cond_type = self.visit_expression(node[0])
                then_type = self.visit_expression(node[2])
                else_type = self.visit_expression(node[4])
                if cond_type not in ('bool', 'any'):
                    self.error(f"If condition must be bool, got {cond_type}", None)
                if not self.is_type_compatible(then_type, else_type):
                    self.error(f"Ternary branches have different types: {then_type} and {else_type}", None)
                return then_type
            self.error(f"Expected single expression AST node, got list of length {len(node)}", None)
            return None

        if getattr(node, 'cached_type', None) is not None:
            return node.cached_type

        result: Optional[str] = None
        if isinstance(node, Literal):
            result = self._literal_type(node)
        elif isinstance(node, Identifier):
            result = self._identifier_type(node)
        elif isinstance(node, BinaryOp):
            result = self._binary_op_type(node)
        elif isinstance(node, UnaryOp):
            result = self._unary_op_type(node)
        elif isinstance(node, Assignment):
            result = self._assignment_type(node)
        elif isinstance(node, Call):
            result = self._call_type(node)
        elif isinstance(node, AwaitExpression):
            result = self.visit_expression(node.expression)
        elif isinstance(node, MemberAccess):
            result = self._member_access_type(node)
        elif isinstance(node, Conditional):
            result = self._conditional_type(node)
        elif isinstance(node, TagAnnotation):
            result = self.visit_expression(node.expression)
        elif isinstance(node, FString):
            result = self._fstring_type(node)
        elif isinstance(node, ArrayLiteral):
            result = self._array_literal_type(node)
        elif isinstance(node, DictLiteral):
            result = self._dict_literal_type(node)
        elif isinstance(node, IndexExpression):
            result = self._index_expression_type(node)
        elif isinstance(node, SuperCall):
            if not self.current_class:
                self.error("super used outside class", node)
                result = None
            else:
                parent = self.current_scope.lookup(self.current_class).parent_class
                if not parent:
                    self.error("class has no parent", node)
                    result = None
                else:
                    parent_sym = self.current_scope.lookup(parent)
                    if not parent_sym or parent_sym.kind != 'class':
                        self.error("parent class not found", node)
                        result = None
                    else:
                        for m in parent_sym.all_methods:
                            if m.name == node.method:
                                result = self.resolve_type(m.return_type)
                                break
                        else:
                            self.error(f"Method '{node.method}' not found in parent class '{parent}'", node)
                            result = None
        else:
            self.error(f"Unknown expression type: {type(node).__name__}", node)
            result = None

        # Записываем кэш только если у объекта есть __dict__
        if hasattr(node, '__dict__'):
            node.cached_type = result

        return result

    def _literal_type(self, node: Literal) -> str:
        """Returns the type of a literal expression."""
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

    def _identifier_type(self, node: Identifier) -> str:
        sym = self.current_scope.lookup(node.name)
        if not sym:
            # Не генерируем ошибку и НЕ объявляем переменную в scope.
            # Просто отдаем 'any', позволяя выражению жить дальше.
            return 'any'
        
        if sym.kind == 'class':
            return sym.name

        return sym.type or 'any'

    def _binary_op_type(self, node: BinaryOp) -> Optional[str]:
        left_type = self.visit_expression(node.left)
        right_type = self.visit_expression(node.right)
        if left_type is None or right_type is None:
            return None
        op = node.operator

        # Перегрузка операторов в классах
        if left_type in self.classes_ast:
            cls = self.classes_ast[left_type]
            method_name = {
                '+': '__add', '-': '__sub', '*': '__mul', '/': '__div', '%': '__mod',
                '==': '__eq', '!=': '__ne', '<': '__lt', '<=': '__le', '>': '__gt', '>=': '__ge'
            }.get(op)
            if method_name:
                sym = self.current_scope.lookup(left_type)
                if sym and sym.kind == 'class':
                    for m in getattr(sym, 'all_methods', []):
                        if m.name == method_name:
                            return self.resolve_type(m.return_type) if getattr(m, 'return_type', None) else 'any'
                self.error(f"Class '{left_type}' has no operator '{op}'", node)
                return None

        # Математические операции
        if op in ('+', '-', '*', '/', '%'):
            if left_type == 'any' or right_type == 'any':
                return 'any'
            if op == '+':
                if left_type == 'str' or right_type == 'str':
                    return 'str'
            if self.is_numeric(left_type) and self.is_numeric(right_type):
                return left_type
            self.error(f"Operator '{op}' requires numeric types or strings, got {left_type} and {right_type}", node)
            return None

        # Операции сравнения (всегда возвращают bool)
        elif op in ('<', '>', '<=', '>=', '==', '!='):
            if left_type == 'any' or right_type == 'any' or self.is_comparable(left_type, right_type):
                return 'bool'
            else:
                self.error(f"Cannot compare {left_type} and {right_type} with '{op}'", node)
                return None

        # Логические операции (всегда возвращают bool)
        elif op in ('&&', '||'):
            if left_type in ('bool', 'any') and right_type in ('bool', 'any'):
                return 'bool'
            else:
                self.error(f"Logical operator '{op}' requires bool operands", node)
                return None
        else:
            self.error(f"Unknown binary operator '{op}'", node)
            return None

    def _unary_op_type(self, node: UnaryOp) -> Optional[str]:
        """
        Determines the type of a unary operation expression.

        Handles logical negation, numeric negation, and dereference operations.

        Определяет тип выражения с унарной операцией.
        Обрабатывает логическое отрицание, числовое отрицание и операции разыменования.
        """
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
        """
        Determines the type of an assignment expression.

        Validates that the value type is compatible with the target type.

        Определяет тип выражения присваивания.
        Проверяет, что тип значения совместим с типом цели.
        """
        target_type = self.visit_expression(node.target)
        value_type = self.visit_expression(node.value)
        if target_type is None or value_type is None:
            return None
        target_sym = self.current_scope.lookup(target_type)
        value_sym = self.current_scope.lookup(value_type)
        if target_sym and target_sym.kind == 'class' and value_sym and value_sym.kind == 'class':
            if not self._is_subclass(value_type, target_type):
                self.error(f"Cannot assign {value_type} to {target_type} (not a subclass)", node)
        elif not self.is_type_compatible(target_type, value_type):
            self.error(f"Cannot assign {value_type} to {target_type}", node)
        return target_type

    def _call_type(self, node: Call) -> Optional[str]:
        """
        Determines the return type of a function, method, or constructor call.

        Handles type inference for generic functions and validates arguments.

        Определяет возвращаемый тип вызова функции, метода или конструктора.
        Обрабатывает вывод типов для обобщённых функций и проверяет аргументы.
        """
        if isinstance(node.callee, Identifier):
            sym = self.current_scope.lookup(node.callee.name)
            if sym:
                if sym.kind == 'class':
                    # Конструктор класса
                    init_method = self._find_class_method(node.callee.name, '__init__') or self._find_class_method(node.callee.name, 'init')
                    if init_method:
                        for i, (arg, param) in enumerate(zip(node.arguments, getattr(init_method, 'parameters', []))):
                            arg_type = self.visit_expression(arg)
                            if arg_type and not self.is_type_compatible(param.type, arg_type):
                                self.error(f"Argument {i+1} of constructor '{node.callee.name}' expected {param.type}, got {arg_type}", node)
                    else:
                        for arg in node.arguments:
                            self.visit_expression(arg)
                    return node.callee.name

                elif sym.kind == 'function':
                    concrete_types = {}
                    if getattr(sym, 'type_params', None):
                        for arg, param in zip(node.arguments, sym.parameters):
                            arg_type = self.visit_expression(arg)
                            if arg_type is None:
                                continue
                            param_type = param.type
                            if param_type in sym.type_params:
                                concrete_types[param_type] = arg_type
                        for tp in sym.type_params:
                            if tp not in concrete_types:
                                self.error(f"Could not infer type parameter '{tp}'", node)
                                return None
                        return_type = sym.type or 'void'
                        for tp, ct in concrete_types.items():
                            return_type = return_type.replace(tp, ct)
                        return return_type
                    else:
                        has_variadic = getattr(sym, 'is_variadic', False)
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
            obj_type = self.visit_expression(node.callee.object)
            if obj_type in self.classes_ast:
                cls = self.classes_ast[obj_type]
                for sm in getattr(cls, 'static_methods', []):
                    if sm.name == node.callee.member:
                        return self.resolve_type(sm.return_type) if getattr(sm, 'return_type', None) else 'any'
                for prop in getattr(cls, 'properties', []):
                    if prop.name == node.callee.member and getattr(prop, 'getter', None):
                        return self.resolve_type(prop.getter.return_type)
                for m in getattr(cls, 'all_methods', cls.methods):
                    if m.name == node.callee.member:
                        return self.resolve_type(m.return_type) if getattr(m, 'return_type', None) else 'any'
                self.error(f"Class '{obj_type}' has no member '{node.callee.member}'", node)
                return None
            sym = self.current_scope.lookup(obj_type)
            if sym and sym.kind == 'interface':
                for m in getattr(sym, 'methods', []):
                    if m.name == node.callee.member:
                        return self.resolve_type(m.return_type) if getattr(m, 'return_type', None) else 'any'
                self.error(f"Interface '{obj_type}' has no method '{node.callee.member}'", node)
                return None
            return 'any'

        return None

    def _member_access_type(self, node: MemberAccess) -> Optional[str]:
        """
        Determines the type of a member access expression.

        Handles namespaces, classes, structs, dictionaries, and other types.

        Определяет тип выражения доступа к члену.
        Обрабатывает пространства имён, классы, структуры, словари и другие типы.
        """
        obj_type = self.visit_expression(node.object)
        if obj_type is None:
            return None

        if obj_type in self.namespace_scopes:
            scope = self.namespace_scopes[obj_type]
            inner = scope.lookup_local(node.member)
            if inner:
                if inner.kind == 'class':
                    return node.member
                elif inner.kind == 'typealias':
                    return self.resolve_type(inner.type)
                else:
                    return inner.type if inner.type else 'any'
            else:
                self.error(f"Namespace '{obj_type}' has no member '{node.member}'", node)
                return None

        if obj_type in self.classes_ast:
            res = self._lookup_class_member(obj_type, node.member)
            if res:
                return res[1]
            self.error(f"Class '{obj_type}' has no member '{node.member}'", node)
            return None

        if obj_type.startswith('dict<'):
            inner = obj_type[5:-1]
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
            if key_type not in ('str', 'any'):
                self.error(f"Dict key must be string for dot access, got {key_type}", node)
            return value_type
        else:
            sym = self.current_scope.lookup(obj_type)
            if sym and sym.kind == 'struct':
                for field in getattr(sym, 'fields', []):
                    if field.name == node.member:
                        return self.resolve_type(field.type)
                self.error(f"Struct '{obj_type}' has no field '{node.member}'", node)
                return None
            if sym and sym.kind == 'namespace':
                if sym.scope:
                    inner = sym.scope.lookup_local(node.member)
                    if inner:
                        if inner.kind == 'class':
                            return node.member
                        elif inner.kind == 'typealias':
                            return self.resolve_type(inner.type)
                        else:
                            return inner.type if inner.type else 'any'
                    else:
                        self.error(f"Namespace '{obj_type}' has no member '{node.member}'", node)
                        return None
            self.error(f"Member access not implemented for type {obj_type}", node)
            return None

    def _conditional_type(self, node: Conditional) -> Optional[str]:
        """
        Determines the type of a conditional (ternary) expression.

        Validates that the condition is boolean and both branches have compatible types.

        Определяет тип условного (тернарного) выражения.
        Проверяет, что условие является логическим, и обе ветви имеют совместимые типы.
        """
        cond_type = self.visit_expression(node.condition)
        if cond_type not in ('bool', 'any'):
            self.error(f"If condition must be bool, got {cond_type}", node)
        then_type = self.visit_expression(node.then_expr)
        else_type = self.visit_expression(node.else_expr)
        if then_type is None or else_type is None:
            return None
        if not self.is_type_compatible(then_type, else_type):
            self.error(f"Ternary branches have different types: {then_type} and {else_type}", node)
        return then_type

    def _fstring_type(self, node: FString) -> str:
        """Returns the type of an f-string expression."""
        for part in getattr(node, 'parts', []):
            if isinstance(part, Expression):
                self.visit_expression(part)
        return 'str'

    def _array_literal_type(self, node: ArrayLiteral) -> str:
        """
        Determines the type of an array literal.

        Ensures all elements have compatible types.

        Определяет тип литерала массива.
        Проверяет, что все элементы имеют совместимые типы.
        """
        if not getattr(node, 'elements', []):
            return 'arr<any>'
        first_type = self.visit_expression(node.elements[0])
        for elem in node.elements[1:]:
            elem_type = self.visit_expression(elem)
            if not self.is_type_compatible(first_type, elem_type):
                self.error(f"Array literal elements must have same type: {first_type} vs {elem_type}", node)
        return f'arr<{first_type}>'

    def _dict_literal_type(self, node: DictLiteral) -> str:
        """
        Determines the type of a dictionary literal.

        Ensures all keys and values have compatible types.

        Определяет тип литерала словаря.
        Проверяет, что все ключи и значения имеют совместимые типы.
        """
        if not getattr(node, 'pairs', []):
            return 'dict<any, any>'
        first_key_type = self.visit_expression(node.pairs[0].key)
        first_val_type = self.visit_expression(node.pairs[0].value)
        for pair in node.pairs[1:]:
            key_type = self.visit_expression(pair.key)
            if not self.is_type_compatible(first_key_type, key_type):
                first_key_type = 'any'
        val_type = first_val_type
        for pair in node.pairs[1:]:
            val_type2 = self.visit_expression(pair.value)
            if not self.is_type_compatible(val_type, val_type2):
                val_type = 'any'
        return f'dict<{first_key_type}, {val_type}>'

    def _index_expression_type(self, node: IndexExpression) -> Optional[str]:
        """
        Determines the type of an index expression.

        Handles array indexing and dictionary key lookup.

        Определяет тип выражения индексации.
        Обрабатывает индексацию массивов и доступ по ключу словаря.
        """
        target_type = self.visit_expression(node.target)
        index_type = self.visit_expression(node.index)
        if target_type is None or index_type is None:
            return None
        if target_type.startswith('arr<'):
            inner = target_type[4:-1]
            if not self.is_numeric(index_type):
                self.error(f"Array index must be numeric, got {index_type}", node)
            return inner
        elif target_type.startswith('dict<'):
            inner = target_type[5:-1]
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
            if target_type == 'any':
                return 'any'
            self.error(f"Indexing not supported for type {target_type}", node)
            return None

    def resolve_type(self, type_name: str) -> str:
        """
        Resolves a type name to its canonical form.

        Handles pointers, generic types, type aliases, and type variables.

        Приводит имя типа к канонической форме.
        Обрабатывает указатели, обобщённые типы, псевдонимы типов и переменные типов.
        """
        if type_name.endswith('*'):
            inner = type_name[:-1].strip()
            resolved_inner = self.resolve_type(inner)
            return f"{resolved_inner}*"
        if type_name.startswith('arr<') and type_name.endswith('>'):
            inner = type_name[4:-1].strip()
            resolved_inner = self.resolve_type(inner)
            return f'arr<{resolved_inner}>'
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
                return type_name
            key_part = inner[:comma_pos].strip()
            val_part = inner[comma_pos+1:].strip()
            resolved_key = self.resolve_type(key_part)
            resolved_val = self.resolve_type(val_part)
            return f'dict<{resolved_key}, {resolved_val}>'
        sym = self.current_scope.lookup(type_name)
        if sym and sym.kind == 'typevar':
            return type_name
        if sym and sym.kind == 'typealias':
            return self.resolve_type(sym.type)
        return type_name

    def is_valid_type(self, type_name: str) -> bool:
        """
        Checks if a type name is valid in the current context.

        Validates primitive types, generics, and user-defined types.

        Проверяет, является ли имя типа допустимым в текущем контексте.
        Проверяет примитивные типы, обобщённые типы и пользовательские типы.
        """
        if type_name == '...':
            return True
        if type_name.endswith('*'):
            inner = type_name[:-1].strip()
            return self.is_valid_type(inner)
        sym = self.current_scope.lookup(type_name)
        if sym and sym.kind == 'typevar':
            return True
        if type_name in ('void', 'bool', 'int', 'uint', 'more', 'umore', 'flt', 'double', 'noised', 'str', 'char', 'byte', 'ubyte', 'any'):
            return True
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
        sym = self.current_scope.lookup(type_name)
        if sym and sym.kind in ('class', 'struct', 'typealias', 'interface'):
            return True
        if type_name and type_name[0].isupper():
            return True
        return False

    def is_numeric(self, type_name: str) -> bool:
        """Checks if a type is numeric."""
        if type_name in ('int', 'uint', 'more', 'umore', 'flt', 'double', 'noised', 'byte', 'ubyte'):
            return True
        return False

    def is_comparable(self, left: str, right: str) -> bool:
        """
        Checks if two types can be compared with relational operators.

        Проверяет, можно ли сравнивать два типа с помощью операторов сравнения.
        """
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
        """
        Checks if a source type can be assigned to a target type.

        Handles numeric promotion, subclass relationships, and generic variance.

        Проверяет, может ли исходный тип быть присвоен целевому типу.
        Обрабатывает числовое продвижение, отношения подклассов и вариантность обобщений.
        """
        target_resolved = self.resolve_type(target)
        source_resolved = self.resolve_type(source)
        if target_resolved == source_resolved:
            return True
        if target_resolved == 'any' or source_resolved == 'any':
            return True
        if self.is_numeric(target_resolved) and self.is_numeric(source_resolved):
            return True
        target_sym = self.current_scope.lookup(target_resolved)
        source_sym = self.current_scope.lookup(source_resolved)
        if target_sym and target_sym.kind == 'class' and source_sym and source_sym.kind == 'class':
            return self._is_subclass(source_resolved, target_resolved)
        if target_resolved.startswith('arr<') and source_resolved.startswith('arr<'):
            t_inner = target_resolved[4:-1].strip()
            s_inner = source_resolved[4:-1].strip()
            return self.is_type_compatible(t_inner, s_inner)
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
        """Splits dictionary type parameters into key and value types."""
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
        """
        Gets the expected return type of the current function or method.

        Возвращает ожидаемый возвращаемый тип текущей функции или метода.
        """
        if self.current_method:
            sym = self.current_scope.lookup(self.current_method)
            if sym:
                return sym.type
        if self.current_function:
            sym = self.current_scope.lookup(self.current_function)
            if sym:
                return sym.type
        return 'void'

    def _ensure_declared(self, name: str, node: Expression) -> Optional[str]:
        """
        Ensures an identifier is declared, auto-declaring it if necessary.

        Provides automatic variable declaration for dynamic typing support.

        Гарантирует, что идентификатор объявлен, при необходимости объявляя его автоматически.
        Обеспечивает автоматическое объявление переменных для поддержки динамической типизации.
        """
        if name in self.namespace_scopes:
            return name
        sym = self.current_scope.lookup(name)
        if sym:
            if sym.kind == 'namespace':
                return name
            return sym.type
        sym = Symbol(name, 'variable', 'any')
        self.current_scope.declare(name, sym)
        return 'any'

    def _is_subclass(self, child: str, parent: str) -> bool:
        """
        Checks if a class is a subclass of another class.

        Проверяет, является ли класс подклассом другого класса.
        """
        sym = self.current_scope.lookup(child)
        if not sym or sym.kind != 'class':
            return False
        cur = sym
        while cur:
            if cur.name == parent:
                return True
            if getattr(cur, 'parent_class', None):
                cur = self.current_scope.lookup(cur.parent_class)
            else:
                break
        return False

    def _find_class_method(self, class_name: str, method_name: str) -> Optional[MethodDeclaration]:
        """Finds a method in a class by name."""
        sym = self.current_scope.lookup(class_name)
        if not sym or sym.kind != 'class':
            return None
        for m in getattr(sym, 'all_methods', []):
            if m.name == method_name:
                return m
        return None

    def _lookup_class_member(self, class_name: str, member_name: str):
        """
        Looks up a member in a class and its parents.

        Returns a tuple of (kind, type) or None if not found.

        Ищет член класса и его родителей.
        Возвращает кортеж (kind, type) или None, если не найдено.
        """
        class_sym = self.current_scope.lookup(class_name)
        if not class_sym or class_sym.kind != 'class':
            return None
        for f in getattr(class_sym, 'fields', []):
            if f.name == member_name:
                return ('field', self.resolve_type(f.type))
        for prop in getattr(class_sym, 'properties', []):
            if prop.name == member_name:
                if getattr(prop, 'getter', None):
                    return ('property', self.resolve_type(prop.getter.return_type))
                else:
                    self.error(f"Property '{member_name}' has no getter", None)
                    return ('property', None)
        for m in getattr(class_sym, 'all_methods', []):
            if m.name == member_name:
                return ('method', self.resolve_type(m.return_type))
        if getattr(class_sym, 'parent_class', None):
            return self._lookup_class_member(class_sym.parent_class, member_name)
        return None