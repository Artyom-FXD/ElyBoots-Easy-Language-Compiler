# package_manager.py
"""
Ely Package Manager core library.

Handles module installation from stdmodules/ or GitHub,
dependency tracking in manager.json, and package metadata (elymodule.json).
"""

import json
import os
import sys
import re
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# When frozen by PyInstaller, __file__ points to the temp extraction directory.
# We need the directory of the actual .exe to find stdmodules/ and ebt.py.
if getattr(sys, 'frozen', False):
    _BASE_DIR = Path(sys.executable).parent
else:
    _BASE_DIR = Path(__file__).parent


class PackageManager:
    """
    Core package management for Ely projects.

    Resolves modules from:
      - stdmodules/  (built-in standard modules shipped with the compiler)
      - GitHub repositories (e.g. user/repo)

    Installs into: <project>/modules/<name>/
    Updates manager.json: modules { "name": "modules/name/src/lib.ely" }
    """

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = Path(project_root).resolve() if project_root else Path.cwd()
        self.stdmodules_dir = self._find_stdmodules()
        self.modules_dir = self.project_root / 'modules'

    def _find_stdmodules(self) -> Path:
        """Find the stdmodules/ directory relative to the EasyBoots installation."""
        # This file is at EasyBoots/package_manager.py
        # stdmodules is at EasyBoots/stdmodules/
        candidate = _BASE_DIR / 'stdmodules'
        if candidate.is_dir():
            return candidate
        # Fallback: relative to cwd
        candidate2 = Path.cwd() / 'stdmodules'
        if candidate2.is_dir():
            return candidate2
        # Last resort
        return candidate

    @staticmethod
    def resolve_manager_path(path_str: str | None) -> Optional[Path]:
        """
        Разрешает путь к manager.json из строки.
        - None → ищет manager.json в CWD
        - директория → ищет manager.json внутри
        - файл .json → использует напрямую
        Возвращает Path к manager.json или None.
        """
        if path_str:
            p = Path(path_str)
        else:
            p = Path.cwd()
        if p.is_dir():
            manager = p / 'manager.json'
            if manager.exists():
                return manager.resolve()
            return None
        if p.suffix == '.json' and p.exists():
            return p.resolve()
        return None

    # ------------------------------------------------------------------
    # init
    # ------------------------------------------------------------------
    def init(self, name: str = 'my-module') -> bool:
        elymodule_path = self.project_root / 'elymodule.json'
        if elymodule_path.exists():
            print(f"elymodule.json already exists in {self.project_root}")
            return False

        elymodule = {
            "name": name,
            "version": "0.1.0",
            "language_version": "26.5",
            "stx": {"processType": "module"},
            "description": "",
            "author": "",
            "linkfile": "link.ely",
            "exports": [],
            "include": []
        }
        with open(elymodule_path, 'w', encoding='utf-8') as f:
            json.dump(elymodule, f, indent=4)

        src_dir = self.project_root / 'src'
        src_dir.mkdir(exist_ok=True)
        (src_dir / 'lib.ely').write_text("""// Module entry point
public int func hello() {
    println("Hello from module!");
    return 0;
}
""", encoding='utf-8')

        print(f"Initialised {name} in {self.project_root}")
        print(f"  created: elymodule.json, src/lib.ely")
        return True

    # ------------------------------------------------------------------
    # manager.json helpers
    # ------------------------------------------------------------------
    def _load_manager(self) -> Dict[str, Any]:
        manager_path = self.project_root / 'manager.json'
        if not manager_path.exists():
            return {}
        with open(manager_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _save_manager(self, data: Dict[str, Any]):
        manager_path = self.project_root / 'manager.json'
        with open(manager_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)

    # ------------------------------------------------------------------
    # install
    # ------------------------------------------------------------------
    def install(self, package_spec: str) -> bool:
        """
        Install a module into modules/<name>/.

        Resolves from:
          1. stdmodules/<name>/   (standard library)
          2. GitHub user/repo    (community packages)

        Usage:
          elp install file           # from stdmodules
          elp install json           # from stdmodules
          elp install user/repo      # from GitHub
        """
        spec = package_spec.strip()

        # GitHub: user/repo or user/repo@branch
        if '/' in spec and not re.match(r'^[a-zA-Z]:', spec):
            return self._install_from_github(spec)

        # stdmodules/<name>/
        return self._install_from_stdmodules(spec)

    def install_local(self, package_path: str) -> bool:
        """Install a module from a local directory (contains elymodule.json)."""
        src = Path(package_path).resolve()
        if not src.exists():
            print(f"Path not found: {src}")
            return False

        elymodule_path = src / 'elymodule.json'
        if not elymodule_path.exists():
            print(f"No elymodule.json found in {src}")
            return False

        with open(elymodule_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)

        module_name = meta.get('name', src.name)
        return self._copy_and_register(src, module_name, meta)

    def _install_from_stdmodules(self, name: str) -> bool:
        """Install a module from stdmodules/<name>/.
        
        Copies pre-built artifacts from stdmodules/<name>/output/<name>/
        (link.ely, lib/, include/, elymodule.json) into the project's
        modules/ directory.  If the output/ is missing, the source is
        compiled first via ebt.
        """
        if not self.stdmodules_dir or not self.stdmodules_dir.is_dir():
            print(f"stdmodules directory not found.")
            print(f"Expected at: {self.stdmodules_dir}")
            return False

        src = self.stdmodules_dir / name
        if not src.is_dir():
            print(f"Module '{name}' not found in stdmodules.")
            print(f"Available modules:")
            for d in sorted(self.stdmodules_dir.iterdir()):
                if d.is_dir() and (d / 'elymodule.json').exists():
                    print(f"  - {d.name}")
            return False

        elymodule_path = src / 'elymodule.json'
        if not elymodule_path.exists():
            print(f"Module '{name}' has no elymodule.json in {src}")
            return False

        with open(elymodule_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)

        module_name = meta.get('name', name)
        version = meta.get('version', '?')
        print(f"Installing {module_name}@{version} from stdmodules/{name}")

        # --- Prefer pre-built output/<name>/ ---------------------------------
        output_dir = src / 'output' / module_name
        if output_dir.is_dir():
            output_meta = output_dir / 'elymodule.json'
            if output_meta.exists():
                with open(output_meta, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                print(f"  Using pre-built artifacts from output/{module_name}/")
                return self._copy_and_register(output_dir, module_name, meta)
            else:
                # Bare output — copy anyway but use root meta
                print(f"  Using artifacts from output/{module_name}/")
                return self._copy_and_register(output_dir, module_name, meta)

        # --- Fallback: build from source then install ------------------------
        manager_json = src / 'manager.json'
        if manager_json.exists():
            print(f"  Building module {module_name} from source ...")
            ebt_path = _BASE_DIR / 'ebt.py'
            result = subprocess.run(
                [sys.executable, str(ebt_path), 'build', str(manager_json)],
                capture_output=True, text=True, cwd=str(src)
            )
            if result.returncode != 0:
                print(f"  Build failed for {module_name}:")
                print(f"  {result.stderr}")
                return False
            print(f"  Build succeeded.")
            # Retry with output
            output_dir = src / 'output' / module_name
            if output_dir.is_dir():
                print(f"  Using freshly built artifacts from output/{module_name}/")
                return self._copy_and_register(output_dir, module_name, meta)
            else:
                print(f"  Output directory not found after build: {output_dir}")
                print(f"  Falling back to source copy.")
                return self._copy_and_register(src, module_name, meta)

        # --- Last resort: copy the whole source module directory -------------
        print(f"  No output/ and no manager.json — copying source directory.")
        return self._copy_and_register(src, module_name, meta)

    def _install_from_github(self, spec: str) -> bool:
        """
        Install a module from GitHub.

        spec format: user/repo or user/repo@branch
        """
        branch = 'main'
        if '@' in spec:
            repo_part, branch = spec.split('@', 1)
        else:
            repo_part = spec

        if '/' not in repo_part:
            print(f"Invalid GitHub spec: {spec}. Expected user/repo.")
            return False

        user, repo = repo_part.split('/', 1)
        url = f"https://github.com/{user}/{repo}"

        print(f"Fetching {url} (branch: {branch})...")

        # Try git clone first (fastest for repos), fall back to zip download
        tmpdir = Path(tempfile.mkdtemp(prefix='ely_install_'))
        try:
            clone_url = f"https://github.com/{user}/{repo}.git"
            result = subprocess.run(
                ['git', 'clone', '--depth', '1', '--branch', branch, clone_url, str(tmpdir)],
                capture_output=True, text=True
            )
            if result.returncode != 0:
                # Fallback: download zip
                print(f"  git clone failed, trying zip download...")
                zip_url = f"https://github.com/{user}/{repo}/archive/refs/heads/{branch}.zip"
                zip_path = tmpdir / 'repo.zip'
                urllib.request.urlretrieve(zip_url, zip_path)
                import zipfile
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    # Extract, stripping top-level directory
                    top_dir = zf.namelist()[0].split('/')[0]
                    zf.extractall(tmpdir)
                extracted = tmpdir / top_dir
                if extracted.is_dir():
                    shutil.copytree(extracted, tmpdir / 'repo', dirs_exist_ok=True)
                    tmpdir = tmpdir / 'repo'
                else:
                    tmpdir = extracted
            else:
                # git clone succeeded, tmpdir is the repo
                pass

            elymodule_path = tmpdir / 'elymodule.json'
            if not elymodule_path.exists():
                # May be in subdirectory
                for candidate in tmpdir.rglob('elymodule.json'):
                    elymodule_path = candidate
                    tmpdir = candidate.parent
                    break

            if not elymodule_path.exists():
                print(f"No elymodule.json found in {url}")
                return False

            with open(elymodule_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)

            module_name = meta.get('name', repo)
            print(f"Installing {module_name}@{meta.get('version', '?')} from GitHub ({user}/{repo})")
            return self._copy_and_register(tmpdir, module_name, meta)
        except Exception as e:
            print(f"Failed to install from GitHub: {e}")
            return False
        finally:
            # Clean up temp
            if tmpdir.exists():
                shutil.rmtree(tmpdir, ignore_errors=True)

    def _copy_and_register(self, src: Path, module_name: str, meta: Dict[str, Any]) -> bool:
        """
        Copy module source to modules/<module_name>/ and register in manager.json.
        
        Respects the 'include' field of elymodule.json if present.
        """
        dst = self.modules_dir / module_name

        if dst.exists():
            shutil.rmtree(dst)

        include_list = meta.get('include', [])
        if include_list:
            dst.mkdir(parents=True, exist_ok=True)
            for rel in include_list:
                src_file = src / rel
                dst_file = dst / rel
                if src_file.exists():
                    dst_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_file, dst_file)
                else:
                    print(f"  WARNING: {rel} not found, skipping.")
            # Copy elymodule.json
            elymodule_path = src / 'elymodule.json'
            if elymodule_path.exists():
                shutil.copy2(elymodule_path, dst / 'elymodule.json')
        else:
            # Copy entire directory
            shutil.copytree(src, dst, dirs_exist_ok=True)

        print(f"  Copied to {dst}")

        # Find the linkfile (module entry point)
        linkfile = meta.get('linkfile', 'src/lib.ely')
        # Check common patterns
        if not (dst / linkfile).exists():
            # Try src/lib.ely, src/module.ely, src/main.ely
            for candidate in ['src/lib.ely', 'src/module.ely', 'lib.ely', 'main.ely']:
                if (dst / candidate).exists():
                    linkfile = candidate
                    break

        relative_link = f"modules/{module_name}/{linkfile}"

        # Register in manager.json
        self._update_modules(module_name, relative_link)

        return True

    def _update_modules(self, name: str, module_path: str):
        """Add/update a module entry in manager.json."""
        manager = self._load_manager()
        if not manager:
            return

        if 'modules' not in manager:
            manager['modules'] = {}

        manager['modules'][name] = module_path

        self._save_manager(manager)
        print(f"  Registered '{name}' -> '{module_path}' in manager.json")

    # ------------------------------------------------------------------
    # remove
    # ------------------------------------------------------------------
    def remove(self, name: str) -> bool:
        pkg_dir = self.modules_dir / name
        if not pkg_dir.exists():
            print(f"Module '{name}' not installed.")
            return False

        shutil.rmtree(pkg_dir)
        print(f"Removed {name}")

        manager = self._load_manager()
        modules = manager.get('modules', {})
        if name in modules:
            del modules[name]
            manager['modules'] = modules
            self._save_manager(manager)
            print(f"Removed '{name}' from manager.json modules.")
        return True

    # ------------------------------------------------------------------
    # update
    # ------------------------------------------------------------------
    def update(self) -> bool:
        manager = self._load_manager()
        modules = manager.get('modules', {})
        if not modules:
            print("No modules installed.")
            return True

        for name in list(modules.keys()):
            print(f"Updating {name}...")
            self.install(name)
        return True

    # ------------------------------------------------------------------
    # list
    # ------------------------------------------------------------------
    def list_packages(self) -> List[Dict[str, str]]:
        result = []
        if not self.modules_dir.exists():
            return result

        for pkg_dir in sorted(self.modules_dir.iterdir()):
            if pkg_dir.is_dir():
                elymodule_path = pkg_dir / 'elymodule.json'
                if elymodule_path.exists():
                    with open(elymodule_path, 'r', encoding='utf-8') as f:
                        meta = json.load(f)
                    result.append({
                        'name': meta.get('name', pkg_dir.name),
                        'version': meta.get('version', '?'),
                        'description': meta.get('description', '')
                    })
                else:
                    result.append({
                        'name': pkg_dir.name,
                        'version': '?',
                        'description': '(no elymodule.json)'
                    })
        return result

    # ------------------------------------------------------------------
    # pack
    # ------------------------------------------------------------------
    def pack(self, output_path: Optional[str] = None) -> bool:
        elymodule_path = self.project_root / 'elymodule.json'
        if not elymodule_path.exists():
            print(f"No elymodule.json found in {self.project_root}")
            print("Run 'elp init' first.")
            return False

        with open(elymodule_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)

        name = meta.get('name', self.project_root.name)
        version = meta.get('version', '0.1.0')
        archive_name = output_path or f"{name}-{version}.elypkg"
        archive_path = self.project_root / archive_name

        import zipfile
        include_list = meta.get('include', [])
        if not include_list:
            print("No 'include' list in elymodule.json. Nothing to pack.")
            return False

        with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for rel in include_list:
                file_path = self.project_root / rel
                if file_path.exists():
                    zf.write(file_path, rel)
                    print(f"  + {rel}")
                else:
                    print(f"  WARNING: {rel} not found, skipping.")
            zf.write(elymodule_path, 'elymodule.json')
            print(f"  + elymodule.json")

        print(f"\nPacked: {archive_path}")
        return True

    # ------------------------------------------------------------------
    # publish
    # ------------------------------------------------------------------
    def publish(self) -> bool:
        elymodule_path = self.project_root / 'elymodule.json'
        if not elymodule_path.exists():
            print("No elymodule.json found.")
            return False

        with open(elymodule_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)

        name = meta.get('name', self.project_root.name)
        registry_dir = Path.home() / '.ely' / 'registry' / name
        registry_dir.mkdir(parents=True, exist_ok=True)

        shutil.copy2(elymodule_path, registry_dir / 'elymodule.json')
        for rel in meta.get('include', []):
            src = self.project_root / rel
            if src.exists():
                dst = registry_dir / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

        self._update_registry_index(name, meta)
        print(f"Published {name}@{meta.get('version', '?')} to registry")
        return True

    # ------------------------------------------------------------------
    # info
    # ------------------------------------------------------------------
    def info(self, package_name: str) -> Optional[Dict[str, Any]]:
        local_pkg = self.modules_dir / package_name / 'elymodule.json'
        if local_pkg.exists():
            with open(local_pkg, 'r', encoding='utf-8') as f:
                return json.load(f)

        registry_pkg = Path.home() / '.ely' / 'registry' / package_name / 'elymodule.json'
        if registry_pkg.exists():
            with open(registry_pkg, 'r', encoding='utf-8') as f:
                return json.load(f)

        return None

    # ------------------------------------------------------------------
    # Registry helpers (for publish)
    # ------------------------------------------------------------------
    def _update_registry_index(self, name: str, meta: Dict[str, Any]):
        registry_dir = Path.home() / '.ely' / 'registry'
        registry_index = registry_dir / 'index.json'
        index = {}
        if registry_index.exists():
            with open(registry_index, 'r', encoding='utf-8') as f:
                index = json.load(f)

        if 'packages' not in index:
            index['packages'] = {}

        index['packages'][name] = {
            'version': meta.get('version', '0.1.0'),
            'description': meta.get('description', ''),
            'author': meta.get('author', ''),
            'path': str(registry_dir / name)
        }

        registry_index.parent.mkdir(parents=True, exist_ok=True)
        with open(registry_index, 'w', encoding='utf-8') as f:
            json.dump(index, f, indent=4)

    # ------------------------------------------------------------------
    # list-available (list modules in stdmodules)
    # ------------------------------------------------------------------
    def list_available(self) -> List[Dict[str, str]]:
        """List modules available in stdmodules."""
        result = []
        if not self.stdmodules_dir or not self.stdmodules_dir.is_dir():
            return result

        for d in sorted(self.stdmodules_dir.iterdir()):
            if d.is_dir():
                elymodule_path = d / 'elymodule.json'
                if elymodule_path.exists():
                    with open(elymodule_path, 'r', encoding='utf-8') as f:
                        meta = json.load(f)
                    result.append({
                        'name': meta.get('name', d.name),
                        'version': meta.get('version', '?'),
                        'description': meta.get('description', '')
                    })
        return result