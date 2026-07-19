from enum import Enum
from typing import Any


class TokenType(Enum):
    """
    Enumerates all recognised token types in the Ely language lexer.

    Covers keywords, literals, operators, delimiters, and special tokens
    (EOF, UNKNOWN). Each member's value is the corresponding source string.

    Перечисление всех распознаваемых типов токенов лексера языка Ely.
    Включает ключевые слова, литералы, операторы, разделители и
    специальные токены (EOF, UNKNOWN). Значение элемента — строка источника.
    """

    USING = 'using'
    CLASS = 'class'
    STRUCT = 'struct'
    TYPE = 'type'
    NAMESPACE = 'namespace'
    EXTERN = 'extern'
    CONST = 'const'
    STATIC = 'static'
    VOID = 'void'
    FUNC = 'func'
    GIVEBACK = 'giveback'
    RETURN = 'return'
    IF = 'if'
    ELSE = 'else'
    MATCH = 'match'
    CASE = 'case'
    DEFAULT = 'default'
    BREAK = 'break'
    ASAFE = 'asafe'
    THROW = 'throw'
    EXCEPT = 'except'
    NEW = 'new'
    DELETE = 'delete'
    IN = 'in'
    IS = 'is'
    NOT = 'not'
    PUBLIC = 'public'
    PRIVATE = 'private'
    COLLAPSE = 'collapse'
    FIELDS = 'fields'
    METHODS = 'methods'
    CCODE = 'cCode'
    CPPCODE = 'cppCode'
    WAIT = 'wait'
    UNWAIT = 'unwait'
    SUPER = 'super'

    INT = 'int'
    UINT = 'uint'
    MORE = 'more'
    UMORE = 'umore'
    FLT = 'flt'
    DOUBLE = 'double'
    NOISED = 'noised'
    STR = 'str'
    CHAR = 'char'
    BOOL = 'bool'
    BYTE = 'byte'
    UBYTE = 'ubyte'
    ANY = 'any'
    FSTRING = 'fstring'
    MULTILINE_STRING = 'multiline_string'
    FSTRING_MULTILINE = 'fstring_multiline'

    FOR = 'for'
    FOREACH = 'foreach'
    WHILE = 'while'

    IDENTIFIER = 'identifier'
    MACRO_IDENTIFIER = 'macro_identifier'  # Специальный токен для препроцессора
    NUMBER = 'number'
    STRING = 'string'
    BOOLEAN = 'boolean'
    NULL = 'NULL'

    ASSIGN = '='
    PLUS = '+'
    FAST_PLUS = '+='
    MINUS = '-'
    FAST_MINUS = '-='
    MULTIPLY = '*'
    FAST_MULTIPLY = '*='
    DIVIDE = '/'
    FAST_DIVIDE = '/='
    MODULO = '%'
    EQUAL = '=='
    NOT_EQUAL = '!='
    LESS = '<'
    LESS_EQUAL = '<='
    GREATER = '>'
    GREATER_EQUAL = Rhine = '>='
    LOGICAL_AND = '&&'
    LOGICAL_OR = '||'
    LOGICAL_NOT = '!'
    FAST_CONDITION = '??'
    ARROW = '->'
    FAST_ARROW = '=>'
    ADDRESS = '&'

    LPAREN = '('
    RPAREN = ')'
    LBRACE = '{'
    RBRACE = '}'
    LBRACKET = '['
    RBRACKET = ']'
    COMMA = ','
    DOT = '.'
    SEMICOLON = ';'
    COLON = ':'
    AT = '@'

    EOF = 'eof'
    UNKNOWN = 'unknown'

    INTERFACE = 'interface'
    IMPL = 'impl'
    OVERRIDE = 'override'
    ABSTRACT = 'abstract'
    SEALED = 'sealed'
    ASYNC = 'async'
    AWAIT = 'await'
    SIZEOF = 'sizeof'
    TYPEOF = 'typeof'
    AS = 'as'

    ARRAY = 'arr'
    DICT = 'dict'
    GENERIC = 'generic'


class Token:
    """
    Represents a single lexical token produced by the lexer.

    Stores the token type, the source lexeme, source position (line, column),
    and an optional computed value (e.g. the parsed numeric value of a NUMBER token).

    Представляет один лексический токен, созданный лексером.
    Хранит тип токена, лексему из исходного кода, позицию в исходнике
    (строка, колонка) и опциональное вычисленное значение
    (например, разобранное числовое значение для NUMBER).
    """

    def __init__(self, ttype: TokenType, lexeme: str, line: int, column: int, value: Any = None):
        """
        Initialise a Token instance.

        :param ttype:  The token type.
        :param lexeme: The raw source string matched for this token.
        :param line:   Line number in the source (1‑based).
        :param column: Column number in the source (1‑based).
        :param value:  Optional parsed value (e.g. the numeric or string value).

        Инициализирует экземпляр Token.
        :param ttype:  Тип токена.
        :param lexeme: Исходная строка, совпавшая с токеном.
        :param line:   Номер строки в исходнике (начиная с 1).
        :param column: Номер колонки в исходнике (начиная с 1).
        :param value:  Опциональное разобранное значение (например, число или строка).
        """
        self.type = ttype
        self.lexeme = lexeme
        self.line = line
        self.col = column
        self.value = value

    def __repr__(self):
        """
        Return a debug-friendly string representation of the token.

        :returns: A formatted string showing the token type, lexeme, position, and value.

        Возвращает отладочное строковое представление токена.
        :returns: Форматированная строка с типом, лексемой, позицией и значением.
        """
        return f"Token({self.type.name}, {self.lexeme!r}, line={self.line}, col={self.col}, value={self.value})"