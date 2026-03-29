# builder.py
import json
import subprocess
import shutil
import sys
from pathlib import Path
from typing import List, Dict, Optional

# Импорты модулей компилятора
sys.path.insert(0, str(Path(__file__).parent.parent))
from lexer_module import Lexer
from parser import *
from codegen.c_backend import CCodeGen


class ProjectBuilder:
    def __init__(self, config_path: Path):
        self.config_path = Path(config_path).resolve()
        self.project_root = self.config_path.parent
        with open(self.config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        self.optimization = 'hard'
        self.debug = False
        self.target = None
        self.output_name = None

        # Директории
        self.build_dir = self.project_root / 'build'      # временные файлы (c, o, h)
        self.libs_dir = self.project_root / 'libs'        # скомпилированные модули (dll/so)
        self.output_dir = self.project_root / 'output'    # конечный исполняемый файл

        # Путь к runtime в компиляторе (рядом с builder.py)
        self.compiler_runtime = Path(__file__).parent.parent / 'runtime'

    def _prepare_runtime(self) -> bool:
        """Копирует runtime из компилятора в build/runtime и возвращает путь."""
        self.build_runtime = self.build_dir / 'runtime'
        if self.compiler_runtime.exists():
            # Если папка уже существует, удалим её, чтобы скопировать заново
            if self.build_runtime.exists():
                shutil.rmtree(self.build_runtime)
            shutil.copytree(self.compiler_runtime, self.build_runtime)
            return True
        else:
            print("Error: runtime directory not found in compiler folder.")
            return False

    def _find_compiler(self):
        import __main__
        base_dir = Path(__file__).parent.resolve()
        # Возможные корневые папки: где лежит builder.py, его родитель, где лежит ebt.py
        candidates = [base_dir, base_dir.parent, base_dir.parent.parent]
        try:
            ebt_dir = Path(__main__.__file__).parent.resolve()
            candidates.append(ebt_dir)
        except:
            pass

        for cand in candidates:
            # Варианты путей к tcc.exe
            tcc_paths = [
                cand / 'tools' / 'tcc' / 'tcc.exe',
                cand / 'tools' / 'tcc.exe',
                cand / 'tcc' / 'tcc.exe',
            ]
            for tcc_path in tcc_paths:
                if tcc_path.exists():
                    print(f"Found TCC at {tcc_path}")
                    return 'tcc', str(tcc_path)

        # Поиск в PATH
        tcc = shutil.which('tcc')
        if tcc:
            print(f"Found TCC in PATH: {tcc}")
            return 'tcc', tcc

        # fallback на clang/gcc
        for comp in ['clang', 'gcc']:
            path = shutil.which(comp)
            if path:
                print(f"Using {comp} from {path}")
                return comp, path

        return None, None

    def _type_to_c(self, ely_type: str) -> str:
        """Преобразует тип ely в тип C."""
        mapping = {
            'void': 'void', 'int': 'int', 'uint': 'unsigned int',
            'more': 'long long', 'umore': 'unsigned long long',
            'flt': 'float', 'double': 'double', 'bool': 'int',
            'str': 'char*', 'any': 'void*', 'char': 'char',
            'byte': 'signed char', 'ubyte': 'unsigned char'
        }
        return mapping.get(ely_type, 'int')

    def _compile_module(self, module_name: str, module_path: Path) -> bool:
        """Собирает модуль в динамическую библиотеку (dll/so)."""
        # Собираем исходные .e файлы модуля
        sources = []
        if module_path.is_file():
            sources.append(module_path)
        elif module_path.is_dir():
            sources.extend(module_path.glob('*.e'))
        else:
            print(f"Module path {module_path} is neither file nor directory")
            return False

        if not sources:
            print(f"No .e files found in {module_path}")
            return False

        # Парсим и анализируем
        all_statements = []
        public_functions = []   # список MethodDeclaration
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
            for stmt in prog.statements:
                if isinstance(stmt, MethodDeclaration) and stmt.modifier == 'public':
                    public_functions.append(stmt)

        program = Program(all_statements)
        sem = SemanticAnalyzer()
        errors = sem.analyze(program)
        if errors:
            print(f"Semantic errors in module {module_name}: {errors}")
            return False

        # Генерация C-кода
        codegen = CCodeGen(debug=self.debug, is_module=True)
        c_code = codegen.generate(program)
        c_file = self.build_dir / f'module_{module_name}.c'
        c_file.parent.mkdir(parents=True, exist_ok=True)
        c_file.write_text(c_code, encoding='utf-8')

        # Генерация заголовочного файла (для using)
        header_file = self.build_dir / f'{module_name}.h'
        with open(header_file, 'w', encoding='utf-8') as hf:
            hf.write(f"// Auto-generated header for module {module_name}\n")
            hf.write(f"#ifndef ely_MODULE_{module_name.upper()}_H\n")
            hf.write(f"#define ely_MODULE_{module_name.upper()}_H\n\n")
            hf.write('#include "ely_runtime.h"\n\n')
            for func in public_functions:
                ret = func.return_type or 'void'
                params = ', '.join([f"{self._type_to_c(p.type)} {p.name}" for p in func.parameters])
                hf.write(f"extern {self._type_to_c(ret)} {func.name}({params});\n")
            hf.write("\n#endif\n")

            # Компиляция в динамическую библиотеку
        compiler, comp_path = self._find_compiler()
        if not compiler:
            print("No C compiler found for building module.")
            return False

        # Определяем имя библиотеки
        if sys.platform == 'win32':
            lib_name = f'{module_name}.dll'
        else:
            lib_name = f'{module_name}.so'
        lib_file = self.libs_dir / lib_name
        lib_file.parent.mkdir(parents=True, exist_ok=True)

        cmd = [comp_path, '-shared', '-o', str(lib_file), str(c_file)]
        # Для TCC добавляем экспорт всех символов
        if compiler == 'tcc' and sys.platform == 'win32':
            cmd.append('-Wl,--export-all-symbols')
        if self.optimization == 'hard':
            cmd.append('-O2')
        elif self.optimization == 'soft':
            cmd.append('-O1')
        if self.debug:
            cmd.append('-g')
        # Пути к include
        cmd.append(f'-I{self.build_runtime}')
        cmd.append(f'-I{self.build_dir}')
        # Системные библиотеки
        if sys.platform == 'win32':
            cmd.append('-lmsvcrt')
        else:
            cmd.append('-lm')

        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            print(f"Module {module_name} built as {lib_file}")
            print(f"Header generated: {header_file}")
            return True
        except subprocess.CalledProcessError as e:
            print(f"Compilation of module {module_name} failed: {e.stderr}")
            return False

    def _collect_sources(self) -> List[Path]:
        """Собирает только точку входа (enter)."""
        sources = []
        main_file = self.config.get('enter')
        if main_file:
            main_path = (self.project_root / main_file).resolve()
            if main_path.exists() and main_path.is_file():
                sources.append(main_path)
            else:
                print(f"Warning: main file {main_path} not found")
        return sources

    def build(self) -> bool:
        """Основная сборка проекта."""
        # 0. Подготовка runtime
        if not self._prepare_runtime():
            return False


        # 1. Собрать все модули
        modules = self.config.get('modules', {})
        for mod_name, mod_path_str in modules.items():
            mod_path = self.project_root / mod_path_str
            if not mod_path.exists():
                print(f"Module path {mod_path} not found")
                return False
            if not self._compile_module(mod_name, mod_path):
                return False

        # 2. Собрать основной проект
        sources = self._collect_sources()
        if not sources:
            print("No source files found.")
            return False

        # Парсим и анализируем все исходные файлы
        all_statements = []
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

        program = Program(all_statements)
        sem = SemanticAnalyzer()
        errors = sem.analyze(program)
        if errors:
            print("Semantic errors:")
            for err in errors:
                print(f"  {err}")
            return False
        print("✓ Semantic analysis successful")

        # Генерация C-кода основного проекта
        codegen = CCodeGen(debug=self.debug)
        c_code = codegen.generate(program)
        c_file = self.build_dir / 'output.c'
        c_file.parent.mkdir(parents=True, exist_ok=True)
        c_file.write_text(c_code, encoding='utf-8')

        # Находим компилятор
        compiler, comp_path = self._find_compiler()
        if not compiler:
            print("No C compiler found.")
            return False

        # Компилируем output.c в объектный файл
        main_obj = self.build_dir / 'output.o'
        cmd = [comp_path, '-c', str(c_file), '-o', str(main_obj)]
        if self.optimization == 'hard':
            cmd.append('-O2')
        elif self.optimization == 'soft':
            cmd.append('-O1')
        if self.debug:
            cmd.append('-g')
        cmd.append(f'-I{self.build_runtime}')
        cmd.append(f'-I{self.build_dir}')
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            print(f"Compilation of main project failed: {e.stderr}")
            return False

        # Компилируем runtime.c из скопированной папки
        runtime_c = self.build_runtime / 'ely_runtime.c'
        runtime_obj = None
        if runtime_c.exists():
            runtime_obj = self.build_dir / 'runtime.o'
            cmd = [comp_path, '-c', str(runtime_c), '-o', str(runtime_obj)]
            if self.optimization == 'hard':
                cmd.append('-O2')
            elif self.optimization == 'soft':
                cmd.append('-O1')
            if self.debug:
                cmd.append('-g')
            cmd.append(f'-I{self.build_runtime}')
            try:
                subprocess.run(cmd, check=True, capture_output=True, text=True)
            except subprocess.CalledProcessError as e:
                print(f"Compilation of runtime failed: {e.stderr}")
                return False

        # Линковка
        output_exe_name = self.config.get('output', {}).get('enter', {}).get('name', 'a.out')
        output_exe = self.output_dir / output_exe_name
        self.output_dir.mkdir(parents=True, exist_ok=True)

        cmd = [comp_path, '-o', str(output_exe), str(main_obj)]
        if runtime_obj:
            cmd.append(str(runtime_obj))

        # Добавляем библиотеки модулей (файлы .dll/.so) – они нужны для линковки
        for mod_name in modules.keys():
            if sys.platform == 'win32':
                lib_name = f'{mod_name}.dll'
            else:
                lib_name = f'{mod_name}.so'
            lib_file = self.libs_dir / lib_name
            if lib_file.exists():
                cmd.append(str(lib_file))
            else:
                print(f"Warning: module library {lib_file} not found, skipping")

        # Добавляем системные библиотеки из конфигурации
        libraries = self.config.get('libraries', [])
        for lib in libraries:
            cmd.append(f'-l{lib}')

        # Системные библиотеки
        if sys.platform == 'win32':
            cmd.append('-lmsvcrt')
        else:
            cmd.append('-lm')

        if self.optimization == 'hard':
            cmd.append('-O2')
        elif self.optimization == 'soft':
            cmd.append('-O1')
        if self.debug:
            cmd.append('-g')

        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            print(f"✓ Executable created: {output_exe}")
        except subprocess.CalledProcessError as e:
            print(f"Linking failed: {e.stderr}")
            return False

        # Копируем DLL/so модулей в output/ для удобства запуска
        for mod_name in modules.keys():
            if sys.platform == 'win32':
                src = self.libs_dir / f'{mod_name}.dll'
                dst = self.output_dir / f'{mod_name}.dll'
            else:
                src = self.libs_dir / f'{mod_name}.so'
                dst = self.output_dir / f'{mod_name}.so'
            if src.exists():
                shutil.copy(src, dst)
                print(f"Copied {src.name} to {dst}")

        self.output_name = str(output_exe)
        return True

    def build_module(self, module_name: str) -> bool:
        """Собрать только указанный модуль."""
        # Подготовка runtime
        if not self._prepare_runtime():
            return False

        modules = self.config.get('modules', {})
        if module_name not in modules:
            print(f"Module '{module_name}' not found in manager.json")
            return False
        mod_path = self.project_root / modules[module_name]
        if not mod_path.exists():
            print(f"Module path {mod_path} not found")
            return False
        return self._compile_module(module_name, mod_path)