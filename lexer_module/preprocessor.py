import re

class CompilerContext:
    def __init__(self):
        self.primitive_types = {"int", "uint", "more", "umore", "byte", "ubyte", "flt", "double", "str", "char", "bool", "void", "any"}
        self.inline_macros = {}
        self.debug_mode = False

    def register_primitive_type(self, name: str):
        self.primitive_types.add(name)

def patch_source(original_source: str, replacements: list[tuple[int, int, str]]) -> str:
    """
    replacements: список кортежей (start_pos, end_pos, new_text)
    Сортируем замены с конца в начало, чтобы индексы не плыли при модификации строки.
    """
    valid_replacements = [r for r in replacements if r[0] is not None and r[1] is not None and r[0] <= r[1]]
    valid_replacements.sort(key=lambda x: x[0], reverse=True)
    
    patched_source = original_source
    for start, end, new_text in valid_replacements:
        patched_source = patched_source[:start] + new_text + patched_source[end:]
        
    return patched_source

def correct_whitespaces(tokens: list, original_source: str) -> str:
    if not tokens:
        return ""
        
    result = []
    
    for i, t in enumerate(tokens):
        if i > 0:
            prev_t = tokens[i-1]
            prev_end = getattr(prev_t, 'end_pos', getattr(prev_t, 'end', None))
            curr_start = getattr(t, 'start_pos', getattr(t, 'start', None))
            
            if (prev_end is not None and curr_start is not None and 
                prev_end <= curr_start and curr_start <= len(original_source)):
                
                whitespace_bridge = original_source[prev_end:curr_start]
                if whitespace_bridge.count('\n') > 2:
                    # Сохраняем ровно 2 переноса и ТАБЫ/пробелы перед текущим токеном
                    last_indent = whitespace_bridge.split('\n')[-1]
                    result.append("\n\n" + last_indent)
                else:
                    result.append(whitespace_bridge)
            else:
                t_line = getattr(t, 'line', 1)
                prev_line = getattr(prev_t, 'line', 1)
                
                if t_line > prev_line:
                    result.append("\n" * min(2, t_line - prev_line)) 
                else:
                    lexeme = t.lexeme
                    prev_lexeme = prev_t.lexeme
                    
                    need_space = True
                    if lexeme in (',', ';', '.', ')', ']', '}', '>'):
                        need_space = False
                    elif prev_lexeme in ('.', '(', '[', '{', '<'):
                        need_space = False
                    elif lexeme == '(' and (prev_lexeme.isidentifier() or prev_lexeme in ('print', 'str', 'int', 'bool')):
                        need_space = False
                        
                    if need_space and result and not result[-1].endswith((" ", "\n", "\t")):
                        result.append(" ")

        # Обработка Си-блоков с сохранением всей оригинальной табуляции
        if t.type.name == 'CCODE':
            result.append(f"cCode {{ {t.lexeme} }}")
            continue
        elif t.type.name == 'CPPCODE':
            result.append(f"cppCode {{ {t.lexeme} }}")
            continue
            
        result.append(t.lexeme)
        
    return "".join(result)


class ElyPreprocessor:
    def __init__(self, context, lexer_class):
        self.ctx = context
        self.Lexer = lexer_class

    def _get_start_pos(self, t, source: str) -> int | None:
        for attr in ('start_pos', 'start', 'pos', 'position', 'offset', 'idx', 'index'):
            if hasattr(t, attr):
                val = getattr(t, attr)
                if isinstance(val, int) and val >= 0:
                    return val
        if hasattr(t, 'span') and isinstance(t.span, (tuple, list)):
            return t.span[0]

        line = getattr(t, 'line', None)
        col = getattr(t, 'col', getattr(t, 'column', getattr(t, 'char', None)))
        
        if line is not None and col is not None:
            lines = source.splitlines(keepends=True)
            pos = 0
            for l_idx in range(min(line - 1, len(lines))):
                pos += len(lines[l_idx])
            pos += max(0, col - 1)
            return pos

        return None

    def _get_end_pos(self, t, source: str) -> int | None:
        for attr in ('end_pos', 'end'):
            if hasattr(t, attr):
                val = getattr(t, attr)
                if isinstance(val, int) and val >= 0:
                    return val
        if hasattr(t, 'span') and isinstance(t.span, (tuple, list)):
            return t.span[1]

        start = self._get_start_pos(t, source)
        if start is not None:
            lexeme = getattr(t, 'lexeme', '')
            return start + len(lexeme)

        return None

    def process(self, source_code: str) -> tuple[str, object]:
        current_source = source_code
        iteration = 0
        
        if self.ctx.debug_mode:
            print("\n" + "="*60)
            print(" [PREPROCESSOR DEBUG] STARTING MACRO EXPANSION")
            print("="*60)
            print(f"Initial Source Code:\n{current_source.strip()}")
            print("-"*60)
        
        while True:
            iteration += 1
            lexer = self.Lexer(current_source)
            tokens = lexer.tokenize()
            
            if not self._has_macros(tokens):
                if self.ctx.debug_mode and iteration > 1:
                    print(f" -> No more macros detected at iteration {iteration}. Exiting.")
                    print("="*60 + "\n")
                return current_source, self.ctx

            replacements = []

            # 1. Пасс директив компилятора
            dir_replacements = self._process_compiler_directives(tokens, current_source)
            replacements.extend(dir_replacements)

            # 2. Пасс инлайн-макросов (@)
            inline_replacements = self._process_inline_macros(tokens, current_source)
            replacements.extend(inline_replacements)

            # 3. Пасс структурных инъекций (%)
            struct_replacements = self._process_structural_injections(tokens, current_source)
            replacements.extend(struct_replacements)

            if replacements:
                current_source = patch_source(current_source, replacements)
                has_changed = True
            else:
                has_changed = False

            if self.ctx.debug_mode:
                status = "CHANGED" if has_changed else "NO CHANGES"
                print(f" [Iteration {iteration}] Status: {status}")
                print(f"Generated Source:\n{current_source.strip()}")
                print("-"*60)

            if not has_changed:
                if self.ctx.debug_mode:
                    print(" -> Fixed-point reached. No changes in this iteration. Exiting.")
                    print("="*60 + "\n")
                return current_source, self.ctx
                
            if iteration > 100:
                raise RuntimeError(f"Превышена максимальная глубина вложенности макросов на итерации {iteration}.")

    def _has_macros(self, tokens) -> bool:
        return any(t.lexeme in ('#', '@', '%') or t.lexeme.startswith(('#', '@', '%')) for t in tokens)

    def _clean_string_literal(self, lexeme: str) -> str:
        if lexeme.startswith('"""') and lexeme.endswith('"""'): return lexeme[3:-3]
        if lexeme.startswith("'''") and lexeme.endswith("'''"): return lexeme[3:-3]
        if lexeme.startswith('"') and lexeme.endswith('"'): return lexeme[1:-1]
        if lexeme.startswith("'") and lexeme.endswith("'"): return lexeme[1:-1]
        return lexeme

    # =========================================================================
    # ПАССЫ МАКРОСОВ
    # =========================================================================

    def _process_compiler_directives(self, tokens: list, source: str) -> list[tuple[int, int, str]]:
        replacements = []
        i = 0
        while i < len(tokens):
            if tokens[i].lexeme == '#' or tokens[i].lexeme.startswith('#'):
                if tokens[i].lexeme == '#':
                    if i + 3 < len(tokens) and tokens[i+1].lexeme == 'typedef' and tokens[i+3].lexeme == ';':
                        self.ctx.register_primitive_type(tokens[i+2].lexeme)
                        start_pos = self._get_start_pos(tokens[i], source)
                        end_pos = self._get_end_pos(tokens[i+3], source)
                        if start_pos is not None and end_pos is not None:
                            replacements.append((start_pos, end_pos, ""))
                        i += 4
                        continue
                    elif i + 3 < len(tokens) and tokens[i+1].lexeme == 'debug' and tokens[i+3].lexeme == ';':
                        val = tokens[i+2].lexeme.lower()
                        self.ctx.debug_mode = val not in ('null', '0', 'void', 'false')
                        start_pos = self._get_start_pos(tokens[i], source)
                        end_pos = self._get_end_pos(tokens[i+3], source)
                        if start_pos is not None and end_pos is not None:
                            replacements.append((start_pos, end_pos, ""))
                        i += 4
                        continue
            i += 1
        return replacements

    def _process_inline_macros(self, tokens: list, source: str) -> list[tuple[int, int, str]]:
        replacements = []
        i = 0
        while i < len(tokens):
            lexeme = tokens[i].lexeme
            is_decl = False
            macro_name = ""
            consumed = 0
            
            if lexeme == '@' and i + 1 < len(tokens):
                is_decl = True
                macro_name = tokens[i+1].lexeme
                consumed = 2
            elif lexeme.startswith('@') and len(lexeme) > 1:
                is_decl = True
                macro_name = lexeme[1:]
                consumed = 1
                
            if is_decl:
                next_idx = i + consumed
                if next_idx < len(tokens) and tokens[next_idx].lexeme == '{':
                    depth = 1
                    body_tokens = []
                    j = next_idx + 1
                    while j < len(tokens) and depth > 0:
                        if tokens[j].lexeme == '{': depth += 1
                        elif tokens[j].lexeme == '}': depth -= 1
                        if depth > 0: body_tokens.append(tokens[j])
                        j += 1
                    end_idx = j
                    if j < len(tokens) and tokens[j].lexeme == ';': 
                        end_idx = j + 1
                    
                    # Убираем все переносы строк из тела @ макроса
                    raw_body = " ".join([t.lexeme for t in body_tokens])
                    clean_body = re.sub(r'\s+', ' ', raw_body).strip()
                    self.ctx.inline_macros[macro_name] = clean_body
                    
                    start_pos = self._get_start_pos(tokens[i], source)
                    end_pos = self._get_end_pos(tokens[end_idx-1], source)
                    if start_pos is not None and end_pos is not None:
                        replacements.append((start_pos, end_pos, ""))
                    i = end_idx
                    continue
                elif next_idx < len(tokens) and tokens[next_idx].lexeme != ';':
                    clean_val = re.sub(r'\s+', ' ', tokens[next_idx].lexeme).strip()
                    self.ctx.inline_macros[macro_name] = clean_val
                    start_pos = self._get_start_pos(tokens[i], source)
                    end_pos = self._get_end_pos(tokens[next_idx], source)
                    if start_pos is not None and end_pos is not None:
                        replacements.append((start_pos, end_pos, ""))
                    i = next_idx + 1
                    continue

            is_usage = False
            use_name = ""
            use_consumed = 0
            
            if lexeme == '@' and i + 1 < len(tokens) and tokens[i+1].lexeme in self.ctx.inline_macros:
                is_usage = True
                use_name = tokens[i+1].lexeme
                use_consumed = 2
            elif lexeme.startswith('@') and lexeme[1:] in self.ctx.inline_macros:
                is_usage = True
                use_name = lexeme[1:]
                use_consumed = 1
            elif lexeme in self.ctx.inline_macros:
                is_usage = True
                use_name = lexeme
                use_consumed = 1
                
            if is_usage:
                start_pos = self._get_start_pos(tokens[i], source)
                end_pos = self._get_end_pos(tokens[i + use_consumed - 1], source)
                # Подставляемый код гарантированно без \n
                inserted_code = re.sub(r'\s+', ' ', self.ctx.inline_macros[use_name]).strip()
                if start_pos is not None and end_pos is not None:
                    replacements.append((start_pos, end_pos, inserted_code))
                i += use_consumed
                continue
                
            i += 1
        return replacements

    def _process_structural_injections(self, tokens: list, current_source: str) -> list[tuple[int, int, str]]:
        replacements = []
        i = 0
        while i < len(tokens):
            lexeme = tokens[i].lexeme
            if lexeme == '%' or lexeme.startswith('%'):
                macro_start = i
                while i < len(tokens) and (tokens[i].lexeme == '%' or tokens[i].lexeme == ''):
                    i += 1
                if i >= len(tokens): break
                
                target_token = tokens[i].lexeme if tokens[macro_start].lexeme == '%' else tokens[macro_start].lexeme.lstrip('%')
                
                if target_token.startswith('['):
                    target_node = target_token.strip('[]')
                    i += 1
                else:
                    target_node = target_token
                    if tokens[macro_start].lexeme == '%': i += 1
                
                if i >= len(tokens): break
                
                args_str = ""
                if tokens[i].lexeme == '(':
                    i += 1
                    args_tokens = []
                    while i < len(tokens) and tokens[i].lexeme != ')':
                        args_tokens.append(tokens[i].lexeme)
                        i += 1
                    args_str = "".join(args_tokens)
                    i += 1
                    
                if i >= len(tokens): break
                macro_name = tokens[i].lexeme
                i += 1
                
                params_str = ""
                if i < len(tokens) and tokens[i].lexeme == '(':
                    i += 1
                    if i < len(tokens) and tokens[i].lexeme == '{':
                        i += 1
                        param_tokens = []
                        depth = 1
                        while i < len(tokens) and depth > 0:
                            if tokens[i].lexeme == '{': depth += 1
                            elif tokens[i].lexeme == '}': depth -= 1
                            if depth > 0: param_tokens.append(tokens[i].lexeme)
                            i += 1
                        params_str = "".join(param_tokens)
                    if i < len(tokens) and tokens[i].lexeme == ')': i += 1
                    
                while i < len(tokens) and tokens[i].lexeme != 'quotes':
                    i += 1
                    
                if i >= len(tokens) or tokens[i].lexeme != 'quotes': continue
                i += 1
                if i >= len(tokens) or tokens[i].lexeme != '(': continue
                i += 1
                
                # Очищаем шаблон от переносов строк еще до подстановки параметров
                raw_template = self._clean_string_literal(tokens[i].lexeme)
                flat_template = re.sub(r'\s+', ' ', raw_template).strip()
                
                i += 1
                if i >= len(tokens) or tokens[i].lexeme != ')': continue
                i += 1
                if i >= len(tokens) or tokens[i].lexeme != ';': continue
                i += 1
                macro_end = i
                
                code_to_inject = self._substitute_parameters(flat_template, args_str, params_str)
                brace_idx, mod_idx = self._find_injection_point_forward(tokens, macro_end, target_node, macro_name)
                
                if brace_idx is not None:
                    macro_start_pos = self._get_start_pos(tokens[macro_start], current_source)
                    macro_end_pos = self._get_end_pos(tokens[macro_end - 1], current_source)
                    if macro_start_pos is not None and macro_end_pos is not None:
                        replacements.append((macro_start_pos, macro_end_pos, ""))

                    if mod_idx is not None:
                        mod_start_pos = self._get_start_pos(tokens[mod_idx], current_source)
                        mod_end_pos = self._get_end_pos(tokens[mod_idx], current_source)
                        if mod_start_pos is not None and mod_end_pos is not None:
                            replacements.append((mod_start_pos, mod_end_pos, ""))

                    brace_pos = self._get_end_pos(tokens[brace_idx], current_source)
                    if brace_pos is not None:
                        inj_lexer = self.Lexer(code_to_inject)
                        inj_tokens = inj_lexer.tokenize()
                        if inj_tokens and inj_tokens[-1].type.name == 'EOF': inj_tokens.pop()
                        
                        # Сплющиваем весь вставляемый фрагмент строго в 1 строку
                        clean_injected_code = re.sub(r'\s+', ' ', correct_whitespaces(inj_tokens, code_to_inject)).strip()
                        formatted_injection = f" {clean_injected_code}"
                        
                        replacements.append((brace_pos, brace_pos, formatted_injection))
                    
                    return replacements
            i += 1
        return replacements

    def _substitute_parameters(self, template: str, args_str: str, params_str: str) -> str:
        context_dict = {}
        if params_str:
            pairs = re.findall(r'(\w+)\s*:\s*([^,}]+)', params_str)
            for k, v in pairs:
                context_dict[k.strip()] = v.strip()
        if args_str:
            context_dict['args'] = args_str.strip()
            for idx, arg in enumerate(args_str.split(',')):
                context_dict[f'arg{idx}'] = arg.strip()
                
        expanded_code = template
        for key, value in context_dict.items():
            expanded_code = expanded_code.replace(f"{{{{{key}}}}}", value)
        return expanded_code

    def _find_injection_point_forward(self, tokens: list, start_from: int, target_node: str, macro_name: str):
        j = start_from
        target_keyword = None
        if target_node in ("FuncDecl", "MethodDecl"): target_keyword = "func"
        elif target_node == "ClassDecl": target_keyword = "class"
        elif target_node == "StructDecl": target_keyword = "struct"
            
        keyword_found = False
        mod_idx = None
        
        while j < len(tokens):
            if tokens[j].lexeme == macro_name and not keyword_found:
                mod_idx = j
            if target_keyword and tokens[j].lexeme == target_keyword:
                keyword_found = True
            if tokens[j].lexeme == '{':
                if target_keyword and not keyword_found:
                    return None, None
                return j, mod_idx
            j += 1
        return None, None