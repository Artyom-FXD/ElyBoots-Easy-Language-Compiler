import json
import hashlib
import os
import subprocess
import shutil
import sys
from pathlib import Path
from typing import List, Optional, Tuple

if getattr(sys, 'frozen', False):
    if hasattr(sys, '_MEIPASS'):
        _BASE_DIR = Path(sys._MEIPASS)
    else:
        _BASE_DIR = Path(sys.executable).parent
elif sys.argv[0] and sys.argv[0].lower().endswith('.exe'):
    _BASE_DIR = Path(os.path.abspath(sys.argv[0])).parent
else:
    _BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(_BASE_DIR))

# Новый парсер и грамматика
from parser import EarleyParser, SemanticAnalyzer, Program, ClassDeclaration, InterfaceDeclaration, MethodDeclaration, NamespaceDeclaration, UsingDirective
from parser.rules import ely_grammar
from codegen.codegen import CppCodeGen


class TC:
    """ANSI terminal color/style codes."""
    RED    = '\033[91m'
    GREEN  = '\033[92m'
    YELLOW = '\033[93m'
    BLUE   = '\033[94m'
    CYAN   = '\033[96m'
    WHITE  = '\033[97m'
    BOLD   = '\033[1m'
    DIM    = '\033[2m'
    RESET  = '\033[0m'

    @staticmethod
    def tag(label: str) -> str:
        t = label.upper()
        if t == 'INFO':
            return f"{TC.BLUE}{TC.BOLD}[{t}]{TC.RESET}"
        if t == 'OK':
            return f"{TC.GREEN}{TC.BOLD}[{t}]{TC.RESET}"
        if t == 'ERROR':
            return f"{TC.RED}{TC.BOLD}[{t}]{TC.RESET}"
        if t == 'WARN':
            return f"{TC.YELLOW}{TC.BOLD}[{t}]{TC.RESET}"
        if t == 'SKIP':
            return f"{TC.DIM}[{t}]{TC.RESET}"
        if t == 'BUILD':
            return f"{TC.CYAN}{TC.BOLD}[{t}]{TC.RESET}"
        return f"[{label}]"


class ProjectBuilder:
    """Orchestrates the end-to-end build pipeline for an Ely language project."""

    def __init__(self, config_path: Path, compiler_path=None,
                 young_mb=None, old_mb=None, target=None):
        self.config_path = config_path.resolve()
        self.project_root = self.config_path.parent
        self.target = target
        with open(self.config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        self.compiler_path = compiler_path
        self.gc_young_mb = young_mb if young_mb else 16
        self.gc_old_mb = old_mb if old_mb else 8
        self.optimization = 'hard'
        self.debug = False
        self.force_rebuild = False
        self.build_dir = self.project_root / 'build'
        self.output_dir = self.project_root / 'output'
        self.libs_dir = self.project_root / 'libs'
        self.compiler_runtime = _BASE_DIR / 'runtime'
        self.cache_path = self.build_dir / 'cache.json'
        self.mode = 'build'

        # Инициализация нового Earley-парсера
        self.parser = EarleyParser(ely_grammar)

    def _parse_ely_file(self, src_path: Path) -> Optional[List]:
        """Вынесенная функция: считывает и прогоняет один файл .ely через парсер,
        возвращая список его AST-инструкций (statements) или None при ошибке."""
        try:
            with open(src_path, 'r', encoding='utf-8') as f:
                source_text = f.read()
            ast, _ = self.parser.run(source_text)
            if ast and hasattr(ast, 'statements'):
                return ast.statements
            return []
        except (SyntaxError, RuntimeError) as e:
            print(f"\n{TC.tag('ERROR')} Parse error in file {src_path}:")
            print(f"{TC.RED}{e}{TC.RESET}")
            return None

    def _get_svlm_paths(self) -> Tuple[Optional[Path], Optional[Path]]:
        """Ищет SVLM.exe строго в двух указанных местах относительно корня компилятора."""
        path_spruce = _BASE_DIR / 'Spruce' / 'SVLM.exe'
        if path_spruce.is_file():
            ssdk = path_spruce.parent / 'SSDK'
            return path_spruce, (ssdk if ssdk.exists() else None)

        path_root = _BASE_DIR / 'SVLM.exe'
        if path_root.is_file():
            ssdk = path_root.parent / 'SSDK'
            return path_root, (ssdk if ssdk.exists() else None)

        if self.compiler_path:
            p = Path(self.compiler_path)
            if p.is_file() and p.name.lower() == 'svlm.exe':
                ssdk = p.parent / 'SSDK'
                return p, (ssdk if ssdk.exists() else None)

        return None, None

    def _ensure_gpp(self, gcc_path: Path):
        gxx = gcc_path.with_name('g++.exe') if sys.platform == 'win32' else gcc_path.with_name('g++')
        if not gxx.exists():
            try:
                shutil.copy2(gcc_path, gxx)
                print(f"  {TC.tag('OK')} Created {gxx.name} from {gcc_path.name}")
            except OSError as e:
                print(f"  {TC.tag('WARN')} Could not create {gxx.name}: {e}")
                return False
        return True

    def _find_compiler(self) -> Tuple[Optional[str], Optional[str], List[str]]:
        extra_flags = []
        if self.compiler_path:
            p = Path(self.compiler_path)
            if p.exists() and p.is_file() and p.name.lower() != 'svlm.exe':
                return p.stem, str(p), extra_flags
        for comp in ['g++', 'gcc', 'clang++', 'clang']:
            if shutil.which(comp):
                return comp, comp, extra_flags
        return None, None, extra_flags

    def _compile_runtime(self, compiler: str, comp_path: str,
                         src: Path, obj: Path, defines=None) -> bool:
        cmd = [comp_path, '-c', str(src), '-o', str(obj)]
        if compiler in ('g++', 'c++', 'clang++'):
            cmd.insert(1, '-x')
            cmd.insert(2, 'c')
        if self.optimization == 'hard':
            cmd.append('-O2')
        if defines:
            for d in defines:
                cmd.append(f'-D{d}')
        cmd.append(f'-I{self.build_dir}/runtime')
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            return True
        except subprocess.CalledProcessError as e:
            print(f"\n{TC.tag('ERROR')} Runtime compilation failed: {src.name}")
            self._show_compiler_error(e.stderr, str(src))
            return False

    def _file_hash(self, path: Path) -> str:
        try:
            h = hashlib.sha256()
            with open(path, 'rb') as f:
                for chunk in iter(lambda: f.read(65536), b''):
                    h.update(chunk)
            return h.hexdigest()
        except (OSError, IOError):
            return ''

    def _load_cache(self) -> dict:
        if not self.cache_path.exists():
            return {}
        try:
            with open(self.cache_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}

    def _save_cache(self, cache: dict):
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache, f, indent=2, sort_keys=True)

    def _sources_changed(self, sources: List[Path], cache: dict) -> bool:
        cached_hashes = cache.get('source_hashes', {})
        new_hashes = {}
        changed = False
        for src in sources:
            abs_path = str(src.resolve())
            h = self._file_hash(src)
            new_hashes[abs_path] = h
            cached_h = cached_hashes.get(abs_path)
            if cached_h != h:
                changed = True
        cache['source_hashes'] = new_hashes
        return changed

    def _runtime_o_files_uptodate(self, obj_files: List[Path]) -> bool:
        for obj in obj_files:
            if not obj.exists():
                return False
        return True

    def _print_project_info(self, sources: List[Path]):
        name = self.config.get('name', 'unknown')
        out_cfg = self.config.get('output', {}).get('enter', {})
        exe_name = out_cfg.get('name', 'a.out')
        exe_type = out_cfg.get('type', 'exe')
        entry = self.config.get('enter', '?')
        modules = self.config.get('modules', {})

        hdr = f"{TC.BOLD}{TC.WHITE}"
        dim = f"{TC.DIM}"
        rst = TC.RESET

        print(f"\n{hdr}  Project: {name}{rst}")
        print(f"  {dim}Entry point:{rst} {entry}")
        print(f"  {dim}Source files:{rst} {len(sources)}")
        print(f"  {dim}Output:{rst} {exe_name} ({exe_type})")
        print(f"  {dim}Modules:{rst} {', '.join(modules.keys()) if modules else 'none'}")
        print(f"  {dim}GC heap:{rst} {self.gc_young_mb} MiB young / {self.gc_old_mb} MiB old")
        opt_str = {'none': 'off', 'soft': 'light (O1)', 'hard': 'full (O2)'}.get(self.optimization, self.optimization)
        print(f"  {dim}Optimization:{rst} {opt_str}  {dim}Debug:{rst} {'on' if self.debug else 'off'}")

    def build_module(self, module_name: str) -> bool:
        stdmodule_config = _BASE_DIR / 'stdmodules' / module_name / 'manager.json'
        if stdmodule_config.exists():
            builder = ProjectBuilder(stdmodule_config,
                                     compiler_path=self.compiler_path,
                                     young_mb=self.gc_young_mb,
                                     old_mb=self.gc_old_mb,
                                     target=self.target)
            builder.optimization = self.optimization
            builder.debug = self.debug
            builder.force_rebuild = self.force_rebuild
            return builder.build()

        modules_config = self.config.get('modules', {})
        if module_name in modules_config:
            module_path = self.project_root / modules_config[module_name]
            if module_path.exists():
                temp_config = {
                    "name": module_name,
                    "version": "1.0.0",
                    "stx": {"processType": "module"},
                    "output": {
                        "libmain": str(module_path.relative_to(self.project_root)),
                        "native": False,
                        "nativeSources": [],
                        "elyfile": []
                    }
                }
                builder = ProjectBuilder.from_config(temp_config, self.project_root,
                                                     compiler_path=self.compiler_path,
                                                     young_mb=self.gc_young_mb,
                                                     old_mb=self.gc_old_mb,
                                                     target=self.target)
                builder.optimization = self.optimization
                builder.debug = self.debug
                builder.force_rebuild = self.force_rebuild
                return builder.build()

        print(f"\n{TC.tag('ERROR')} Module '{module_name}' not found")
        return False

    @classmethod
    def from_config(cls, config: dict, project_root: Path,
                    compiler_path=None, young_mb=None, old_mb=None, target=None):
        import tempfile
        tmp_dir = Path(tempfile.mkdtemp(prefix='elybuild_'))
        tmp_config = tmp_dir / 'manager.json'
        with open(tmp_config, 'w', encoding='utf-8') as f:
            json.dump(config, f)
        builder = cls(tmp_config, compiler_path=compiler_path,
                      young_mb=young_mb, old_mb=old_mb, target=target)
        builder._project_root_override = project_root
        builder.build_dir = project_root / 'build'
        builder.output_dir = project_root / 'output'
        builder.libs_dir = project_root / 'libs'
        builder.cache_path = builder.build_dir / 'cache.json'
        return builder

    def build(self) -> bool:
        process_type = self.config.get('stx', {}).get('processType', 'console')

        if process_type == 'module':
            return self._build_module()

        sources = self._collect_sources()
        if not sources:
            return False

        self._print_project_info(sources)
        self.build_dir.mkdir(parents=True, exist_ok=True)

        if not self._prepare_runtime():
            return False

        # --------------------------------------------------------------------
        # ЭТАП 1. ФРОНТЕНД И ГЕНЕРАЦИЯ C++ КОДА
        # --------------------------------------------------------------------
        print(f"\n{TC.tag('BUILD')} Parsing and analyzing Ely sources...")
        all_statements = []
        parser_errors_occurred = False

        for src in sources:
            stmts = self._parse_ely_file(src)
            if stmts is None:
                parser_errors_occurred = True
            else:
                all_statements.extend(stmts)

        if parser_errors_occurred:
            return False

        decls = []
        bodies = []
        for stmt in all_statements:
            if isinstance(stmt, (ClassDeclaration, InterfaceDeclaration, MethodDeclaration, NamespaceDeclaration)):
                decls.append(stmt)
            else:
                bodies.append(stmt)
        all_statements = decls + bodies

        sem = SemanticAnalyzer()
        errors = sem.analyze(Program(all_statements))
        if errors:
            self._show_semantic_errors(errors)
            return False
        print(f"  {TC.tag('OK')} Semantic analysis passed")

        codegen = CppCodeGen()
        cpp_code = codegen.generate(Program(all_statements))

        out_cpp_path = self.build_dir / 'output.cpp'
        with open(out_cpp_path, 'w', encoding='utf-8') as f:
            f.write(cpp_code)
        print(f"  {TC.tag('OK')} Generated C++ bridge -> {out_cpp_path}")

        # --------------------------------------------------------------------
        # ЭТАП 2. СОЗДАНИЕ КАТАЛОГА BUILD И ДИНАМИЧЕСКОГО СПИСКА SOURCES.TXT
        # --------------------------------------------------------------------
        sources_txt_path = self.build_dir / 'sources.txt'
        try:
            svlm_payload = []
            seen_paths = set()

            def add_to_payload(p: Path):
                abs_p = p.resolve()
                if abs_p not in seen_paths:
                    seen_paths.add(abs_p)
                    svlm_payload.append(abs_p)

            add_to_payload(out_cpp_path)

            target_extensions = ('.c', '.cpp', '.cxx', '.cc', '.h', '.hpp')

            if self.build_dir.exists():
                for item in self.build_dir.rglob('*'):
                    if item.is_file() and item.suffix.lower() in target_extensions:
                        add_to_payload(item)

            if self.libs_dir.exists():
                for item in self.libs_dir.rglob('*'):
                    if item.is_file() and item.suffix.lower() in ('.lib', '.a', '.dll', '.so'):
                        add_to_payload(item)

            out_cfg = self.config.get('output', {})
            native_sources = out_cfg.get('nativeSources', [])
            for rel_path in native_sources:
                native_path = (self.project_root / rel_path).resolve()
                if native_path.exists() and native_path.is_file():
                    add_to_payload(native_path)

            with open(sources_txt_path, 'w', encoding='utf-8') as f:
                for path in svlm_payload:
                    f.write(f"{path}\n")

            print(f"  {TC.tag('OK')} Created dynamic manifest ({len(svlm_payload)} files) -> {sources_txt_path}")
        except OSError as e:
            print(f"\n{TC.tag('ERROR')} Failed to write sources.txt: {e}")
            return False

        # --------------------------------------------------------------------
        # ЭТАП 3. ОРКЕСТРАЦИЯ ЧЕРЕЗ ДРАЙВЕР SVLM
        # --------------------------------------------------------------------
        svlm_bin, ssdk_dir = self._get_svlm_paths()
        if not svlm_bin or not ssdk_dir:
            print(f"\n{TC.tag('ERROR')} SVLM.exe or SSDK directory not found!")
            return False

        cmd = [
            str(svlm_bin),
            self.mode,
            str(self.project_root),
            'sources.txt',
            '--sdk', str(ssdk_dir)
        ]

        if self.mode == 'build':
            out_name = getattr(self, 'output_name', None)
            if not out_name:
                cfg = getattr(self, 'config', {}) or getattr(self, 'manager_json', {})
                out_name = cfg.get('output', {}).get('enter', {}).get('name', 'output.exe')
            cmd.extend(['-o', str(out_name)])

        print(f"\n{TC.tag('SVLM')} Launching core engine...")
        print(f"  {TC.DIM}Command: {' '.join(cmd)}{TC.RESET}")

        try:
            res = subprocess.run(cmd, check=False)
            if res.returncode != 0:
                print(f"\n{TC.tag('ERROR')} SVLM backend exited with error code: {res.returncode}")
                return False
            
            print(f"\n  {TC.GREEN}{TC.BOLD}SUCCESS: SVLM PROCESSING COMPLETED{TC.RESET}")
            return True
        except Exception as e:
            print(f"\n{TC.tag('ERROR')} Failed to invoke SVLM binary: {e}")
            return False

    def _prepare_runtime(self) -> bool:
        self.build_runtime = self.build_dir
        if self.compiler_runtime.exists():
            for item in self.compiler_runtime.iterdir():
                dest_item = self.build_runtime / item.name
                if item.is_dir():
                    if dest_item.exists():
                        shutil.rmtree(dest_item)
                    shutil.copytree(item, dest_item)
                else:
                    shutil.copy2(item, dest_item)
            return True
            
        print(f"\n{TC.tag('ERROR')} Runtime directory not found at {self.compiler_runtime}")
        return False

    def _collect_sources(self) -> list:
        main_file = self.config.get('enter')
        if not main_file:
            print(f"\n{TC.tag('ERROR')} 'enter' not specified in manager.json")
            return []
        main_path = (self.project_root / main_file).resolve()
        if not main_path.exists() or not main_path.is_file():
            print(f"\n{TC.tag('ERROR')} Main file not found: {main_path}")
            return []

        collected = {}
        pending = [main_path]

        modules_config = self.config.get('modules', {})
        for module_name, module_path in modules_config.items():
            candidate = (self.project_root / module_path).resolve()
            if candidate.exists():
                mod_dir = candidate.parent
                elymod = mod_dir / 'elymodule.json'
                if elymod.exists():
                    pending.append(elymod)
                else:
                    pending.append(candidate)
            else:
                pkg_candidate = self._resolve_package_module(module_path)
                if pkg_candidate:
                    pending.append(pkg_candidate)
                    pkg_elymod = pkg_candidate.parent / 'elymodule.json'
                    if pkg_elymod.exists():
                        pending.append(pkg_elymod)
                else:
                    print(f"  {TC.tag('WARN')} Module '{module_name}' not found at: {candidate}")

        while pending:
            current = pending.pop()
            abs_path = current.resolve()
            if abs_path in collected:
                continue

            if abs_path.name == 'elymodule.json':
                try:
                    with open(abs_path, 'r', encoding='utf-8') as f:
                        meta = json.load(f)

                    libmain = meta.get('libmain')
                    if libmain:
                        libmain_path = abs_path.parent / libmain
                        if libmain_path.exists():
                            pending.append(libmain_path)
                        else:
                            print(f"  {TC.tag('WARN')} libmain not found: {libmain_path}")

                    src_dir = abs_path.parent / 'src'
                    if src_dir.is_dir():
                        for ely_file in src_dir.rglob('*.ely'):
                            pending.append(ely_file)

                    ely_dir = abs_path.parent / 'ely'
                    if ely_dir.is_dir():
                        for ely_file in ely_dir.rglob('*.ely'):
                            pending.append(ely_file)
                except Exception:
                    pass
                continue

            collected[abs_path] = current

            stmts = self._parse_ely_file(abs_path)
            if stmts is None:
                return []

            for stmt in stmts:
                if isinstance(stmt, UsingDirective):
                    module = stmt.module
                    if module.startswith('"') and module.endswith('"'):
                        module = module[1:-1]
                    elif module not in ('"', '') and not module.startswith('"'):
                        modules_config = self.config.get('modules', {})
                        if module in modules_config:
                            module = modules_config[module]
                        else:
                            print(f"  {TC.tag('WARN')} Module '{module}' not found in manager.json")
                            continue
                    candidate = (abs_path.parent / module).resolve()
                    if candidate.exists():
                        pending.append(candidate)
                        mod_dir = candidate.parent
                        elymod = mod_dir / 'elymodule.json'
                        if elymod.exists():
                            pending.append(elymod)
                    else:
                        modules_config2 = self.config.get('modules', {})
                        if module in modules_config2:
                            mod_candidate = (self.project_root / modules_config2[module]).resolve()
                            if mod_candidate.exists():
                                pending.append(mod_candidate)
                                mod_dir2 = mod_candidate.parent
                                elymod2 = mod_dir2 / 'elymodule.json'
                                if elymod2.exists():
                                    pending.append(elymod2)
                                continue
                        pkg_candidate = self._resolve_package_module(module)
                        if pkg_candidate:
                            pending.append(pkg_candidate)
                            pkg_elymod = pkg_candidate.parent / 'elymodule.json'
                            if pkg_elymod.exists():
                                pending.append(pkg_elymod)
                        else:
                            print(f"  {TC.tag('WARN')} Module file not found: {candidate}")

        return list(collected.keys())

    def _show_semantic_errors(self, errors):
        total = len(errors)
        print(f"\n{TC.tag('ERROR')} {TC.BOLD}{TC.RED}Semantic errors ({total}):{TC.RESET}")
        for i, e in enumerate(errors, 1):
            msg = str(e)
            if ':' in msg:
                print(f"\n  {TC.DIM}{i}/{total}{TC.RESET} {TC.YELLOW}{TC.BOLD}{msg}{TC.RESET}")
            else:
                print(f"  {TC.DIM}{i}/{total}{TC.RESET} {TC.YELLOW}{msg}{TC.RESET}")
        print()

    def _build_module(self) -> bool:
        name = self.config.get('name', 'module')
        out_cfg = self.config.get('output', {})
        native = out_cfg.get('native', True)
        libmain_rel = out_cfg.get('libmain', 'src/lib.ely')
        elyfile_list = out_cfg.get('elyfile', [])
        native_sources = out_cfg.get('nativeSources', [])

        output_pkg_dir = self.output_dir / name
        output_lib_dir = output_pkg_dir / 'lib'
        output_include_dir = output_pkg_dir / 'include'
        output_ely_dir = output_pkg_dir / 'ely'

        output_pkg_dir.mkdir(parents=True, exist_ok=True)
        self.build_dir.mkdir(parents=True, exist_ok=True)

        libmain_path = (self.project_root / libmain_rel).resolve()
        if not libmain_path.exists():
            print(f"\n{TC.tag('ERROR')} libmain not found: {libmain_path}")
            return False

        sources = self._collect_module_sources(libmain_path)
        if not sources:
            return False

        print(f"\n{TC.BOLD}{TC.WHITE}  Module: {name}{TC.RESET}")
        print(f"  {TC.DIM}libmain:{TC.RESET} {libmain_rel}")
        print(f"  {TC.DIM}Source files:{TC.RESET} {len(sources)}")
        print(f"  {TC.DIM}Native:{TC.RESET} {'yes' if native else 'no'}")
        print(f"  {TC.DIM}Output:{TC.RESET} {output_pkg_dir}/")

        if not self._prepare_runtime():
            return False

        print(f"\n{TC.tag('BUILD')} Parsing module sources...")
        all_statements = []
        parser_errors_occurred = False

        for src in sources:
            stmts = self._parse_ely_file(src)
            if stmts is None:
                parser_errors_occurred = True
            else:
                all_statements.extend(stmts)

        if parser_errors_occurred:
            return False

        sem = SemanticAnalyzer()
        errors = sem.analyze(Program(all_statements))
        if errors:
            self._show_semantic_errors(errors)
            return False
        print(f"  {TC.tag('OK')} Semantic analysis passed")

        public_funcs = self._extract_public_functions(all_statements)
        pub_names = [f[0] for f in public_funcs]
        print(f"  {TC.tag('OK')} Public exports: {', '.join(pub_names) if pub_names else '(none)'}")

        cpp_file = self.build_dir / 'output.cpp'
        codegen = CppCodeGen(debug=self.debug)
        cpp_code = codegen.generate(Program(all_statements))
        cpp_file.write_text(cpp_code, encoding='utf-8')
        print(f"  {TC.tag('OK')} C++ code generated -> {cpp_file.name}")

        print(f"\n{TC.tag('INFO')} Searching for C++ compiler...")
        compiler, comp_path, extra_flags = self._find_compiler()
        if not compiler:
            print(f"\n{TC.tag('ERROR')} No C++ compiler found.")
            return False
        print(f"  {TC.tag('OK')} Using {compiler} -> {comp_path}")

        if compiler == 'gcc':
            gcc_path = Path(comp_path)
            if gcc_path.name == 'gcc.exe' or gcc_path.name == 'gcc':
                self._ensure_gpp(gcc_path)
                compiler = 'g++'
                comp_path = str(gcc_path.with_name('g++.exe' if sys.platform == 'win32' else 'g++'))

        main_obj = self.build_dir / 'output.o'
        print(f"\n{TC.tag('BUILD')} Compiling {cpp_file.name} -> {main_obj.name}...")
        cmd = [comp_path, '-c', str(cpp_file), '-o', str(main_obj)]
        if self.optimization == 'hard':
            cmd.append('-O2')
        elif self.optimization == 'soft':
            cmd.append('-O1')
        if self.debug:
            cmd.append('-g')
        cmd.append(f'-I{self.build_dir}/runtime')
        cmd.append('-fexceptions')
        cmd.append('-std=c++20')
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            print(f"  {TC.tag('OK')} Compilation succeeded")
        except subprocess.CalledProcessError as e:
            print(f"\n{TC.tag('ERROR')} C++ compilation failed")
            self._show_compiler_error(e.stderr, str(cpp_file))
            return False

        native_objs = []
        if native and native_sources:
            print(f"\n{TC.tag('BUILD')} Compiling native sources ({len(native_sources)} files)...")
            for rel_path in native_sources:
                src_path = (self.project_root / rel_path).resolve()
                if not src_path.exists():
                    print(f"  {TC.tag('WARN')} Native source not found: {rel_path}")
                    continue
                obj_path = self.build_dir / (src_path.stem + '.o')
                is_cpp = src_path.suffix in ('.cpp', '.cxx', '.cc')
                ncmd = [comp_path, '-c', str(src_path), '-o', str(obj_path)]
                if not is_cpp and compiler in ('g++', 'c++'):
                    ncmd.insert(1, '-x')
                    ncmd.insert(2, 'c')
                if self.optimization == 'hard':
                    ncmd.append('-O2')
                ncmd.append(f'-I{self.build_dir}/runtime')
                ncmd.append(f'-I{self.project_root}/src')
                if is_cpp:
                    ncmd.append('-std=c++20')
                try:
                    subprocess.run(ncmd, check=True, capture_output=True, text=True)
                    native_objs.append(obj_path)
                    print(f"  {TC.tag('OK')} {rel_path} -> {obj_path.name}")
                except subprocess.CalledProcessError as e:
                    print(f"\n{TC.tag('ERROR')} Native compilation failed: {rel_path}")
                    self._show_compiler_error(e.stderr, str(src_path))
                    return False

        if native:
            output_lib_dir.mkdir(parents=True, exist_ok=True)
            lib_file = output_lib_dir / f'{name}.lib'
            print(f"\n{TC.tag('BUILD')} Creating static library {lib_file.name}...")
            all_objs_for_lib = [main_obj] + native_objs
            ar_exe = Path(comp_path).with_name('ar.exe')
            if not ar_exe.exists():
                ar_exe = shutil.which('ar')
                if not ar_exe:
                    print(f"  {TC.tag('WARN')} ar.exe not found, skipping static library. Copying .o instead.")
                    shutil.copy2(main_obj, lib_file.with_suffix('.o'))
                else:
                    ar_exe = Path(ar_exe)
            if ar_exe and ar_exe.exists():
                try:
                    ar_cmd = [str(ar_exe), 'rcs', str(lib_file)] + [str(o) for o in all_objs_for_lib]
                    subprocess.run(ar_cmd, check=True, capture_output=True, text=True)
                    print(f"  {TC.tag('OK')} Static library created: {lib_file}")
                except subprocess.CalledProcessError as e:
                    print(f"  {TC.tag('WARN')} ar failed: {e.stderr}. Copying .o instead.")
                    shutil.copy2(main_obj, lib_file.with_suffix('.o'))
            else:
                shutil.copy2(main_obj, lib_file.with_suffix('.o'))

            output_include_dir.mkdir(parents=True, exist_ok=True)
            h_file = output_include_dir / f'{name}.h'
            print(f"  {TC.tag('BUILD')} Generating {h_file.name}...")
            with open(h_file, 'w', encoding='utf-8') as hf:
                hf.write(f"// Auto-generated header for module {name}\n")
                hf.write(f"#ifndef ELY_MODULE_{name.upper()}_H\n")
                hf.write(f"#define ELY_MODULE_{name.upper()}_H\n\n")
                hf.write('#include "ely_runtime.h"\n\n')
                for func_name, ret_type, params in public_funcs:
                    c_ret = self._ely_to_c_type(ret_type)
                    c_params = ', '.join([f"{self._ely_to_c_type(pt)} {pn}" for pt, pn in params])
                    hf.write(f"extern {c_ret} {func_name}({c_params});\n")
                hf.write("\n#endif\n")
            print(f"  {TC.tag('OK')} Header generated: {h_file}")

        link_file = output_pkg_dir / 'link.ely'
        print(f"\n{TC.tag('BUILD')} Generating link.ely wrapper...")
        with open(link_file, 'w', encoding='utf-8') as lf:
            lf.write(f"// Auto-generated link wrapper for module {name}\n")
            lf.write(f"// language_version: 26.5\n")
            lf.write(f"// Do not edit manually.\n\n")
            for func_name, ret_type, params in public_funcs:
                param_str = ', '.join([f"{pt} {pn}" for pt, pn in params])
                lf.write(f"public {ret_type} func {func_name}({param_str}) {{}}\n")
        print(f"  {TC.tag('OK')} link.ely -> {link_file}")

        if elyfile_list:
            output_ely_dir.mkdir(parents=True, exist_ok=True)
            print(f"\n{TC.tag('INFO')} Copying elyfile assets...")
            for rel_path in elyfile_list:
                src_path = (self.project_root / rel_path).resolve()
                dst_path = output_ely_dir / Path(rel_path).name
                if src_path.exists():
                    shutil.copy2(src_path, dst_path)
                    print(f"  {TC.tag('OK')} {rel_path} -> {dst_path}")
                else:
                    print(f"  {TC.tag('WARN')} elyfile not found: {rel_path}")

        print(f"\n{TC.tag('BUILD')} Generating elymodule.json...")
        include_files = ['link.ely', 'elymodule.json']
        if native:
            include_files.append(f'lib/{name}.lib')
            include_files.append(f'include/{name}.h')
        for rel in elyfile_list:
            include_files.append(f'ely/{Path(rel).name}')
        elymodule = {
            "name": name,
            "version": self.config.get('version', '0.1.0'),
            "language_version": "26.5",
            "stx": {"processType": "module"},
            "description": self.config.get('description', ''),
            "author": self.config.get('author', ''),
            "linkfile": "link.ely",
            "exports": pub_names,
            "include": include_files
        }
        elymodule_path = output_pkg_dir / 'elymodule.json'
        with open(elymodule_path, 'w', encoding='utf-8') as ef:
            json.dump(elymodule, ef, indent=4)
        print(f"  {TC.tag('OK')} elymodule.json -> {elymodule_path}")

        print(f"\n  {TC.GREEN}{TC.BOLD}BUILD SUCCESS{TC.RESET}")
        print(f"  {TC.BOLD}{TC.WHITE}Module:{TC.RESET} {output_pkg_dir}/")
        self.output_name = str(output_pkg_dir)
        return True

    def _collect_module_sources(self, libmain_path: Path) -> list:
        collected = {}
        pending = [libmain_path]

        while pending:
            current = pending.pop()
            abs_path = current.resolve()
            if abs_path in collected:
                continue
            if not abs_path.exists():
                print(f"  {TC.tag('WARN')} File not found: {abs_path}")
                continue
            collected[abs_path] = current

            stmts = self._parse_ely_file(abs_path)
            if stmts is None:
                return []

            for stmt in stmts:
                if isinstance(stmt, UsingDirective):
                    module = stmt.module
                    if module.startswith('"') and module.endswith('"'):
                        module = module[1:-1]
                    elif module not in ('"', '') and not module.startswith('"'):
                        modules_config = self.config.get('modules', {})
                        if module in modules_config:
                            module = modules_config[module]
                        else:
                            print(f"  {TC.tag('WARN')} Module '{module}' not found in manager.json")
                            continue
                    candidate = (abs_path.parent / module).resolve()
                    if candidate.exists():
                        pending.append(candidate)
                    else:
                        pkg_candidate = self._resolve_package_module(module)
                        if pkg_candidate:
                            pending.append(pkg_candidate)
                        else:
                            print(f"  {TC.tag('WARN')} Module file not found: {candidate}")

        return list(collected.keys())

    def _resolve_package_module(self, module_name: str) -> Optional[Path]:
        pkg_dir = self.project_root / 'ely_packages' / module_name
        if pkg_dir.exists():
            elymodule_json = pkg_dir / 'elymodule.json'
            if elymodule_json.exists():
                with open(elymodule_json, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                linkfile = meta.get('linkfile', 'link.ely')
                link_path = pkg_dir / linkfile
                if link_path.exists():
                    return link_path
        return None

    def _extract_public_functions(self, statements: list) -> list:
        result = []
        for stmt in statements:
            if isinstance(stmt, MethodDeclaration) and stmt.modifier == 'public':
                params = [(p.type, p.name) for p in stmt.parameters]
                result.append((stmt.name, stmt.return_type or 'void', params))
        return result

    @staticmethod
    def _ely_to_c_type(ely_type: str) -> str:
        mapping = {
            'void': 'void',
            'int': 'int',
            'uint': 'unsigned int',
            'more': 'long long',
            'umore': 'unsigned long long',
            'flt': 'float',
            'double': 'double',
            'bool': 'int',
            'str': 'char*',
            'any': 'void*',
            'char': 'char',
            'byte': 'signed char',
            'ubyte': 'unsigned char'
        }
        return mapping.get(ely_type, 'int')

    @staticmethod
    def _show_compiler_error(stderr_text: str, context_hint: str = ''):
        keywords = ['error:', 'Error:', 'ERROR:', 'undefined reference',
                    'collect2:', 'ld returned']
        for line in stderr_text.strip().split('\n'):
            stripped = line.strip()
            if any(kw in stripped for kw in keywords):
                print(f"  {TC.RED}{TC.BOLD}{stripped}{TC.RESET}")
            elif stripped.startswith(('In file', 'from', 'note:')):
                print(f"  {TC.DIM}{stripped}{TC.RESET}")
            else:
                print(f"  {TC.YELLOW}{stripped}{TC.RESET}")