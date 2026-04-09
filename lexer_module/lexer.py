from .token import Token, TokenType

class Lexer:
    def __init__(self, source: str):
        self.source = source
        self.pos = 0
        self.line = 1
        self.col = 1
        self.tokens = []
        self.debug = False

        self.keywords = {
            'using': TokenType.USING,
            'class': TokenType.CLASS,
            'struct': TokenType.STRUCT,
            'type': TokenType.TYPE,
            'namespace': TokenType.NAMESPACE,
            'extern': TokenType.EXTERN,
            'const': TokenType.CONST,
            'static': TokenType.STATIC,
            'void': TokenType.VOID,
            'func': TokenType.FUNC,
            'giveback': TokenType.GIVEBACK,
            'return': TokenType.RETURN,
            'if': TokenType.IF,
            'else': TokenType.ELSE,
            'match': TokenType.MATCH,
            'case': TokenType.CASE,
            'default': TokenType.DEFAULT,
            'break': TokenType.BREAK,
            'asafe': TokenType.ASAFE,
            'throw': TokenType.THROW,
            'except': TokenType.EXCEPT,
            'new': TokenType.NEW,
            'delete': TokenType.DELETE,
            'in': TokenType.IN,
            'is': TokenType.IS,
            'not': TokenType.NOT,
            'public': TokenType.PUBLIC,
            'private': TokenType.PRIVATE,
            'collapse': TokenType.COLLAPSE,
            'int': TokenType.INT,
            'uint': TokenType.UINT,
            'more': TokenType.MORE,
            'umore': TokenType.UMORE,
            'flt': TokenType.FLT,
            'double': TokenType.DOUBLE,
            'noised': TokenType.NOISED,
            'str': TokenType.STR,
            'char': TokenType.CHAR,
            'bool': TokenType.BOOL,
            'byte': TokenType.BYTE,
            'ubyte': TokenType.UBYTE,
            'any': TokenType.ANY,
            'true': TokenType.BOOLEAN,
            'false': TokenType.BOOLEAN,
            'NULL': TokenType.NULL,
            'for': TokenType.FOR,
            'while': TokenType.WHILE,
            'foreach': TokenType.FOREACH,
            'interface': TokenType.INTERFACE,
            'impl': TokenType.IMPL,
            'override': TokenType.OVERRIDE,
            'abstract': TokenType.ABSTRACT,
            'sealed': TokenType.SEALED,
            'async': TokenType.ASYNC,
            'await': TokenType.AWAIT,
            'sizeof': TokenType.SIZEOF,
            'typeof': TokenType.TYPEOF,
            'as': TokenType.AS,
            # Новые ключевые слова
            'arr': TokenType.ARRAY,
            'dict': TokenType.DICT,
            'generic': TokenType.GENERIC,
        }

        self.two_char_ops = {
            '+=', '-=', '*=', '/=', '==', '!=', '<=', '>=', '&&', '||', '??', '->'
        }

    def tokenize(self, debug=False):
        self.debug = debug
        self.tokens = []

        while self.pos < len(self.source):
            self._skip_whitespace()
            if self.pos >= len(self.source):
                break

            if self._skip_comment():
                continue

            ch = self.source[self.pos]

            # Проверка на многострочную f-строку f"""
            if (ch == 'f' or ch == 'F') and self._peek(1) == '"' and self._peek(2) == '"' and self._peek(3) == '"':
                self._advance()  # съедаем f
                self._read_multiline_fstring()
                continue

            # Проверка на многострочную строку """
            if ch == '"' and self._peek(1) == '"' and self._peek(2) == '"':
                self._read_multiline_string()
                continue

            if ch == 'f' or ch == 'F':
                next_ch = self._peek(1)
                if next_ch == '"' or next_ch == "'":
                    self._advance()  # съедаем f
                    self._read_fstring(next_ch)  # передаём кавычку
                    continue

            if ch.isalpha() or ch == '_':
                self._read_identifier_or_keyword()
                continue

            if ch.isdigit():
                self._read_number()
                continue

            if ch == '"':
                self._read_string()
                continue

            if self._try_read_two_char_operator():
                continue

            if self._try_read_one_char_operator_or_delimiter():
                continue

            self._add_unknown_token()

        self._add_token(TokenType.EOF, '', self.line, self.col)
        return self.tokens

    def _advance(self):
        if self.pos < len(self.source) and self.source[self.pos] == '\n':
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        self.pos += 1

    def _peek(self, offset=0):
        idx = self.pos + offset
        return self.source[idx] if 0 <= idx < len(self.source) else None

    def _match(self, expected):
        if self._peek() == expected:
            self._advance()
            return True
        return False

    def _skip_whitespace(self):
        while self.pos < len(self.source):
            ch = self.source[self.pos]
            if ch in ' \t\r\n':
                self._advance()
            else:
                break

    def _skip_comment(self) -> bool:
        if self._peek() == '/' and self._peek(1) == '/':
            self._advance()
            self._advance()
            while self.pos < len(self.source) and self.source[self.pos] != '\n':
                self._advance()
            return True
        if self._peek() == '/' and self._peek(1) == '*':
            self._advance()
            self._advance()
            while self.pos < len(self.source):
                if self.source[self.pos] == '*' and self._peek(1) == '/':
                    self._advance()
                    self._advance()
                    break
                self._advance()
            return True
        return False

    def _add_token(self, token_type: TokenType, lexeme: str, line: int, col: int, value=None):
        token = Token(token_type, lexeme, line, col, value)
        self.tokens.append(token)
        if self.debug:
            print(f"DEBUG: {token}")

    def _read_identifier_or_keyword(self):
        start_col = self.col
        start_pos = self.pos
        while self.pos < len(self.source) and (self.source[self.pos].isalnum() or self.source[self.pos] == '_'):
            self._advance()
        lexeme = self.source[start_pos:self.pos]
        token_type = self.keywords.get(lexeme, TokenType.IDENTIFIER)
        self._add_token(token_type, lexeme, self.line, start_col)

    def _read_number(self):
        start_col = self.col
        start_pos = self.pos
        while self.pos < len(self.source) and self.source[self.pos].isdigit():
            self._advance()
        if self._peek() == '.' and self._peek(1) and self._peek(1).isdigit():
            self._advance()
            while self.pos < len(self.source) and self.source[self.pos].isdigit():
                self._advance()
        lexeme = self.source[start_pos:self.pos]
        if '.' in lexeme:
            value = float(lexeme)
        else:
            value = int(lexeme)
        self._add_token(TokenType.NUMBER, lexeme, self.line, start_col, value)

    def _read_string(self):
        start_col = self.col
        start_pos = self.pos
        self._advance()

        chars = []
        escaped = False

        while self.pos < len(self.source):
            ch = self.source[self.pos]

            if escaped:
                if ch == 'n':
                    chars.append('\n')
                elif ch == 't':
                    chars.append('\t')
                elif ch == 'r':
                    chars.append('\r')
                elif ch == '"':
                    chars.append('"')
                elif ch == '\\':
                    chars.append('\\')
                else:
                    chars.append('\\' + ch)
                escaped = False
                self._advance()
                continue

            if ch == '\\':
                escaped = True
                self._advance()
                continue

            if ch == '"':
                self._advance()
                break

            chars.append(ch)
            self._advance()
        else:
            # строка не закрыта
            pass

        raw_lexeme = self.source[start_pos:self.pos]
        value = ''.join(chars)
        self._add_token(TokenType.STRING, raw_lexeme, self.line, start_col, value)

    def _read_fstring(self, quote_char):
        start_col = self.col
        start_pos = self.pos
        self._advance()  # съедаем кавычку

        chars = []
        escaped = False

        while self.pos < len(self.source):
            ch = self.source[self.pos]

            if escaped:
                if ch == 'n':
                    chars.append('\n')
                elif ch == 't':
                    chars.append('\t')
                elif ch == 'r':
                    chars.append('\r')
                elif ch == '"':
                    chars.append('"')
                elif ch == "'":
                    chars.append("'")
                elif ch == '\\':
                    chars.append('\\')
                elif ch == '{':
                    chars.append('{')
                elif ch == '}':
                    chars.append('}')
                else:
                    chars.append('\\' + ch)
                escaped = False
                self._advance()
                continue

            if ch == '\\':
                escaped = True
                self._advance()
                continue

            if ch == quote_char:
                self._advance()
                break

            chars.append(ch)
            self._advance()
        else:
            # незакрытая строка – можно добавить ошибку, но пока игнорируем
            pass

        raw_lexeme = self.source[start_pos:self.pos]
        value = ''.join(chars)
        self._add_token(TokenType.FSTRING, raw_lexeme, self.line, start_col, value)

    def _try_read_two_char_operator(self) -> bool:
        if self.pos + 1 >= len(self.source):
            return False
        two_chars = self.source[self.pos:self.pos+2]
        if two_chars in self.two_char_ops:
            start_col = self.col
            self._advance()
            self._advance()
            try:
                token_type = TokenType(two_chars)
            except ValueError:
                return False
            self._add_token(token_type, two_chars, self.line, start_col)
            return True
        return False

    def _try_read_one_char_operator_or_delimiter(self) -> bool:
        ch = self.source[self.pos]
        start_col = self.col
        # Обработка оператора взятия адреса &
        if ch == '&' and self._peek(1) != '&':
            token_type = TokenType.ADDRESS
            self._advance()
            self._add_token(token_type, ch, self.line, start_col)
            return True
        try:
            token_type = TokenType(ch)
        except ValueError:
            return False
        self._advance()
        self._add_token(token_type, ch, self.line, start_col)
        return True

    def _add_unknown_token(self):
        start_col = self.col
        ch = self.source[self.pos]
        self._advance()
        self._add_token(TokenType.UNKNOWN, ch, self.line, start_col)

    def _read_multiline_string(self):
        start_col = self.col
        start_pos = self.pos
        # Пропускаем """
        self._advance()
        self._advance()
        self._advance()

        chars = []
        escaped = False

        while self.pos < len(self.source):
            ch = self.source[self.pos]

            if escaped:
                if ch == 'n':
                    chars.append('\n')
                elif ch == 't':
                    chars.append('\t')
                elif ch == 'r':
                    chars.append('\r')
                elif ch == '"':
                    chars.append('"')
                elif ch == '\\':
                    chars.append('\\')
                else:
                    chars.append('\\' + ch)
                escaped = False
                self._advance()
                continue

            if ch == '\\':
                escaped = True
                self._advance()
                continue

            if ch == '"' and self.pos + 2 < len(self.source) and self.source[self.pos+1] == '"' and self.source[self.pos+2] == '"':
                self._advance()
                self._advance()
                self._advance()
                break

            chars.append(ch)
            self._advance()
        else:
            self._error("Unclosed multiline string")
            return

        raw_lexeme = self.source[start_pos:self.pos]
        value = ''.join(chars)
        self._add_token(TokenType.MULTILINE_STRING, raw_lexeme, self.line, start_col, value)

    def _read_multiline_fstring(self):
        start_col = self.col
        start_pos = self.pos
        # Пропускаем f"""
        self._advance()  # f
        self._advance()  # "
        self._advance()  # "
        self._advance()  # "

        # Найдём позицию закрывающих """
        end_pos = self.pos
        depth = 0
        while end_pos < len(self.source):
            ch = self.source[end_pos]
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
            elif ch == '"' and end_pos + 2 < len(self.source) and self.source[end_pos+1] == '"' and self.source[end_pos+2] == '"' and depth == 0:
                break
            end_pos += 1
        else:
            self._error("Unclosed multiline f-string")
            return

        content = self.source[self.pos:end_pos]
        # Перемещаем позицию на закрывающие """
        self.pos = end_pos
        self._advance()
        self._advance()
        self._advance()

        raw_lexeme = self.source[start_pos:self.pos]
        self._add_token(TokenType.FSTRING_MULTILINE, raw_lexeme, self.line, start_col, content)