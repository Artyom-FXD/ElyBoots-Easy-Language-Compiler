import sys
import os
from typing import List, Optional, Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from lexer_module import Lexer, Token, TokenType
from parser import *


class Parser:
    """
    Recursive-descent parser for the Ely programming language.

    Converts a stream of tokens from the Lexer into an Abstract Syntax Tree (AST)
    using a series of mutually recursive parsing methods. Handles expressions,
    statements, declarations, type annotations, and control-flow constructs.

    Рекурсивный нисходящий парсер для языка программирования Ely.
    Преобразует поток токенов от лексера в абстрактное синтаксическое дерево (AST),
    используя ряд взаимно-рекурсивных методов разбора. Обрабатывает выражения,
    инструкции, объявления, аннотации типов и конструкции управления потоком.
    """
    RED = '\033[91m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    RESET = '\033[0m'

    def __init__(self, lexer: Lexer):
        """Инициализирует парсер, токенизируя входной код через лексер."""
        self.lexer = lexer
        self.tokens: List[Token] = lexer.tokenize()
        self.source = lexer.source
        self.source_lines = self.source.splitlines()
        self.pos = 0
        self.current_token: Optional[Token] = self.tokens[0] if self.tokens else None
        self._pending_externs = []
        self.errors: List[str] = []

    def _advance(self):
        """Переходит к следующему токену в потоке."""
        self.pos += 1
        if self.pos < len(self.tokens):
            self.current_token = self.tokens[self.pos]
        else:
            self.current_token = None

    def _peek(self, offset: int = 0) -> Optional[Token]:
        """Возвращает токен со смещением offset от текущей позиции без продвижения."""
        idx = self.pos + offset
        if idx < len(self.tokens):
            return self.tokens[idx]
        return None

    def _check(self, token_type: TokenType) -> bool:
        """Проверяет, является ли текущий токен указанным типом без продвижения."""
        return self.current_token is not None and self.current_token.type == token_type

    def _match(self, token_type: TokenType) -> bool:
        """Если текущий токен совпадает с типом, продвигается и возвращает True."""
        if self._check(token_type):
            self._advance()
            return True
        return False

    def _consume(self, token_type: TokenType, message: str) -> Optional[Token]:
        """Ожидает токен указанного типа; при успехе продвигается, иначе сообщает об ошибке."""
        if self._check(token_type):
            token = self.current_token
            self._advance()
            return token
        self._error(message)
        return None

    def _error(self, message: str):
        """
        Report a syntax error and attempt panic-mode recovery by skipping tokens
        until a synchronisation point (; , }, or EOF).

        :param message: Description of the syntax error.

        Сообщает о синтаксической ошибке и пытается восстановиться в паническом режиме,
        пропуская токены до точки синхронизации (;, }, или EOF).
        :param message: Описание синтаксической ошибки.
        """
        if self.current_token:
            self._error_at(self.current_token, message)
        else:
            self.errors.append(message)
        skip_limit = 100
        skipped = 0
        while (self.current_token is not None and
                self.current_token.type not in (TokenType.SEMICOLON, TokenType.RBRACE, TokenType.EOF)):
            self._advance()
            skipped += 1
            if skipped >= skip_limit:
                break

        if self.current_token is not None and self.current_token.type in (TokenType.SEMICOLON, TokenType.RBRACE):
            self._advance()

    def _error_at(self, token: Token, message: str):
        """Форматирует и выводит сообщение об ошибке с указанием строки, колонки и контекста кода."""
        line_no = token.line
        col_no = token.col
        line_text = self.source_lines[line_no - 1] if line_no <= len(self.source_lines) else ""

        prefix = f"{self.BOLD}{self.RED}SyntaxError{self.RESET}: {message}\n"
        file_info = f"  {self.BOLD}{self.CYAN}-->{self.RESET} line {line_no}, column {col_no}\n"
        code_line = f"  {self.BOLD}{line_text}{self.RESET}\n"
        pointer = f"  {' ' * (col_no - 1)}{self.BOLD}{self.RED}^{self.RESET}\n"

        error_msg = f"{prefix}{file_info}{code_line}{pointer}"
        sys.stderr.write(error_msg)
        self.errors.append(f"Syntax error at line {line_no}, column {col_no}: {message}")

    def _is_type_token(self) -> bool:
        """Проверяет, является ли текущий токен встроенным типом (int, str, bool, array, dict и т.д.)."""
        return (self._check(TokenType.INT) or self._check(TokenType.UINT) or
                self._check(TokenType.MORE) or self._check(TokenType.UMORE) or
                self._check(TokenType.FLT) or self._check(TokenType.DOUBLE) or
                self._check(TokenType.NOISED) or self._check(TokenType.STR) or
                self._check(TokenType.CHAR) or self._check(TokenType.BOOL) or
                self._check(TokenType.BYTE) or self._check(TokenType.UBYTE) or
                self._check(TokenType.ANY) or self._check(TokenType.VOID) or
                self._check(TokenType.ARRAY) or self._check(TokenType.DICT))

    def _parse_type(self) -> str:
        """
        Разбирает аннотацию типа. Поддерживает:
        - встроенные типы (int, flt, str, bool, ...)
        - параметризованные типы (array<T>, dict<K, V>)
        - дженерики (MyClass<T, U>)
        - указатели (type*)
        Возвращает строковое представление типа или "error" при ошибке.
        """
        base_type = None
        if self._match(TokenType.ARRAY):
            if self._match(TokenType.LESS):
                inner = self._parse_type()
                if inner == "error":
                    return "error"
                if self._consume(TokenType.GREATER, "Expected '>' after array type") is None:
                    return "error"
                base_type = f"arr<{inner}>"
            else:
                base_type = "arr<any>"
        elif self._match(TokenType.DICT):
            if self._match(TokenType.LESS):
                key_type = self._parse_type()
                if key_type == "error":
                    return "error"
                if self._consume(TokenType.COMMA, "Expected ',' in dict type") is None:
                    return "error"
                value_type = self._parse_type()
                if value_type == "error":
                    return "error"
                if self._consume(TokenType.GREATER, "Expected '>' after dict type") is None:
                    return "error"
                base_type = f"dict<{key_type}, {value_type}>"
            else:
                base_type = "dict<any,any>"
        elif self._is_type_token():
            base_type = self.current_token.lexeme
            self._advance()
            if self._match(TokenType.LBRACKET):
                if self._consume(TokenType.RBRACKET, "Expected ']' after array type") is None:
                    return "error"
                base_type = f"arr<{base_type}>"
        elif self._check(TokenType.IDENTIFIER):
            typ = self.current_token.lexeme
            self._advance()
            if self._match(TokenType.LESS):
                params = []
                while True:
                    param = self._parse_type()
                    if param == "error":
                        return "error"
                    params.append(param)
                    if self._match(TokenType.COMMA):
                        continue
                    break
                if self._consume(TokenType.GREATER, "Expected '>' after generic parameters") is None:
                    return "error"
                base_type = f"{typ}<{', '.join(params)}>"
            else:
                base_type = typ
        else:
            self._error("Expected type")
            return "error"

        while self._match(TokenType.MULTIPLY):
            base_type = f"{base_type}*"

        return base_type

    def parse(self) -> Program:
        """Запускает полный разбор программы, возвращая корневой узел AST — Program."""
        statements = []
        while self.current_token and self.current_token.type != TokenType.EOF:
            stmt = self._parse_statement()
            if stmt:
                statements.append(stmt)
                if hasattr(self, '_pending_externs') and self._pending_externs:
                    statements.extend(self._pending_externs)
                    self._pending_externs.clear()
        return Program(statements)

    def _parse_type_parameters(self) -> List[str]:
        """Разбирает список параметров дженериков <T, U, V>. Возвращает пустой список, если '<' отсутствует."""
        if not self._match(TokenType.LESS):
            return []
        params = []
        if self._check(TokenType.IDENTIFIER):
            params.append(self.current_token.lexeme)
            self._advance()
            while self._match(TokenType.COMMA):
                if not self._check(TokenType.IDENTIFIER):
                    self._error("Expected type parameter name")
                    return []
                params.append(self.current_token.lexeme)
                self._advance()
        if not self._consume(TokenType.GREATER, "Expected '>' after type parameters"):
            return []
        return params

    def _parse_statement(self) -> Optional[Statement]:
        """
        Диспетчер разбора инструкций. Определяет тип инструкции по первому токену
        и делегирует соответствующему методу. Обрабатывает:
        - аннотации (@tag)
        - using, public/private, class, struct, type, namespace, extern, const
        - интерфейсы (interface, impl)
        - управляющие конструкции (if, for, while, match, asafe)
        - throw, giveback, return, collapse, break
        - объявления переменных и выражения
        """
        if self._match(TokenType.AT):
            tag = self._parse_tag()
            if tag is None:
                return None
            saved_pos = self.pos
            saved_token = self.current_token
            var_decl = self._parse_variable_declaration(modifier=None)
            if var_decl is not None:
                var_decl.tag = tag
                if self._consume(TokenType.SEMICOLON, "Expected ';' after variable declaration") is None:
                    return None
                return var_decl
            self.pos = saved_pos
            self.current_token = saved_token
            if not (self._check(TokenType.INT) or self._check(TokenType.FLT) or
                    self._check(TokenType.STR) or self._check(TokenType.BOOL) or
                    self._check(TokenType.CHAR)):
                self._error("Expected type after tag")
                return None
            line = self.current_token.line
            col = self.current_token.col
            data_type = self.current_token.lexeme
            self._advance()
            data_memory = None
            if self._match(TokenType.LPAREN):
                if not self._check(TokenType.IDENTIFIER):
                    self._error("Expected memory type identifier")
                    return None
                data_memory = self.current_token.lexeme
                self._advance()
                if self._consume(TokenType.RPAREN, "Expected ')' after memory type") is None:
                    return None
            if self._consume(TokenType.ASSIGN, "Expected '=' after type") is None:
                return None
            expr = self._parse_expression()
            if expr is None:
                return None
            if self._consume(TokenType.SEMICOLON, "Expected ';' after expression") is None:
                return None
            memory_type = tag.arguments[0].name if tag.arguments else ''
            return OpMemDirective(
                line=line, col=col,
                memory_type=memory_type,
                data_type=data_type,
                data_memory=data_memory,
                expression=expr
            )

        if self._match(TokenType.USING):
            line = self.current_token.line if self.current_token else 0
            col = self.current_token.col if self.current_token else 0
            module = None
            if self._check(TokenType.IDENTIFIER):
                module = self.current_token.lexeme
                self._advance()
            elif self._check(TokenType.STRING):
                module = self.current_token.value
                self._advance()
            else:
                self._error("Expected module name or string after 'using'")
                return None
            if self._consume(TokenType.SEMICOLON, "Expected ';' after using") is None:
                return None
            return UsingDirective(line=line, col=col, module=module)

        if self._check(TokenType.PUBLIC) or self._check(TokenType.PRIVATE):
            saved_pos = self.pos
            is_async = False
            if self._match(TokenType.ASYNC):
                is_async = True
            saved_token = self.current_token

            mod_token = self.current_token
            self._advance()
            modifier = mod_token.lexeme

            is_abstract_cls = False
            is_sealed_cls = False
            if self._match(TokenType.ABSTRACT):
                is_abstract_cls = True
            elif self._match(TokenType.SEALED):
                is_sealed_cls = True

            if is_abstract_cls or is_sealed_cls:
                if self._check(TokenType.CLASS) or (self._check(TokenType.IDENTIFIER) and self._peek(1) and self._peek(1).type == TokenType.CLASS):
                    return self._parse_class_declaration(is_abstract=is_abstract_cls, is_sealed=is_sealed_cls)
                else:
                    self._error("Expected 'class' after abstract/sealed")
                    return None

            self.pos = saved_pos
            self.current_token = saved_token
            modifier = None

        if self._match(TokenType.PUBLIC) or self._match(TokenType.PRIVATE):
            modifier = self._previous().lexeme

            is_async = False
            if self._match(TokenType.ASYNC):
                is_async = True

            if self._check(TokenType.CLASS) or (self._check(TokenType.IDENTIFIER) and self._peek(1) and self._peek(1).type == TokenType.CLASS):
                return self._parse_class_declaration()
            if self._check(TokenType.STRUCT):
                return self._parse_struct_declaration()

            if self._match(TokenType.OVERRIDE):
                ret_type = self._parse_type()
                if ret_type == "error": return None
                if self._match(TokenType.FUNC):
                    method = self._parse_method_declaration(return_type=ret_type, modifier=modifier)
                    if method: method.is_override = True
                    return method
                else:
                    self._error("Expected 'func' after return type")
                    return None

            static = self._match(TokenType.STATIC)
            saved = self.pos
            saved_tok = self.current_token
            ret_type = None
            if self._is_type_token():
                ret_type = self._parse_type()
                if ret_type == "error": return None
            elif self._check(TokenType.VOID):
                ret_type = "void"
                self._advance()
            else:
                ret_type = 'any'

            if self._match(TokenType.FUNC):
                final_mod = 'static' if static else modifier
                return self._parse_method_declaration(return_type=ret_type, modifier=final_mod, is_async=is_async)
            else:
                if not self._check(TokenType.IDENTIFIER):
                    self._error("Expected variable name")
                    return None
                var_name = self.current_token.lexeme
                line = self.current_token.line
                col = self.current_token.col
                self._advance()
                initializer = None
                if self._match(TokenType.ASSIGN):
                    initializer = self._parse_expression()
                    if initializer is None: return None
                vdecl = VariableDeclaration(line=line, col=col,
                                            modifier='static' if static else modifier,
                                            type=ret_type,
                                            name=var_name,
                                            initializer=initializer)
                if self._consume(TokenType.SEMICOLON, "Expected ';' after variable declaration") is None:
                    return None
                return vdecl

        if self._match(TokenType.THROW):
            line = self.current_token.line if self.current_token else 0
            col = self.current_token.col if self.current_token else 0
            value = self._parse_expression()
            if self._consume(TokenType.SEMICOLON, "Expected ';' after throw") is None:
                return None
            return ThrowStatement(line=line, col=col, value=value)

        if self._match(TokenType.INTERFACE):
            return self._parse_interface_declaration()
        if self._match(TokenType.IMPL):
            if not self._check(TokenType.IDENTIFIER):
                self._error("Expected class name after 'impl'")
                return None
            class_name = self.current_token.lexeme
            self._advance()
            if not self._check(TokenType.IDENTIFIER):
                self._error("Expected interface name")
                return None
            interface_name = self.current_token.lexeme
            self._advance()
            return self._parse_impl_body(interface_name, class_name)

        if self._check(TokenType.CLASS):
            return self._parse_class_declaration()
        if self._match(TokenType.STRUCT):
            return self._parse_struct_declaration()
        if self._match(TokenType.TYPE):
            return self._parse_type_alias()
        if self._match(TokenType.NAMESPACE):
            return self._parse_namespace_declaration()
        if self._match(TokenType.EXTERN):
            return self._parse_extern_function()
        if self._match(TokenType.CONST):
            return self._parse_const_declaration()
        if self._match(TokenType.STATIC):
            var = self._parse_variable_declaration(modifier='static')
            if var is None: return None
            if self._consume(TokenType.SEMICOLON, "Expected ';' after static variable") is None:
                return None
            return var

        if self._match(TokenType.DELETE):
            self._error("delete not implemented yet")
            return None

        is_async = False
        if self._match(TokenType.ASYNC):
            is_async = True
        if self._match(TokenType.FUNC):
            return self._parse_method_declaration(is_async=is_async)

        if self._match(TokenType.IF):
            return self._parse_if_statement()
        if self._match(TokenType.FOREACH):
            return self._parse_for_statement()
        if self._match(TokenType.FOR):
            return self._parse_for_statement()
        if self._match(TokenType.WHILE):
            return self._parse_while_statement()
        if self._match(TokenType.MATCH):
            return self._parse_match_statement()
        if self._match(TokenType.ASAFE):
            return self._parse_asafe_block()

        if self._match(TokenType.GIVEBACK):
            return self._parse_giveback_statement()
        if self._match(TokenType.RETURN):
            return self._parse_return_statement()
        if self._match(TokenType.COLLAPSE):
            return self._parse_collapse_statement()
        if self._match(TokenType.BREAK):
            line = self.current_token.line if self.current_token else 0
            col = self.current_token.col if self.current_token else 0
            if self._consume(TokenType.SEMICOLON, "Expected ';' after break") is None:
                return None
            return BreakStatement(line=line, col=col)

        if self._match(TokenType.VOID):
            if not self._check(TokenType.FUNC):
                self._error("Expected 'func' after void")
                return None
            self._advance()
            return self._parse_method_declaration(return_type='void')

        if self._check(TokenType.CCODE):
            token = self.current_token
            self._advance()
            code = token.value
            if not code:
                self._error("Empty cCode block")
                return None
            line = token.line
            col = token.col
            import re
            extern_pattern = re.compile(
                r'extern\s+([a-zA-Z_][\w\s*]+?)\s+([a-zA-Z_]\w*)\s*\(([^)]*)\)\s*;'
            )
            for match in extern_pattern.finditer(code):
                ret_type = match.group(1).strip()
                func_name = match.group(2)
                params_str = match.group(3).strip()
                parameters = []
                if params_str:
                    for param in params_str.split(','):
                        param = param.strip()
                        if not param: continue
                        parts = param.rsplit(None, 1)
                        if len(parts) == 2:
                            param_type, param_name = parts
                            parameters.append(Parameter(type=param_type, name=param_name))
                        else:
                            parameters.append(Parameter(type=param, name=''))
                if not hasattr(self, '_pending_externs'): self._pending_externs = []
                self._pending_externs.append(
                    ExternFunction(line=line, col=col, return_type=ret_type, name=func_name, parameters=parameters)
                )
            return GlobalCBlock(line=line, col=col, code=code)
        if self._check(TokenType.CPPCODE):
            token = self.current_token
            self._advance()
            code = token.value
            if not code:
                self._error("Empty cppCode block")
                return None
            line = token.line
            col = token.col
            return GlobalCBlock(line=line, col=col, code=code)

        if self._check(TokenType.IDENTIFIER) and self._peek(1) and self._peek(1).type == TokenType.IMPL:
            interface_name = self.current_token.lexeme
            self._advance()
            self._advance()
            if not self._check(TokenType.IDENTIFIER):
                self._error("Expected class name after 'impl'")
                return None
            class_name = self.current_token.lexeme
            self._advance()
            return self._parse_impl_body(interface_name, class_name)

        if self._is_type_token() or (self._check(TokenType.IDENTIFIER) and self._peek(1) and self._peek(1).type not in (TokenType.FUNC, TokenType.LPAREN, TokenType.DOT, TokenType.ASSIGN, TokenType.LBRACKET)):
            saved_pos = self.pos
            saved_token = self.current_token
            type_name = self._parse_type()
            if type_name == "error": return None
            if self._match(TokenType.FUNC):
                return self._parse_method_declaration(return_type=type_name)
            else:
                if not self._check(TokenType.IDENTIFIER):
                    self._error("Expected variable name")
                    return None
                var_line = self.current_token.line if self.current_token else 0
                var_col = self.current_token.col if self.current_token else 0
                var_name = self.current_token.lexeme
                self._advance()
                initializer = None
                if self._match(TokenType.ASSIGN):
                    initializer = self._parse_expression()
                    if initializer is None: return None
                stmt = VariableDeclaration(line=var_line, col=var_col, modifier=None, type=type_name, name=var_name, initializer=initializer)
                if self._consume(TokenType.SEMICOLON, "Expected ';' after variable declaration") is None:
                    return None
                return stmt

        expr = self._parse_expression()
        if expr is None:
            return None
        if self._consume(TokenType.SEMICOLON, "Expected ';' after expression") is None:
            return None
        return ExpressionStatement(line=expr.line, col=expr.col, expression=expr)

    def _parse_tag(self) -> Optional[TagAnnotation]:
        """Разбирает аннотацию @tag_name[args]. Возвращает TagAnnotation."""
        if not self._check(TokenType.IDENTIFIER):
            self._error("Expected tag name after '@'")
            return None
        line = self.current_token.line
        col = self.current_token.col
        name = self.current_token.lexeme
        self._advance()
        args = []
        if self._match(TokenType.LBRACKET):
            if not self._check(TokenType.RBRACKET):
                arg = self._parse_expression()
                if arg is None:
                    return None
                args.append(arg)
                while self._match(TokenType.COMMA):
                    arg = self._parse_expression()
                    if arg is None:
                        return None
                    args.append(arg)
            if self._consume(TokenType.RBRACKET, "Expected ']' after tag arguments") is None:
                return None
        return TagAnnotation(line=line, col=col, name=name, arguments=args)

    def _parse_variable_declaration(self, modifier: Optional[str] = None) -> Optional[VariableDeclaration]:
        """Разбирает объявление переменной с необязательной инициализацией."""
        line = self.current_token.line if self.current_token else 0
        col = self.current_token.col if self.current_token else 0
        if self._is_type_token():
            type_name = self._parse_type()
            if type_name == "error": return None
        else:
            type_name = 'any'
        if not self._check(TokenType.IDENTIFIER):
            self._error("Expected variable name")
            return None
        name = self.current_token.lexeme
        self._advance()
        initializer = None
        if self._match(TokenType.ASSIGN):
            initializer = self._parse_expression()
            if initializer is None: return None
        return VariableDeclaration(
            line=line, col=col,
            modifier=modifier,
            type=type_name,
            name=name,
            initializer=initializer,
            tag=None
        )

    def _parse_class_declaration(self, is_abstract=False, is_sealed=False) -> Optional[ClassDeclaration]:
        """
        Разбирает объявление класса, включая:
        - наследование (ChildClass class ParentClass)
        - параметры дженериков
        - вызов super в конструкторе
        - поля, методы, статические члены, свойства, wait-поля, абстрактные методы.
        """
        line = self.current_token.line if self.current_token else 0
        col = self.current_token.col if self.current_token else 0

        extends = None
        if self._check(TokenType.IDENTIFIER) and self._peek(1) and self._peek(1).type == TokenType.CLASS:
            extends = self.current_token.lexeme
            self._advance()
        if not self._match(TokenType.CLASS):
            self._error("Expected 'class'")
            return None
        if not self._check(TokenType.IDENTIFIER):
            self._error("Expected class name")
            return None
        name = self.current_token.lexeme
        self._advance()

        type_params = self._parse_type_parameters()

        if self._consume(TokenType.LBRACE, "Expected '{' before class body") is None:
            return None

        methods = []
        fields = []
        super_args = []
        wait_fields = []
        static_fields = []
        static_methods = []
        properties = []

        if self._match(TokenType.SUPER):
            if self._consume(TokenType.LPAREN, "Expected '(' after super") is None:
                return None
            if not self._check(TokenType.RPAREN):
                super_args.append(self._parse_expression())
                while self._match(TokenType.COMMA):
                    super_args.append(self._parse_expression())
            if self._consume(TokenType.RPAREN, "Expected ')' after super arguments") is None:
                return None
            if self._consume(TokenType.SEMICOLON, "Expected ';' after super") is None:
                return None

        while not self._check(TokenType.RBRACE) and self.current_token:
            ret_type = None
            modifier = None
            if self._match(TokenType.PUBLIC) or self._match(TokenType.PRIVATE):
                modifier = self._previous().lexeme
            is_static = self._match(TokenType.STATIC)
            is_override = self._match(TokenType.OVERRIDE)

            if self._match(TokenType.ABSTRACT):
                ret_type = self._parse_type()
                if ret_type == "error": return None
                if not self._match(TokenType.FUNC):
                    self._error("Expected 'func' after abstract method return type")
                    return None
                if not self._check(TokenType.IDENTIFIER):
                    self._error("Expected method name")
                    return None
                mname = self.current_token.lexeme
                self._advance()
                if self._consume(TokenType.LPAREN, "Expected '('") is None: return None
                params = []
                if not self._check(TokenType.RPAREN):
                    param = self._parse_parameter()
                    if param is None: return None
                    params.append(param)
                    while self._match(TokenType.COMMA):
                        param = self._parse_parameter()
                        if param is None: return None
                        params.append(param)
                if self._consume(TokenType.RPAREN, "Expected ')'") is None: return None
                if self._consume(TokenType.SEMICOLON, "Expected ';' after abstract method") is None: return None
                method = MethodDeclaration(
                    line=line, col=col,
                    return_type=ret_type,
                    name=mname,
                    parameters=params,
                    body=[],
                    modifier=modifier,
                    is_abstract=True
                )
                methods.append(method)
                continue

            effective_mod = 'static' if is_static else modifier

            if self._match(TokenType.WAIT):
                wait_line = self.current_token.line if self.current_token else line
                wait_col = self.current_token.col if self.current_token else col
                wait_type = self._parse_type()
                if wait_type == "error":
                    return None
                if not self._check(TokenType.IDENTIFIER):
                    self._error("Expected wait field name")
                    return None
                wait_name = self.current_token.lexeme
                self._advance()
                init = None
                if self._match(TokenType.ASSIGN):
                    init = self._parse_expression()
                    if init is None: return None
                if self._consume(TokenType.SEMICOLON, "Expected ';' after wait field") is None:
                    return None
                field_decl = VariableDeclaration(
                    line=wait_line, col=wait_col,
                    modifier=None,
                    type=wait_type,
                    name=wait_name,
                    initializer=init
                )
                fields.append(field_decl)
                wait_fields.append(field_decl)
                continue

            # -------- unwait поля (через идентификатор 'unwait') --------
            if self._check(TokenType.IDENTIFIER) and self.current_token.lexeme == 'unwait':
                self._advance()  # съедаем 'unwait'
                uw_type = self._parse_type()
                if uw_type == "error":
                    return None
                if not self._check(TokenType.IDENTIFIER):
                    self._error("Expected field name after unwait type")
                    return None
                uw_name = self.current_token.lexeme
                self._advance()
                init = None
                if self._match(TokenType.ASSIGN):
                    init = self._parse_expression()
                    if init is None: return None
                else:
                    self._error("unwait field must have a default value")
                    return None
                if self._consume(TokenType.SEMICOLON, "Expected ';' after unwait field") is None:
                    return None
                field = VariableDeclaration(
                    line=line, col=col,
                    modifier=None,
                    type=uw_type,
                    name=uw_name,
                    initializer=init,
                    is_unwait=True,
                    unwait_default=init
                )
                fields.append(field)
                continue

            if ret_type and self._check(TokenType.IDENTIFIER):
                prop_name = self.current_token.lexeme
                prop_line = self.current_token.line
                prop_col = self.current_token.col
                prop_pos = self.pos
                prop_token = self.current_token
                self._advance()
                if self._check(TokenType.LBRACE):
                    self._advance()
                    if self._match(TokenType.IDENTIFIER) and self._previous().lexeme == 'get':
                        self._consume(TokenType.SEMICOLON, "Expected ';' after get")
                    else:
                        self._error("Expected 'get;' in property")
                        return None
                    if self._match(TokenType.IDENTIFIER) and self._previous().lexeme == 'set':
                        self._consume(TokenType.SEMICOLON, "Expected ';' after set")
                    else:
                        self._error("Expected 'set;' in property")
                        return None
                    if self._consume(TokenType.RBRACE, "Expected '}' after property") is None:
                        return None

                    fields.append(VariableDeclaration(
                        line=prop_line, col=prop_col,
                        modifier='public', type=ret_type, name=f"__{prop_name}"
                    ))

                    getter = MethodDeclaration(
                        line=prop_line, col=prop_col,
                        return_type=ret_type,
                        name=f"get{prop_name[0].upper()}{prop_name[1:]}",
                        parameters=[], body=[
                            ReturnStatement(line=prop_line, col=prop_col,
                                            value=Identifier(line=prop_line, col=prop_col, name=f"__{prop_name}"))
                        ],
                        modifier='public'
                    )

                    setter = MethodDeclaration(
                        line=prop_line, col=prop_col,
                        return_type='void',
                        name=f"set{prop_name[0].upper()}{prop_name[1:]}",
                        parameters=[Parameter(type=ret_type, name="value")],
                        body=[
                            Assignment(line=prop_line, col=prop_col,
                                       target=Identifier(line=prop_line, col=prop_col, name=f"__{prop_name}"),
                                       value=Identifier(line=prop_line, col=prop_col, name="value"),
                                       operator='=')
                        ],
                        modifier='public'
                    )

                    methods.append(getter)
                    methods.append(setter)
                    properties.append(PropertyDeclaration(name=prop_name, type=ret_type, getter=getter, setter=setter))
                    continue
                else:
                    self.pos = prop_pos
                    self.current_token = prop_token

            if self._check(TokenType.IDENTIFIER) and self.current_token.lexeme == name:
                ctor_pos = self.pos
                ctor_token = self.current_token
                self._advance()
                if self._check(TokenType.LPAREN):
                    ctor = self._parse_constructor(name)
                    if ctor:
                        methods.append(ctor)
                    continue
                else:
                    self.pos = ctor_pos
                    self.current_token = ctor_token

            ret_type = None
            saved_pos = self.pos
            saved_token = self.current_token
            if self._is_type_token() or self._check(TokenType.VOID) or (
                self._check(TokenType.IDENTIFIER) and
                self._peek(1) and
                self._peek(1).type not in (TokenType.LPAREN, TokenType.DOT, TokenType.LBRACE, TokenType.ASSIGN)
            ):
                ret_type = self._parse_type()
                if ret_type == "error":
                    return None

            if self._check(TokenType.FUNC):
                if ret_type is None:
                    self._error("Method must have a return type")
                    return None
                self._advance()
                method = self._parse_method_declaration(return_type=ret_type, modifier=effective_mod)
                if method:
                    if is_override:
                        method.is_override = True
                    methods.append(method)
                continue

            if ret_type and self._check(TokenType.IDENTIFIER):
                prop_name = self.current_token.lexeme
                prop_pos = self.pos
                prop_token = self.current_token
                self._advance()
                if self._check(TokenType.LBRACE):
                    prop = self._parse_property(ret_type, prop_name)
                    if prop:
                        fields.append(VariableDeclaration(
                            line=prop_token.line,
                            col=prop_token.col,
                            modifier='public',
                            type=ret_type,
                            name=f"__{prop_name}",
                            initializer=None
                        ))
                        properties.append(prop)
                    continue
                else:
                    self.pos = prop_pos
                    self.current_token = prop_token

            if ret_type and self._check(TokenType.IDENTIFIER):
                var_name = self.current_token.lexeme
                var_line = self.current_token.line if self.current_token else line
                var_col = self.current_token.col if self.current_token else col
                self._advance()
                init = None
                if self._match(TokenType.ASSIGN):
                    init = self._parse_expression()
                    if init is None: return None
                if self._consume(TokenType.SEMICOLON, "Expected ';' after field") is None:
                    return None
                field_decl = VariableDeclaration(
                    line=var_line, col=var_col,
                    modifier=effective_mod,
                    type=ret_type,
                    name=var_name,
                    initializer=init
                )
                fields.append(field_decl)
                if is_static:
                    static_fields.append(field_decl)
                continue

            self._error("Unexpected token in class body")
            self._advance()

        if self._consume(TokenType.RBRACE, "Expected '}' after class body") is None:
            return None

        for prop in properties:
            if prop.getter:
                methods.append(prop.getter)
            if prop.setter:
                methods.append(prop.setter)

        return ClassDeclaration(line=line, col=col, name=name, extends=extends,
                                methods=methods, type_params=type_params,
                                fields=fields, super_args=super_args,
                                wait_fields=wait_fields,
                                static_fields=static_fields,
                                static_methods=static_methods,
                                properties=properties,
                                is_abstract=is_abstract,
                                is_sealed=is_sealed)

    def _parse_method_declaration(self, return_type: Optional[str] = None, modifier: Optional[str] = None,
                                allow_func_keyword: bool = False, is_async: bool = False) -> Optional[MethodDeclaration]:
        """
        Разбирает объявление метода/функции.
        Поддерживает:
        - параметры дженериков
        - необязательный возвращаемый тип через ->
        - тело { ... } или краткое => expression
        - модификатор async
        """
        line = self.current_token.line if self.current_token else 0
        col = self.current_token.col if self.current_token else 0
        if allow_func_keyword and self._match(TokenType.FUNC):
            pass

        if not is_async and self._match(TokenType.ASYNC):
            is_async = True
            if not self._match(TokenType.FUNC):
                self._error("Expected 'func' after 'async'")
                return None

        if not self._check(TokenType.IDENTIFIER):
            self._error("Expected method name")
            return None
        name = self.current_token.lexeme
        self._advance()

        type_params = self._parse_type_parameters()

        if self._consume(TokenType.LPAREN, "Expected '(' after method name") is None:
            return None
        parameters = []
        if not self._check(TokenType.RPAREN):
            param = self._parse_parameter()
            if param is None:
                return None
            parameters.append(param)
            while self._match(TokenType.COMMA):
                param = self._parse_parameter()
                if param is None:
                    return None
                parameters.append(param)
        if self._consume(TokenType.RPAREN, "Expected ')' after parameters") is None:
            return None

        if self._match(TokenType.ARROW):
            return_type = self._parse_type()
            if return_type == "error":
                return None
        elif return_type is None:
            return_type = 'void'

        if self._match(TokenType.FAST_ARROW):
            expr = self._parse_expression()
            if expr is None:
                return None
            body = [ReturnStatement(line=expr.line, col=expr.col, value=expr)]
            if self._consume(TokenType.SEMICOLON, "Expected ';' after arrow expression") is None:
                return None
            return MethodDeclaration(
                line=line, col=col,
                return_type=return_type,
                name=name,
                parameters=parameters,
                body=body,
                modifier=modifier,
                type_params=type_params,
                is_async=is_async
            )
        else:
            if self._consume(TokenType.LBRACE, "Expected '{' before method body") is None:
                return None
            body = []
            while not self._check(TokenType.RBRACE) and self.current_token:
                stmt = self._parse_statement()
                if stmt:
                    body.append(stmt)
            if self._consume(TokenType.RBRACE, "Expected '}' after method body") is None:
                return None
            return MethodDeclaration(
                line=line, col=col,
                return_type=return_type,
                name=name,
                parameters=parameters,
                body=body,
                modifier=modifier,
                type_params=type_params,
                is_async=is_async
            )

    def _parse_parameter(self) -> Optional[Parameter]:
        """Разбирает один параметр: тип имя."""
        type_name = self._parse_type()
        if type_name == "error":
            return None
        if not self._check(TokenType.IDENTIFIER):
            self._error("Expected parameter name")
            return None
        name = self.current_token.lexeme
        self._advance()
        return Parameter(type=type_name, name=name)

    # ------------------------------------------------------------------
    # Control flow constructs
    # ------------------------------------------------------------------

    def _parse_if_statement(self) -> Optional[IfStatement]:
        """Разбирает if (условие) { тело } [else { тело }]."""
        line = self.current_token.line if self.current_token else 0
        col = self.current_token.col if self.current_token else 0
        if self._consume(TokenType.LPAREN, "Expected '(' after 'if'") is None:
            return None
        condition = self._parse_expression()
        if condition is None:
            return None
        if self._consume(TokenType.RPAREN, "Expected ')' after condition") is None:
            return None
        if self._consume(TokenType.LBRACE, "Expected '{' for if body") is None:
            return None
        then_body = []
        while not self._check(TokenType.RBRACE) and self.current_token:
            stmt = self._parse_statement()
            if stmt:
                then_body.append(stmt)
        if self._consume(TokenType.RBRACE, "Expected '}' after if body") is None:
            return None
        else_body = None
        if self._match(TokenType.ELSE):
            if self._consume(TokenType.LBRACE, "Expected '{' for else body") is None:
                return None
            else_body = []
            while not self._check(TokenType.RBRACE) and self.current_token:
                stmt = self._parse_statement()
                if stmt:
                    else_body.append(stmt)
            if self._consume(TokenType.RBRACE, "Expected '}' after else body") is None:
                return None
        return IfStatement(line=line, col=col, condition=condition, then_body=then_body, else_body=else_body)

    def _parse_while_statement(self) -> Optional[WhileLoop]:
        """Разбирает while (условие) { тело }."""
        line = self.current_token.line if self.current_token else 0
        col = self.current_token.col if self.current_token else 0
        if self._consume(TokenType.LPAREN, "Expected '(' after 'while'") is None:
            return None
        condition = self._parse_expression()
        if condition is None:
            return None
        if self._consume(TokenType.RPAREN, "Expected ')' after condition") is None:
            return None
        if self._consume(TokenType.LBRACE, "Expected '{' for while body") is None:
            return None
        body = []
        while not self._check(TokenType.RBRACE) and self.current_token:
            stmt = self._parse_statement()
            if stmt:
                body.append(stmt)
        if self._consume(TokenType.RBRACE, "Expected '}' after while body") is None:
            return None
        return WhileLoop(line=line, col=col, condition=condition, body=body)

    def _parse_for_statement(self) -> Optional[Statement]:
        """
        Разбирает for (инициализация; условие; шаг) { тело }
        или for (тип имя in коллекция) { тело } (for-each).
        """
        line = self.current_token.line if self.current_token else 0
        col = self.current_token.col if self.current_token else 0
        if self._consume(TokenType.LPAREN, "Expected '(' after 'for'") is None:
            return None
        saved_pos = self.pos
        saved_token = self.current_token
        try:
            init = None
            if not self._check(TokenType.SEMICOLON):
                if self._is_type_token():
                    type_name = self._parse_type()
                    if type_name == "error":
                        return None
                    if not self._check(TokenType.IDENTIFIER):
                        self._error("Expected variable name in for init")
                        return None
                    name = self.current_token.lexeme
                    self._advance()
                    initializer = None
                    if self._match(TokenType.ASSIGN):
                        initializer = self._parse_expression()
                        if initializer is None:
                            return None
                    init = VariableDeclaration(line=line, col=col, modifier=None, type=type_name, name=name, initializer=initializer)
                else:
                    expr = self._parse_expression()
                    if expr is None:
                        return None
                    init = ExpressionStatement(line=expr.line, col=expr.col, expression=expr)
            if self._check(TokenType.SEMICOLON):
                self._advance()
                condition = None
                if not self._check(TokenType.SEMICOLON):
                    condition = self._parse_expression()
                    if condition is None:
                        return None
                if self._consume(TokenType.SEMICOLON, "Expected ';' after for condition") is None:
                    return None
                update = None
                if not self._check(TokenType.RPAREN):
                    update = self._parse_expression()
                    if update is None:
                        return None
                if self._consume(TokenType.RPAREN, "Expected ')' after for clauses") is None:
                    return None
                if self._consume(TokenType.LBRACE, "Expected '{' for for body") is None:
                    return None
                body = []
                while not self._check(TokenType.RBRACE) and self.current_token:
                    stmt = self._parse_statement()
                    if stmt:
                        body.append(stmt)
                if self._consume(TokenType.RBRACE, "Expected '}' after for body") is None:
                    return None
                return ForLoop(line=line, col=col, init=init, condition=condition, update=update, body=body)
            else:
                self.pos = saved_pos
                self.current_token = saved_token
                item_type = None
                memory = None
                if self._is_type_token():
                    item_type = self._parse_type()
                    if item_type == "error":
                        return None
                    if self._match(TokenType.LPAREN):
                        if self._check(TokenType.IDENTIFIER):
                            memory = self.current_token.lexeme
                            self._advance()
                        if self._consume(TokenType.RPAREN, "Expected ')'") is None:
                            return None
                    if not self._check(TokenType.IDENTIFIER):
                        self._error("Expected variable name in for-each")
                        return None
                    name = self.current_token.lexeme
                    self._advance()
                    item_decl = VariableDeclaration(line=line, col=col, modifier=None, type=item_type, name=name, initializer=None, tag=None)
                else:
                    if not self._check(TokenType.IDENTIFIER):
                        self._error("Expected variable name in for-each")
                        return None
                    name = self.current_token.lexeme
                    self._advance()
                    item_decl = VariableDeclaration(line=line, col=col, modifier=None, type=None, name=name, initializer=None, tag=None)
                if not (self._check(TokenType.IN) or (self._check(TokenType.IDENTIFIER) and self.current_token.lexeme == 'in')):
                    self._error("Expected 'in' in for-each loop")
                    return None
                self._advance()
                iterable = self._parse_expression()
                if iterable is None:
                    return None
                if self._consume(TokenType.RPAREN, "Expected ')' after iterable") is None:
                    return None
                if self._consume(TokenType.LBRACE, "Expected '{' for for-each body") is None:
                    return None
                body = []
                while not self._check(TokenType.RBRACE) and self.current_token:
                    stmt = self._parse_statement()
                    if stmt:
                        body.append(stmt)
                if self._consume(TokenType.RBRACE, "Expected '}' after for-each body") is None:
                    return None
                return ForEachLoop(line=line, col=col, item_decl=item_decl, iterable=iterable, body=body)
        except Exception:
            self.pos = saved_pos
            self.current_token = saved_token
            self._error("Invalid for loop syntax")
            return None

    def _parse_match_statement(self) -> Optional[MatchStatement]:
        """Разбирает match выражение { case value: тело ... default: тело }."""
        line = self.current_token.line if self.current_token else 0
        col = self.current_token.col if self.current_token else 0
        expr = self._parse_expression()
        if expr is None:
            return None
        if self._consume(TokenType.LBRACE, "Expected '{' after match expression") is None:
            return None
        cases = []
        default_body = None
        while not self._check(TokenType.RBRACE) and self.current_token:
            if self._match(TokenType.CASE):
                case_line = self.current_token.line if self.current_token else line
                case_col = self.current_token.col if self.current_token else col
                case_value = self._parse_expression()
                if case_value is None:
                    return None
                if self._consume(TokenType.COLON, "Expected ':' after case value") is None:
                    return None
                body = []
                while not self._check(TokenType.CASE) and not self._check(TokenType.DEFAULT) and not self._check(TokenType.RBRACE) and self.current_token:
                    stmt = self._parse_statement()
                    if stmt:
                        body.append(stmt)
                cases.append(Case(value=case_value, body=body, line=case_line, col=case_col))
            elif self._match(TokenType.DEFAULT):
                if self._consume(TokenType.COLON, "Expected ':' after default") is None:
                    return None
                default_body = []
                while not self._check(TokenType.RBRACE) and self.current_token:
                    stmt = self._parse_statement()
                    if stmt:
                        default_body.append(stmt)
            else:
                self._error("Expected 'case' or 'default' in match")
                return None
        if self._consume(TokenType.RBRACE, "Expected '}' after match") is None:
            return None
        return MatchStatement(line=line, col=col, expression=expr, cases=cases, default_body=default_body)

    def _parse_asafe_block(self) -> Optional[AsafeBlock]:
        """Разбирает asafe { тело } except (Тип переменная) { тело }."""
        line = self.current_token.line if self.current_token else 0
        col = self.current_token.col if self.current_token else 0
        if self._consume(TokenType.LBRACE, "Expected '{' after asafe") is None:
            return None
        body = []
        while not self._check(TokenType.RBRACE) and self.current_token:
            stmt = self._parse_statement()
            if stmt:
                body.append(stmt)
        if self._consume(TokenType.RBRACE, "Expected '}' after asafe body") is None:
            return None
        except_handler = None
        if self._match(TokenType.EXCEPT):
            if self._consume(TokenType.LPAREN, "Expected '(' after except") is None:
                return None
            exc_type = self._parse_type()
            if exc_type == "error":
                return None
            if not self._check(TokenType.IDENTIFIER):
                self._error("Expected exception variable name after type")
                return None
            param = self.current_token.lexeme
            self._advance()
            if self._consume(TokenType.RPAREN, "Expected ')' after except parameter") is None:
                return None
            if self._consume(TokenType.LBRACE, "Expected '{' for except body") is None:
                return None
            exc_body = []
            while not self._check(TokenType.RBRACE) and self.current_token:
                stmt = self._parse_statement()
                if stmt:
                    exc_body.append(stmt)
            if self._consume(TokenType.RBRACE, "Expected '}' after except body") is None:
                return None
            except_handler = ExceptHandler(exception_type=exc_type, parameter=param, body=exc_body)
        return AsafeBlock(line=line, col=col, body=body, except_handler=except_handler)

    def _parse_giveback_statement(self) -> Optional[GivebackStatement]:
        """Разбирает giveback [выражение];."""
        line = self.current_token.line if self.current_token else 0
        col = self.current_token.col if self.current_token else 0
        value = None
        if not self._check(TokenType.SEMICOLON):
            value = self._parse_expression()
            if value is None:
                return None
        if self._consume(TokenType.SEMICOLON, "Expected ';' after giveback") is None:
            return None
        return GivebackStatement(line=line, col=col, value=value)

    def _parse_return_statement(self) -> Optional[ReturnStatement]:
        """Разбирает return [выражение];."""
        line = self.current_token.line if self.current_token else 0
        col = self.current_token.col if self.current_token else 0
        value = None
        if not self._check(TokenType.SEMICOLON):
            value = self._parse_expression()
            if value is None:
                return None
        if self._consume(TokenType.SEMICOLON, "Expected ';' after return") is None:
            return None
        return ReturnStatement(line=line, col=col, value=value)

    def _parse_collapse_statement(self) -> Optional[CollapseStatement]:
        """Разбирает collapse идентификатор;."""
        line = self.current_token.line if self.current_token else 0
        col = self.current_token.col if self.current_token else 0
        if not self._check(TokenType.IDENTIFIER):
            self._error("Expected variable name after collapse")
            return None
        name = self.current_token.lexeme
        self._advance()
        if self._consume(TokenType.SEMICOLON, "Expected ';' after collapse") is None:
            return None
        return CollapseStatement(line=line, col=col, name=name)

    def _parse_break_statement(self) -> Optional[BreakStatement]:
        """Разбирает break;."""
        line = self.current_token.line if self.current_token else 0
        col = self.current_token.col if self.current_token else 0
        if self._consume(TokenType.SEMICOLON, "Expected ';' after break") is None:
            return None
        return BreakStatement(line=line, col=col)

    # ------------------------------------------------------------------
    # Expressions — recursive descent with precedence climbing
    # ------------------------------------------------------------------

    def _parse_expression(self) -> Optional[Expression]:
        """Точка входа для разбора выражений. Начинает с самого низкоприоритетного — присваивания."""
        return self._parse_assignment()

    def _parse_assignment(self) -> Optional[Expression]:
        """
        Разбирает присваивание (=, +=, -=, *=, /=).
        Левая часть должна быть Identifier, MemberAccess или IndexExpression.
        """
        expr = self._parse_conditional()
        if expr is None:
            return None
        op_token = None
        if self._match(TokenType.ASSIGN):
            op_token = '='
        elif self._match(TokenType.FAST_PLUS):
            op_token = '+='
        elif self._match(TokenType.FAST_MINUS):
            op_token = '-='
        elif self._match(TokenType.FAST_MULTIPLY):
            op_token = '*='
        elif self._match(TokenType.FAST_DIVIDE):
            op_token = '/='
        if op_token:
            line = self.current_token.line if self.current_token else expr.line
            col = self.current_token.col if self.current_token else expr.col
            value = self._parse_assignment()
            if value is None:
                return None
            if isinstance(expr, (Identifier, MemberAccess, IndexExpression)):
                return Assignment(line=line, col=col, target=expr, value=value, operator=op_token)
            else:
                self._error("Invalid left-hand side of assignment")
                return None
        return expr

    def _parse_conditional(self) -> Optional[Expression]:
        """Разбирает тернарный оператор условие ? then_expr : else_expr."""
        expr = self._parse_logical_or()
        if expr is None:
            return None
        if self._match(TokenType.FAST_CONDITION):
            line = self.current_token.line if self.current_token else expr.line
            col = self.current_token.col if self.current_token else expr.col
            then_expr = self._parse_expression()
            if then_expr is None:
                return None
            if self._consume(TokenType.COLON, "Expected ':' in conditional expression") is None:
                return None
            else_expr = self._parse_expression()
            if else_expr is None:
                return None
            return Conditional(line=line, col=col, condition=expr, then_expr=then_expr, else_expr=else_expr)
        return expr

    def _parse_logical_or(self) -> Optional[Expression]:
        """Разбирает логическое ИЛИ (||)."""
        expr = self._parse_logical_and()
        if expr is None:
            return None
        while self._match(TokenType.LOGICAL_OR):
            line = self.current_token.line if self.current_token else expr.line
            col = self.current_token.col if self.current_token else expr.col
            right = self._parse_logical_and()
            if right is None:
                return None
            expr = BinaryOp(line=line, col=col, left=expr, operator='||', right=right)
        return expr

    def _parse_logical_and(self) -> Optional[Expression]:
        """Разбирает логическое И (&&)."""
        expr = self._parse_equality()
        if expr is None:
            return None
        while self._match(TokenType.LOGICAL_AND):
            line = self.current_token.line if self.current_token else expr.line
            col = self.current_token.col if self.current_token else expr.col
            right = self._parse_equality()
            if right is None:
                return None
            expr = BinaryOp(line=line, col=col, left=expr, operator='&&', right=right)
        return expr

    def _parse_equality(self) -> Optional[Expression]:
        """Разбирает операторы сравнения на равенство (==, !=)."""
        expr = self._parse_comparison()
        if expr is None:
            return None
        while self._match(TokenType.EQUAL) or self._match(TokenType.NOT_EQUAL):
            line = self.current_token.line if self.current_token else expr.line
            col = self.current_token.col if self.current_token else expr.col
            op = '==' if self._previous().type == TokenType.EQUAL else '!='
            right = self._parse_comparison()
            if right is None:
                return None
            expr = BinaryOp(line=line, col=col, left=expr, operator=op, right=right)
        return expr

    def _parse_comparison(self) -> Optional[Expression]:
        """Разбирает операторы сравнения (<, <=, >, >=)."""
        expr = self._parse_term()
        if expr is None:
            return None
        while self._match(TokenType.LESS) or self._match(TokenType.LESS_EQUAL) or \
            self._match(TokenType.GREATER) or self._match(TokenType.GREATER_EQUAL):
            line = self.current_token.line if self.current_token else expr.line
            col = self.current_token.col if self.current_token else expr.col
            if self._previous().type == TokenType.LESS:
                op = '<'
            elif self._previous().type == TokenType.LESS_EQUAL:
                op = '<='
            elif self._previous().type == TokenType.GREATER:
                op = '>'
            else:
                op = '>='
            right = self._parse_term()
            if right is None:
                return None
            expr = BinaryOp(line=line, col=col, left=expr, operator=op, right=right)
        return expr

    def _parse_term(self) -> Optional[Expression]:
        """Разбирает сложение и вычитание (+, -)."""
        expr = self._parse_factor()
        if expr is None:
            return None
        while self._match(TokenType.PLUS) or self._match(TokenType.MINUS):
            line = self.current_token.line if self.current_token else expr.line
            col = self.current_token.col if self.current_token else expr.col
            op = '+' if self._previous().type == TokenType.PLUS else '-'
            right = self._parse_factor()
            if right is None:
                return None
            expr = BinaryOp(line=line, col=col, left=expr, operator=op, right=right)
        return expr

    def _parse_factor(self) -> Optional[Expression]:
        """Разбирает умножение, деление и остаток от деления (*, /, %)."""
        expr = self._parse_unary()
        if expr is None:
            return None
        while self._match(TokenType.MULTIPLY) or self._match(TokenType.DIVIDE) or self._match(TokenType.MODULO):
            line = self.current_token.line if self.current_token else expr.line
            col = self.current_token.col if self.current_token else expr.col
            if self._previous().type == TokenType.MULTIPLY:
                op = '*'
            elif self._previous().type == TokenType.DIVIDE:
                op = '/'
            else:
                op = '%'
            right = self._parse_unary()
            if right is None:
                return None
            expr = BinaryOp(line=line, col=col, left=expr, operator=op, right=right)
        return expr

    def _parse_unary(self) -> Optional[Expression]:
        """Разбирает унарные операторы (!, -, *, &)."""
        if self._match(TokenType.LOGICAL_NOT) or self._match(TokenType.MINUS) or self._match(TokenType.MULTIPLY) or self._match(TokenType.ADDRESS):
            line = self.current_token.line if self.current_token else 0
            col = self.current_token.col if self.current_token else 0
            op = self._previous().lexeme
            expr = self._parse_unary()
            if expr is None:
                return None
            return UnaryOp(line=line, col=col, operator=op, operand=expr)
        return self._parse_call()

    def _parse_call(self) -> Optional[Expression]:
        """
        Разбирает вызовы функций/методов, доступ к членам (.) и индексацию ([]).
        Левоассоциативный цикл для постфиксных операторов.
        """
        expr = self._parse_primary()
        if expr is None:
            return None
        while True:
            if self._match(TokenType.LPAREN):
                line = self.current_token.line if self.current_token else expr.line
                col = self.current_token.col if self.current_token else expr.col
                args = self._parse_arguments()
                if args is None:
                    return None
                if self._consume(TokenType.RPAREN, "Expected ')' after arguments") is None:
                    return None
                expr = Call(line=line, col=col, callee=expr, arguments=args)
            elif self._match(TokenType.DOT):
                line = self.current_token.line if self.current_token else expr.line
                col = self.current_token.col if self.current_token else expr.col
                if not self._check(TokenType.IDENTIFIER):
                    self._error("Expected identifier after '.'")
                    return None
                member = self.current_token.lexeme
                self._advance()
                expr = MemberAccess(line=line, col=col, object=expr, member=member)
            elif self._match(TokenType.LBRACKET):
                line = self.current_token.line if self.current_token else expr.line
                col = self.current_token.col if self.current_token else expr.col
                index = self._parse_expression()
                if index is None:
                    return None
                if self._consume(TokenType.RBRACKET, "Expected ']' after index") is None:
                    return None
                expr = IndexExpression(line=line, col=col, target=expr, index=index)
            else:
                break
        return expr

    def _parse_arguments(self) -> Optional[List[Expression]]:
        """Разбирает список аргументов, разделённых запятыми."""
        args = []
        if not self._check(TokenType.RPAREN):
            arg = self._parse_expression()
            if arg is None:
                return None
            args.append(arg)
            while self._match(TokenType.COMMA):
                arg = self._parse_expression()
                if arg is None:
                    return None
                args.append(arg)
        return args

    def _parse_primary(self) -> Optional[Expression]:
        """
        Разбирает первичные выражения:
        await, typeof, fields, methods, new, f-string, строки, числа,
        булевы значения, null, массивы, словари, super, идентификаторы,
        а также выражения в скобках и @tag аннотации.
        """
        if self._match(TokenType.AWAIT):
            line = self.current_token.line if self.current_token else 0
            col = self.current_token.col if self.current_token else 0
            expr = self._parse_expression()
            if expr is None:
                return None
            return AwaitExpression(line=line, col=col, expression=expr)

        if self._match(TokenType.TYPEOF):
            line = self.current_token.line if self.current_token else 0
            col = self.current_token.col if self.current_token else 0
            if self._consume(TokenType.LPAREN, "Expected '(' after typeof"):
                arg = self._parse_expression()
                if self._consume(TokenType.RPAREN, "Expected ')'"):
                    return TypeOfExpression(line=line, col=col, argument=arg)
            return None

        if self._match(TokenType.FIELDS):
            line = self.current_token.line if self.current_token else 0
            col = self.current_token.col if self.current_token else 0
            if self._consume(TokenType.LPAREN, "Expected '(' after fields"):
                arg = self._parse_expression()
                if self._consume(TokenType.RPAREN, "Expected ')'"):
                    return FieldsExpression(line=line, col=col, argument=arg)
            return None

        if self._match(TokenType.METHODS):
            line = self.current_token.line if self.current_token else 0
            col = self.current_token.col if self.current_token else 0
            if self._consume(TokenType.LPAREN, "Expected '(' after methods"):
                arg = self._parse_expression()
                if self._consume(TokenType.RPAREN, "Expected ')'"):
                    return MethodsExpression(line=line, col=col, argument=arg)
            return None

        if self._match(TokenType.NEW):
            line = self.current_token.line if self.current_token else 0
            col = self.current_token.col if self.current_token else 0
            if not self._check(TokenType.IDENTIFIER):
                self._error("Expected class name after 'new'")
                return None
            class_name = self.current_token.lexeme
            self._advance()
            if self._consume(TokenType.LPAREN, "Expected '(' after class name") is None:
                return None
            args = self._parse_arguments()
            if args is None:
                return None
            if self._consume(TokenType.RPAREN, "Expected ')' after constructor arguments") is None:
                return None
            callee = Identifier(line=line, col=col, name=f"{class_name}_constructor")
            return Call(line=line, col=col, callee=callee, arguments=args)

        if self._check(TokenType.FSTRING):
            line = self.current_token.line
            col = self.current_token.col
            value = self.current_token.value
            self._advance()
            parts = self._parse_fstring_parts(value)
            return FString(line=line, col=col, parts=parts)

        if self._check(TokenType.FSTRING_MULTILINE):
            line = self.current_token.line
            col = self.current_token.col
            content = self.current_token.value
            self._advance()
            parts = self._parse_fstring_parts(content)
            return FString(line=line, col=col, parts=parts)

        if self._check(TokenType.MULTILINE_STRING):
            val = self.current_token.value
            line = self.current_token.line
            col = self.current_token.col
            self._advance()
            return Literal(line=line, col=col, value=val)

        if self._check(TokenType.NULL):
            line = self.current_token.line
            col = self.current_token.col
            self._advance()
            return Literal(line=line, col=col, value=None)

        if self._match(TokenType.AT):
            tag = self._parse_tag()
            if tag is None:
                return None
            expr = self._parse_expression()
            return expr

        if self._match(TokenType.LPAREN):
            expr = self._parse_expression()
            if expr is None:
                return None
            if self._consume(TokenType.RPAREN, "Expected ')' after expression") is None:
                return None
            return expr

        if self._check(TokenType.NUMBER):
            val = self.current_token.value
            line = self.current_token.line
            col = self.current_token.col
            self._advance()
            return Literal(line=line, col=col, value=val)

        if self._check(TokenType.STRING):
            val = self.current_token.value
            line = self.current_token.line
            col = self.current_token.col
            self._advance()
            return Literal(line=line, col=col, value=val)

        if self._check(TokenType.BOOLEAN):
            val = self.current_token.lexeme == 'true'
            line = self.current_token.line
            col = self.current_token.col
            self._advance()
            return Literal(line=line, col=col, value=val)

        if self._match(TokenType.LBRACKET):
            line = self.current_token.line if self.current_token else 0
            col = self.current_token.col if self.current_token else 0
            elements = []
            if not self._check(TokenType.RBRACKET):
                elem = self._parse_expression()
                if elem is None:
                    return None
                elements.append(elem)
                while self._match(TokenType.COMMA):
                    elem = self._parse_expression()
                    if elem is None:
                        return None
                    elements.append(elem)
            if self._consume(TokenType.RBRACKET, "Expected ']' after array literal") is None:
                return None
            return ArrayLiteral(line=line, col=col, elements=elements)

        if self._match(TokenType.LBRACE):
            line = self.current_token.line if self.current_token else 0
            col = self.current_token.col if self.current_token else 0
            pairs = []
            if not self._check(TokenType.RBRACE):
                key_expr = self._parse_expression()
                if key_expr is None:
                    return None
                if isinstance(key_expr, Identifier):
                    key_expr = Literal(line=key_expr.line, col=key_expr.col, value=key_expr.name)
                if self._consume(TokenType.COLON, "Expected ':' in dict literal") is None:
                    return None
                value = self._parse_expression()
                if value is None:
                    return None
                pairs.append(DictPair(key=key_expr, value=value))

                while self._match(TokenType.COMMA):
                    key_expr = self._parse_expression()
                    if key_expr is None:
                        return None
                    if isinstance(key_expr, Identifier):
                        key_expr = Literal(line=key_expr.line, col=key_expr.col, value=key_expr.name)
                    if self._consume(TokenType.COLON, "Expected ':' in dict literal") is None:
                        return None
                    value = self._parse_expression()
                    if value is None:
                        return None
                    pairs.append(DictPair(key=key_expr, value=value))
            if self._consume(TokenType.RBRACE, "Expected '}' after dict literal") is None:
                return None
            return DictLiteral(line=line, col=col, pairs=pairs)

        if self._match(TokenType.SUPER):
            line = self.current_token.line if self.current_token else 0
            col = self.current_token.col if self.current_token else 0
            if not self._check(TokenType.DOT):
                self._error("Expected '.' after super")
                return None
            self._advance()
            if not self._check(TokenType.IDENTIFIER):
                self._error("Expected method name after super.")
                return None
            method = self.current_token.lexeme
            self._advance()
            if self._consume(TokenType.LPAREN, "Expected '(' after method name") is None:
                return None
            args = self._parse_arguments()
            if args is None:
                return None
            if self._consume(TokenType.RPAREN, "Expected ')' after arguments") is None:
                return None
            return SuperCall(line=line, col=col, method=method, arguments=args)

        if self._check(TokenType.IDENTIFIER):
            name = self.current_token.lexeme
            line = self.current_token.line
            col = self.current_token.col
            self._advance()
            return Identifier(line=line, col=col, name=name)

        self._error(f"Unexpected token in expression: {self.current_token}")
        return None

    def _parse_fstring_parts(self, s: str) -> List[Any]:
        """Разбирает содержимое f-строки на строковые литералы и выражения в {...}."""
        parts = []
        i = 0
        n = len(s)
        while i < n:
            if s[i] == '{':
                j = i + 1
                depth = 1
                while j < n and depth > 0:
                    if s[j] == '{':
                        depth += 1
                    elif s[j] == '}':
                        depth -= 1
                    j += 1
                if depth != 0:
                    self._error("Unclosed '{' in f-string")
                    return []
                expr_str = s[i+1:j-1].strip()
                expr = self._parse_expression_from_string(expr_str)
                parts.append(expr)
                i = j
            else:
                start = i
                while i < n and s[i] != '{':
                    i += 1
                parts.append(s[start:i])
        return parts

    def _parse_expression_from_string(self, s: str) -> Expression:
        """Создаёт временный парсер для разбора выражения внутри f-строки."""
        saved_pos = self.pos
        saved_token = self.current_token
        saved_tokens = self.tokens
        from lexer_module import Lexer
        temp_lexer = Lexer(s)
        temp_parser = Parser(temp_lexer)
        expr = temp_parser._parse_expression()
        self.pos = saved_pos
        self.current_token = saved_token
        self.tokens = saved_tokens
        return expr

    def _parse_struct_declaration(self) -> Optional[StructDeclaration]:
        """Разбирает объявление структуры: struct Имя { поля }."""
        line = self.current_token.line if self.current_token else 0
        col = self.current_token.col if self.current_token else 0
        if not self._check(TokenType.IDENTIFIER):
            self._error("Expected struct name")
            return None
        name = self.current_token.lexeme
        self._advance()
        type_params = self._parse_type_parameters()
        if self._consume(TokenType.LBRACE, "Expected '{' after struct name") is None:
            return None
        fields = []
        while not self._check(TokenType.RBRACE) and self.current_token:
            field_type = self._parse_type()
            if field_type == "error":
                return None
            if not self._check(TokenType.IDENTIFIER):
                self._error("Expected field name")
                return None
            field_name = self.current_token.lexeme
            self._advance()
            if self._consume(TokenType.SEMICOLON, "Expected ';' after field") is None:
                return None
            field_decl = VariableDeclaration(
                line=self.current_token.line if self.current_token else line,
                col=self.current_token.col if self.current_token else col,
                modifier=None,
                type=field_type,
                name=field_name,
                initializer=None
            )
            fields.append(field_decl)
        if self._consume(TokenType.RBRACE, "Expected '}' after struct body") is None:
            return None
        return StructDeclaration(line=line, col=col, name=name, fields=fields, type_params=type_params)

    def _parse_type_alias(self) -> Optional[TypeAlias]:
        """Разбирает type Имя = Тип;."""
        line = self.current_token.line if self.current_token else 0
        col = self.current_token.col if self.current_token else 0
        if not self._check(TokenType.IDENTIFIER):
            self._error("Expected type alias name")
            return None
        name = self.current_token.lexeme
        self._advance()
        if self._consume(TokenType.ASSIGN, "Expected '=' after type alias name") is None:
            return None
        target_type = self._parse_type()
        if target_type == "error":
            return None
        if self._consume(TokenType.SEMICOLON, "Expected ';' after type alias") is None:
            return None
        return TypeAlias(line=line, col=col, name=name, target_type=target_type)

    def _parse_namespace_declaration(self) -> Optional[NamespaceDeclaration]:
        """Разбирает namespace Имя { тело }."""
        line = self.current_token.line if self.current_token else 0
        col = self.current_token.col if self.current_token else 0
        if not self._check(TokenType.IDENTIFIER):
            self._error("Expected namespace name")
            return None
        name = self.current_token.lexeme
        self._advance()
        if self._consume(TokenType.LBRACE, "Expected '{' after namespace name") is None:
            return None
        body = []
        while not self._check(TokenType.RBRACE) and self.current_token:
            stmt = self._parse_statement()
            if stmt:
                body.append(stmt)
        if self._consume(TokenType.RBRACE, "Expected '}' after namespace body") is None:
            return None
        return NamespaceDeclaration(line=line, col=col, name=name, body=body)

    def _parse_extern_function(self) -> Optional[ExternFunction]:
        """Разбирает extern [func] тип имя(параметры); — объявление внешней функции."""
        line = self.current_token.line if self.current_token else 0
        col = self.current_token.col if self.current_token else 0
        if self._match(TokenType.FUNC):
            pass
        return_type = self._parse_type()
        if return_type == "error":
            return None
        if not self._check(TokenType.IDENTIFIER):
            self._error("Expected extern function name")
            return None
        name = self.current_token.lexeme
        self._advance()
        if self._consume(TokenType.LPAREN, "Expected '(' after function name") is None:
            return None
        parameters = []
        if not self._check(TokenType.RPAREN):
            while True:
                if self._check(TokenType.DOT) and self._peek(1) and self._peek(1).lexeme == '.' and self._peek(2) and self._peek(2).lexeme == '.':
                    self._advance()
                    self._advance()
                    self._advance()
                    parameters.append(Parameter(type='...', name=''))
                    break
                param_type = self._parse_type()
                if param_type == "error":
                    return None
                if not self._check(TokenType.IDENTIFIER):
                    self._error("Expected parameter name")
                    return None
                param_name = self.current_token.lexeme
                self._advance()
                parameters.append(Parameter(type=param_type, name=param_name))
                if self._match(TokenType.COMMA):
                    continue
                else:
                    break
        if self._consume(TokenType.RPAREN, "Expected ')' after parameters") is None:
            return None
        if self._consume(TokenType.SEMICOLON, "Expected ';' after extern declaration") is None:
            return None
        return ExternFunction(line=line, col=col, name=name, parameters=parameters, return_type=return_type)

    def _parse_const_declaration(self) -> Optional[ConstDeclaration]:
        """Разбирает const тип имя = значение;."""
        line = self.current_token.line if self.current_token else 0
        col = self.current_token.col if self.current_token else 0
        type_name = self._parse_type()
        if type_name == "error":
            return None
        if not self._check(TokenType.IDENTIFIER):
            self._error("Expected const name")
            return None
        name = self.current_token.lexeme
        self._advance()
        if self._consume(TokenType.ASSIGN, "Expected '=' after const name") is None:
            return None
        value = self._parse_expression()
        if value is None:
            return None
        if self._consume(TokenType.SEMICOLON, "Expected ';' after const declaration") is None:
            return None
        return ConstDeclaration(line=line, col=col, name=name, type=type_name, value=value)

    def _parse_static_variable(self) -> Optional[StaticVariable]:
        """Разбирает static тип имя = значение;."""
        line = self.current_token.line if self.current_token else 0
        col = self.current_token.col if self.current_token else 0
        type_name = self._parse_type()
        if type_name == "error":
            return None
        if not self._check(TokenType.IDENTIFIER):
            self._error("Expected static variable name")
            return None
        name = self.current_token.lexeme
        self._advance()
        initializer = None
        if self._match(TokenType.ASSIGN):
            initializer = self._parse_expression()
            if initializer is None:
                return None
        if self._consume(TokenType.SEMICOLON, "Expected ';' after static variable declaration") is None:
            return None
        return StaticVariable(line=line, col=col, name=name, type=type_name, initializer=initializer)

    def _previous(self) -> Optional[Token]:
        """Возвращает предыдущий токен (если есть)."""
        if self.pos > 0:
            return self.tokens[self.pos - 1]
        return None

    def _parse_interface_declaration(self) -> Optional[InterfaceDeclaration]:
        """Разбирает interface Имя { тип func имя(параметры); ... }."""
        line = self.current_token.line if self.current_token else 0
        col = self.current_token.col if self.current_token else 0
        if not self._check(TokenType.IDENTIFIER):
            self._error("Expected interface name")
            return None
        name = self.current_token.lexeme
        self._advance()
        if self._consume(TokenType.LBRACE, "Expected '{' after interface name") is None:
            return None
        methods = []
        while not self._check(TokenType.RBRACE) and self.current_token:
            ret_type = self._parse_type()
            if ret_type == "error":
                return None
            if not self._match(TokenType.FUNC):
                self._error("Expected 'func' in interface method")
                return None
            if not self._check(TokenType.IDENTIFIER):
                self._error("Expected method name")
                return None
            mname = self.current_token.lexeme
            self._advance()
            if self._consume(TokenType.LPAREN, "Expected '('") is None:
                return None
            params = []
            if not self._check(TokenType.RPAREN):
                param = self._parse_parameter()
                if param is None:
                    return None
                params.append(param)
                while self._match(TokenType.COMMA):
                    param = self._parse_parameter()
                    if param is None:
                        return None
                    params.append(param)
            if self._consume(TokenType.RPAREN, "Expected ')'") is None:
                return None
            if self._consume(TokenType.SEMICOLON, "Expected ';'") is None:
                return None
            methods.append(MethodDeclaration(
                line=line, col=col,
                return_type=ret_type,
                name=mname,
                parameters=params,
                body=[], modifier=None
            ))
        if self._consume(TokenType.RBRACE, "Expected '}'") is None:
            return None
        return InterfaceDeclaration(line=line, col=col, name=name, methods=methods)

    def _parse_impl_body(self, interface_name: str, class_name: str) -> Optional[ImplDeclaration]:
        """Разбирает impl ClassName InterfaceName { реализации методов }."""
        line = self.current_token.line if self.current_token else 0
        col = self.current_token.col if self.current_token else 0
        if self._consume(TokenType.LBRACE, "Expected '{' after class name") is None:
            return None
        methods = []
        while not self._check(TokenType.RBRACE) and self.current_token:
            stmt = self._parse_statement()
            if stmt and isinstance(stmt, MethodDeclaration):
                methods.append(stmt)
        if self._consume(TokenType.RBRACE, "Expected '}'") is None:
            return None
        return ImplDeclaration(line=line, col=col, class_name=class_name, interface_name=interface_name, methods=methods)

    def _parse_constructor(self, class_name: str) -> Optional[MethodDeclaration]:
        """Разбирает конструктор класса: Имя(параметры) { тело }."""
        line = self.current_token.line if self.current_token else 0
        col = self.current_token.col if self.current_token else 0
        if self._consume(TokenType.LPAREN, "Expected '('") is None:
            return None
        params = []
        if not self._check(TokenType.RPAREN):
            param = self._parse_parameter()
            if param is None: return None
            params.append(param)
            while self._match(TokenType.COMMA):
                param = self._parse_parameter()
                if param is None: return None
                params.append(param)
        if self._consume(TokenType.RPAREN, "Expected ')'") is None:
            return None
        if self._consume(TokenType.LBRACE, "Expected '{'") is None:
            return None
        body = []
        while not self._check(TokenType.RBRACE) and self.current_token:
            stmt = self._parse_statement()
            if stmt:
                body.append(stmt)
        if self._consume(TokenType.RBRACE, "Expected '}'") is None:
            return None
        return MethodDeclaration(
            line=line, col=col,
            return_type=None,
            name=f"{class_name}_constructor",
            parameters=params,
            body=body,
            modifier='public'
        )

    def _parse_property(self, prop_type: str, prop_name: str) -> Optional[PropertyDeclaration]:
        """Разбирает тело свойства: { get; set; } или { get { ... } set { ... } }."""
        if self._consume(TokenType.LBRACE, "Expected '{' at start of property body") is None:
            return None
        getter = None
        setter = None
        hidden_field = f"__{prop_name}"

        while not self._check(TokenType.RBRACE) and self.current_token:
            if self._check(TokenType.IDENTIFIER):
                token = self.current_token
                if token.lexeme == 'get':
                    self._advance()
                    if self._match(TokenType.SEMICOLON):
                        body = [ReturnStatement(
                            line=token.line, col=token.col,
                            value=Identifier(line=token.line, col=token.col, name=hidden_field)
                        )]
                        getter = MethodDeclaration(
                            line=token.line, col=token.col,
                            return_type=prop_type,
                            name=f"get{prop_name[0].upper()}{prop_name[1:]}",
                            parameters=[],
                            body=body,
                            modifier='public'
                        )
                    else:
                        if self._consume(TokenType.LBRACE, "Expected '{' after 'get'") is None: return None
                        body = []
                        while not self._check(TokenType.RBRACE) and self.current_token:
                            stmt = self._parse_statement()
                            if stmt: body.append(stmt)
                        if self._consume(TokenType.RBRACE, "Expected '}' after get body") is None: return None
                        getter = MethodDeclaration(
                            line=token.line, col=token.col,
                            return_type=prop_type,
                            name=f"get{prop_name[0].upper()}{prop_name[1:]}",
                            parameters=[],
                            body=body,
                            modifier='public'
                        )
                elif token.lexeme == 'set':
                    self._advance()
                    if self._match(TokenType.SEMICOLON):
                        body = [Assignment(
                            line=token.line, col=token.col,
                            target=Identifier(line=token.line, col=token.col, name=hidden_field),
                            value=Identifier(line=token.line, col=token.col, name="value"),
                            operator='='
                        )]
                        setter = MethodDeclaration(
                            line=token.line, col=token.col,
                            return_type='void',
                            name=f"set{prop_name[0].upper()}{prop_name[1:]}",
                            parameters=[Parameter(type=prop_type, name="value")],
                            body=body,
                            modifier='public'
                        )
                    else:
                        if self._consume(TokenType.LBRACE, "Expected '{' after 'set'") is None: return None
                        body = []
                        while not self._check(TokenType.RBRACE) and self.current_token:
                            stmt = self._parse_statement()
                            if stmt: body.append(stmt)
                        if self._consume(TokenType.RBRACE, "Expected '}' after set body") is None: return None
                        setter = MethodDeclaration(
                            line=token.line, col=token.col,
                            return_type='void',
                            name=f"set{prop_name[0].upper()}{prop_name[1:]}",
                            parameters=[Parameter(type=prop_type, name="value")],
                            body=body,
                            modifier='public'
                        )
                else:
                    self._error("Expected 'get' or 'set' in property")
                    return None
            else:
                self._error("Expected 'get' or 'set'")
                return None
        if self._consume(TokenType.RBRACE, "Expected '}' after property body") is None:
            return None
        return PropertyDeclaration(name=prop_name, type=prop_type, getter=getter, setter=setter)

    def _parse_property(self, prop_type: str, prop_name: str) -> Optional[PropertyDeclaration]:
        """Разбирает тело блока { ... } и возвращает список инструкций."""
        if self._consume(TokenType.LBRACE, "Expected '{' at start of property body") is None:
            return None
        getter = None
        setter = None
        hidden_field = f"__{prop_name}"

        while not self._check(TokenType.RBRACE) and self.current_token:
            if self._check(TokenType.IDENTIFIER):
                token = self.current_token
                if token.lexeme == 'get':
                    self._advance()
                    if self._match(TokenType.SEMICOLON):
                        body = [ReturnStatement(
                            line=token.line, col=token.col,
                            value=Identifier(line=token.line, col=token.col, name=hidden_field)
                        )]
                        getter = MethodDeclaration(
                            line=token.line, col=token.col,
                            return_type=prop_type,
                            name=f"get{prop_name[0].upper()}{prop_name[1:]}",
                            parameters=[],
                            body=body,
                            modifier='public'
                        )
                    else:
                        if self._consume(TokenType.LBRACE, "Expected '{' after 'get'") is None: return None
                        body = []
                        while not self._check(TokenType.RBRACE) and self.current_token:
                            stmt = self._parse_statement()
                            if stmt: body.append(stmt)
                        if self._consume(TokenType.RBRACE, "Expected '}' after get body") is None: return None
                        getter = MethodDeclaration(
                            line=token.line, col=token.col,
                            return_type=prop_type,
                            name=f"get{prop_name[0].upper()}{prop_name[1:]}",
                            parameters=[],
                            body=body,
                            modifier='public'
                        )
                elif token.lexeme == 'set':
                    self._advance()
                    if self._match(TokenType.SEMICOLON):
                        body = [Assignment(
                            line=token.line, col=token.col,
                            target=Identifier(line=token.line, col=token.col, name=hidden_field),
                            value=Identifier(line=token.line, col=token.col, name="value"),
                            operator='='
                        )]
                        setter = MethodDeclaration(
                            line=token.line, col=token.col,
                            return_type='void',
                            name=f"set{prop_name[0].upper()}{prop_name[1:]}",
                            parameters=[Parameter(type=prop_type, name="value")],
                            body=body,
                            modifier='public'
                        )
                    else:
                        if self._consume(TokenType.LBRACE, "Expected '{' after 'set'") is None: return None
                        body = []
                        while not self._check(TokenType.RBRACE) and self.current_token:
                            stmt = self._parse_statement()
                            if stmt: body.append(stmt)
                        if self._consume(TokenType.RBRACE, "Expected '}' after set body") is None: return None
                        setter = MethodDeclaration(
                            line=token.line, col=token.col,
                            return_type='void',
                            name=f"set{prop_name[0].upper()}{prop_name[1:]}",
                            parameters=[Parameter(type=prop_type, name="value")],
                            body=body,
                            modifier='public'
                        )
                else:
                    self._error("Expected 'get' or 'set' in property")
                    return None
            else:
                self._error("Expected 'get' or 'set'")
                return None
        if self._consume(TokenType.RBRACE, "Expected '}' after property body") is None:
            return None
        return PropertyDeclaration(name=prop_name, type=prop_type, getter=getter, setter=setter)

    def _parse_block_body(self) -> List[Statement]:
        """Разбирает тело блока { ... } и возвращает список инструкций."""
        body = []
        while not self._check(TokenType.RBRACE) and self.current_token:
            stmt = self._parse_statement()
            if stmt:
                body.append(stmt)
        if self._consume(TokenType.RBRACE, "Expected '}' after body") is None:
            return body

