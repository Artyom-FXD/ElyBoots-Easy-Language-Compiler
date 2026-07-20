from typing import List, Optional, Any, Tuple
import sys, os
import dataclasses

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from parser import *
from parser.earley_core import ParseNode

def dump_ast(node: Any, depth: int = 0) -> None:
    """
    Рекурсивный красивый вывод AST-дерева в консоль для отладки.
    """
    indent = "  " * depth
    
    if node is None:
        return

    if isinstance(node, list):
        for item in node:
            dump_ast(item, depth)
        return

    if dataclasses.is_dataclass(node):
        class_name = node.__class__.__name__
        line_col = f" (line {getattr(node, 'line', '?')}, col {getattr(node, 'col', '?')})" if hasattr(node, 'line') else ""
        print(f"{indent}├─ [{class_name}]{line_col}")
        
        for field in dataclasses.fields(node):
            # Пропускаем технические/служебные поля
            if field.name in ('line', 'col', 'cached_type', 'raw_type', 'ely_type'):
                continue
                
            val = getattr(node, field.name)
            if val is None or val == [] or val == False:
                continue

            if isinstance(val, list):
                print(f"{indent}  ├─ {field.name}:")
                for item in val:
                    dump_ast(item, depth + 2)
            elif dataclasses.is_dataclass(val):
                print(f"{indent}  ├─ {field.name}:")
                dump_ast(val, depth + 2)
            else:
                print(f"{indent}  ├─ {field.name} = {val!r}")
    else:
        print(f"{indent}{node!r}")


class ASTBuilder:
    def __init__(self, debug: bool = False):
        self.debug = debug

    def build(self, node: ParseNode) -> Optional[Any]:
        if node is None:
            return None

        method_name = f"visit_{node.name}"
        if hasattr(self, method_name):
            res = getattr(self, method_name)(node)
            return res

        if node.token:
            return node.token.lexeme

        children_results = [self.build(child) for child in node.children]
        children_results = [c for c in children_results if c is not None]

        if len(children_results) == 1:
            return children_results[0]
        return children_results

    # =========================================================================
    # ВПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # =========================================================================

    def _get_pos(self, node: ParseNode) -> Tuple[int, int]:
        """Возвращает (line, col) первого найденного токена в поддереве."""
        if node is None:
            return (1, 1)
        if node.token:
            return (node.token.line, node.token.col)
        for child in node.children:
            pos = self._get_pos(child)
            if pos != (1, 1):
                return pos
        return (1, 1)

    def _find_child(self, node: ParseNode, name: str) -> Optional[ParseNode]:
        for child in node.children:
            if child.name == name:
                return child
        return None

    def _find_children(self, node: ParseNode, name: str) -> List[ParseNode]:
        return [child for child in node.children if child.name == name]

    def _extract_type(self, type_node: ParseNode) -> str:
        if type_node is None:
            return "any"
        
        dt_node = self._find_child(type_node, "DataType")
        if not dt_node and type_node.name == "DataType":
            dt_node = type_node
            
        if not dt_node:
            # Простая свертка текста
            tokens = []
            def collect(n):
                if n.token: tokens.append(n.token.lexeme)
                for c in n.children: collect(c)
            collect(type_node)
            return "".join(tokens) if tokens else "any"

        # Собираем строку типа (например, dict<str, any> или arr<int>)
        tokens = []
        def collect_dt(n):
            if n.token: tokens.append(n.token.lexeme)
            for c in n.children: collect_dt(c)
        collect_dt(dt_node)
        return "".join(tokens)

    # =========================================================================
    # ВЕРХНЕУРОВНЕВЫЕ СУЩНОСТИ (Root, Decls)
    # =========================================================================

    def visit_Root(self, node: ParseNode) -> Program:
        top_decls = self._find_child(node, "TopLevelDecls")
        statements = self._collect_top_level_decls(top_decls) if top_decls else []
        return Program(statements=statements)

    def _collect_top_level_decls(self, node: ParseNode) -> List[Statement]:
        stmts = []
        curr = node
        while curr and curr.children:
            decl_child = self._find_child(curr, "TopLevelDecl")
            if decl_child and decl_child.children:
                stmt = self.build(decl_child.children[0])
                if isinstance(stmt, Statement):
                    stmts.append(stmt)
            curr = self._find_child(curr, "TopLevelDecls")
        return stmts

    def visit_UsingDecl(self, node: ParseNode) -> UsingDirective:
        line, col = self._get_pos(node)
        path_node = self._find_child(node, "Path")
        module_path = "".join([t.token.lexeme for t in path_node.children if t.token]) if path_node else ""
        return UsingDirective(line=line, col=col, module=module_path)

    def visit_NamespaceDecl(self, node: ParseNode) -> NamespaceDeclaration:
        line, col = self._get_pos(node)
        path_node = self._find_child(node, "Path")
        ns_name = "".join([t.token.lexeme for t in path_node.children if t.token]) if path_node else ""
        
        top_decls = self._find_child(node, "TopLevelDecls")
        body = self._collect_top_level_decls(top_decls) if top_decls else []
        return NamespaceDeclaration(line=line, col=col, name=ns_name, body=body)

    def _find_identifier(self, node: ParseNode) -> Optional[str]:
        if node is None:
            return None
        if node.token and node.token.type.name == 'IDENTIFIER':
            return node.token.lexeme
        for child in node.children:
            found = self._find_identifier(child)
            if found:
                return found
        return None

    def visit_TypeAliasDecl(self, node: ParseNode) -> TypeAlias:
        line, col = self._get_pos(node)
        ident_name = self._find_identifier(node) or "unknown"
        dt_node = self._find_child(node, "DataType")
        target_type = self._extract_type(dt_node)
        return TypeAlias(line=line, col=col, name=ident_name, target_type=target_type)

    def visit_ExternDecl(self, node: ParseNode) -> ExternFunction:
        line, col = self._get_pos(node)
        type_node = self._find_child(node, "Type")
        ret_type = self._extract_type(type_node)
        
        ident_name = self._find_identifier(node) or "unknown"

        params_node = self._find_child(node, "Params")
        params = self._process_params(params_node)
        
        return ExternFunction(line=line, col=col, name=ident_name, parameters=params, return_type=ret_type)

    # =========================================================================
    # ФУНКЦИИ И ПАРАМЕТРЫ
    # =========================================================================

    def visit_FuncDecl(self, node: ParseNode) -> MethodDeclaration:
        line, col = self._get_pos(node)
        
        prefixes_node = self._find_child(node, "Prefixes")
        modifiers = self._extract_prefixes(prefixes_node)
        
        type_node = self._find_child(node, "Type")
        ret_type = self._extract_type(type_node)
        
        ident_name = self._find_identifier(node) or "unknown"
        
        generic_node = self._find_child(node, "GenericParamsOpt")
        type_params = self._extract_generic_params(generic_node)
        
        params_node = self._find_child(node, "Params")
        params = self._process_params(params_node)
        
        block_node = self._find_child(node, "Block")
        body = self.visit_Block(block_node) if block_node else []
        
        return MethodDeclaration(
            line=line, col=col,
            name=ident_name,
            return_type=ret_type,
            parameters=params,
            body=body,
            modifier=" ".join(modifiers) if modifiers else None,
            type_params=type_params,
            is_async="async" in modifiers,
            is_abstract="abstract" in modifiers,
            is_override="override" in modifiers
        )

    def _process_params(self, node: ParseNode) -> List[Parameter]:
        params = []
        if not node:
            return params
            
        curr = node
        while curr and curr.children:
            param_child = self._find_child(curr, "Param")
            if param_child:
                dt_node = self._find_child(param_child, "DataType")
                p_type = self._extract_type(dt_node)
                p_ident = [c for c in param_child.children if c.token and c.token.type.name == 'IDENTIFIER'][0]
                params.append(Parameter(type=p_type, name=p_ident.token.lexeme))
            curr = self._find_child(curr, "Params")
        return params

    def _extract_prefixes(self, node: ParseNode) -> List[str]:
        prefixes = []
        if not node:
            return prefixes
        curr = node
        while curr and curr.children:
            prefix = self._find_child(curr, "Prefix")
            if prefix:
                for c in prefix.children:
                    if c.token: prefixes.append(c.token.lexeme)
                    elif c.children: prefixes.append(c.children[0].token.lexeme)
            curr = self._find_child(curr, "Prefixes")
        return prefixes

    def _extract_generic_params(self, node: ParseNode) -> List[str]:
        if not node or not node.children:
            return []
        tpl_node = self._find_child(node, "TemplateParams")
        if not tpl_node:
            return []
        
        params = []
        curr = tpl_node
        while curr and curr.children:
            idents = [c for c in curr.children if c.token and c.token.type.name == 'IDENTIFIER']
            if idents:
                params.append(idents[0].token.lexeme)
            curr = self._find_child(curr, "TemplateParams")
        return params

    # =========================================================================
    # ООП СТРУКТУРЫ (Классы, Структуры, Интерфейсы, Impl)
    # =========================================================================

    def visit_ClassDecl(self, node: ParseNode) -> ClassDeclaration:
        line, col = self._get_pos(node)
        
        modifiers_node = self._find_child(node, "ClassModifiers")
        modifiers = self._extract_class_modifiers(modifiers_node)
        
        ident_name = self._find_identifier(node) or "unknown"
        
        base_node = self._find_child(node, "BaseClassOpt")
        extends = base_node.children[0].token.lexeme if (base_node and base_node.children) else None
        
        members_node = self._find_child(node, "ClassMembers")
        methods, fields, wait_fields, super_args = self._process_class_members(members_node)
        
        return ClassDeclaration(
            line=line, col=col,
            name=ident_name,
            extends=extends,
            methods=methods,
            fields=fields,
            wait_fields=wait_fields,
            super_args=super_args,
            is_sealed="sealed" in modifiers,
            is_abstract="abstract" in modifiers
        )

    def visit_StructDecl(self, node: ParseNode) -> StructDeclaration:
        line, col = self._get_pos(node)
        ident_name = self._find_identifier(node) or "unknown"
        
        generic_node = self._find_child(node, "GenericParamsOpt")
        type_params = self._extract_generic_params(generic_node)
        
        members_node = self._find_child(node, "ClassMembers")
        _, fields, wait_fields, _ = self._process_class_members(members_node)
        
        return StructDeclaration(
            line=line, col=col,
            name=ident_name,
            fields=fields + wait_fields,
            type_params=type_params
        )

    def visit_InterfaceDecl(self, node: ParseNode) -> InterfaceDeclaration:
        line, col = self._get_pos(node)
        ident_name = self._find_identifier(node) or "unknown"
        members_node = self._find_child(node, "ClassMembers")
        methods, _, _, _ = self._process_class_members(members_node)
        return InterfaceDeclaration(line=line, col=col, name=ident_name, methods=methods)

    def visit_ImplDecl(self, node: ParseNode) -> ImplDeclaration:
        line, col = self._get_pos(node)
        idents = [c for c in node.children if c.token and c.token.type.name == 'IDENTIFIER']
        
        class_name = idents[0].token.lexeme
        interface_name = idents[1].token.lexeme if len(idents) > 1 else ""
        
        members_node = self._find_child(node, "ClassMembers")
        methods, _, _, _ = self._process_class_members(members_node)
        
        return ImplDeclaration(
            line=line, col=col,
            class_name=class_name,
            interface_name=interface_name,
            methods=methods
        )

    def _extract_class_modifiers(self, node: ParseNode) -> List[str]:
        mods = []
        if not node: return mods
        curr = node
        while curr and curr.children:
            mod = self._find_child(curr, "ClassModifier")
            if mod and mod.children:
                mods.append(mod.children[0].token.lexeme)
            curr = self._find_child(curr, "ClassModifiers")
        return mods

    def _process_class_members(self, node: ParseNode):
        methods = []
        fields = []
        wait_fields = []
        super_args = []
        
        if not node:
            return methods, fields, wait_fields, super_args
            
        curr = node
        while curr and curr.children:
            member = self._find_child(curr, "ClassMember")
            if member and member.children:
                child = member.children[0]
                if child.name == "FieldDecl":
                    vdecl = self.visit_FieldDecl(child)
                    if vdecl.is_unwait or "wait" in (vdecl.modifier or ""):
                        wait_fields.append(vdecl)
                    else:
                        fields.append(vdecl)
                elif child.name == "MethodDecl":
                    methods.append(self.visit_MethodDecl(child))
                elif child.name == "SuperCall":
                    super_args = self._process_super_call(child)
            curr = self._find_child(curr, "ClassMembers")
            
        return methods, fields, wait_fields, super_args

    def visit_FieldDecl(self, node: ParseNode) -> VariableDeclaration:
        line, col = self._get_pos(node)
        mod_opt = self._find_child(node, "FieldModifierOpt")
        modifier = mod_opt.children[0].token.lexeme if (mod_opt and mod_opt.children) else None
        
        dt_node = self._find_child(node, "DataType")
        dt_type = self._extract_type(dt_node)
        
        ident_name = self._find_identifier(node) or "unknown"
        
        init_opt = self._find_child(node, "InitOpt")
        initializer = self.build(init_opt.children[1]) if (init_opt and len(init_opt.children) > 1) else None
        
        return VariableDeclaration(
            line=line, col=col,
            modifier=modifier,
            type=dt_type,
            name=ident_name,
            initializer=initializer,
            is_unwait=(modifier == "unwait")
        )

    def visit_MethodDecl(self, node: ParseNode) -> MethodDeclaration:
        line, col = self._get_pos(node)
        prefixes_node = self._find_child(node, "Prefixes")
        modifiers = self._extract_prefixes(prefixes_node)
        
        type_node = self._find_child(node, "Type")
        ret_type = self._extract_type(type_node)
        
        ident_name = self._find_identifier(node) or "unknown"
        
        params_node = self._find_child(node, "Params")
        params = self._process_params(params_node)
        
        body_node = self._find_child(node, "MethodBody")
        body = []
        if body_node and body_node.children:
            if body_node.children[0].name == "Block":
                body = self.visit_Block(body_node.children[0])
                
        return MethodDeclaration(
            line=line, col=col,
            name=ident_name,
            return_type=ret_type,
            parameters=params,
            body=body,
            modifier=" ".join(modifiers) if modifiers else None,
            is_async="async" in modifiers,
            is_abstract="abstract" in modifiers or not body,
            is_override="override" in modifiers
        )

    def _process_super_call(self, node: ParseNode) -> List[Expression]:
        args_node = self._find_child(node, "Args")
        return self._process_args(args_node) if args_node else []

    # =========================================================================
    # БЛОКИ И ИНСТРУКЦИИ (Statements & Control Flow)
    # =========================================================================

    def visit_Block(self, node: ParseNode) -> List[Statement]:
        stmts_node = self._find_child(node, "Statements")
        return self._process_statements(stmts_node) if stmts_node else []

    def _process_statements(self, node: ParseNode) -> List[Statement]:
        stmts = []
        curr = node
        while curr and curr.children:
            stmt_child = self._find_child(curr, "Statement")
            if stmt_child and stmt_child.children:
                res = self.build(stmt_child.children[0])
                if isinstance(res, Statement):
                    stmts.append(res)
                elif isinstance(res, Expression):
                    stmts.append(ExpressionStatement(line=res.line, col=res.col, expression=res))
            curr = self._find_child(curr, "Statements")
        return stmts

    def visit_VarDecl(self, node: ParseNode) -> VariableDeclaration:
        line, col = self._get_pos(node)
        const_opt = self._find_child(node, "ConstOpt")
        modifier = "const" if (const_opt and const_opt.children) else None
        
        dt_node = self._find_child(node, "DataType")
        dt_type = self._extract_type(dt_node)
        
        ident_name = self._find_identifier(node) or "unknown"
        
        init_opt = self._find_child(node, "InitOpt")
        initializer = None
        if init_opt and len(init_opt.children) > 1:
            initializer = self.build(init_opt.children[1])
            
        return VariableDeclaration(
            line=line, col=col,
            modifier=modifier,
            type=dt_type,
            name=ident_name,
            initializer=initializer
        )

    def visit_IfStmt(self, node: ParseNode) -> IfStatement:
        line, col = self._get_pos(node)
        expr_node = self._find_child(node, "Expr")
        cond = self.build(expr_node)
        
        blocks = self._find_children(node, "Block")
        then_body = self.visit_Block(blocks[0]) if blocks else []
        
        else_opt = self._find_child(node, "ElseOpt")
        else_body = None
        if else_opt and else_opt.children:
            if else_opt.children[1].name == "Block":
                else_body = self.visit_Block(else_opt.children[1])
            elif else_opt.children[1].name == "IfStmt":
                else_body = [self.visit_IfStmt(else_opt.children[1])]

        return IfStatement(line=line, col=col, condition=cond, then_body=then_body, else_body=else_body)

    def visit_WhileStmt(self, node: ParseNode) -> WhileLoop:
        line, col = self._get_pos(node)
        cond = self.build(self._find_child(node, "Expr"))
        body = self.visit_Block(self._find_child(node, "Block"))
        return WhileLoop(line=line, col=col, condition=cond, body=body)

    def visit_ForStmt(self, node: ParseNode) -> ForLoop:
        line, col = self._get_pos(node)
        
        vdecl_node = self._find_child(node, "VarDecl")
        vdecl = self.visit_VarDecl(vdecl_node) if vdecl_node else None
        
        expr_node = self._find_child(node, "Expr")
        cond = self.build(expr_node) if expr_node else None
        
        assign_node = self._find_child(node, "Assignment")
        update = self.build(assign_node) if assign_node else None
        
        block_node = self._find_child(node, "Block")
        body = self.visit_Block(block_node) if block_node else []
        
        return ForLoop(line=line, col=col, init=vdecl, condition=cond, update=update, body=body)

    def visit_ForeachStmt(self, node: ParseNode) -> ForEachLoop:
        line, col = self._get_pos(node)
        ident_name = self._find_identifier(node) or "unknown"
        item_var = VariableDeclaration(line=line, col=col, modifier=None, type="any", name=ident_name, initializer=None)
        iterable = self.build(self._find_child(node, "Expr"))
        body = self.visit_Block(self._find_child(node, "Block"))
        return ForEachLoop(line=line, col=col, item_decl=item_var, iterable=iterable, body=body)

    def visit_ReturnStmt(self, node: ParseNode) -> ReturnStatement:
        line, col = self._get_pos(node)
        opt_expr = self._find_child(node, "ExprOpt")
        val = self.build(opt_expr.children[0]) if (opt_expr and opt_expr.children) else None
        return ReturnStatement(line=line, col=col, value=val)

    def visit_GivebackStmt(self, node: ParseNode) -> GivebackStatement:
        line, col = self._get_pos(node)
        opt_expr = self._find_child(node, "ExprOpt")
        val = self.build(opt_expr.children[0]) if (opt_expr and opt_expr.children) else None
        return GivebackStatement(line=line, col=col, value=val)

    def visit_CCODE(self, node: ParseNode) -> GlobalCBlock:
        line, col = self._get_pos(node)
        return GlobalCBlock(line=line, col=col, code=node.token.lexeme if node.token else "")

    def visit_CPPCODE(self, node: ParseNode) -> GlobalCBlock:
        line, col = self._get_pos(node)
        return GlobalCBlock(line=line, col=col, code=node.token.lexeme if node.token else "")

    # =========================================================================
    # ВЫРАЖЕНИЯ И КАСКАД ПРИОРИТЕТОВ (Expressions)
    # =========================================================================

    def _binary_cascade(self, node: ParseNode) -> Expression:
        if not node.children:
            return None
        if len(node.children) == 1:
            return self.build(node.children[0])

        line, col = self._get_pos(node)
        left = self.build(node.children[0])

        # Сворачиваем цепочки операндов и операторов: [left, op1, right1, op2, right2, ...]
        i = 1
        while i < len(node.children):
            op_node = node.children[i]
            # Извлекаем лексему оператора
            if op_node.token:
                op = op_node.token.lexeme
            else:
                op_res = self.build(op_node)
                op = op_res if isinstance(op_res, str) else op_node.name

            right = self.build(node.children[i + 1])
            left = BinaryOp(line=line, col=col, left=left, operator=op, right=right)
            i += 2

        return left

    visit_Expr = _binary_cascade
    visit_NullCoalescing = _binary_cascade
    visit_LogicOr = _binary_cascade
    visit_LogicAnd = _binary_cascade
    visit_Equality = _binary_cascade
    visit_Relational = _binary_cascade
    visit_Additive = _binary_cascade
    visit_Multiplicative = _binary_cascade

    def visit_Unary(self, node: ParseNode) -> Expression:
        if len(node.children) == 1:
            return self.build(node.children[0])
        line, col = self._get_pos(node)
        op_token = node.children[0].token.lexeme if node.children[0].token else node.children[0].name
        operand = self.build(node.children[1])
        if op_token.lower() == 'await':
            return AwaitExpression(line=line, col=col, expression=operand)
        return UnaryOp(line=line, col=col, operator=op_token, operand=operand)

    def visit_Assignment(self, node: ParseNode) -> Assignment:
        line, col = self._get_pos(node)
        lval = self.build(node.children[0])
        op_node = node.children[1]
        op = op_node.children[0].token.lexeme if op_node.children else "="
        rval = self.build(node.children[2])
        return Assignment(line=line, col=col, target=lval, value=rval, operator=op)

    def visit_Primary(self, node: ParseNode) -> Expression:
        line, col = self._get_pos(node)
        children = node.children

        # Литералы, идентификаторы
        if len(children) == 1:
            return self.build(children[0])

        # Выражения в скобках: ( expr )
        if len(children) == 3 and children[0].token and children[0].token.lexeme == '(' and children[2].token and children[2].token.lexeme == ')':
            return self.build(children[1])

        # Вызов функции: print(...) ИЛИ IDENTIFIER(...)
        if len(children) == 4 and children[0].token and children[1].token and children[1].token.lexeme == '(':
            callee = Identifier(line=line, col=col, name=children[0].token.lexeme)
            args = self._process_args(children[2])
            return Call(line=line, col=col, callee=callee, arguments=args)

        # Вызов new Class(...)
        if len(children) >= 4 and children[0].token and children[0].token.lexeme == 'new':
            class_name = children[1].token.lexeme
            args_node = self._find_child(node, "Args")
            args = self._process_args(args_node) if args_node else []
            return Call(line=line, col=col, callee=Identifier(line=line, col=col, name=class_name), arguments=args)

        # Доступ к полям: primary.ident
        if len(children) == 3 and children[1].token and children[1].token.lexeme == '.':
            obj = self.build(children[0])
            member = children[2].token.lexeme if children[2].token else children[2].name
            return MemberAccess(line=line, col=col, object=obj, member=member)

        # Индексация: primary[expr]
        if len(children) == 4 and children[1].token and children[1].token.lexeme == '[':
            target = self.build(children[0])
            idx = self.build(children[2])
            return IndexExpression(line=line, col=col, target=target, index=idx)

        # Вызов метода: primary.method(...)
        if len(children) >= 5 and children[1].token and children[1].token.lexeme == '.':
            obj = self.build(children[0])
            method_name = children[2].token.lexeme
            args_node = self._find_child(node, "Args")
            args = self._process_args(args_node) if args_node else []
            callee = MemberAccess(line=line, col=col, object=obj, member=method_name)
            return Call(line=line, col=col, callee=callee, arguments=args)

        return self.build(children[0])

    def _process_args(self, node: ParseNode) -> List[Expression]:
        args = []
        if not node: return args
        curr = node
        while curr and curr.children:
            arg_node = self._find_child(curr, "Arg")
            if arg_node and arg_node.children:
                # Arg -> Expr ИЛИ Arg -> IDENTIFIER = Expr
                expr_child = arg_node.children[-1]
                args.append(self.build(expr_child))
            curr = self._find_child(curr, "Args")
        return args

    # =========================================================================
    # ЛИТЕРАЛЫ И КОЛЛЕКЦИИ
    # =========================================================================

# =========================================================================
    # ЛИТЕРАЛЫ И F-СТРОКИ
    # =========================================================================

    def visit_Literal(self, node: ParseNode) -> Expression:
        line, col = self._get_pos(node)
        token = node.children[0].token
        
        if token.type.name == 'NUMBER':
            val = float(token.lexeme) if '.' in token.lexeme else int(token.lexeme)
            return Literal(line=line, col=col, value=val)
        elif token.type.name == 'BOOLEAN':
            return Literal(line=line, col=col, value=(token.lexeme == 'true'))
        elif token.type.name in ('STRING', 'MULTILINE_STRING'):
            clean_str = token.lexeme.strip('"\'')
            return Literal(line=line, col=col, value=clean_str)
        elif token.type.name in ('FSTRING', 'FSTRING_MULTILINE'):
            # Разбираем f-строку на статический текст и выражение(я)
            parts = self._parse_fstring(token.lexeme, line, col)
            return FString(line=line, col=col, parts=parts)
            
        return Literal(line=line, col=col, value=token.lexeme)

    def _parse_fstring(self, lexeme: str, line: int, col: int) -> List[Expression]:
        s = lexeme
        
        # 1. Снимаем префикс f/F если есть
        if s.startswith(('f', 'F')):
            s = s[1:]
            
        # 2. Очищаем от внешних кавычек (включая тройные)
        if s.startswith('"""') and s.endswith('"""'):
            s = s[3:-3]
        elif s.startswith("'''") and s.endswith("'''"):
            s = s[3:-3]
        elif (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
            s = s[1:-1]

        parts = []
        buf = []
        i = 0
        n = len(s)

        while i < n:
            if s[i] == '{':
                # Экранирование {{
                if i + 1 < n and s[i + 1] == '{':
                    buf.append('{')
                    i += 2
                    continue
                
                # Сбрасываем накопленный текст как Literal
                if buf:
                    parts.append(Literal(line=line, col=col, value="".join(buf)))
                    buf = []
                
                # Вытаскиваем выражение внутри { ... } с учетом вложенных скобок
                i += 1
                start_expr = i
                brace_depth = 1
                while i < n and brace_depth > 0:
                    if s[i] == '{': brace_depth += 1
                    elif s[i] == '}': brace_depth -= 1
                    if brace_depth > 0: i += 1
                
                expr_str = s[start_expr:i]
                i += 1  # пропуск закрывающей '}'
                
                # Парсим выражение внутри { ... } в полноценный AST-узел!
                expr_ast = self._parse_fstring_expr(expr_str, line, col)
                parts.append(expr_ast)

            elif s[i] == '}':
                # Экранирование }}
                if i + 1 < n and s[i + 1] == '}':
                    buf.append('}')
                    i += 2
                else:
                    buf.append(s[i])
                    i += 1
            else:
                buf.append(s[i])
                i += 1

        if buf:
            parts.append(Literal(line=line, col=col, value="".join(buf)))

        return parts

    def _parse_fstring_expr(self, expr_str: str, line: int, col: int) -> Expression:
        expr_str = expr_str.strip()
        if not expr_str:
            return Literal(line=line, col=col, value="")

        try:
            from lexer_module import Lexer, TokenType
            from parser.rules import ely_grammar
            from parser.earley_core import ElyEarleyParser

            # Токенизируем внутренности {expr}
            sub_lexer = Lexer(expr_str)
            sub_tokens = sub_lexer.tokenize(debug=False)
            pure_tokens = [t for t in sub_tokens if t.type != TokenType.EOF]

            # Запускаем Earley с целевым правилом "Expr"
            sub_parser = ElyEarleyParser(ely_grammar, start_symbol="Expr")
            cst, err = sub_parser.parse(pure_tokens)

            if cst and not err:
                return self.build(cst)
            
            return Identifier(line=line, col=col, name=expr_str)
        except Exception:
            return Identifier(line=line, col=col, name=expr_str)

    def visit_ArrayLiteral(self, node: ParseNode) -> ArrayLiteral:
        line, col = self._get_pos(node)
        args_node = self._find_child(node, "Args")
        elements = self._process_args(args_node) if args_node else []
        return ArrayLiteral(line=line, col=col, elements=elements)

    def visit_DictLiteral(self, node: ParseNode) -> DictLiteral:
        line, col = self._get_pos(node)
        entries_node = self._find_child(node, "DictEntries")
        pairs = []
        
        if entries_node:
            curr = entries_node
            while curr and curr.children:
                entry = self._find_child(curr, "DictEntry")
                if entry and len(entry.children) >= 3:
                    k = self.build(entry.children[0])
                    v = self.build(entry.children[2])
                    pairs.append(DictPair(key=k, value=v))
                curr = self._find_child(curr, "DictEntries")
                
        return DictLiteral(line=line, col=col, pairs=pairs)

    def visit_IDENTIFIER(self, node: ParseNode) -> Identifier:
        line, col = self._get_pos(node)
        return Identifier(line=line, col=col, name=node.token.lexeme)

    # =========================================================================
    # ТЕРНАРНЫЙ ОПЕРАТОР И УСЛОВНЫЕ ВЫРАЖЕНИЯ
    # =========================================================================

    def visit_Conditional(self, node: ParseNode) -> Expression:
        return self._build_conditional(node)

    def visit_ConditionalExpr(self, node: ParseNode) -> Expression:
        return self._build_conditional(node)

    def visit_Ternary(self, node: ParseNode) -> Expression:
        return self._build_conditional(node)

    def visit_TernaryExpr(self, node: ParseNode) -> Expression:
        return self._build_conditional(node)

    def _build_conditional(self, node: ParseNode) -> Expression:
        if len(node.children) == 1:
            return self.build(node.children[0])

        line, col = self._get_pos(node)

        # Отфильтровываем токены-разделители '?' и ':'
        expr_children = [c for c in node.children if not (c.token and c.token.lexeme in ('?', ':'))]

        if len(expr_children) == 3:
            cond = self.build(expr_children[0])
            then_expr = self.build(expr_children[1])
            else_expr = self.build(expr_children[2])
            return Conditional(line=line, col=col, condition=cond, then_expr=then_expr, else_expr=else_expr)

        # Прямой фолбэк для 5 дочерних элементов [cond, '?', then, ':', else]
        if len(node.children) >= 5:
            cond = self.build(node.children[0])
            then_expr = self.build(node.children[2])
            else_expr = self.build(node.children[4])
            return Conditional(line=line, col=col, condition=cond, then_expr=then_expr, else_expr=else_expr)

        return self.build(node.children[0])