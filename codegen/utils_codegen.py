import sys, os
from typing import List, Optional, Any, Dict, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from parser import *


class ExprCode:
    """Expression code with explicit C++ type information.
    
    Replaces bare strings in codegen. Every expression now carries:
    - code: the C++ expression text
    - raw_type: the C++ type of this expression ('ely_value', 'char*', 'long long', etc.)
    - ely_type: the Ely type ('int', 'str', 'bool', 'File', etc.)
    
    Behaves like a string for backward compatibility (__str__ returns .code),
    but new code should use .raw_type for type decisions instead of startswith() heuristics.
    """
    __slots__ = ('code', 'raw_type', 'ely_type')
    
    def __init__(self, code: str, raw_type: str, ely_type: str):
        self.code = code
        self.raw_type = raw_type
        self.ely_type = ely_type
    
    def __str__(self) -> str:
        return self.code
    
    def __repr__(self) -> str:
        return f"EC({self.code!r}, r={self.raw_type!r}, e={self.ely_type!r})"
    
    def __len__(self) -> int:
        return len(self.code)
    
    def __bool__(self) -> bool:
        return bool(self.code)
    
    def __eq__(self, other) -> bool:
        if isinstance(other, ExprCode):
            return self.code == other.code
        return self.code == other
    
    def __hash__(self) -> int:
        return hash(self.code)
    
    @property
    def is_wrapped(self) -> bool:
        """True if the C++ expression is already ely_value"""
        return self.raw_type == 'ely_value'
    
    @property
    def is_native(self) -> bool:
        """True if the C++ expression is a native C++ type (not ely_value)"""
        return not self.is_wrapped and self.raw_type not in ('void',)


class CodeGenUtils:
    def __init__(self, debug=False, is_module=False):
        self.debug = debug
        self.is_module = is_module
        self.code: List[str] = []
        self.method_code: List[str] = []
        self.specializations: List[str] = []
        self.indent: int = 0
        self.var_types: Dict[str, str] = {}
        self.global_types: Dict[str, str] = {}
        self.scopes: List[Dict[str, str]] = []
        self.scope_roots: List[List[str]] = []
        self.temp_counter: int = 0
        self.type_aliases: Dict[str, str] = {}
        self.used_modules: List[str] = []
        self.global_vars_to_init: List[Tuple[str, str, Expression]] = []
        self.original_functions: Dict[str, MethodDeclaration] = {}
        self.builtin_signatures: Dict[str, Tuple[str, str, List[str]]] = {}
        self.current_class_name: Optional[str] = None
        self.current_namespace: Optional[str] = None
        self.classes_ast: Dict[str, ClassDeclaration] = {}
        self.structs: set = set()
        self.namespaces: Dict[str, Dict[str, str]] = {}
        self.imported_namespaces: Dict[str, str] = {}
        # RAII-корни: True для C++ (GC_AUTO_ROOT), False для C (ручные gc_add_root/gc_remove_root)
        self.use_raii_roots: bool = False
        # Счётчик открытых блоков после collapse (для переиспользования имён с другим типом)
        self.collapse_depth: int = 0

    # --- scopes ---
    def push_scope(self):
        """new scope"""
        self.scopes.append(self.var_types)
        self.var_types = {}
        self.scope_roots.append([])

    def pop_scope(self):
        """closes scope"""
        if self.scopes:
            self.var_types = self.scopes.pop()
        if self.scope_roots:
            for name in reversed(self.scope_roots.pop()):
                if name not in ('None', 'NULL'):
                    if not self.use_raii_roots:
                        # Так как ely_value теперь uint64_t, адрес &name кастуется к void**
                        self.emit_to_method(f"gc_remove_root((void**)&{name});")

    def ensure_identifier(self, name: str, line=0, col=0):
        if name in self.var_types: return
        for s in reversed(self.scopes):
            if name in s: return
        if name in self.global_types: return
        if '_' in name and not name.startswith('__'):
            parts = name.split('_', 1)
            if parts[0] in self.classes_ast:
                return
        # Изменено: теперь ely_value вместо ely_value
        self.emit_to_method(f"ely_value {name} = ely_value_new_null();")
        if self.use_raii_roots:
            self.emit_to_method(f"GC_AUTO_ROOT({name});")
        else:
            self.emit_to_method(f"gc_add_root((void**)&{name});")
        self.var_types[name] = 'any'
        if self.scope_roots:
            self.scope_roots[-1].append(name)

    # --- types ---
    def get_expression_type(self, expr: Expression) -> str:
        if expr.cached_type is not None:
            return expr.cached_type
        if isinstance(expr, Literal):
            v = expr.value
            if isinstance(v, bool): return 'bool'
            if isinstance(v, int): return 'int'
            if isinstance(v, float): return 'flt'
            if isinstance(v, str): return 'str'
            return 'any'
        if isinstance(expr, Identifier):
            name = expr.name
            if name == 'self' and self.current_class_name:
                return self.current_class_name
            if name in self.classes_ast:
                return name
            if name in self.interfaces_ast:
                return name
            if name in self.imported_namespaces:
                return self.imported_namespaces[name]
            if name in self.var_types:
                return self.resolve_type_alias(self.var_types[name])
            if name in self.global_types:
                return self.resolve_type_alias(self.global_types[name])
            for s in reversed(self.scopes):
                if name in s:
                    return self.resolve_type_alias(s[name])
            return 'any'
        if isinstance(expr, BinaryOp):
            return self.get_expression_type(expr.left)
        if isinstance(expr, UnaryOp):
            return self.get_expression_type(expr.operand)
        if isinstance(expr, ArrayLiteral): return 'arr<any>'
        if isinstance(expr, DictLiteral): return 'dict<any, any>'
        if isinstance(expr, IndexExpression): return 'any'
        if isinstance(expr, MemberAccess):
            obj_type = self.get_expression_type(expr.object)
            if obj_type in self.classes_ast:
                cls = self.classes_ast[obj_type]
                def find_field(c):
                    for f in c.fields:
                        if f.name == expr.member: return f.type
                    if c.extends and c.extends in self.classes_ast:
                        return find_field(self.classes_ast[c.extends])
                    return None
                ft = find_field(cls)
                if ft: return self.resolve_type_alias(ft)
            if obj_type in self.interfaces_ast:
                return 'any'
            return 'any'
        if isinstance(expr, Call):
            if isinstance(expr.callee, Identifier):
                if expr.callee.name.endswith('_constructor'):
                    cn = expr.callee.name[:-len('_constructor')]
                    if cn in self.classes_ast: return cn
                if expr.callee.name in self.original_functions:
                    ret = self.original_functions[expr.callee.name].return_type
                    if ret: return self.resolve_type_alias(ret)
                if expr.callee.name in self.extern_functions:
                    ret = self.extern_functions[expr.callee.name].return_type
                    if ret in ('char*', 'const char*'):
                        return 'str'
                    return ret if ret else 'any'
                if expr.callee.name in self.builtin_signatures:
                    return self.builtin_signatures[expr.callee.name][1]
            return 'any'
        return 'any'

    def type_to_cpp(self, ely_type: str, for_signature=False, is_param=False,
                    is_self=False, is_field=False) -> str:
        ely_type = self.resolve_type_alias(ely_type)
        # Изменено: методы теперь возвращают чистый ely_value вместо ely_value
        if ely_type in self.classes_ast:
            if for_signature and not is_param:
                return 'ely_value'
            return f"{ely_type}*"
        mapping = {
            'void':'void','bool':'int','byte':'signed char','ubyte':'unsigned char',
            'int':'int','uint':'unsigned int','more':'long long','umore':'unsigned long long',
            'flt':'float','double':'double','str':'char*','any':'ely_value','char':'char',
        }
        if ely_type.startswith('arr<') or ely_type.startswith('dict<'):
            return 'ely_value'
        if ely_type in mapping:
            if for_signature and not is_param and ely_type != 'void':
                return 'ely_value'
            return mapping[ely_type]
        if ely_type in self.structs:
            return f"struct {ely_type}"
        if ely_type.endswith('*'):
            inner = ely_type[:-1].strip()
            return self.type_to_cpp(inner, for_signature, is_param, is_self, is_field) + '*'
        return 'ely_value'

    def resolve_type_alias(self, t: str) -> str:
        while t in self.type_aliases:
            t = self.type_aliases[t]
        return t

    def is_numeric(self, t: str) -> bool:
        return t in ('int','uint','more','umore','flt','double','byte','ubyte')

    # -------------------------------------------------------------------
    # Единая конверсия типов: ExprCode ↔ native / ely_value
    # -------------------------------------------------------------------
    def _wrap_to_ely(self, expr: ExprCode) -> ExprCode:
        """Wrap native expression to flat ely_value (uint64_t)."""
        if expr.is_wrapped:
            return expr
        t = expr.ely_type
        if t in ('int','uint','more','umore','byte','ubyte','long long','unsigned int','unsigned long long','size_t'):
            return ExprCode(f"ely_value_new_int({expr.code})", "ely_value", t)
        if t in ('flt', 'double', 'float'):
            return ExprCode(f"ely_value_new_double({expr.code})", "ely_value", t)
        if t == 'bool':
            return ExprCode(f"ely_value_new_bool({expr.code})", "ely_value", t)
        if t == 'str':
            # Короткие строки оптимизируются прямо на этапе генерации или через макрос рантайма
            return ExprCode(f"ely_value_new_string({expr.code})", "ely_value", t)
        if t in self.classes_ast or t in getattr(self, 'interfaces_ast', {}):
            return ExprCode(f"ely_value_new_object((void*)({expr.code}))", "ely_value", t)
        return ExprCode(expr.code, "ely_value", t)

    def _unwrap_from_ely(self, expr: ExprCode, target_raw: str) -> ExprCode:
        """Unwrap flat ely_value expression to native C++ type."""
        if not expr.is_wrapped:
            return expr
        prefix_map = {
            'ely_value_new_string(' : 'char*',
            'ely_value_new_int('    : 'long long',
            'ely_value_new_double(' : 'double',
            'ely_value_new_bool('   : 'int',
        }
        for prefix, raw in prefix_map.items():
            if expr.code.startswith(prefix) and expr.code.endswith(')'):
                inner = expr.code[len(prefix):-1]
                if inner.count('(') == inner.count(')'):
                    stripped = ExprCode(inner, raw, expr.ely_type)
                    if raw == target_raw:
                        return stripped
        
        if target_raw == 'char*':
            return ExprCode(f"ely_value_to_string({expr.code})", 'char*', expr.ely_type)
        if target_raw in ('int', 'long long', 'unsigned int', 'unsigned long long',
                          'signed char', 'unsigned char', 'size_t'):
            if expr.code.startswith(('ely_time_now_ms', 'ely_time_now')):
                return ExprCode(expr.code, target_raw, expr.ely_type)
            return ExprCode(f"ely_value_as_int({expr.code})", target_raw, expr.ely_type)
        if target_raw in ('float', 'double'):
            return ExprCode(f"ely_value_as_double({expr.code})", target_raw, expr.ely_type)
        if target_raw == 'int' and expr.ely_type == 'bool':
            return ExprCode(f"ely_value_as_bool({expr.code})", 'int', expr.ely_type)
        if target_raw.endswith('*') and not target_raw.startswith('ely_'):
            return ExprCode(f"({target_raw})({expr.code})", target_raw, expr.ely_type)
        return expr

    def ensure_type(self, expr: ExprCode, target_raw: str) -> ExprCode:
        """Main entry point: ensure expression is in target_raw C++ type."""
        if expr.raw_type == target_raw:
            return expr
        if target_raw in ('ely_value', 'void*'):
            return self._wrap_to_ely(expr)
        if expr.is_wrapped:
            return self._unwrap_from_ely(expr, target_raw)
        return expr

    # --- emitters ---
    def emit(self, line: str):
        self.code.append("    " * self.indent + line)

    def emit_to_method(self, line: str):
        self.method_code.append("    " * self.indent + line)

    # --- names ---
    def method_full_name(self, name: str) -> str:
        ns = self.ns_prefix()
        if self.current_class_name:
            return f"{ns}{self.current_class_name}_{name}"
        return f"{ns}{name}"

    def ns_prefix(self) -> str:
        return self.current_namespace + "_" if self.current_namespace else ""

    # --- helpers ---
    def gen_expr_rooted(self, expr: Expression) -> str:
        code = self.gen_expression(expr)
        if isinstance(expr, Identifier):
            return code
        tmp = f"__tmp_{self.temp_counter}"
        self.temp_counter += 1
        # Изменено: теперь выделяется плоский ely_value
        self.emit_to_method(f"ely_value {tmp} = {code};")
        if self.use_raii_roots:
            self.emit_to_method(f"GC_AUTO_ROOT({tmp});")
        else:
            self.emit_to_method(f"gc_add_root((void**)&{tmp});")
        return tmp

    def error(self, msg: str, node: Optional[Expression] = None):
        if node:
            print(f"Code generation error: {msg} at line {node.line}, col {node.col}")
        else:
            print(f"Code generation error: {msg}")

    def set_builtins(self, builtins: Dict[str, Tuple[str, str, List[str]]]):
        self.builtin_signatures = builtins