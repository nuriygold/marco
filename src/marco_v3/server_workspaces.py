"""Workspace registry for the Marco server.

Stores a list of repo paths in ``~/.marco/workspaces.json`` so the UI can
switch between them. Marco's own repo is a normal selectable entry — not a
hidden default.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


REGISTRY_PATH = Path.home() / '.marco' / 'workspaces.json'


@dataclass(frozen=True)
class Workspace:
    name: str
    path: str
    added: str


@dataclass(frozen=True)
class Registry:
    active: str | None
    workspaces: list[Workspace]


def _default_registry() -> Registry:
    return Registry(active=None, workspaces=[])


def load_registry(path: Path = REGISTRY_PATH) -> Registry:
    if not path.exists():
        return _default_registry()
    data = json.loads(path.read_text())
    workspaces = [Workspace(**entry) for entry in data.get('workspaces', [])]
    return Registry(active=data.get('active'), workspaces=workspaces)


def save_registry(registry: Registry, path: Path = REGISTRY_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'active': registry.active,
        'workspaces': [asdict(ws) for ws in registry.workspaces],
    }
    path.write_text(json.dumps(payload, indent=2))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_name(name: str) -> str:
    safe = ''.join(ch if ch.isalnum() or ch in '-_' else '-' for ch in name.strip())
    return safe.strip('-') or 'workspace'


def add_workspace(name: str, path: Path, registry_path: Path = REGISTRY_PATH) -> Workspace:
    registry = load_registry(registry_path)
    resolved = path.expanduser().resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise ValueError(f'Workspace path does not exist or is not a directory: {resolved}')
    clean_name = _normalize_name(name)
    for ws in registry.workspaces:
        if ws.name == clean_name:
            raise ValueError(f'Workspace name already registered: {clean_name}')
        if Path(ws.path) == resolved:
            raise ValueError(f'Workspace path already registered as {ws.name!r}: {resolved}')
    ws = Workspace(name=clean_name, path=str(resolved), added=_now())
    updated = Registry(
        active=registry.active or clean_name,
        workspaces=[*registry.workspaces, ws],
    )
    save_registry(updated, registry_path)
    return ws


def remove_workspace(name: str, registry_path: Path = REGISTRY_PATH) -> bool:
    registry = load_registry(registry_path)
    remaining = [ws for ws in registry.workspaces if ws.name != name]
    if len(remaining) == len(registry.workspaces):
        return False
    new_active = registry.active if registry.active != name else (remaining[0].name if remaining else None)
    save_registry(Registry(active=new_active, workspaces=remaining), registry_path)
    return True


def set_active(name: str, registry_path: Path = REGISTRY_PATH) -> Workspace:
    registry = load_registry(registry_path)
    for ws in registry.workspaces:
        if ws.name == name:
            save_registry(Registry(active=name, workspaces=registry.workspaces), registry_path)
            return ws
    raise KeyError(f'Unknown workspace: {name}')


def get_active(registry_path: Path = REGISTRY_PATH) -> Workspace | None:
    registry = load_registry(registry_path)
    if registry.active is None:
        return None
    for ws in registry.workspaces:
        if ws.name == registry.active:
            return ws
    return None


def ensure_workspace_from_cwd(registry_path: Path = REGISTRY_PATH) -> Workspace | None:
    """Auto-register CWD as a workspace if nothing is registered yet."""
    registry = load_registry(registry_path)
    if registry.workspaces:
        return get_active(registry_path)
    cwd = Path(os.getcwd())
    if not (cwd / '.git').exists():
        return None
    return add_workspace(cwd.name, cwd, registry_path)
