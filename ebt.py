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
    return 0

def build_command(args):
    from builder import ProjectBuilder
    builder = ProjectBuilder(Path(args.file))
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
        "modules": {},
        "enter": "main.e",
        "output": {"enter": {"name": f"{args.name}.exe", "type": "exe"}}
    }
    (project_dir / 'manager.json').write_text(json.dumps(manager, indent=4), encoding='utf-8')
    # main.e
    (project_dir / 'main.e').write_text("""public int func main() {
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

if __name__ == '__main__':
    sys.exit(main())