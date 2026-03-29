import os
import json
import subprocess
import sys
import shutil
from pathlib import Path
from lexer_module import Lexer
from parser import Parser
from parser import *
from codegen.c_backend import CCodeGen

class ModuleManager:
    def __init__(self, config_path):
        self.config_path = Path(config_path).resolve()
        self.project_root = self.config_path.parent
        with open(self.config_path, 'r') as f:
            self.config = json.load(f)

    def build_module(self, module_name):
        """Скомпилировать модуль в DLL и сгенерировать .h файл."""
        modules = self.config.get('modules', {})
        if module_name not in modules:
            print(f"Module '{module_name}' not found in manager.json")
            return False

        module_path = self.project_root / modules[module_name]
        if not module_path.exists():
            print(f"Module path {module_path} not found")
            return False

        # Собираем все исходники модуля
        sources = []
        if module_path.is_dir():
            sources.extend(module_path.glob('*.e'))
        else:
            sources.append(module_path)

        if not sources:
            print(f"No .e files found in {module_path}")
            return False

        # Парсим и анализируем модуль
        all_statements = []
        public_functions = []   # список (имя, возвращаемый тип, параметры)

        for src in sources:
            with open(src, 'r', encoding='utf-8') as f:
                source = f.read()
            lexer = Lexer(source)
            parser = Parser(lexer)
            prog = parser.parse()
            if parser.errors:
                print(f"Parse errors in {src}: {parser.errors}")
                return False
            all_statements.extend(prog.statements)

            # Извлекаем public функции
            for stmt in prog.statements:
                if isinstance(stmt, MethodDeclaration) and stmt.modifier == 'public':
                    params = [(p.type, p.name) for p in stmt.parameters]
                    public_functions.append((stmt.name, stmt.return_type or 'void', params))

        program = Program(all_statements)
        sem = SemanticAnalyzer()
        errors = sem.analyze(program)
        if errors:
            print(f"Semantic errors: {errors}")
            return False

        # Генерируем C-код
        codegen = CCodeGen()
        c_code = codegen.generate(program)

        # Сохраняем C-файл
        build_dir = self.project_root / 'build' / 'modules'
        build_dir.mkdir(parents=True, exist_ok=True)
        c_file = build_dir / f'{module_name}.c'
        with open(c_file, 'w', encoding='utf-8') as f:
            f.write(c_code)

        # Генерируем заголовочный файл .h
        h_file = build_dir / f'{module_name}.h'
        with open(h_file, 'w', encoding='utf-8') as f:
            f.write(f"// Auto-generated header for module {module_name}\n")
            f.write("#ifndef ely_MODULE_{0}_H\n".format(module_name.upper()))
            f.write("#define ely_MODULE_{0}_H\n\n".format(module_name.upper()))
            f.write('#include "ely_runtime.h"\n\n')
            for func in public_functions:
                ret = func[1]
                name = func[0]
                params = ', '.join([f"{self._c_type(p[0])} {p[1]}" for p in func[2]])
                f.write(f"extern {self._c_type(ret)} {name}({params});\n")
            f.write("\n#endif\n")

        # Компилируем DLL
        compiler = self._find_compiler()
        if not compiler:
            print("No suitable compiler found for building DLL")
            return False

        runtime_dir = self.project_root / 'runtime'
        if not runtime_dir.exists():
            print("Runtime directory not found")
            return False

        output = self.project_root / 'libs' / f'{module_name}.dll'
        output.parent.mkdir(exist_ok=True)

        cmd = [compiler, '-shared', '-o', str(output), str(c_file)]
        cmd.append(f'-I{runtime_dir}')
        cmd.append(f'-I{build_dir}')
        if sys.platform == 'win32':
            cmd.append('-lmsvcrt')
        else:
            cmd.append('-lm')
        cmd.append('-O2')

        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            print(f"Module {module_name} built as {output}")
            print(f"Header generated: {h_file}")
            return True
        except subprocess.CalledProcessError as e:
            print(f"Compilation failed: {e.stderr}")
            return False

    def _c_type(self, ely_type):
        mapping = {
            'void': 'void', 'int': 'int', 'uint': 'unsigned int',
            'more': 'long long', 'umore': 'unsigned long long',
            'flt': 'float', 'double': 'double', 'bool': 'int',
            'str': 'char*', 'any': 'void*', 'char': 'char',
            'byte': 'signed char', 'ubyte': 'unsigned char'
        }
        return mapping.get(ely_type, 'int')

    def _find_compiler(self):
        for comp in ['clang', 'gcc']:
            if shutil.which(comp):
                return comp
        return None