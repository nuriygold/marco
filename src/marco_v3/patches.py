from __future__ import annotations

import difflib
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .config import MarcoProfile
from .storage import MarcoStorage


@dataclass(frozen=True)
class PatchProposal:
    patch_id: str
    name: str
    target: str
    find_text: str
    replace_text: str
    status: str
    diff: str
    created_at: str
    applied_at: str | None = None
    rollback_at: str | None = None


def _patch_id(name: str, target: str, timestamp: str) -> str:
    return hashlib.sha256(f'{name}:{target}:{timestamp}'.encode('utf-8')).hexdigest()[:12]


def _load(storage: MarcoStorage, patch_id: str) -> PatchProposal:
    path = storage.patches / f'{patch_id}.json'
    data = json.loads(path.read_text())
    return PatchProposal(**data)


def propose_patch(storage: MarcoStorage, root: Path, *, name: str, target: str, find_text: str, replace_text: str) -> PatchProposal:
    created_at = storage.now()
    patch_id = _patch_id(name, target, created_at)
    target_path = root / target
    if not target_path.exists():
        raise FileNotFoundError(f'Target file does not exist: {target}')

    original = target_path.read_text()
    if find_text not in original:
        raise ValueError('find_text was not found in target file')
    updated = original.replace(find_text, replace_text, 1)
    diff = ''.join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            updated.splitlines(keepends=True),
            fromfile=target,
            tofile=target,
        )
    )
    proposal = PatchProposal(
        patch_id=patch_id,
        name=name,
        target=target,
        find_text=find_text,
        replace_text=replace_text,
        status='pending',
        diff=diff,
        created_at=created_at,
    )
    storage.write_json(storage.patches / f'{patch_id}.json', proposal.__dict__)
    return proposal


def list_patches(storage: MarcoStorage) -> list[PatchProposal]:
    patches: list[PatchProposal] = []
    for path in sorted(storage.patches.glob('*.json')):
        data = json.loads(path.read_text())
        patches.append(PatchProposal(**data))
    return patches


def show_patch(storage: MarcoStorage, patch_id: str) -> PatchProposal:
    return _load(storage, patch_id)


def apply_patch(storage: MarcoStorage, root: Path, profile: MarcoProfile, patch_id: str, *, force: bool = False) -> PatchProposal:
    proposal = _load(storage, patch_id)
    if proposal.status == 'applied':
        return proposal
    if profile.safety_mode == 'read-only':
        raise PermissionError('cannot apply patch in read-only safety mode')
    if profile.pause_before_mutation and not force:
        raise PermissionError('apply requires explicit confirmation (--yes) under current profile')

    target_path = root / proposal.target
    original = target_path.read_text()
    if proposal.find_text not in original:
        raise ValueError('Cannot apply patch; target text is no longer present')

    checkpoint_dir = storage.checkpoints / patch_id
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = checkpoint_dir / Path(proposal.target).name
    checkpoint_path.write_text(original)

    updated = original.replace(proposal.find_text, proposal.replace_text, 1)
    target_path.write_text(updated)

    applied = PatchProposal(**{**proposal.__dict__, 'status': 'applied', 'applied_at': storage.now()})
    storage.write_json(storage.patches / f'{patch_id}.json', applied.__dict__)
    return applied


def rollback_patch(storage: MarcoStorage, root: Path, patch_id: str) -> PatchProposal:
    proposal = _load(storage, patch_id)
    checkpoint_dir = storage.checkpoints / patch_id
    checkpoint_path = checkpoint_dir / Path(proposal.target).name
    if not checkpoint_path.exists():
        raise FileNotFoundError(f'No checkpoint found for patch {patch_id}')
    (root / proposal.target).write_text(checkpoint_path.read_text())
    rolled_back = PatchProposal(**{**proposal.__dict__, 'status': 'rolled_back', 'rollback_at': storage.now()})
    storage.write_json(storage.patches / f'{patch_id}.json', rolled_back.__dict__)
    return rolled_back
