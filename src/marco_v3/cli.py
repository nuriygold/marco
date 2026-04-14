from __future__ import annotations

import argparse
import json
import shlex
import subprocess
from pathlib import Path
from typing import Any

from .autonomy import create_plan, execute_plan, list_sessions, recover_session, resume_session, validate_session
from .config import ensure_profile, load_profile
from .extensions import default_schedules, default_subagents
from .memory import add_entry, list_entries, recall, remember
from .patches import apply_patch, list_patches, propose_patch, rollback_patch, show_patch
from .repo_intel import (
    architecture_map,
    config_map,
    discover_env_vars,
    discover_routes,
    discover_scripts,
    find_files,
    generate_file_map,
    integration_map,
    lookup_content,
    render_tree,
    scan_repository,
    where_edit,
)
from .scaffold import scaffold_component, scaffold_page, scaffold_route, scaffold_service
from .storage import MarcoStorage


V3_COMMANDS = {
    'doctor',
    'status',
    'summary',
    'manifest',
    'inspect',
    'plan',
    'execute',
    'validate',
    'recover',
    'sessions',
    'resume',
    'find',
    'lookup',
    'routes',
    'env',
    'scripts',
    'run-script',
    'script-info',
    'tree',
    'note',
    'notes',
    'remember',
    'recall',
    'decision',
    'decisions',
    'convention',
    'conventions',
    'propose-patch',
    'show-patch',
    'apply-patch',
    'rollback-patch',
    'list-patches',
    'scaffold',
    'repl',
}


def register_v3_parsers(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    doctor = subparsers.add_parser('doctor', help='run Marco v3 environment checks')
    doctor.add_argument('--json', action='store_true')

    status = subparsers.add_parser('status', help='render repo-aware status')
    status.add_argument('--json', action='store_true')

    inspect = subparsers.add_parser('inspect', help='build repo intelligence maps')
    inspect.add_argument('--query', default='')
    inspect.add_argument('--json', action='store_true')

    plan = subparsers.add_parser('plan', help='create an autonomous session plan')
    plan.add_argument('goal')
    plan.add_argument('--json', action='store_true')

    execute = subparsers.add_parser('execute', help='mark a session as executing')
    execute.add_argument('session_id')
    execute.add_argument('--json', action='store_true')

    validate = subparsers.add_parser('validate', help='run validation loop for a session')
    validate.add_argument('session_id')
    validate.add_argument('--json', action='store_true')

    recover = subparsers.add_parser('recover', help='run recovery loop for a session')
    recover.add_argument('session_id')
    recover.add_argument('--json', action='store_true')

    sessions = subparsers.add_parser('sessions', help='list Marco v3 session artifacts')
    sessions.add_argument('--json', action='store_true')

    resume = subparsers.add_parser('resume', help='resume a stored Marco v3 session')
    resume.add_argument('session_id')
    resume.add_argument('--json', action='store_true')

    find = subparsers.add_parser('find', help='find files by glob pattern')
    find.add_argument('pattern')
    find.add_argument('--limit', type=int, default=50)
    find.add_argument('--json', action='store_true')

    lookup = subparsers.add_parser('lookup', help='lookup content matches in repository files')
    lookup.add_argument('needle')
    lookup.add_argument('--limit', type=int, default=50)
    lookup.add_argument('--json', action='store_true')

    routes = subparsers.add_parser('routes', help='discover route candidates in repository')
    routes.add_argument('--limit', type=int, default=100)
    routes.add_argument('--json', action='store_true')

    env = subparsers.add_parser('env', help='discover environment variable references')
    env.add_argument('--limit', type=int, default=200)
    env.add_argument('--json', action='store_true')

    scripts = subparsers.add_parser('scripts', help='discover runnable scripts and targets')
    scripts.add_argument('--json', action='store_true')

    run_script = subparsers.add_parser('run-script', help='run a discovered script or show dry-run')
    run_script.add_argument('name')
    run_script.add_argument('--execute', action='store_true')

    script_info = subparsers.add_parser('script-info', help='show metadata for one script')
    script_info.add_argument('name')
    script_info.add_argument('--json', action='store_true')

    tree = subparsers.add_parser('tree', help='render lightweight workspace tree')
    tree.add_argument('--depth', type=int, default=3)

    note = subparsers.add_parser('note', help='save a technical notebook note')
    note.add_argument('key')
    note.add_argument('topic')
    note.add_argument('text')

    notes = subparsers.add_parser('notes', help='list saved notes')
    notes.add_argument('--limit', type=int, default=50)
    notes.add_argument('--json', action='store_true')

    remember_parser = subparsers.add_parser('remember', help='alias for note command')
    remember_parser.add_argument('key')
    remember_parser.add_argument('topic')
    remember_parser.add_argument('text')

    recall_parser = subparsers.add_parser('recall', help='recall notes/decisions/conventions by fuzzy query')
    recall_parser.add_argument('query')
    recall_parser.add_argument('--limit', type=int, default=20)
    recall_parser.add_argument('--json', action='store_true')

    decision = subparsers.add_parser('decision', help='store a technical decision')
    decision.add_argument('key')
    decision.add_argument('topic')
    decision.add_argument('text')

    decisions = subparsers.add_parser('decisions', help='list stored decisions')
    decisions.add_argument('--limit', type=int, default=50)
    decisions.add_argument('--json', action='store_true')

    convention = subparsers.add_parser('convention', help='store a coding convention')
    convention.add_argument('key')
    convention.add_argument('topic')
    convention.add_argument('text')

    conventions = subparsers.add_parser('conventions', help='list stored conventions')
    conventions.add_argument('--limit', type=int, default=50)
    conventions.add_argument('--json', action='store_true')

    propose = subparsers.add_parser('propose-patch', help='propose a staged patch')
    propose.add_argument('--name', required=True)
    propose.add_argument('--target', required=True)
    propose.add_argument('--find', required=True)
    propose.add_argument('--replace', required=True)

    show = subparsers.add_parser('show-patch', help='show a staged patch diff')
    show.add_argument('patch_id')

    apply = subparsers.add_parser('apply-patch', help='apply a staged patch with checkpoint safety')
    apply.add_argument('patch_id')
    apply.add_argument('--yes', action='store_true')

    rollback = subparsers.add_parser('rollback-patch', help='rollback an applied patch from checkpoint')
    rollback.add_argument('patch_id')

    list_patch = subparsers.add_parser('list-patches', help='list patch sessions')
    list_patch.add_argument('--json', action='store_true')

    scaffold = subparsers.add_parser('scaffold', help='scaffold common code structures')
    scaffold_sub = scaffold.add_subparsers(dest='scaffold_kind', required=True)
    for kind in ('page', 'component', 'route', 'service'):
        p = scaffold_sub.add_parser(kind, help=f'scaffold {kind}')
        p.add_argument('name')

    repl = subparsers.add_parser('repl', help='interactive slash-command operator shell')
    repl.add_argument('--once', help='run one slash command and exit')


def _print(payload: Any, as_json: bool = False) -> None:
    if as_json:
        print(json.dumps(payload, indent=2))
        return
    if isinstance(payload, str):
        print(payload)
        return
    print(json.dumps(payload, indent=2))


def run_v3_command(args: argparse.Namespace, cwd: Path | None = None) -> int | None:
    if args.command not in V3_COMMANDS:
        return None

    root = cwd or Path.cwd()
    storage = MarcoStorage(root)
    ensure_profile(root)
    profile = load_profile(root)

    if args.command == 'doctor':
        report = {
            'ok': True,
            'cwd': str(root),
            'safety_mode': profile.safety_mode,
            'pause_before_mutation': profile.pause_before_mutation,
            'python_version': subprocess.run('python3 --version', shell=True, capture_output=True, text=True).stdout.strip(),
            'git_available': subprocess.run('git --version', shell=True, capture_output=True, text=True).returncode == 0,
            'profile_path': str((root / '.marco/config.json')),
        }
        _print(report, as_json=getattr(args, 'json', False))
        return 0

    if args.command == 'status':
        scan = scan_repository(root)
        report = {
            'repo': scan.root,
            'file_count': scan.file_count,
            'total_bytes': scan.total_bytes,
            'top_extensions': dict(list(scan.by_extension.items())[:8]),
            'pending_patches': len([p for p in list_patches(storage) if p.status == 'pending']),
            'sessions': len(list_sessions(storage)),
            'safety_mode': profile.safety_mode,
        }
        _print(report, as_json=getattr(args, 'json', False))
        return 0

    if args.command == 'summary':
        scan = scan_repository(root)
        payload = {
            'title': 'Python Porting Workspace Summary (Marco v3)',
            'repo': str(root),
            'file_count': scan.file_count,
            'top_extensions': dict(list(scan.by_extension.items())[:5]),
            'session_count': len(list_sessions(storage)),
            'pending_patches': len([p for p in list_patches(storage) if p.status == 'pending']),
            'memory_counts': {
                'notes': len(list_entries(storage, 'note')),
                'decisions': len(list_entries(storage, 'decision')),
                'conventions': len(list_entries(storage, 'convention')),
            },
        }
        if getattr(args, 'json', False):
            print(json.dumps(payload, indent=2))
        else:
            print(payload['title'])
            print(f"Repo: {payload['repo']}")
            print(f"Files: {payload['file_count']}")
            print(f"Pending patches: {payload['pending_patches']}")
            print(f"Sessions: {payload['session_count']}")
            print('Top extensions:')
            for ext, count in payload['top_extensions'].items():
                print(f'- {ext}: {count}')
            print('Command surface: Marco v3 operator commands')
            print('Tool surface: repo intel, patch safety, memory notebook, scaffold')
        return 0

    if args.command == 'manifest':
        payload = {
            'file_map': generate_file_map(root, limit=50),
            'architecture': architecture_map(root),
            'config': config_map(root),
            'integration': integration_map(root),
            'extensions': {
                'sub_agents': [hook.__dict__ for hook in default_subagents()],
                'schedules': [hook.__dict__ for hook in default_schedules()],
            },
        }
        _print(payload, as_json=True)
        return 0

    if args.command == 'inspect':
        payload = {
            'scan': scan_repository(root).__dict__,
            'file_map': generate_file_map(root, limit=40),
            'architecture': architecture_map(root),
            'config_map': config_map(root),
            'integration_map': integration_map(root),
            'where_edit': where_edit(root, args.query, limit=10) if args.query else [],
        }
        _print(payload, as_json=getattr(args, 'json', False) or True)
        return 0

    if args.command == 'plan':
        artifact = create_plan(root, storage, args.goal)
        _print(artifact.__dict__, as_json=True)
        return 0

    if args.command == 'execute':
        artifact = execute_plan(storage, args.session_id)
        _print(artifact.__dict__, as_json=True)
        return 0

    if args.command == 'validate':
        artifact = validate_session(root, storage, profile, args.session_id)
        _print(artifact.__dict__, as_json=True)
        return 0

    if args.command == 'recover':
        artifact = recover_session(storage, args.session_id)
        _print(artifact.__dict__, as_json=True)
        return 0

    if args.command == 'sessions':
        _print([entry.__dict__ for entry in list_sessions(storage)], as_json=True)
        return 0

    if args.command == 'resume':
        _print(resume_session(storage, args.session_id).__dict__, as_json=True)
        return 0

    if args.command == 'find':
        _print({'matches': find_files(root, args.pattern, limit=args.limit)}, as_json=getattr(args, 'json', False) or True)
        return 0

    if args.command == 'lookup':
        _print({'matches': lookup_content(root, args.needle, limit=args.limit)}, as_json=getattr(args, 'json', False) or True)
        return 0

    if args.command == 'routes':
        _print({'routes': [entry.__dict__ for entry in discover_routes(root, limit=args.limit)]}, as_json=getattr(args, 'json', False) or True)
        return 0

    if args.command == 'env':
        _print({'env_vars': discover_env_vars(root, limit=args.limit)}, as_json=getattr(args, 'json', False) or True)
        return 0

    if args.command == 'scripts':
        _print({'scripts': [entry.__dict__ for entry in discover_scripts(root)]}, as_json=getattr(args, 'json', False) or True)
        return 0

    if args.command == 'run-script':
        scripts = {entry.name: entry for entry in discover_scripts(root)}
        entry = scripts.get(args.name)
        if entry is None:
            print(f'Script not found: {args.name}')
            return 1
        if not args.execute:
            print(f"[DRY_RUN] {entry.command}")
            return 0
        proc = subprocess.run(entry.command, cwd=root, shell=True)
        return proc.returncode

    if args.command == 'script-info':
        scripts = {entry.name: entry for entry in discover_scripts(root)}
        entry = scripts.get(args.name)
        if entry is None:
            print(f'Script not found: {args.name}')
            return 1
        _print(entry.__dict__, as_json=getattr(args, 'json', False) or True)
        return 0

    if args.command == 'tree':
        for line in render_tree(root, max_depth=args.depth):
            print(line)
        return 0

    if args.command == 'note':
        entry = add_entry(storage, kind='note', key=args.key, topic=args.topic, text=args.text)
        _print(entry.__dict__, as_json=True)
        return 0

    if args.command == 'notes':
        _print([entry.__dict__ for entry in list_entries(storage, 'note', limit=args.limit)], as_json=getattr(args, 'json', False) or True)
        return 0

    if args.command == 'remember':
        _print(remember(storage, args.key, args.topic, args.text).__dict__, as_json=True)
        return 0

    if args.command == 'recall':
        _print([entry.__dict__ for entry in recall(storage, args.query, limit=args.limit)], as_json=getattr(args, 'json', False) or True)
        return 0

    if args.command == 'decision':
        _print(add_entry(storage, kind='decision', key=args.key, topic=args.topic, text=args.text).__dict__, as_json=True)
        return 0

    if args.command == 'decisions':
        _print([entry.__dict__ for entry in list_entries(storage, 'decision', limit=args.limit)], as_json=getattr(args, 'json', False) or True)
        return 0

    if args.command == 'convention':
        _print(add_entry(storage, kind='convention', key=args.key, topic=args.topic, text=args.text).__dict__, as_json=True)
        return 0

    if args.command == 'conventions':
        _print([entry.__dict__ for entry in list_entries(storage, 'convention', limit=args.limit)], as_json=getattr(args, 'json', False) or True)
        return 0

    if args.command == 'propose-patch':
        proposal = propose_patch(storage, root, name=args.name, target=args.target, find_text=args.find, replace_text=args.replace)
        _print(proposal.__dict__, as_json=True)
        return 0

    if args.command == 'show-patch':
        proposal = show_patch(storage, args.patch_id)
        print(proposal.diff)
        return 0

    if args.command == 'apply-patch':
        proposal = apply_patch(storage, root, profile, args.patch_id, force=args.yes)
        _print(proposal.__dict__, as_json=True)
        return 0

    if args.command == 'rollback-patch':
        proposal = rollback_patch(storage, root, args.patch_id)
        _print(proposal.__dict__, as_json=True)
        return 0

    if args.command == 'list-patches':
        _print([proposal.__dict__ for proposal in list_patches(storage)], as_json=getattr(args, 'json', False) or True)
        return 0

    if args.command == 'scaffold':
        if args.scaffold_kind == 'page':
            result = scaffold_page(root, args.name)
        elif args.scaffold_kind == 'component':
            result = scaffold_component(root, args.name)
        elif args.scaffold_kind == 'route':
            result = scaffold_route(root, args.name)
        else:
            result = scaffold_service(root, args.name)
        _print(result.__dict__, as_json=True)
        return 0

    if args.command == 'repl':
        return _run_repl(root, args.once)

    return None


def _run_repl(root: Path, once: str | None) -> int:
    banner = 'Marco v3 REPL (slash commands). Example: /status or /inspect --query routes'
    if once:
        command_line = once.strip()
        return _run_repl_command(command_line, root)

    print(banner)
    while True:
        try:
            line = input('marco> ').strip()
        except EOFError:
            print()
            return 0
        if not line:
            continue
        if line in {'exit', 'quit', '/exit', '/quit'}:
            return 0
        code = _run_repl_command(line, root)
        if code != 0:
            print(f'error={code}')


def _run_repl_command(line: str, root: Path) -> int:
    raw = line[1:] if line.startswith('/') else line
    argv = shlex.split(raw)
    if not argv:
        return 0
    parser = argparse.ArgumentParser(prog='marco repl', add_help=False)
    subparsers = parser.add_subparsers(dest='command', required=True)
    register_v3_parsers(subparsers)
    args = parser.parse_args(argv)
    result = run_v3_command(args, cwd=root)
    return 0 if result is None else result
