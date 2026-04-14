from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class ScaffoldResult:
    kind: str
    name: str
    path: str
    created: bool


def _to_pascal_case(name: str) -> str:
    if not re.match(r'^[a-zA-Z][a-zA-Z0-9_-]*$', name):
        raise ValueError(f'invalid scaffold name: {name}')
    if name[0] in {'-', '_'} or name[-1] in {'-', '_'} or '__' in name or '--' in name or '_-' in name or '-_' in name:
        raise ValueError(f'invalid scaffold separator usage: {name}')
    return ''.join(part.capitalize() for part in name.replace('-', '_').split('_') if part)


def detect_convention_root(root: Path) -> Path:
    for candidate in ('src', 'app', 'services'):
        path = root / candidate
        if path.exists() and path.is_dir():
            return path
    return root


def _write(path: Path, content: str) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return True


def scaffold_page(root: Path, name: str) -> ScaffoldResult:
    base = detect_convention_root(root)
    path = base / 'pages' / f'{name}.py'
    created = _write(path, f'def render_{name}() -> str:\n    return "{name} page"\n')
    return ScaffoldResult(kind='page', name=name, path=str(path.relative_to(root)), created=created)


def scaffold_component(root: Path, name: str) -> ScaffoldResult:
    base = detect_convention_root(root)
    path = base / 'components' / f'{name}.py'
    created = _write(path, f'class {_to_pascal_case(name)}:\n    def render(self) -> str:\n        return "{name} component"\n')
    return ScaffoldResult(kind='component', name=name, path=str(path.relative_to(root)), created=created)


def scaffold_route(root: Path, name: str) -> ScaffoldResult:
    base = detect_convention_root(root)
    path = base / 'routes' / f'{name}_route.py'
    created = _write(path, f'def register_{name}_route() -> dict[str, str]:\n    return {{"path": "/{name}", "handler": "{name}"}}\n')
    return ScaffoldResult(kind='route', name=name, path=str(path.relative_to(root)), created=created)


def scaffold_service(root: Path, name: str) -> ScaffoldResult:
    base = detect_convention_root(root)
    path = base / 'services' / f'{name}_service.py'
    created = _write(path, f'class {_to_pascal_case(name)}Service:\n    def run(self) -> str:\n        return "{name} service"\n')
    return ScaffoldResult(kind='service', name=name, path=str(path.relative_to(root)), created=created)
