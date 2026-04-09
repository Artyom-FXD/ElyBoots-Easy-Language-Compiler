import sys
import os
from typing import List, Optional, Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from lexer_module import Lexer, Token, TokenType
from parser import *

class Parser:
    def __init__(self, lexer: Lexer):
        self.tokens: List[Token] = lexer.tokenize()
        self.pos = 0
        self.current_token: Optional[Token] = self.tokens[0] if self.tokens else None
        self.errors: List[str] = []

    def _advance(self):
        self.pos += 1
        if self.pos < len(self.tokens):
            self.current_token = self.tokens[self.pos]
        else:
            self.current_token = None

    def _peek(self, offset: int = 0) -> Optional[Token]:
        idx = self.pos + offset
        if idx < len(self.tokens):
            return self.tokens[idx]
        return None

    def _check(self, token_type: TokenType) -> bool:
        return self.current_token is not None and self.current_token.type == token_type

    def _match(self, token_type: TokenType) -> bool:
        if self._check(token_type):
            self._advance()
            return True
        return False

    def _consume(self, token_type: TokenType, message: str) -> Optional[Token]:
        if self._check(token_type):
            token = self.current_token
            self._advance()
            return token
        self._error(message)
        return None

    def _error(self, message: str):
        line = self.current_token.line if self.current_token else -1
        col = self.current_token.col if self.current_token else -1
        error_msg = f"Syntax error at line {line}, column {col}: {message}"
        self.errors.append(error_msg)
        while self.current_token and self.current_token.type not in (TokenType.SEMICOLON, TokenType.RBRACE, TokenType.EOF):
            self._advance()
        if self.current_token and self.current_token.type in (TokenType.SEMICOLON, TokenType.RBRACE):
            self._advance()

    def _is_type_token(self) -> bool:
        return (self._check(TokenType.INT) or self._check(TokenType.UINT) or
                self._check(TokenType.MORE) or self._check(TokenType.UMORE) or
                self._check(TokenType.FLT) or self._check(TokenType.DOUBLE) or
                self._check(TokenType.NOISED) or self._check(TokenType.STR) or
                self._check(TokenType.CHAR) or self._check(TokenType.BOOL) or
                self._check(TokenType.BYTE) or self._check(TokenType.UBYTE) or
                self._check(TokenType.ANY) or self._check(TokenType.VOID) or
                self._check(TokenType.ARRAY) or self._check(TokenType.DICT))

    def _parse_type(self) -> str:
        # Сначала разбираем базовый тип
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
            # int[] -> arr<int>
            if self._match(TokenType.LBRACKET):
                if self._consume(TokenType.RBRACKET, "Expected ']' after array type") is None:
                    return "error"
                base_type = f"arr<{base_type}>"
        elif self._check(TokenType.IDENTIFIER):
            typ = self.current_token.lexeme
            self._advance()
            # Возможны параметризованные типы для пользовательских типов (generic)
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

        # После получения базового типа обрабатываем звёздочки (указатели)
        while self._match(TokenType.MULTIPLY):
            base_type = f"{base_type}*"

        return base_type

    def parse(self) -> Program:
        statements = []
        while self.current_token and self.current_token.type != TokenType.EOF:
            stmt = self._parse_statement()
            if stmt:
                statements.append(stmt)
        return Program(statements)

    def _parse_type_parameters(self) -> List[str]:
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
        # Тег перед инструкцией
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
            if not self._check(TokenType.IDENTIFIER):
                self._error("Expected module name after 'using'")
                return None
            module = self.current_token.lexeme
            self._advance()
            if self._consume(TokenType.SEMICOLON, "Expected ';' after using") is None:
                return None
            return UsingDirective(line=line, col=col, module=module)

        if self._match(TokenType.PUBLIC):
            saved_pos = self.pos
            saved_token = self.current_token
            method = self._parse_method_declaration(modifier='public', allow_func_keyword=True)
            if method is not None:
                return method
            self.pos = saved_pos
            self.current_token = saved_token
            stmt = self._parse_variable_declaration(modifier='public')
            if stmt is None:
                return None
            if self._consume(TokenType.SEMICOLON, "Expected ';' after variable declaration") is None:
                return None
            return stmt

        if self._match(TokenType.PRIVATE):
            saved_pos = self.pos
            saved_token = self.current_token
            method = self._parse_method_declaration(modifier='private', allow_func_keyword=True)
            if method is not None:
                return method
            self.pos = saved_pos
            self.current_token = saved_token
            stmt = self._parse_variable_declaration(modifier='private')
            if stmt is None:
                return None
            if self._consume(TokenType.SEMICOLON, "Expected ';' after variable declaration") is None:
                return None
            return stmt

        if self._match(TokenType.THROW):
            line = self.current_token.line if self.current_token else 0
            col = self.current_token.col if self.current_token else 0
            value = self._parse_expression()
            if self._consume(TokenType.SEMICOLON, "Expected ';' after throw") is None:
                return None
            return ThrowStatement(line=line, col=col, value=value)

        if self._match(TokenType.CLASS):
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
            return self._parse_static_variable()
        if self._match(TokenType.DELETE):
            self._error("delete not implemented yet")
            return None
        if self._match(TokenType.FUNC):
            return self._parse_method_declaration()
        if self._match(TokenType.IF):
            return self._parse_if_statement()
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
        if self._is_type_token() or (self._check(TokenType.IDENTIFIER) and self._peek(1) and self._peek(1).type == TokenType.IDENTIFIER):
            saved_pos = self.pos
            saved_token = self.current_token
            type_name = self._parse_type()
            if type_name == "error":
                return None
            if self._match(TokenType.FUNC):
                return self._parse_method_declaration(return_type=type_name)
            else:
                self.pos = saved_pos
                self.current_token = saved_token
                stmt = self._parse_variable_declaration(modifier=None)
                if stmt is None:
                    return None
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
        line = self.current_token.line if self.current_token else 0
        col = self.current_token.col if self.current_token else 0
        type_name = self._parse_type()
        if type_name == "error":
            return None
        if not self._check(TokenType.IDENTIFIER):
            self._error("Expected variable name")
            return None
        name = self.current_token.lexeme
        self._advance()
        initializer = None
        if self._match(TokenType.ASSIGN):
            initializer = self._parse_expression()
            if initializer is None:
                return None
        return VariableDeclaration(
            line=line, col=col,
            modifier=modifier,
            type=type_name,
            name=name,
            initializer=initializer,
            tag=None
        )

    def _parse_class_declaration(self) -> Optional[ClassDeclaration]:
        line = self.current_token.line if self.current_token else 0
        col = self.current_token.col if self.current_token else 0
        if not self._check(TokenType.IDENTIFIER):
            self._error("Expected class name")
            return None
        name = self.current_token.lexeme
        self._advance()
        type_params = self._parse_type_parameters()   # добавлено
        extends = None
        if self._match(TokenType.COLON):
            if not self._check(TokenType.IDENTIFIER):
                self._error("Expected parent class name")
                return None
            extends = self.current_token.lexeme
            self._advance()
        if self._consume(TokenType.LBRACE, "Expected '{' before class body") is None:
            return None
        methods = []
        while not self._check(TokenType.RBRACE) and self.current_token:
            if self._match(TokenType.FUNC):
                method = self._parse_method_declaration()
                if method is None:
                    return None
                methods.append(method)
            else:
                self._advance()
        if self._consume(TokenType.RBRACE, "Expected '}' after class body") is None:
            return None
        return ClassDeclaration(line=line, col=col, name=name, extends=extends, methods=methods, type_params=type_params)

    def _parse_method_declaration(self, return_type: Optional[str] = None, modifier: Optional[str] = None, allow_func_keyword: bool = False) -> Optional[MethodDeclaration]:
        line = self.current_token.line if self.current_token else 0
        col = self.current_token.col if self.current_token else 0
        if allow_func_keyword and self._match(TokenType.FUNC):
            pass
        if not self._check(TokenType.IDENTIFIER):
            self._error("Expected method name")
            return None
        name = self.current_token.lexeme
        self._advance()

        # Разбор параметров типов (дженерики)
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

        # Разбор возвращаемого типа
        if return_type is None:
            if self._match(TokenType.ARROW):
                return_type = self._parse_type()
                if return_type == "error":
                    return None
            else:
                return_type = 'void'
        # else: return_type уже задан (например, для void func)

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
            type_params=type_params
        )

    def _parse_parameter(self) -> Optional[Parameter]:
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
    # Управляющие конструкции
    # ------------------------------------------------------------------
    def _parse_if_statement(self) -> Optional[IfStatement]:
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
                if self._is_type_token():
                    type_name = self._parse_type()
                    if type_name == "error":
                        return None
                    memory = None
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
                    item_decl = VariableDeclaration(line=line, col=col, modifier=None, type=type_name, initializer=None, tag=None)
                else:
                    if not self._check(TokenType.IDENTIFIER):
                        self._error("Expected variable name in for-each")
                        return None
                    name = self.current_token.lexeme
                    self._advance()
                    item_decl = VariableDeclaration(line=line, col=col, modifier=None, type=None, name=name, initializer=None, tag=None)
                if not self._check(TokenType.IDENTIFIER) or self.current_token.lexeme != 'of':
                    self._error("Expected 'of' in for-each loop")
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
            # Разбираем тип исключения (может быть ключевым словом, например str)
            exc_type = self._parse_type()
            if exc_type == "error":
                return None
            param = None
            if self._check(TokenType.IDENTIFIER):
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
        line = self.current_token.line if self.current_token else 0
        col = self.current_token.col if self.current_token else 0
        if self._consume(TokenType.SEMICOLON, "Expected ';' after break") is None:
            return None
        return BreakStatement(line=line, col=col)

    # ------------------------------------------------------------------
    # Выражения
    # ------------------------------------------------------------------
    def _parse_expression(self) -> Optional[Expression]:
        return self._parse_assignment()

    def _parse_assignment(self) -> Optional[Expression]:
        expr = self._parse_conditional()
        if expr is None:
            return None
        if self._match(TokenType.ASSIGN):
            line = self.current_token.line if self.current_token else expr.line
            col = self.current_token.col if self.current_token else expr.col
            value = self._parse_assignment()
            if value is None:
                return None
            return Assignment(line=line, col=col, target=expr, value=value)
        return expr

    def _parse_conditional(self) -> Optional[Expression]:
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
        if self._check(TokenType.FSTRING):
            line = self.current_token.line
            col = self.current_token.col
            raw = self.current_token.lexeme
            value = self.current_token.value
            self._advance()
            parts = self._parse_fstring_parts(value)
            return FString(line=line, col=col, parts=parts)
        if self._check(TokenType.FSTRING_MULTILINE):
            line = self.current_token.line
            col = self.current_token.col
            content = self.current_token.value  # содержимое между кавычками
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
                # парсим первый ключ
                key_expr = self._parse_expression()
                if key_expr is None:
                    return None
                # если ключ — идентификатор, превращаем в строковый литерал
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
        if self._check(TokenType.IDENTIFIER):
            name = self.current_token.lexeme
            line = self.current_token.line
            col = self.current_token.col
            self._advance()
            return Identifier(line=line, col=col, name=name)
        self._error(f"Unexpected token in expression: {self.current_token}")
        return None

    def _parse_fstring_parts(self, s: str) -> List[Any]:
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
        line = self.current_token.line if self.current_token else 0
        col = self.current_token.col if self.current_token else 0
        if not self._check(TokenType.IDENTIFIER):
            self._error("Expected struct name")
            return None
        name = self.current_token.lexeme
        self._advance()
        type_params = self._parse_type_parameters()   # добавлено
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
                # Check for variadic ...
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
        if self.pos > 0:
            return self.tokens[self.pos - 1]
        return None