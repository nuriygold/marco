from __future__ import annotations

import fnmatch
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

IGNORE_DIRS = {'.git', '.marco', '__pycache__', '.venv', 'node_modules', 'target'}
ROUTE_FILE_PATTERNS = ('*route*', '*router*', '*routes*', '*urls.py', '*app.py')
TEXT_EXTENSIONS = {'.py', '.ts', '.tsx', '.js', '.jsx', '.go', '.rs', '.java', '.kt', '.yml', '.yaml', '.json', '.toml', '.env', '.md'}
ENV_PATTERNS = [
    re.compile(r"os\.environ\[['\"]([A-Za-z0-9_]+)['\"]\]"),
    re.compile(r"os\.getenv\(['\"]([A-Za-z0-9_]+)['\"]"),
    re.compile(r"process\.env\.([A-Za-z0-9_]+)"),
    re.compile(r"import\.meta\.env\.([A-Za-z0-9_]+)"),
    re.compile(r"\$\{([A-Za-z][A-Za-z0-9_]*)\}"),
]


@dataclass(frozen=True)
class RepoScan:
    root: str
    file_count: int
    total_bytes: int
    by_extension: dict[str, int]
    top_dirs: dict[str, int]


@dataclass(frozen=True)
class ScriptEntry:
    name: str
    command: str
    source: str


@dataclass(frozen=True)
class RouteEntry:
    file: str
    hint: str


def _iter_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob('*'):
        if not path.is_file():
            continue
        if any(part in IGNORE_DIRS for part in path.parts):
            continue
        files.append(path)
    return files


def scan_repository(root: Path) -> RepoScan:
    files = _iter_files(root)
    by_extension: Counter[str] = Counter(path.suffix or '<none>' for path in files)
    top_dirs: Counter[str] = Counter(path.relative_to(root).parts[0] if path.relative_to(root).parts else '.' for path in files)
    return RepoScan(
        root=str(root),
        file_count=len(files),
        total_bytes=sum(path.stat().st_size for path in files),
        by_extension=dict(by_extension.most_common()),
        top_dirs=dict(top_dirs.most_common()),
    )


def generate_file_map(root: Path, limit: int = 200) -> dict[str, list[str]]:
    grouped: defaultdict[str, list[str]] = defaultdict(list)
    for path in _iter_files(root):
        grouped[path.suffix or '<none>'].append(str(path.relative_to(root)))
    for suffix in list(grouped):
        grouped[suffix] = sorted(grouped[suffix])[:limit]
    return dict(grouped)


def architecture_map(root: Path) -> dict[str, object]:
    scan = scan_repository(root)
    return {
        'top_level': scan.top_dirs,
        'largest_extensions': dict(list(scan.by_extension.items())[:10]),
        'entry_points': [
            p for p in ('src/main.py', 'README.md', 'package.json', 'pyproject.toml', 'rust/Cargo.toml') if (root / p).exists()
        ],
    }


def config_map(root: Path) -> dict[str, list[str]]:
    patterns = ['**/package.json', '**/pyproject.toml', '**/Cargo.toml', '**/*.yaml', '**/*.yml', '**/.env*', '**/Makefile']
    found: list[str] = []
    for pattern in patterns:
        for path in root.glob(pattern):
            if path.is_file() and not any(part in IGNORE_DIRS for part in path.parts):
                found.append(str(path.relative_to(root)))
    return {'configs': sorted(set(found))}


def integration_map(root: Path, limit: int = 200) -> dict[str, list[str]]:
    env_refs = discover_env_vars(root, limit=limit)
    route_refs = discover_routes(root, limit=limit)
    scripts = discover_scripts(root)
    return {
        'env_vars': sorted(env_refs.keys()),
        'routes': [entry.file for entry in route_refs],
        'scripts': [entry.name for entry in scripts],
    }


def where_edit(root: Path, query: str, limit: int = 10) -> list[str]:
    tokens = [token.lower() for token in re.split(r'\W+', query) if token]
    if not tokens:
        return []
    scored: list[tuple[int, str]] = []
    for path in _iter_files(root):
        rel = str(path.relative_to(root)).lower()
        score = sum(1 for token in tokens if token in rel)
        if score:
            scored.append((score, str(path.relative_to(root))))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [path for _, path in scored[:limit]]


def find_files(root: Path, pattern: str, limit: int = 50) -> list[str]:
    matches: list[str] = []
    for path in _iter_files(root):
        rel = str(path.relative_to(root))
        if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(path.name, pattern):
            matches.append(rel)
        if len(matches) >= limit:
            break
    return matches


def lookup_content(root: Path, needle: str, limit: int = 50) -> list[dict[str, object]]:
    matches: list[dict[str, object]] = []
    for path in _iter_files(root):
        if path.suffix not in TEXT_EXTENSIONS and path.suffix:
            continue
        try:
            for idx, line in enumerate(path.read_text(errors='ignore').splitlines(), start=1):
                if needle.lower() in line.lower():
                    matches.append({'file': str(path.relative_to(root)), 'line': idx, 'text': line.strip()[:200]})
                    if len(matches) >= limit:
                        return matches
        except OSError:
            continue
    return matches


def discover_routes(root: Path, limit: int = 100) -> list[RouteEntry]:
    hits: list[RouteEntry] = []
    for path in _iter_files(root):
        rel = str(path.relative_to(root))
        name = path.name.lower()
        if any(fnmatch.fnmatch(name, pattern) for pattern in ROUTE_FILE_PATTERNS):
            hint = 'route-like filename'
            hits.append(RouteEntry(file=rel, hint=hint))
            continue
        if path.suffix in {'.py', '.ts', '.tsx', '.js', '.jsx'}:
            content = path.read_text(errors='ignore')
            if 'router' in content or 'app.get(' in content or '@app.route' in content or 'Route(' in content:
                hits.append(RouteEntry(file=rel, hint='route symbols in file content'))
        if len(hits) >= limit:
            break
    return hits


def discover_env_vars(root: Path, limit: int = 200) -> dict[str, list[str]]:
    found: defaultdict[str, list[str]] = defaultdict(list)
    for path in _iter_files(root):
        if path.suffix not in TEXT_EXTENSIONS and path.suffix:
            continue
        content = path.read_text(errors='ignore')
        rel = str(path.relative_to(root))
        for pattern in ENV_PATTERNS:
            for match in pattern.findall(content):
                if isinstance(match, str):
                    key = match
                elif isinstance(match, tuple) and match:
                    key = match[0]
                else:
                    continue
                if rel not in found[key]:
                    found[key].append(rel)
                if len(found) >= limit:
                    return dict(found)
    return dict(found)


def discover_scripts(root: Path) -> list[ScriptEntry]:
    scripts: list[ScriptEntry] = []
    package_json = root / 'package.json'
    if package_json.exists():
        import json

        data = json.loads(package_json.read_text())
        for name, command in (data.get('scripts') or {}).items():
            scripts.append(ScriptEntry(name=name, command=str(command), source='package.json'))

    makefile = root / 'Makefile'
    if makefile.exists():
        for line in makefile.read_text(errors='ignore').splitlines():
            if ':' in line and not line.startswith(('\t', '#')):
                target = line.split(':', 1)[0].strip()
                if target and ' ' not in target:
                    scripts.append(ScriptEntry(name=target, command=f'make {target}', source='Makefile'))

    pyproject = root / 'pyproject.toml'
    if pyproject.exists():
        text = pyproject.read_text(errors='ignore')
        in_section = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped == '[project.scripts]':
                in_section = True
                continue
            if in_section and stripped.startswith('['):
                break
            if in_section and '=' in stripped:
                name, target = stripped.split('=', 1)
                target_ref = target.strip().strip("\"'")
                if ':' in target_ref:
                    module_name, callable_name = target_ref.split(':', 1)
                    safe_ref = re.compile(r'^[A-Za-z_][A-Za-z0-9_.]*$')
                    if not safe_ref.match(module_name) or not safe_ref.match(callable_name):
                        continue
                    command = f'python -c "from {module_name} import {callable_name} as _entry; _entry()"'
                else:
                    command = f'python -m {target_ref}'
                scripts.append(ScriptEntry(name=name.strip(), command=command, source='pyproject.toml'))

    unique: dict[tuple[str, str], ScriptEntry] = {}
    for item in scripts:
        unique[(item.name, item.source)] = item
    return sorted(unique.values(), key=lambda x: (x.name, x.source))


def render_tree(root: Path, max_depth: int = 3, max_entries: int = 200) -> list[str]:
    lines: list[str] = [str(root)]
    count = 0
    for path in sorted(root.rglob('*')):
        if any(part in IGNORE_DIRS for part in path.parts):
            continue
        rel = path.relative_to(root)
        depth = len(rel.parts)
        if depth > max_depth:
            continue
        indent = '  ' * (depth - 1)
        marker = '📄' if path.is_file() else '📁'
        lines.append(f'{indent}{marker} {rel.name}')
        count += 1
        if count >= max_entries:
            lines.append('… truncated …')
            break
    return lines
