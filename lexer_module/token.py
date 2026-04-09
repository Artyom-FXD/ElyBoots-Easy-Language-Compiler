from enum import Enum
from typing import Any

class TokenType(Enum):
    # Ключевые слова
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

    # Типы данных
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

    # Циклы
    FOR = 'for'
    FOREACH = 'foreach'
    WHILE = 'while'

    # Литералы
    IDENTIFIER = 'identifier'
    NUMBER = 'number'
    STRING = 'string'
    BOOLEAN = 'boolean'
    NULL = 'NULL'

    # Операторы
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
    GREATER_EQUAL = '>='
    LOGICAL_AND = '&&'
    LOGICAL_OR = '||'
    LOGICAL_NOT = '!'
    FAST_CONDITION = '??'
    ARROW = '->'
    ADDRESS = '&'

    # Разделители
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

    # Прочее
    EOF = 'eof'
    UNKNOWN = 'unknown'

    # Зарезервированные для будущего
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


    # Новые ключевые слова
    ARRAY = 'arr'
    DICT = 'dict'
    GENERIC = 'generic'


class Token:
    def __init__(self, ttype: TokenType, lexeme: str, line: int, column: int, value: Any = None):
        self.type = ttype
        self.lexeme = lexeme
        self.line = line
        self.col = column
        self.value = value

    def __repr__(self):
        return f"Token({self.type.name}, {self.lexeme!r}, line={self.line}, col={self.col}, value={self.value})"