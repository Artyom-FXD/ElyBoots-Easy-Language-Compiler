import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from parser.earley_core import Grammar, Rule

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
    Rule("TopLevelDecl", ["VarDecl", "SEMICOLON"]),
    Rule("TopLevelDecl", ["Assignment", "SEMICOLON"]),
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

# =====================================================================
    # 7. МАТЕМАТИЧЕСКИЕ И ЛОГИЧЕСКИЕ ВЫРАЖЕНИЯ (Полный каскад приоритетов)
    # =====================================================================
    Rule("Expr", ["Ternary"]),

    # ---------------------------------------------------------------------
    # 0. ТЕРНАРНЫЕ ОПЕРАТОРЫ
    # ---------------------------------------------------------------------
    # Python-style:  a = 2 if (1 == 1) else 4
    Rule("Ternary", ["LogicOr", "IF", "LogicOr", "ELSE", "Ternary"]),

    # C/Ely-style:   a = (1 == 1) ?? 2 : 4  (FAST_CONDITION = '??', COLON = ':')
    Rule("Ternary", ["LogicOr", "FAST_CONDITION", "Ternary", "COLON", "Ternary"]),

    # (Опционально) Одиночный '?' на случай, если в будущем добавишь QUESTION в лексер:
    Rule("Ternary", ["LogicOr", "QUESTION", "Ternary", "COLON", "Ternary"]),

    # ---------------------------------------------------------------------
    # 0.1. NULL-COALESCING (a ?? default_val) & Спуск приоритета
    # ---------------------------------------------------------------------
    Rule("Ternary", ["NullCoalescing"]),

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