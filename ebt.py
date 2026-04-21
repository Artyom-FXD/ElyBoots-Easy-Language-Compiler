#!/usr/bin/env python3
import sys
import os
import argparse
import json
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

def main():
    parser = argparse.ArgumentParser(prog='ebt', description='ely Language Compiler')
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # build
    build_parser = subparsers.add_parser('build', help='Build project')
    build_parser.add_argument('file', nargs='?', default='manager.json', help='Project file')
    build_parser.add_argument('-o', '--output', help='Output executable name')
    build_parser.add_argument('--optimize', choices=['none', 'soft', 'hard'], default='hard')
    build_parser.add_argument('--debug', action='store_true')
    build_parser.add_argument('--target', help='Target triple')
    build_parser.add_argument('--compiler', help='Path to C compiler executable')
    build_parser.add_argument('--young-mb', type=int, help='Young generation size in MB')
    build_parser.add_argument('--old-mb', type=int, help='Old generation initial size in MB')

    # build-module
    mod_parser = subparsers.add_parser('build-module', help='Build a specific module')
    mod_parser.add_argument('module', help='Module name')
    mod_parser.add_argument('--file', default='manager.json', help='Project file')
    mod_parser.add_argument('--optimize', choices=['none', 'soft', 'hard'], default='hard')
    mod_parser.add_argument('--debug', action='store_true')

    # run
    run_parser = subparsers.add_parser('run', help='Build and run')
    run_parser.add_argument('file', nargs='?', default='manager.json')
    run_parser.add_argument('--args', nargs='+', default=[])

    # clean
    clean_parser = subparsers.add_parser('clean', help='Remove build artifacts')
    clean_parser.add_argument('--all', action='store_true')

    # project
    proj_parser = subparsers.add_parser('project', help='Create new project')
    proj_parser.add_argument('name', nargs='?', default='new_project')
    
    # Новая команда install-compiler
    install_parser = subparsers.add_parser('install-compiler', help='Manage GCC compiler installation')
    install_subparsers = install_parser.add_subparsers(dest='install_command', help='Subcommands')

    # ebt install-compiler install
    install_cmd = install_subparsers.add_parser('install', help='Install GCC into tools/')
    install_cmd.add_argument('--version', help='GCC version to install (e.g., 13.2.0)')

    # ebt install-compiler remove
    remove_cmd = install_subparsers.add_parser('remove', help='Remove installed GCC')

    # ebt install-compiler list
    list_cmd = install_subparsers.add_parser('list', help='List available GCC versions')

    # ebt install-compiler set-path <path>
    set_path_cmd = install_subparsers.add_parser('set-path', help='Set custom path to GCC executable')
    set_path_cmd.add_argument('path', help='Path to GCC executable (e.g., /usr/bin/gcc-13)')

    config_parser = subparsers.add_parser('config', help='Manage compiler configuration')
    config_subparsers = config_parser.add_subparsers(dest='config_command', help='Config commands')

    set_parser = config_subparsers.add_parser('set', help='Set configuration value')
    set_parser.add_argument('key', help='Configuration key (e.g., compiler.path)')
    set_parser.add_argument('value', help='Configuration value')
    set_parser.add_argument('--global', dest='global_scope', action='store_true', help='Set globally (~/.ely/config.json)')
    set_parser.add_argument('--local', dest='local_scope', action='store_true', help='Set locally (./.ely_config)')

    get_parser = config_subparsers.add_parser('get', help='Get configuration value')
    get_parser.add_argument('key', nargs='?', help='Configuration key (omit to show all)')

    list_parser = config_subparsers.add_parser('list', help='List current effective configuration')

    reset_parser = config_subparsers.add_parser('reset', help='Reset configuration')
    reset_parser.add_argument('--global', dest='global_scope', action='store_true', help='Reset global config')
    reset_parser.add_argument('--local', dest='local_scope', action='store_true', help='Reset local config')

    args = parser.parse_args()

    if args.command == 'install-compiler':
        return install_compiler_command(args)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 1

    if args.command == 'build':
        return build_command(args)
    elif args.command == 'build-module':
        return build_module_command(args)
    elif args.command == 'run':
        return run_command(args)
    elif args.command == 'clean':
        return clean_command(args)
    elif args.command == 'project':
        return project_command(args)
    elif args.command == 'config':
        return config_command(args)
    return 0

def build_command(args):
    from builder import ProjectBuilder
    builder = ProjectBuilder(Path(args.file),
                            compiler_path=args.compiler,
                            young_mb=args.young_mb,
                            old_mb=args.old_mb,
                            target=args.target)
    builder.optimization = args.optimize
    builder.debug = args.debug
    if args.target:
        builder.target = args.target
    success = builder.build()
    if not success:
        return 1
    if args.output and builder.output_name:
        shutil.move(builder.output_name, args.output)
        print(f"Output renamed to {args.output}")
    return 0

def build_module_command(args):
    from builder import ProjectBuilder
    builder = ProjectBuilder(Path(args.file))
    builder.optimization = args.optimize
    builder.debug = args.debug
    success = builder.build_module(args.module)
    return 0 if success else 1

def run_command(args):
    from builder import ProjectBuilder
    import subprocess
    builder = ProjectBuilder(Path(args.file))
    builder.optimization = 'hard'
    builder.debug = False
    success = builder.build()
    if not success:
        return 1
    exe = builder.output_name
    if not exe or not os.path.isfile(exe):
        print(f"Executable not found: {exe}")
        return 1
    return subprocess.call([exe] + args.args)

def clean_command(args):
    build_dir = Path.cwd() / 'build'
    if build_dir.exists():
        shutil.rmtree(build_dir)
        print("Removed build/")
    if args.all:
        for ext in ['.exe', '.obj', '.o', '.a', '.lib']:
            for f in Path.cwd().glob(f'*{ext}'):
                f.unlink()
                print(f"Removed {f}")

def project_command(args):
    project_dir = Path(args.name).resolve()
    if project_dir.exists():
        print(f"Directory {project_dir} already exists.")
        return 1
    project_dir.mkdir(parents=True)
    # manager.json
    manager = {
        "name": args.name,
        "modules": {
            "DictServer": "./modules/DictServer/DictServer.ely"   # было .e
        },
        "enter": "main.ely",                                      # было main.e
        "output": {"enter": {"name": f"{args.name}.exe", "type": "exe"}}
    }
    (project_dir / 'manager.json').write_text(json.dumps(manager, indent=4), encoding='utf-8')

    # main.ely
    (project_dir / 'main.ely').write_text("""public int func main() {
    println("Hello from ely!");
    return 0;
}
""", encoding='utf-8')

    # runtime
    runtime_src = BASE_DIR / 'runtime'
    runtime_dst = project_dir / 'runtime'
    if runtime_src.exists():
        shutil.copytree(runtime_src, runtime_dst)
        print(f"Runtime copied to {runtime_dst}")
    else:
        print("Warning: runtime not found. Copy manually.")
    # Копирование модуля DictServer
    dictserver_src = BASE_DIR / 'runtime' / 'DictServer.e'
    if dictserver_src.exists():
        modules_dir = project_dir / 'modules' / 'DictServer'
        modules_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(dictserver_src, modules_dir / 'DictServer.e')
    print(f"Project created at {project_dir}")
    return 0

def install_compiler_command(args):
    from base_installer import CompilerInstaller
    installer = CompilerInstaller()

    if args.install_command == 'install':
        return installer.install(args.version)
    elif args.install_command == 'remove':
        return installer.remove()
    elif args.install_command == 'list':
        return installer.list_versions()
    elif args.install_command == 'set-path':
        return installer.set_custom_path(args.path)
    else:
        print("Use: ebt install-compiler {install|remove|list|set-path}")
        return 1

def config_command(args):
    from config_manager import ConfigManager
    mgr = ConfigManager(project_root=Path.cwd())
    
    if args.config_command == 'set':
        if args.global_scope:
            mgr.set_global(args.key, args.value)
            print(f"Global config {args.key} = {args.value}")
        elif args.local_scope:
            mgr.set_local(args.key, args.value)
            print(f"Local config {args.key} = {args.value}")
        else:
            # По умолчанию локально
            mgr.set_local(args.key, args.value)
            print(f"Local config {args.key} = {args.value}")
        return 0

    elif args.config_command == 'get':
        merged = mgr.get_merged_config()
        if args.key:
            parts = args.key.split('.')
            val = merged
            for p in parts:
                val = val.get(p, {})
            print(val)
        else:
            print(json.dumps(merged, indent=4))
        return 0

    elif args.config_command == 'list':
        merged = mgr.get_merged_config()
        print("Effective configuration:")
        print(json.dumps(merged, indent=4))
        return 0

    elif args.config_command == 'reset':
        if args.global_scope:
            mgr.reset_global()
            print("Global config reset.")
        elif args.local_scope:
            mgr.reset_local()
            print("Local config reset.")
        else:
            print("Please specify --global or --local.")
            return 1
        return 0

    else:
        print("Unknown config command.")
        return 1

if __name__ == '__main__':
    sys.exit(main())