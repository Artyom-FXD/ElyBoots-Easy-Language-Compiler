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


# builder.py (фрагмент)

class ProjectBuilder:
    def __init__(self, config_path: Path, compiler_path: Optional[str] = None,
                young_mb: Optional[int] = None, old_mb: Optional[int] = None,
                target: Optional[str] = None):
        self.config_path = Path(config_path).resolve()
        self.project_root = self.config_path.parent
        self.target = target
        with open(self.config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)

        # Загружаем настройки (compiler и gc)
        self._load_compiler_config(compiler_path, young_mb, old_mb)

        self.build_dir = self.project_root / 'build'
        self.libs_dir = self.project_root / 'libs'
        self.output_dir = self.project_root / 'output'
        self.compiler_runtime = Path(__file__).parent.parent / 'runtime'

    def _load_compiler_config(self, compiler_path: Optional[str] = None,
                              young_mb: Optional[int] = None,
                              old_mb: Optional[int] = None):
        """
        Приоритет: аргументы > глобальный ely.json > пользовательский ~/.ely/ely.json
        """
        self.compiler_path = compiler_path
        self.optimization = 'hard'
        self.debug = False
        self.gc_young_mb = 16
        self.gc_old_mb = 8

        def extract_compiler_path(data: dict) -> Optional[str]:
            if 'compiler_path' in data:
                return data['compiler_path']
            if 'compiler' in data and isinstance(data['compiler'], dict):
                return data['compiler'].get('path')
            return None

        base_dir = Path(__file__).parent.parent
        global_config = base_dir / 'ely.json'

        if global_config.exists():
            try:
                with open(global_config, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if not self.compiler_path:
                    path = extract_compiler_path(data)
                    if path:
                        self.compiler_path = path
                self.optimization = data.get('optimization', self.optimization)
                self.debug = data.get('debug', self.debug)
                if 'gc' in data:
                    self.gc_young_mb = data['gc'].get('young_size_mb', self.gc_young_mb)
                    self.gc_old_mb = data['gc'].get('old_initial_size_mb', self.gc_old_mb)
            except Exception as e:
                print(f"Warning: failed to read {global_config}: {e}")

        user_config = Path.home() / '.ely' / 'ely.json'
        if user_config.exists():
            try:
                with open(user_config, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if not self.compiler_path:
                    path = extract_compiler_path(data)
                    if path:
                        self.compiler_path = path
                if 'optimization' in data and self.optimization == 'hard':
                    self.optimization = data['optimization']
                if 'debug' in data and not self.debug:
                    self.debug = data['debug']
                if 'gc' in data:
                    if self.gc_young_mb == 16:
                        self.gc_young_mb = data['gc'].get('young_size_mb', self.gc_young_mb)
                    if self.gc_old_mb == 8:
                        self.gc_old_mb = data['gc'].get('old_initial_size_mb', self.gc_old_mb)
            except Exception as e:
                print(f"Warning: failed to read {user_config}: {e}")

        # Аргументы командной строки имеют высший приоритет
        if young_mb is not None:
            self.gc_young_mb = young_mb
        if old_mb is not None:
            self.gc_old_mb = old_mb

    def _prepare_runtime(self) -> bool:
        self.build_runtime = self.build_dir / 'runtime'
        if self.compiler_runtime.exists():
            if self.build_runtime.exists():
                shutil.rmtree(self.build_runtime)
            shutil.copytree(self.compiler_runtime, self.build_runtime)
            return True
        else:
            print("Error: runtime directory not found in compiler folder.")
            return False

    def _find_compiler(self):
        # 0. Если указана целевая тройка, ищем кросс-компилятор
        if self.target:
            # Пробуем префиксный gcc: <triple>-gcc
            prefixed = f"{self.target}-gcc"
            path = shutil.which(prefixed)
            if path:
                print(f"Found cross-compiler for {self.target}: {path}")
                return prefixed, path
            # Пробуем clang с явным -target
            clang = shutil.which("clang")
            if clang:
                print(f"Using clang with -target {self.target}")
                return 'clang', clang
            print(f"Warning: cross-compiler for {self.target} not found. Falling back to default.")

        # 1. Явно указанный путь (из аргумента или конфига)
        if self.compiler_path:
            path = Path(self.compiler_path)
            if path.exists() and path.is_file():
                print(f"Using specified compiler: {path}")
                return path.stem, str(path)
            else:
                print(f"Warning: specified compiler '{self.compiler_path}' not found, falling back to search.")

        # 2. Установленный через ebt install-compiler в tools/gcc
        tools_gcc = self.project_root / 'tools' / 'gcc' / 'bin' / ('gcc.exe' if sys.platform == 'win32' else 'gcc')
        if tools_gcc.exists():
            print(f"Found GCC in tools: {tools_gcc}")
            return 'gcc', str(tools_gcc)

        # 3. Поиск в системном PATH
        for comp in ['gcc', 'clang']:
            path = shutil.which(comp)
            if path:
                print(f"Found {comp} in PATH: {path}")
                return comp, path

        # 4. Запасной вариант – TCC
        tcc = shutil.which('tcc')
        if tcc:
            print(f"Found TCC in PATH: {tcc}")
            return 'tcc', tcc

        # 5. Поиск TCC в папке tools проекта
        base_dir = Path(__file__).parent.resolve()
        tcc_path = base_dir / 'tools' / 'tcc' / 'tcc.exe'
        if tcc_path.exists():
            print(f"Found TCC at {tcc_path}")
            return 'tcc', str(tcc_path)

        return None, None

    def _type_to_c(self, ely_type: str) -> str:
        mapping = {
            'void': 'void', 'int': 'int', 'uint': 'unsigned int',
            'more': 'long long', 'umore': 'unsigned long long',
            'flt': 'float', 'double': 'double', 'bool': 'int',
            'str': 'char*', 'any': 'void*', 'char': 'char',
            'byte': 'signed char', 'ubyte': 'unsigned char'
        }
        if ely_type.startswith('arr<'):
            return 'arr*'                     # было 'ely_array*'
        if ely_type.startswith('dict<'):
            return 'dict*'                    # было 'ely_dict*'
        return mapping.get(ely_type, 'int')

    def _compile_module(self, module_name: str, module_path: Path) -> bool:
        sources = []
        if module_path.is_file():
            sources.append(module_path)
        elif module_path.is_dir():
            sources.extend(module_path.glob('*.ely'))
        else:
            print(f"Module path {module_path} is neither file nor directory")
            return False

        if not sources:
            print(f"No .e files found in {module_path}")
            return False

        all_statements = []
        public_functions = []
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

        codegen = CCodeGen(debug=self.debug, is_module=True)
        c_code = codegen.generate(program)
        c_file = self.build_dir / f'module_{module_name}.c'
        c_file.parent.mkdir(parents=True, exist_ok=True)
        c_file.write_text(c_code, encoding='utf-8')

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

        compiler, comp_path = self._find_compiler()
        if not compiler:
            print("No C compiler found for building module.")
            return False

        if sys.platform == 'win32':
            lib_name = f'{module_name}.dll'
        else:
            lib_name = f'{module_name}.so'
        lib_file = self.libs_dir / lib_name
        lib_file.parent.mkdir(parents=True, exist_ok=True)

        cmd = [comp_path, '-shared', '-o', str(lib_file), str(c_file)]
        if compiler == 'tcc' and sys.platform == 'win32':
            cmd.append('-Wl,--export-all-symbols')
        if self.optimization == 'hard':
            cmd.append('-O2')
        elif self.optimization == 'soft':
            cmd.append('-O1')
        if self.debug:
            cmd.append('-g')
        if compiler == 'clang' and self.target:
            cmd.extend(['-target', self.target])
        elif compiler == 'gcc' and self.target:
            pass
        cmd.append(f'-I{self.build_runtime}')
        cmd.append(f'-I{self.build_dir}')
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
        except subprocess.TimeoutExpired:
            print(f"Compilation of module {module_name} timed out")
            return False

    def _collect_sources(self) -> List[Path]:
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
        if not self._prepare_runtime():
            return False

        modules = self.config.get('modules', {})
        for mod_name, mod_path_str in modules.items():
            mod_path = self.project_root / mod_path_str
            if not mod_path.exists():
                print(f"Module path {mod_path} not found")
                return False
            if not self._compile_module(mod_name, mod_path):
                return False

        sources = self._collect_sources()
        if not sources:
            print("No source files found.")
            return False

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

        codegen = CCodeGen(debug=self.debug)
        c_code = codegen.generate(program)
        c_file = self.build_dir / 'output.c'
        c_file.parent.mkdir(parents=True, exist_ok=True)
        c_file.write_text(c_code, encoding='utf-8')

        compiler, comp_path = self._find_compiler()
        if not compiler:
            print("No C compiler found.")
            return False

        main_obj = self.build_dir / 'output.o'
        cmd = [comp_path, '-c', str(c_file), '-o', str(main_obj)]
        if self.optimization == 'hard':
            cmd.append('-O2')
        elif self.optimization == 'soft':
            cmd.append('-O1')
        if self.debug:
            cmd.append('-g')
        if compiler == 'clang' and self.target:
            cmd.extend(['-target', self.target])
        elif compiler == 'gcc' and self.target:
            pass
        cmd.append(f'-I{self.build_runtime}')
        cmd.append(f'-I{self.build_dir}')
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=60)
        except subprocess.CalledProcessError as e:
            print(f"Compilation of main project failed: {e.stderr}")
            return False
        except subprocess.TimeoutExpired:
            print(f"Compilation of main project timed out")
            return False
        
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
                subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=60)
            except subprocess.CalledProcessError as e:
                print(f"Compilation of runtime failed: {e.stderr}")
                return False
            except subprocess.TimeoutExpired:
                print(f"Compilation of runtime timed out")
                return False
        gc_c = self.build_runtime / 'ely_gc.c'
        gc_obj = None
        if gc_c.exists():
            gc_obj = self.build_dir / 'gc.o'
            cmd = [comp_path, '-c', str(gc_c), '-o', str(gc_obj)]
            if self.optimization == 'hard':
                cmd.append('-O2')
            elif self.optimization == 'soft':
                cmd.append('-O1')
            if self.debug:
                cmd.append('-g')
            # Передаём размеры поколений через макросы
            cmd.append(f'-DGC_YOUNG_SIZE_MB={self.gc_young_mb}')
            cmd.append(f'-DGC_OLD_INITIAL_SIZE_MB={self.gc_old_mb}')
            cmd.append(f'-I{self.build_runtime}')
            try:
                subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=60)
                print(f"Compiled {gc_c} with young={self.gc_young_mb}MB, old={self.gc_old_mb}MB")
            except subprocess.CalledProcessError as e:
                print(f"Compilation of ely_gc failed: {e.stderr}")
                return False
            except subprocess.TimeoutExpired:
                print(f"Compilation of ely_gc timed out")
                return False
        else:
            print(f"Warning: {gc_c} not found")
        collections_c = self.build_runtime / 'collections.c'
        collections_obj = None
        if collections_c.exists():
            collections_obj = self.build_dir / 'collections.o'
            cmd = [comp_path, '-c', str(collections_c), '-o', str(collections_obj)]
            if self.optimization == 'hard':
                cmd.append('-O2')
            elif self.optimization == 'soft':
                cmd.append('-O1')
            if self.debug:
                cmd.append('-g')
            cmd.append(f'-I{self.build_runtime}')
            try:
                subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=60)
            except subprocess.CalledProcessError as e:
                print(f"Compilation of collections failed: {e.stderr}")
                return False
            except subprocess.TimeoutExpired:
                print(f"Compilation of collections timed out")
                return False

        output_exe_name = self.config.get('output', {}).get('enter', {}).get('name', 'a.out')
        output_exe = self.output_dir / output_exe_name
        self.output_dir.mkdir(parents=True, exist_ok=True)

        cmd = [comp_path, '-o', str(output_exe), str(main_obj)]
        if runtime_obj:
            cmd.append(str(runtime_obj))
        if collections_obj:
            cmd.append(str(collections_obj))
        if gc_obj:
            cmd.append(str(gc_obj))

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

        libraries = self.config.get('libraries', [])
        for lib in libraries:
            cmd.append(f'-l{lib}')

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
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=60)
            print(f"✓ Executable created: {output_exe}")
        except subprocess.CalledProcessError as e:
            print(f"Linking failed: {e.stderr}")
            return False
        except subprocess.TimeoutExpired:
            print(f"Linking timed out")
            return False

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