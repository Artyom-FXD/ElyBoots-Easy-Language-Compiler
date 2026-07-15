import sys
import os
from typing import List, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from parser import *
from codegen.funcs_codegen import FuncCodeGen


class ClassCodeGen(FuncCodeGen):
    """Classes generation step"""

    def gen_class_full(self, cls: ClassDeclaration):
        name = cls.name
        parent = cls.extends
        parents = []
        if parent and parent in self.classes_ast:
            parents.append(f"public {parent}")
        for iface in cls.impl_interfaces:
            parents.append(f"public {iface}")
        parent_ref = " : " + ", ".join(parents) if parents else ""
        sealed_kw = " final" if cls.is_sealed else ""

        self.emit(f"class {name}{sealed_kw}{parent_ref} {{")
        self.emit("public:")
        self.indent += 1

        for f in cls.fields:
            if f.modifier != 'static':
                ctype = self.type_to_cpp(f.type, is_field=True)
                self.emit(f"{ctype} {f.name};")

        for sf in cls.static_fields:
            self.emit(f"static ely_value {sf.name};")

        old_emit = self.emit_to_method
        self.emit_to_method = self.emit

        self._gen_constructor_decl(cls)

        # Собираем имена getter/setter из свойств, чтобы не дублировать их
        prop_method_names = set()
        for prop in cls.properties:
            if prop.getter:
                prop_method_names.add(prop.getter.name)
            if prop.setter:
                prop_method_names.add(prop.setter.name)

        for method in cls.methods:
            if method.name == name or method.name == f"{name}_constructor":
                continue
            # Пропускаем getter/setter свойств — они будут сгенерированы ниже
            if method.name in prop_method_names:
                continue
            self._gen_method(cls, method)

        for prop in cls.properties:
            if prop.getter:
                self._gen_method(cls, prop.getter)
            if prop.setter:
                self._gen_method(cls, prop.setter)

        self.emit_to_method = old_emit
        self.indent -= 1
        self.emit("};")

    def _gen_constructor_decl(self, cls: ClassDeclaration):
        name = cls.name
        parent = cls.extends
        params = self.collect_constructor_params(cls)
        param_str = ', '.join([f"{self.type_to_cpp(p.type, is_param=True)} {p.name}" for p in params])

        self.emit(f"{name}({param_str})")

        init_list = []
        if parent and parent in self.classes_ast:
            parent_cls = self.classes_ast[parent]
            parent_params = self.collect_constructor_params(parent_cls)
            parent_param_names = [p.name for p in parent_params]
            if parent_param_names:
                init_list.append(f"{parent}({', '.join(parent_param_names)})")

        if init_list:
            self.emit(f"    : {', '.join(init_list)}")

        self.emit("    {")
        self.indent += 1
        self._gen_constructor_body(cls, params)
        self.indent -= 1
        self.emit("    }")

    def _gen_constructor_body(self, cls: ClassDeclaration, params: List[Parameter]):
        name = cls.name
        
        # Защищаем область видимости конструктора
        self.push_scope()

        # Регистрируем параметры и добавляем их в GC roots, если нужно
        for p in params:
            self.var_types[p.name] = p.type
            if self.type_to_cpp(p.type, is_param=True) == 'ely_value':
                self.emit(f"gc_add_root((void**)&{p.name});")
                if self.scope_roots:
                    self.scope_roots[-1].append(p.name)

        for f in cls.wait_fields:
            if f.type == 'str':
                self.emit(f"this->{f.name} = ely_str_dup({f.name});")
            else:
                self.emit(f"this->{f.name} = {f.name};")

        for f in cls.fields:
            if f.modifier == 'static' or f in cls.wait_fields or f.is_unwait:
                continue
            matched_param = next((p for p in params if p.name == f.name), None)
            if matched_param:
                ctype = self.type_to_cpp(f.type, is_field=True)
                if ctype == 'char*' and f.type == 'str':
                    self.emit(f"this->{f.name} = ely_str_dup({f.name});")
                else:
                    self.emit(f"this->{f.name} = {f.name};")
                continue
            default = self._default_value_for_type(f.type)
            if f.initializer:
                init_val = self.gen_expression(f.initializer)
                ctype = self.type_to_cpp(f.type, is_field=True)
                if ctype != 'ely_value':
                    init_val = self.ensure_type(init_val, ctype)
                    if f.type == 'str':
                        init_val = ExprCode(f"ely_str_dup({init_val.code})", 'char*', f.type)
                default = init_val.code if isinstance(init_val, ExprCode) else init_val
            self.emit(f"this->{f.name} = {default};")

        for f in cls.fields:
            if f.is_unwait and f.unwait_default:
                val_code = self.gen_expression(f.unwait_default)
                ctype = self.type_to_cpp(f.type, is_field=True)
                if ctype != 'ely_value':
                    val_code = self.ensure_type(val_code, ctype)
                    if f.type == 'str':
                        val_code = ExprCode(f"ely_str_dup({val_code.code})", 'char*', f.type)
                self.emit(f"this->{f.name} = {val_code};")

        user_ctor = None
        for m in cls.methods:
            if m.name == name or m.name == f"{name}_constructor":
                user_ctor = m
                break
        if user_ctor:
            old_func = self.current_function
            old_class = self.current_class_name
            self.current_function = f"{name}_constructor"
            self.current_class_name = name
            for stmt in user_ctor.body:
                self.gen_statement(stmt)
            self.current_class_name = old_class
            self.current_function = old_func

        self.pop_scope()

    def _gen_method(self, cls: ClassDeclaration, method: MethodDeclaration):
        is_static = method.modifier == 'static'
        is_virtual = not is_static and not method.name.endswith('_constructor')
        override = method.is_override

        virt = "virtual " if is_virtual or method.is_abstract else ""
        static_kw = "static " if is_static else ""
        override_kw = " override" if override else ""

        ret = self.type_to_cpp(method.return_type or 'void', for_signature=True)
        params = ', '.join([f"{self.type_to_cpp(p.type, for_signature=True, is_param=True)} {p.name}"
                            for p in method.parameters])

        if method.is_abstract:
            self.emit(f"{virt}{static_kw}{ret} {method.name}({params}){override_kw} = 0;")
            return

        self.emit(f"{virt}{static_kw}{ret} {method.name}({params}){override_kw} {{")
        self.indent += 1

        old_class = self.current_class_name
        self.current_class_name = cls.name

        old_func = self.current_function
        self.current_function = f"{cls.name}_{method.name}"
        old_func_ret = getattr(self, 'func_return_type', None)
        self.func_return_type = method.return_type or 'void'
        self.current_function_is_method = True
        
        self.push_scope()

        if not is_static:
            self.var_types['self'] = cls.name

        for p in method.parameters:
            self.var_types[p.name] = p.type
            ctype = self.type_to_cpp(p.type, is_param=True)
            if ctype == 'ely_value':
                self.emit(f"gc_add_root((void**)&{p.name});")
                if self.scope_roots:
                    self.scope_roots[-1].append(p.name)

        for stmt in method.body:
            self.gen_statement(stmt)

        for _ in range(self.collapse_depth):
            self.indent -= 1
            self.emit("}")
        self.collapse_depth = 0

        self.pop_scope()
        self.indent -= 1
        self.emit("}")
        self.current_function = old_func
        self.func_return_type = old_func_ret
        self.current_class_name = old_class

    # -------------------------------------------------------------------
    # Статические поля и методы (объявления вне класса)
    # -------------------------------------------------------------------
    def gen_static_field_definitions(self):
        for cls in self.classes_ast.values():
            for sf in cls.static_fields:
                self.emit(f"ely_value {cls.name}::{sf.name} = ely_value_new_int(0);")

    def gen_static_method_out_of_class(self, cls: ClassDeclaration, method: MethodDeclaration):
        """Статический метод, определённый вне класса."""
        full_name = f"{cls.name}::{method.name}"
        ret = self.type_to_cpp(method.return_type or 'void', for_signature=True)
        params = ', '.join([f"{self.type_to_cpp(p.type, for_signature=True, is_param=True)} {p.name}"
                            for p in method.parameters])
        self.emit(f"{ret} {full_name}({params}) {{")
        self.indent += 1
        
        old_func = self.current_function
        self.current_function = full_name
        old_func_ret = getattr(self, 'func_return_type', None)
        self.func_return_type = method.return_type or 'void'
        
        self.push_scope()
        
        for p in method.parameters:
            self.var_types[p.name] = p.type
            if self.type_to_cpp(p.type, is_param=True) == 'ely_value':
                self.emit(f"gc_add_root((void**)&{p.name});") # Исправлено с emit_to_method на emit
                if self.scope_roots:
                    self.scope_roots[-1].append(p.name)
                    
        for stmt in method.body:
            self.gen_statement(stmt)
            
        # Корректно закрываем collapse блоки для статических методов
        for _ in range(self.collapse_depth):
            self.indent -= 1
            self.emit("}")
        self.collapse_depth = 0
        
        self.pop_scope()
        self.indent -= 1
        self.emit("}")
        
        self.current_function = old_func
        self.func_return_type = old_func_ret

    # -------------------------------------------------------------------
    # Вспомогательные
    # -------------------------------------------------------------------
    def _default_value_for_type(self, ely_type: str) -> str:
        t = self.resolve_type_alias(ely_type)
        if t == 'str':
            return "nullptr"
        if t in ('int', 'uint', 'more', 'umore', 'byte', 'ubyte'):
            return "0"
        if t in ('flt', 'double'):
            return "0.0"
        if t == 'bool':
            return "false"
        return "nullptr"

    def gen_class_info(self, cls: ClassDeclaration):
        name = cls.name
        fields = [f.name for f in cls.fields if f.modifier != 'static']
        types = [f.type for f in cls.fields if f.modifier != 'static']
        self.emit(f"static const char* {name}_field_names[] = {{ {', '.join(f'"{f}"' for f in fields)} }};")
        self.emit(f"static const char* {name}_field_types[] = {{ {', '.join(f'"{t}"' for t in types)} }};")
        self.emit(f"static ely_class_info {name}_class_info = {{ \"{name}\", {len(fields)}, {name}_field_names, {name}_field_types }};")

    def collect_constructor_params(self, cls: ClassDeclaration) -> List[Parameter]:
        params = []
        hierarchy = []
        cur = cls
        while cur:
            hierarchy.insert(0, cur)
            cur = self.classes_ast.get(cur.extends) if cur.extends else None

        unwait_names = set()
        for c in hierarchy:
            for f in c.fields:
                if f.is_unwait:
                    unwait_names.add(f.name)

        for c in hierarchy:
            for f in c.wait_fields:
                if f.name not in unwait_names:
                    params.append(Parameter(type=f.type, name=f.name))

        param_names = {p.name for p in params}
        for c in hierarchy:
            for f in c.fields:
                if f.modifier == 'static':
                    continue
                if f in c.wait_fields:
                    continue
                if f.is_unwait:
                    continue
                if f.name in param_names:
                    continue
                params.append(Parameter(type=f.type, name=f.name))
                param_names.add(f.name)

        seen = set()
        unique = []
        for p in params:
            if p.name not in seen:
                seen.add(p.name)
                unique.append(p)
        return unique

    def gen_interface_full(self, iface: InterfaceDeclaration):
        name = iface.name
        self.emit(f"class {name} {{")
        self.emit("public:")
        self.indent += 1
        self.emit(f"virtual ~{name}() = default;")
        for method in iface.methods:
            ret = self.type_to_cpp(method.return_type or 'void', for_signature=True)
            params = ', '.join([f"{self.type_to_cpp(p.type, for_signature=True, is_param=True)} {p.name}"
                                for p in method.parameters])
            self.emit(f"virtual {ret} {method.name}({params}) = 0;")
        self.indent -= 1
        self.emit("};")