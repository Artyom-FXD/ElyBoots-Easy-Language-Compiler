from .token import Token, TokenType

class Lexer:
    """
    Performs lexical analysis (tokenisation) of Ely source code.
    """

    def __init__(self, source: str):
        self.source = source
        self.pos = 0
        self.line = 1
        self.col = 1
        self.tokens = []
        self.debug = False

        self.keywords = {
            'cCode': TokenType.CCODE,
            'cppCode': TokenType.CPPCODE,
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
            'arr': TokenType.ARRAY, 
            'dict': TokenType.DICT, 
            'generic': TokenType.GENERIC,
            'fields': TokenType.FIELDS, 
            'methods': TokenType.METHODS, 
            'wait': TokenType.WAIT,
            'unwait': TokenType.UNWAIT, # Добавлен пропущенный токен
            'super': TokenType.SUPER,
        }

        self.two_char_ops = {
            '+=', '-=', '*=', '/=', '==', '!=', '<=', '>=', '&&', '||', '??', '->', '=>'
        }

    def tokenize(self, debug=False):
        self.debug = debug
        self.tokens = []
        src_len = len(self.source)

        while self.pos < src_len:
            self._skip_whitespace()
            if self.pos >= src_len:
                break

            if self._skip_comment():
                continue

            ch = self.source[self.pos]

            # Macro Identifier style 1: @macro_name
            if ch == '@':
                next_ch = self._peek(1)
                if next_ch and (next_ch.isalpha() or next_ch == '_'):
                    self._read_macro_directive()
                    continue

            # Поддержка многострочных f-строк: f"""...""" или f'''...'''
            if (ch == 'f' or ch == 'F') and self._peek(1) in ('"', "'") and self._peek(2) == self._peek(1) and self._peek(3) == self._peek(1):
                quote_char = self._peek(1)
                self._advance() # Пропускаем 'f'
                self._read_multiline_fstring(quote_char)
                continue

            # Поддержка многострочных строк: """...""" или '''...'''
            if ch in ('"', "'") and self._peek(1) == ch and self._peek(2) == ch:
                self._read_multiline_string(ch)
                continue

            # Однострочные f-строки: f"..." или f'...'
            if (ch == 'f' or ch == 'F') and (self._peek(1) == '"' or self._peek(1) == "'"):
                self._advance() # Пропускаем 'f'
                self._read_fstring(self._peek())
                continue

            # Raw C/C++ blocks optimization
            if ch == 'c' and self.pos + 5 <= src_len and self.source[self.pos:self.pos+5] == 'cCode':
                next_ch = self._peek(5)
                if next_ch and (next_ch.isalnum() or next_ch == '_'):
                    self._read_identifier_or_keyword()
                else:
                    self._read_c_code()
                continue

            if ch == 'c' and self.pos + 7 <= src_len and self.source[self.pos:self.pos+7] == 'cppCode':
                next_ch = self._peek(7)
                if next_ch and (next_ch.isalnum() or next_ch == '_'):
                    self._read_identifier_or_keyword()
                else:
                    self._read_cpp_code()
                continue

            if ch.isalpha() or ch == '_':
                self._read_identifier_or_keyword()
                continue

            if ch.isdigit():
                self._read_number()
                continue

            # Обычные однострочные строки: "..." или '...'
            if ch == '"' or ch == "'":
                self._read_string(ch)
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
            closed = False
            while self.pos < len(self.source):
                if self.source[self.pos] == '*' and self._peek(1) == '/':
                    self._advance()
                    self._advance()
                    closed = True
                    break
                self._advance()
            if not closed:
                self._error("multiline comment")
            return True
        return False

    def _add_token(self, token_type: TokenType, lexeme: str, line: int, col: int, value=None):
        token = Token(token_type, lexeme, line, col, value)
        self.tokens.append(token)
        if self.debug:
            print(f"DEBUG: {token}")

    def _error(self, context: str):
        raise SyntaxError(f"Unterminated {context} at line {self.line}, column {self.col}")

    def _read_macro_directive(self):
        start_col = self.col
        start_pos = self.pos
        self._advance()
        while self.pos < len(self.source) and (self.source[self.pos].isalnum() or self.source[self.pos] == '_'):
            self._advance()
        lexeme = self.source[start_pos:self.pos]
        macro_name = lexeme[1:]
        self._add_token(TokenType.MACRO_IDENTIFIER, lexeme, self.line, start_col, value=macro_name)

    def _read_identifier_or_keyword(self):
        start_col = self.col
        start_pos = self.pos
        while self.pos < len(self.source) and (self.source[self.pos].isalnum() or self.source[self.pos] == '_'):
            self._advance()
        lexeme = self.source[start_pos:self.pos]
        
        if self._peek() == '!' and self._peek(1) != '=':
            self._advance()
            full_lexeme = self.source[start_pos:self.pos]
            self._add_token(TokenType.MACRO_IDENTIFIER, full_lexeme, self.line, start_col, value=lexeme)
            return

        token_type = self.keywords.get(lexeme, TokenType.IDENTIFIER)
        self._add_token(token_type, lexeme, self.line, start_col)

    def _read_number(self):
        start_col = self.col
        start_pos = self.pos
        
        if self.source[self.pos] == '0' and self.pos + 1 < len(self.source):
            next_ch = self.source[self.pos + 1].lower()
            if next_ch == 'x':
                self._advance()
                self._advance()
                while self.pos < len(self.source) and (self.source[self.pos].isdigit() or self.source[self.pos].lower() in 'abcdef'):
                    self._advance()
                lexeme = self.source[start_pos:self.pos]
                self._add_token(TokenType.NUMBER, lexeme, self.line, start_col, int(lexeme, 16))
                return
            elif next_ch == 'b':
                self._advance()
                self._advance()
                while self.pos < len(self.source) and self.source[self.pos] in '01':
                    self._advance()
                lexeme = self.source[start_pos:self.pos]
                self._add_token(TokenType.NUMBER, lexeme, self.line, start_col, int(lexeme, 2))
                return
            elif next_ch == 'o':
                self._advance()
                self._advance()
                while self.pos < len(self.source) and self.source[self.pos] in '01234567':
                    self._advance()
                lexeme = self.source[start_pos:self.pos]
                self._add_token(TokenType.NUMBER, lexeme, self.line, start_col, int(lexeme, 8))
                return

        while self.pos < len(self.source) and self.source[self.pos].isdigit():
            self._advance()
            
        if self._peek() == '.' and self._peek(1) and self._peek(1).isdigit():
            self._advance()
            while self.pos < len(self.source) and self.source[self.pos].isdigit():
                self._advance()
                
        if self._peek() in ('e', 'E'):
            next_1 = self._peek(1)
            next_2 = self._peek(2)
            is_valid_exp = (next_1 and next_1.isdigit()) or (next_1 in ('+', '-') and next_2 and next_2.isdigit())
            if is_valid_exp:
                self._advance()
                if self._peek() in ('+', '-'):
                    self._advance()
                while self.pos < len(self.source) and self.source[self.pos].isdigit():
                    self._advance()
                    
        lexeme = self.source[start_pos:self.pos]
        value = float(lexeme) if ('.' in lexeme or 'e' in lexeme or 'E' in lexeme) else int(lexeme)
        self._add_token(TokenType.NUMBER, lexeme, self.line, start_col, value)

    def _read_string(self, quote_char):
        start_col = self.col
        start_pos = self.pos
        self._advance()
        chars = []
        escaped = False

        while self.pos < len(self.source):
            ch = self.source[self.pos]
            if escaped:
                # В карту экранирования добавлены и одинарные, и двойные кавычки
                escape_map = {'n': '\n', 't': '\t', 'r': '\r', '"': '"', "'": "'", '\\': '\\'}
                chars.append(escape_map.get(ch, '\\' + ch))
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
            self._error("string literal")

        raw_lexeme = self.source[start_pos:self.pos]
        self._add_token(TokenType.STRING, raw_lexeme, self.line, start_col, ''.join(chars))

    def _read_multiline_string(self, quote_char):
        start_line = self.line
        start_col = self.col
        start_pos = self.pos
        
        # Пропускаем три открывающие кавычки
        self._advance(); self._advance(); self._advance()
        content_start = self.pos
        while self.pos < len(self.source):
            # Ищем три закрывающие кавычки нужного типа
            if self.source[self.pos] == quote_char and self._peek(1) == quote_char and self._peek(2) == quote_char:
                content_end = self.pos
                self._advance(); self._advance(); self._advance()
                break
            self._advance()
        else:
            self._error("multiline string")

        content = self.source[content_start:content_end]
        self._add_token(TokenType.MULTILINE_STRING, self.source[start_pos:self.pos], start_line, start_col, value=content)

    def _read_fstring(self, quote_char):
        start_line = self.line
        start_col = self.col
        start_pos = self.pos
        self._advance() 

        content_start = self.pos
        depth = 0
        escaped = False

        while self.pos < len(self.source):
            ch = self.source[self.pos]
            if escaped:
                escaped = False
                self._advance()
                continue
            if ch == '\\':
                escaped = True
                self._advance()
                continue
            if ch == '\n':
                self._error("unterminated f-string literal")
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
            # Закрываем строку только той кавычкой, которой открыли, и только вне интерполяции {}
            if ch == quote_char and depth == 0:
                content_end = self.pos
                self._advance()
                break
            self._advance()
        else:
            self._error("f-string")

        self._add_token(TokenType.FSTRING, self.source[start_pos:self.pos], start_line, start_col, value=self.source[content_start:content_end])

    def _read_multiline_fstring(self, quote_char):
        start_line = self.line
        start_col = self.col
        start_pos = self.pos
        
        # Пропускаем три открывающие кавычки (символ 'f' уже был пропущен в tokenize)
        self._advance(); self._advance(); self._advance()
        content_start = self.pos
        depth = 0
        escaped = False

        while self.pos < len(self.source):
            ch = self.source[self.pos]
            if escaped:
                escaped = False
                self._advance()
                continue
            if ch == '\\':
                escaped = True
                self._advance()
                continue
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
            # Закрываем строку только если встретили три кавычки нужного типа ВНЕ интерполяции {}
            if ch == quote_char and self._peek(1) == quote_char and self._peek(2) == quote_char and depth == 0:
                content_end = self.pos
                self._advance(); self._advance(); self._advance()
                break
            self._advance()
        else:
            self._error("multiline f-string")

        self._add_token(TokenType.FSTRING_MULTILINE, self.source[start_pos:self.pos], start_line, start_col, value=self.source[content_start:content_end])

    def _read_c_code(self):
        self._skip_whitespace()
        self.pos += 5
        self.col += 5
        self._skip_whitespace()
        line = self.line
        start_col = self.col
        if self.pos >= len(self.source) or self.source[self.pos] != '{':
            self._add_unknown_token()
            return
        self._advance()
        brace_depth = 1
        content_start = self.pos
        
        while self.pos < len(self.source) and brace_depth > 0:
            ch = self.source[self.pos]
            if ch == '/' and self._peek(1) == '/':
                self._advance(); self._advance()
                while self.pos < len(self.source) and self.source[self.pos] != '\n': self._advance()
                continue
            if ch == '/' and self._peek(1) == '*':
                self._advance(); self._advance()
                while self.pos < len(self.source):
                    if self.source[self.pos] == '*' and self._peek(1) == '/':
                        self._advance(); self._advance()
                        break
                    self._advance()
                continue
            if ch == '"' or ch == "'":
                q = ch
                self._advance()
                while self.pos < len(self.source) and self.source[self.pos] != q:
                    if self.source[self.pos] == '\\': self._advance()
                    self._advance()
                self._advance()
            elif ch == '{':
                brace_depth += 1
                self._advance()
            elif ch == '}':
                brace_depth -= 1
                self._advance()
                if brace_depth == 0: break
            else:
                self._advance()
                
        if brace_depth != 0:
            self._add_unknown_token()
            return
        code = self.source[content_start:self.pos-1]
        self._add_token(TokenType.CCODE, code, line, start_col, value=code)

    def _read_cpp_code(self):
        self._skip_whitespace()
        self.pos += 7
        self.col += 7
        self._skip_whitespace()
        line = self.line
        start_col = self.col
        if self.pos >= len(self.source) or self.source[self.pos] != '{':
            self._add_unknown_token()
            return
        self._advance()
        brace_depth = 1
        content_start = self.pos
        while self.pos < len(self.source) and brace_depth > 0:
            ch = self.source[self.pos]
            if ch == '"' or ch == "'":
                q = ch
                self._advance()
                while self.pos < len(self.source) and self.source[self.pos] != q:
                    if self.source[self.pos] == '\\': self._advance()
                    self._advance()
                self._advance()
            elif ch == '{':
                brace_depth += 1
                self._advance()
            elif ch == '}':
                brace_depth -= 1
                self._advance()
                if brace_depth == 0: break
            else:
                self._advance()
        if brace_depth != 0:
            self._add_unknown_token()
            return
        code = self.source[content_start:self.pos-1]
        self._add_token(TokenType.CPPCODE, code, line, start_col, value=code)

    def _try_read_two_char_operator(self) -> bool:
        if self.pos + 1 >= len(self.source):
            return False
        two_chars = self.source[self.pos:self.pos+2]
        if two_chars in self.two_char_ops:
            start_col = self.col
            self._advance(); self._advance()
            self._add_token(TokenType(two_chars), two_chars, self.line, start_col)
            return True
        return False

    def _try_read_one_char_operator_or_delimiter(self) -> bool:
        """
        Пытается прочитать односимвольный оператор или разделитель.
        Текущая версия теперь корректно инкрементирует позицию и генерирует токен.
        """
        ch = self.source[self.pos]
        start_col = self.col
        
        # Специальный случай для амперсанда (ссылка / взятие адреса)
        if ch == '&' and self._peek(1) != '&':
            self._advance()
            self._add_token(TokenType.ADDRESS, ch, self.line, start_col)
            return True
            
        try:
            # Пытаемся автоматически смапить символ через значение TokenType Enum
            token_type = TokenType(ch)
            self._advance() # Фикс: сдвигаем позицию парсинга вперед
            self._add_token(token_type, ch, self.line, start_col) # Фикс: добавляем токен в чарт лексера
            return True
        except ValueError:
            return False

    def _add_unknown_token(self):
        start_col = self.col
        ch = self.source[self.pos]
        self._advance()
        self._add_token(TokenType.UNKNOWN, ch, self.line, start_col)