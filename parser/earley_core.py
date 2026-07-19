from typing import List, Dict, Set, Tuple, Any, Optional
import os, sys

# Импорт лексера Ely
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from lexer_module import Lexer, Token, TokenType

# =====================================================================
# 1. СТРУКТУРЫ ДАННЫХ
# =====================================================================

class Rule:
    def __init__(self, lhs: str, rhs: List[str]):
        self.lhs = lhs
        self.rhs = tuple(rhs)

    def __eq__(self, other):
        return isinstance(other, Rule) and self.lhs == other.lhs and self.rhs == other.rhs

    def __hash__(self):
        return hash((self.lhs, self.rhs))

    def __repr__(self):
        return f"{self.lhs} -> {' '.join(self.rhs) if self.rhs else 'ε'}"


class EarleyState:
    def __init__(self, rule: Rule, dot: int, origin: int, children=None):
        self.rule = rule
        self.dot = dot
        self.origin = origin
        self.children = children if children else []

    @property
    def next_symbol(self) -> Optional[str]:
        if self.dot < len(self.rule.rhs):
            return self.rule.rhs[self.dot]
        return None

    @property
    def is_complete(self) -> bool:
        return self.dot >= len(self.rule.rhs)

    def __eq__(self, other):
        return (isinstance(other, EarleyState) and 
                self.rule == other.rule and 
                self.dot == other.dot and 
                self.origin == other.origin)

    def __hash__(self):
        return hash((self.rule, self.dot, self.origin))

    def __repr__(self):
        rhs_list = list(self.rule.rhs)
        rhs_list.insert(self.dot, '.')
        return f"{self.rule.lhs} -> {' '.join(rhs_list)} ({self.origin})"


class Grammar:
    def __init__(self, rules: List[Rule]):
        self.rules = rules
        self.non_terminals = {rule.lhs for rule in rules}

    def rules_for(self, non_terminal: str) -> List[Rule]:
        return [r for r in self.rules if r.lhs == non_terminal]


class ParseNode:
    def __init__(self, name: str, children=None, token: Token = None):
        self.name = name
        self.children = children if children else []
        self.token = token

    def print_tree(self, depth=0):
        indent = "  " * depth
        if self.token:
            print(f"{indent}└─ {self.name}: {self.token.lexeme!r} (Line: {self.token.line}, Col: {self.token.col})")
        else:
            print(f"{indent}├─ [{self.name}]")
            for child in self.children:
                if isinstance(child, ParseNode):
                    child.print_tree(depth + 1)

# =====================================================================
# 2. ИСПРАВЛЕННЫЙ ДВИЖОК С РЕФЛЕКСИЕЙ ОШИБОК
# =====================================================================

class ElyEarleyParser:
    def __init__(self, grammar: Grammar, start_symbol: str = "Root"):
        self.grammar = grammar
        self.start_symbol = start_symbol

    def _match_terminal(self, expected_sym: str, token: Token) -> bool:
        if hasattr(TokenType, expected_sym):
            if token.type == getattr(TokenType, expected_sym):
                return True
        return token.lexeme == expected_sym

    def parse(self, tokens: List[Token]) -> Tuple[Optional[ParseNode], Optional[str]]:
        n = len(tokens)
        chart: List[List[EarleyState]] = [[] for _ in range(n + 1)]
        chart_sets: List[Set[EarleyState]] = [set() for _ in range(n + 1)]

        def add_state(chart_idx: int, state: EarleyState) -> bool:
            if state not in chart_sets[chart_idx]:
                chart_sets[chart_idx].add(state)
                chart[chart_idx].append(state)
                return True
            return False

        # Инициализация
        gamma_rule = Rule("Gamma", [self.start_symbol])
        add_state(0, EarleyState(gamma_rule, 0, 0))

        furthest_chart_idx = 0

        for i in range(n + 1):
            if chart[i]:
                furthest_chart_idx = i

            j = 0
            while j < len(chart[i]):
                state = chart[i][j]
                j += 1

                if not state.is_complete:
                    next_sym = state.next_symbol

                    if next_sym in self.grammar.non_terminals:
                        # PREDICTOR
                        for rule in self.grammar.rules_for(next_sym):
                            add_state(i, EarleyState(rule, 0, i))
                        
                        # ФИКС ЭПСИЛОН-БАГА: Если этот нетерминал уже завершился в текущем чарте как пустой,
                        # подтягиваем его результаты для только что предсказанного состояния
                        for comp_state in chart[i]:
                            if comp_state.is_complete and comp_state.rule.lhs == next_sym and comp_state.origin == i:
                                node = ParseNode(comp_state.rule.lhs, comp_state.children)
                                add_state(i, EarleyState(state.rule, state.dot + 1, state.origin, state.children + [node]))

                    else:
                        # SCANNER
                        if i < n:
                            token = tokens[i]
                            if self._match_terminal(next_sym, token):
                                node = ParseNode(next_sym, token=token)
                                add_state(i + 1, EarleyState(state.rule, state.dot + 1, state.origin, state.children + [node]))
                else:
                    # COMPLETER
                    node = ParseNode(state.rule.lhs, state.children)
                    origin = state.origin
                    
                    # Защита от динамического изменения размеров: используем while вместо for
                    k = 0
                    while k < len(chart[origin]):
                        old_state = chart[origin][k]
                        k += 1
                        if not old_state.is_complete and old_state.next_symbol == state.rule.lhs:
                            add_state(i, EarleyState(old_state.rule, old_state.dot + 1, old_state.origin, old_state.children + [node]))

        # Проверка на успешное завершение
        for state in chart[n]:
            if state.rule.lhs == "Gamma" and state.is_complete and state.origin == 0:
                return state.children[0], None

        # РЕФЛЕКСИЯ ОШИБОК: вычисляем, где и почему споткнулся разбор
        error_msg = self._generate_error_report(chart, furthest_chart_idx, tokens)
        return None, error_msg

    def _generate_error_report(self, chart: List[List[EarleyState]], error_idx: int, tokens: List[Token]) -> str:
        if error_idx < len(tokens):
            bad_token = tokens[error_idx]
            location = f"line {bad_token.line}, column {bad_token.col} (Token: {bad_token.type.name}, Lexeme: '{bad_token.lexeme}')"
        else:
            location = "End of File (EOF)"

        # Собираем все ожидаемые токены на шаге падения
        expected_symbols = set()
        for state in chart[error_idx]:
            if not state.is_complete:
                sym = state.next_symbol
                if sym:
                    expected_symbols.add(sym)

        expected_readable = []
        for sym in expected_symbols:
            if sym in self.grammar.non_terminals:
                expected_readable.append(f"<{sym}>")
            else:
                expected_readable.append(f"'{sym}'")

        return (
            f"Parsing failed at {location}.\n"
            f"Context: Furthest parsed position successfully reached chart node {error_idx}.\n"
            f"Expected one of the following: {', '.join(sorted(expected_readable))}"
        )

# =====================================================================
# 3. АКТУАЛЬНАЯ ГРАММАТИКА ELY (БЕЗ МАКРОСОВ В ПАРАМЕТРАХ)
# =====================================================================

ely_grammar_rules = [
    # =====================================================================
    # 1. КОРЕНЬ ФАЙЛА И СТРУКТУРА МОДУЛЕЙ
    # =====================================================================
    Rule("Root", ["TopLevelDecls"]),
    Rule("TopLevelDecls", ["TopLevelDecl", "TopLevelDecls"]),
    Rule("TopLevelDecls", []),

    # Что может существовать на глобальном уровне файла
    Rule("TopLevelDecl", ["UsingDecl", "SEMICOLON"]),
    Rule("TopLevelDecl", ["NamespaceDecl"]),
    Rule("TopLevelDecl", ["TypeAliasDecl", "SEMICOLON"]),
    Rule("TopLevelDecl", ["ExternDecl", "SEMICOLON"]),
    Rule("TopLevelDecl", ["FuncDecl"]),
    Rule("TopLevelDecl", ["ClassDecl"]),
    Rule("TopLevelDecl", ["StructDecl"]),
    Rule("TopLevelDecl", ["InterfaceDecl"]),
    Rule("TopLevelDecl", ["ImplDecl"]),
    Rule("TopLevelDecl", ["CPPCODE"]),
    Rule("TopLevelDecl", ["CCODE"]),
    Rule("TopLevelDecl", ["CompilerDirective"]),
    Rule("TopLevelDecl", ["UsingDecl", "SEMICOLON"]),
    Rule("Statement", ["CompilerDirective"]),
    Rule("Statement", ["VarDecl", "SEMICOLON"]),

    # Поддержка модулей: using std.io; ИЛИ namespace App.Core { ... }
    Rule("UsingDecl", ["USING", "Path"]),
    Rule("NamespaceDecl", ["NAMESPACE", "Path", "LBRACE", "TopLevelDecls", "RBRACE"]),
    Rule("Path", ["IDENTIFIER", "DOT", "Path"]),
    Rule("Path", ["IDENTIFIER"]),

    # Алиасы типов: type MyInt = int;
    Rule("TypeAliasDecl", ["TYPE", "IDENTIFIER", "ASSIGN", "DataType"]),

    # Внешние функции: extern public void func printf(str format);
    Rule("ExternDecl", ["EXTERN", "Prefixes", "Type", "FUNC", "IDENTIFIER", "LPAREN", "Params", "RPAREN"]),


    # =====================================================================
    # 2. ДЕКЛАРАЦИЯ ФУНКЦИЙ И ПАРАМЕТРОВ
    # =====================================================================
    Rule("FuncDecl", ["Prefixes", "Type", "FUNC", "IDENTIFIER", "GenericParamsOpt", "LPAREN", "Params", "RPAREN", "Block"]),

    Rule("Params", ["Param", "COMMA", "Params"]),
    Rule("Params", ["Param"]),
    Rule("Params", []),
    Rule("Param", ["DataType", "IDENTIFIER"]),


    # =====================================================================
    # 3. ОБЪЕКТНО-ОРИЕНТИРОВАННЫЕ СУЩНОСТИ (ООП)
    # =====================================================================
    # Декларация Классов, Структур и Интерфейсов
    Rule("ClassDecl", ["ClassModifiers", "BaseClassOpt", "CLASS", "IDENTIFIER", "GenericParamsOpt", "LBRACE", "ClassMembers", "RBRACE"]),
    Rule("StructDecl", ["ClassModifiers", "STRUCT", "IDENTIFIER", "GenericParamsOpt", "LBRACE", "ClassMembers", "RBRACE"]),
    Rule("InterfaceDecl", ["ClassModifiers", "INTERFACE", "IDENTIFIER", "LBRACE", "ClassMembers", "RBRACE"]),
    
    # Реализация интерфейсов/методов: impl Название ИЛИ impl Интерфейс for Структура
    Rule("ImplDecl", ["IMPL", "IDENTIFIER", "ForOpt", "LBRACE", "ClassMembers", "RBRACE"]),
    Rule("ForOpt", ["FOR", "IDENTIFIER"]),
    Rule("ForOpt", []),

    Rule("ClassModifiers", ["ClassModifier", "ClassModifiers"]),
    Rule("ClassModifiers", []),
    Rule("ClassModifier", ["ABSTRACT"]),
    Rule("ClassModifier", ["SEALED"]),
    Rule("ClassModifier", ["PUBLIC"]),
    Rule("ClassModifier", ["PRIVATE"]),

    Rule("BaseClassOpt", ["IDENTIFIER"]),
    Rule("BaseClassOpt", []),

    # Члены ООП-структур
    Rule("ClassMembers", ["ClassMember", "ClassMembers"]),
    Rule("ClassMembers", []),

    Rule("ClassMember", ["FieldDecl", "SEMICOLON"]),
    Rule("ClassMember", ["MethodDecl"]),
    Rule("ClassMember", ["SuperCall", "SEMICOLON"]),

    Rule("SuperCall", ["SUPER", "LPAREN", "Args", "RPAREN"]),

    # Поля с поддержкой wait/unwait
    Rule("FieldDecl", ["FieldModifierOpt", "DataType", "IDENTIFIER", "InitOpt"]),
    Rule("FieldModifierOpt", ["WAIT"]),
    Rule("FieldModifierOpt", ["UNWAIT"]),
    Rule("FieldModifierOpt", []),

    # Методы классов / структур / интерфейсов
    Rule("MethodDecl", ["Prefixes", "Type", "FUNC", "IDENTIFIER", "GenericParamsOpt", "LPAREN", "Params", "RPAREN", "MethodBody"]),
    Rule("MethodBody", ["Block"]),
    Rule("MethodBody", ["SEMICOLON"]),


    # =====================================================================
    # 4. СИСТЕМА ТИПОВ ДАННЫХ (С дженериками и коллекциями)
    # =====================================================================
    Rule("Type", ["DataType"]),
    Rule("Type", []), # Фича: по дефолту any

    Rule("DataType", ["PrimitiveType"]),
    Rule("DataType", ["IDENTIFIER"]),                                           # Обычный тип: Cat
    Rule("DataType", ["IDENTIFIER", "LESS", "GenericArgs", "GREATER"]),         # Шаблонный тип: Vector<int>
    Rule("DataType", ["ARRAY", "LESS", "DataType", "GREATER"]),                 # Встроенный arr<int>
    Rule("DataType", ["DICT", "LESS", "DataType", "COMMA", "DataType", "GREATER"]),
    Rule("GenericArgsOpt", ["COMMA", "DataType", "GenericArgsOpt"]),
    Rule("GenericArgsOpt", []),

    Rule("PrimitiveType", ["INT"]),
    Rule("PrimitiveType", ["UINT"]),
    Rule("PrimitiveType", ["STR"]),
    Rule("PrimitiveType", ["VOID"]),
    Rule("PrimitiveType", ["BOOL"]),
    Rule("PrimitiveType", ["BYTE"]),
    Rule("PrimitiveType", ["FLT"]),
    Rule("PrimitiveType", ["DOUBLE"]),
    Rule("PrimitiveType", ["NOISED"]),
    Rule("PrimitiveType", ["CHAR"]),
    Rule("PrimitiveType", ["UBYTE"]),
    Rule("PrimitiveType", ["ANY"]),
    Rule("PrimitiveType", ["ARRAY"]),
    Rule("PrimitiveType", ["DICT"]),

    # Модификаторы и макросы (универсальные)
    Rule("Prefixes", ["Prefix", "Prefixes"]),
    Rule("Prefixes", []),
    Rule("Prefix", ["Modifier"]),
    Rule("Prefix", ["Macro"]),
    Rule("Modifier", ["PUBLIC"]),
    Rule("Modifier", ["PRIVATE"]),
    Rule("Modifier", ["STATIC"]),
    Rule("Modifier", ["ASYNC"]),
    Rule("Modifier", ["ABSTRACT"]),
    Rule("Modifier", ["SEALED"]),
    Rule("Modifier", ["OVERRIDE"]),
    Rule("Modifier", ["COLLAPSE"]),
    Rule("Macro", ["#", "IDENTIFIER"]),
    Rule("Macro", ["MACRO_IDENTIFIER"]),
    Rule("Macro", ["MODULO", "IDENTIFIER"]),


# =====================================================================
    # 5. БЛОКИ, СТЕМЕНТЫ И УПРАВЛЕНИЕ ПОТОКОМ (Control Flow)
    # =====================================================================
    Rule("Block", ["LBRACE", "Statements", "RBRACE"]),
    Rule("Statements", ["Statement", "Statements"]),
    Rule("Statements", []),

    Rule("Statement", ["VarDecl", "SEMICOLON"]),
    Rule("Statement", ["Assignment", "SEMICOLON"]),
    Rule("Statement", ["Expr", "SEMICOLON"]),
    Rule("Statement", ["ControlFlowStmt"]),
    Rule("Statement", ["TryExceptStmt"]),
    Rule("Statement", ["DeleteStmt", "SEMICOLON"]),
    Rule("Statement", ["CompilerDirective"]),
    
    # --- ВОТ СЮДА ДОБАВЛЯЕМ ЛОКАЛЬНЫЙ КОНТЕКСТ ---
    Rule("Statement", ["FuncDecl"]), # Вложенные функции (локальные области видимости)
    Rule("Statement", ["CPPCODE"]),  # Вставки cppCode { ... } прямо внутри функций
    Rule("Statement", ["CCODE"]),   # Вставки cCode { ... } прямо внутри функций
    Rule("DeleteStmt", ["DELETE", "Expr"]),

    # Управляющие конструкции
    Rule("ControlFlowStmt", ["IfStmt"]),
    Rule("ControlFlowStmt", ["WhileStmt"]),
    Rule("ControlFlowStmt", ["ForStmt"]),
    Rule("ControlFlowStmt", ["ForeachStmt"]),
    Rule("ControlFlowStmt", ["MatchStmt"]),
    Rule("ControlFlowStmt", ["ReturnStmt", "SEMICOLON"]),
    Rule("ControlFlowStmt", ["GivebackStmt", "SEMICOLON"]),
    Rule("ControlFlowStmt", ["BREAK", "SEMICOLON"]),

    Rule("ReturnStmt", ["RETURN", "ExprOpt"]),
    Rule("GivebackStmt", ["GIVEBACK", "ExprOpt"]),
    Rule("ExprOpt", ["Expr"]),
    Rule("ExprOpt", []),

    # Ветвление
    Rule("IfStmt", ["IF", "LPAREN", "Expr", "RPAREN", "Block", "ElseOpt"]),
    Rule("ElseOpt", ["ELSE", "Block"]),
    Rule("ElseOpt", ["ELSE", "IfStmt"]),
    Rule("ElseOpt", []),

    # Циклы (Обычный, C-style For, и Итераторный Foreach)
    Rule("WhileStmt", ["WHILE", "LPAREN", "Expr", "RPAREN", "Block"]),
    Rule("ForStmt", ["FOR", "LPAREN", "VarDecl", "SEMICOLON", "Expr", "SEMICOLON", "Assignment", "RPAREN", "Block"]),
    Rule("ForeachStmt", ["FOREACH", "LPAREN", "IDENTIFIER", "IN", "Expr", "RPAREN", "Block"]),

    # Паттерн-матчинг (match)
    Rule("MatchStmt", ["MATCH", "LPAREN", "Expr", "RPAREN", "LBRACE", "CaseEntries", "RBRACE"]),
    Rule("CaseEntries", ["CaseEntry", "CaseEntries"]),
    Rule("CaseEntries", []),
    Rule("CaseEntry", ["CASE", "Expr", "COLON", "Statements"]),
    Rule("CaseEntry", ["DEFAULT", "COLON", "Statements"]),

    # Безопасное выполнение (asafe / except / throw)
    Rule("TryExceptStmt", ["ASAFE", "Block", "EXCEPT", "LPAREN", "DataType", "IDENTIFIER", "RPAREN", "Block"]),
    Rule("TryExceptStmt", ["THROW", "Expr", "SEMICOLON"]),


    # =====================================================================
    # 6. ОБЪЯВЛЕНИЕ ПЕРЕМЕННЫХ И ПРИСВАИВАНИЕ
    # =====================================================================
    Rule("VarDecl", ["ConstOpt", "DataType", "IDENTIFIER", "InitOpt"]),
    Rule("ConstOpt", ["CONST"]),
    Rule("ConstOpt", []),
    Rule("InitOpt", ["ASSIGN", "Expr"]),
    Rule("InitOpt", []),

    # Продвинутое присваивание (поддерживает l-values вроде arr[i], obj.x и операторы вроде +=, -=)
    Rule("Assignment", ["LValue", "AssignOp", "Expr"]),
    Rule("LValue", ["IDENTIFIER"]),
    Rule("LValue", ["Primary", "DOT", "IDENTIFIER"]),
    Rule("LValue", ["Primary", "LBRACKET", "Expr", "RBRACKET"]),
    
    Rule("AssignOp", ["ASSIGN"]),
    Rule("AssignOp", ["FAST_PLUS"]),
    Rule("AssignOp", ["FAST_MINUS"]),
    Rule("AssignOp", ["FAST_MULTIPLY"]),
    Rule("AssignOp", ["FAST_DIVIDE"]),


    # =====================================================================
    # 7. МАТЕМАТИЧЕСКИЕ И ЛОГИЧЕСКИЕ ВЫРАЖЕНИЯ (Полный каскад приоритетов)
    # =====================================================================
    Rule("Expr", ["NullCoalescing"]),

    # 0. Null-coalescing (??)
    Rule("NullCoalescing", ["NullCoalescing", "FAST_CONDITION", "LogicOr"]),
    Rule("NullCoalescing", ["LogicOr"]),

    # 1. Логическое ИЛИ
    Rule("LogicOr", ["LogicOr", "LOGICAL_OR", "LogicAnd"]),
    Rule("LogicOr", ["LogicAnd"]),

    # 2. Логическое И
    Rule("LogicAnd", ["LogicAnd", "LOGICAL_AND", "Equality"]),
    Rule("LogicAnd", ["Equality"]),

    # 3. Равенство / Сравнение типов (==, !=, is)
    Rule("Equality", ["Equality", "EQUAL", "Relational"]),
    Rule("Equality", ["Equality", "NOT_EQUAL", "Relational"]),
    Rule("Equality", ["Equality", "IS", "Relational"]),
    Rule("Equality", ["Relational"]),

    # 4. Сравнения и оператор вхождения (<, <=, >, >=, in)
    Rule("Relational", ["Relational", "LESS", "Additive"]),
    Rule("Relational", ["Relational", "LESS_EQUAL", "Additive"]),
    Rule("Relational", ["Relational", "GREATER", "Additive"]),
    Rule("Relational", ["Relational", "GREATER_EQUAL", "Additive"]),
    Rule("Relational", ["Relational", "IN", "Additive"]),
    Rule("Relational", ["Additive"]),

    # 5. Аддитивные операции (+, -)
    Rule("Additive", ["Additive", "PLUS", "Multiplicative"]),
    Rule("Additive", ["Additive", "MINUS", "Multiplicative"]),
    Rule("Additive", ["Multiplicative"]),

    # 6. Мультипликативные операции (*, /, %)
    Rule("Multiplicative", ["Multiplicative", "MULTIPLY", "Unary"]),
    Rule("Multiplicative", ["Multiplicative", "DIVIDE", "Unary"]),
    Rule("Multiplicative", ["Multiplicative", "MODULO", "Unary"]),
    Rule("Multiplicative", ["Unary"]),

    # 7. Унарные операции (!, not, -, await, &)
    Rule("Unary", ["LOGICAL_NOT", "Unary"]),
    Rule("Unary", ["NOT", "Unary"]),
    Rule("Unary", ["MINUS", "Unary"]),
    Rule("Unary", ["AWAIT", "Unary"]),
    Rule("Unary", ["ADDRESS", "Unary"]), # Взятие адреса &
    Rule("Unary", ["Primary"]),


    # =====================================================================
    # 8. СВЕРХВЫСОКИЙ ПРИОРИТЕТ И АТОМЫ (Primary)
    # =====================================================================
    # Вызовы методов, свойства рефлексии (fields, methods), касты, литералы
    Rule("Primary", ["IDENTIFIER", "LESS", "GenericArgs", "GREATER", "LPAREN", "Args", "RPAREN"]),
    
    # Добавляем создание шаблонного класса: new Vector<str>()
    Rule("Primary", ["NEW", "IDENTIFIER", "LESS", "GenericArgs", "GREATER", "LPAREN", "Args", "RPAREN"]),

    Rule("Primary", ["Primary", "DOT", "IDENTIFIER"]),                         # kitty.name
    Rule("Primary", ["Primary", "DOT", "FIELDS"]),                             # kitty.fields
    Rule("Primary", ["Primary", "DOT", "METHODS"]),                            # kitty.methods
    Rule("Primary", ["Primary", "DOT", "IDENTIFIER", "LPAREN", "Args", "RPAREN"]), # kitty.say()
    Rule("Primary", ["IDENTIFIER", "LPAREN", "Args", "RPAREN"]),               # print(...)
    Rule("Primary", ["PrimitiveType", "LPAREN", "Args", "RPAREN"]),            # str(12.5)
    Rule("Primary", ["NEW", "IDENTIFIER", "LPAREN", "Args", "RPAREN"]),        # new Cat(...)
    Rule("Primary", ["SIZEOF", "LPAREN", "Expr", "RPAREN"]),                   # sizeof(a)
    Rule("Primary", ["TYPEOF", "LPAREN", "Expr", "RPAREN"]),                   # typeof(a)
    Rule("Primary", ["Primary", "AS", "DataType"]),                            # val as int
    Rule("Primary", ["Primary", "LBRACKET", "Expr", "RBRACKET"]),              # matrix[i]
    Rule("Primary", ["Literal"]),
    Rule("Primary", ["IDENTIFIER"]),
    Rule("Primary", ["NULL"]),
    Rule("Primary", ["LPAREN", "Expr", "RPAREN"]),                             # (a + b)
    Rule("Primary", ["ArrayLiteral"]),                                         # [1, 2, 3]
    Rule("Primary", ["DictLiteral"]),                                          # {"a": 1}
    Rule("Primary", ["LambdaExpr"]),                                           # Лямбды / стрелочные функции

    # Литералы коллекций
    Rule("ArrayLiteral", ["LBRACKET", "Args", "RBRACKET"]),
    Rule("DictLiteral", ["LBRACE", "DictEntries", "RBRACE"]),
    Rule("DictEntries", ["DictEntry", "COMMA", "DictEntries"]),
    Rule("DictEntries", ["DictEntry"]),
    Rule("DictEntries", []),
    Rule("DictEntry", ["Expr", "COLON", "Expr"]),

    # Стрелочные замыкания / лямбды: () -> { } ИЛИ (x) => x * 2
    Rule("LambdaExpr", ["LPAREN", "Params", "RPAREN", "ARROW", "Block"]),
    Rule("LambdaExpr", ["LPAREN", "Params", "RPAREN", "FAST_ARROW", "Expr"]),


    # =====================================================================
    # 9. АРГУМЕНТЫ ВЫЗОВОВ И БАЗОВЫЕ ЛИТЕРАЛЫ
    # =====================================================================
    # Очищенная, СТРОГАЯ и единственная ветка аргументов (без дублирования!)
    Rule("Args", ["Arg", "COMMA", "Args"]),
    Rule("Args", ["Arg"]),
    Rule("Args", []),

    # Именованный (name="Kitty") ИЛИ позиционный ("Kitty") аргумент
    Rule("Arg", ["IDENTIFIER", "ASSIGN", "Expr"]),
    Rule("Arg", ["Expr"]),

    Rule("Literal", ["STRING"]),
    Rule("Literal", ["NUMBER"]),
    Rule("Literal", ["BOOLEAN"]),
    Rule("Literal", ["FSTRING"]),
    Rule("Literal", ["MULTILINE_STRING"]),
    Rule("Literal", ["FSTRING_MULTILINE"]),

    # =====================================================================
    # 10. TEMPLATES
    # =====================================================================
    # Параметры шаблона при объявлении: <T> или <T, U>
    Rule("GenericParamsOpt", ["LESS", "TemplateParams", "GREATER"]),
    Rule("GenericParamsOpt", []),
    Rule("TemplateParams", ["IDENTIFIER", "COMMA", "TemplateParams"]),
    Rule("TemplateParams", ["IDENTIFIER"]),

    # Аргументы шаблона при использовании: <int> или <str, any>
    Rule("GenericArgs", ["DataType", "COMMA", "GenericArgs"]),
    Rule("GenericArgs", ["DataType"]),

    # =====================================================================
    # 11. КОМПИЛЯЦИОННЫЕ ДИРЕКТИВЫ (МАКРОСЫ СБОРОЧНОЙ СРЕДЫ)
    # =====================================================================
    # Синтаксис: #ИМЯ ВЫРАЖЕНИЕ;
    Rule("CompilerDirective", ["#", "IDENTIFIER", "MacroArgOpt", "SEMICOLON"]),
    
    # Опциональный аргумент (для гибкости, если появятся макросы без параметров)
    Rule("MacroArgOpt", ["Expr"]),
    Rule("MacroArgOpt", []),
]

ely_grammar = Grammar(ely_grammar_rules)
parser = ElyEarleyParser(ely_grammar)

# =====================================================================
# 4. ТЕСТОВЫЙ ЗАПУСК
# =====================================================================

if __name__ == "__main__":
    # Твой исходный пример кода
    source_code = """
    #typedef vector;
    #debug true;

    cCode {
        int Cint = 3;
    }

    abstract class Animal {
        wait str name;
        wait bool haveWool;

        abstract void func say();
    }

    Animal class Cat {
        super(name, haveWool);

        sealed void func say() {
            print(f"Cat {name} says meow :3");
        }
    }

    public static async int func main() {
        const int a = 5;
        b = 12.5;
        ba = b + a;
        bas = str(ba);
        c = "Hello";
        arr<int> arr1 = [0, 4];
        arr arr2 = ["hello", 'w', true];
        dict<str, any> bibi = {
            "name": "Kitten",
            "weight": 3,
        };
        dict bebe = {
            "age" : 0,
            2: false
        };
        Cat kitty = new Cat("Kitty");
        kitty.say();
        print(f"{c} from Ely!");
    }
    """

    print("--- ЗАПУСК ЛЕКСЕРА ---")
    lexer = Lexer(source_code)
    tokens = lexer.tokenize(debug=False)

    # Убираем EOF для чистоты разбора ядром
    tokens = [t for t in tokens if t.type != TokenType.EOF]
    print(f"Лексер успешно выдал {len(tokens)} токенов.")

    print("\n--- ЗАПУСК ПАРСЕРА ЭРЛИ ---")
    parse_tree, error = parser.parse(tokens)

    if parse_tree:
        print("Разбор успешен! Дерево разбора построенно:")
        parse_tree.print_tree()
    else:
        print("!!! ОШИБКА СИНТАКСИЧЕСКОГО АНАЛИЗА !!!")
        print(error)