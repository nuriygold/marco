from __future__ import annotations

import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
import shlex

from .config import ALLOWED_SCRIPT_PREFIXES, SHELL_META, MarcoProfile
from .repo_intel import discover_scripts, where_edit
from .storage import MarcoStorage


@dataclass(frozen=True)
class SessionArtifact:
    session_id: str
    goal: str
    phase: str
    status: str
    artifacts: dict[str, object]
    created_at: str


def _new_session_id() -> str:
    return uuid.uuid4().hex[:12]


def create_plan(root: Path, storage: MarcoStorage, goal: str) -> SessionArtifact:
    edits = where_edit(root, goal, limit=5)
    steps = [
        'Inspect repo and constraints',
        'Identify edit targets',
        'Implement scoped changes',
        'Validate with existing scripts/tests',
        'Prepare rollback and recovery notes',
    ]
    artifact = SessionArtifact(
        session_id=_new_session_id(),
        goal=goal,
        phase='plan',
        status='ready',
        artifacts={'steps': steps, 'where_edit': edits},
        created_at=storage.now(),
    )
    storage.write_json(storage.sessions / f'{artifact.session_id}.json', artifact.__dict__)
    return artifact


def execute_plan(storage: MarcoStorage, session_id: str) -> SessionArtifact:
    data = storage.read_json(storage.sessions / f'{session_id}.json')
    artifact = SessionArtifact(
        session_id=session_id,
        goal=data['goal'],
        phase='execute',
        status='running',
        artifacts={'actions': ['session marked executing'], 'origin_phase': data['phase']},
        created_at=storage.now(),
    )
    storage.write_json(storage.sessions / f'{session_id}.json', artifact.__dict__)
    return artifact


def validate_session(root: Path, storage: MarcoStorage, profile: MarcoProfile, session_id: str) -> SessionArtifact:
    scripts = discover_scripts(root)
    test_script = next((item.command for item in scripts if 'test' in item.name.lower()), profile.default_test_command)
    if any(token in test_script for token in SHELL_META) and profile.safety_mode != 'danger-full-access':
        process = subprocess.CompletedProcess(args=test_script, returncode=1, stdout='', stderr='blocked unsafe shell metacharacters')
    else:
        parsed = shlex.split(test_script)
        if not parsed:
            process = subprocess.CompletedProcess(args=test_script, returncode=1, stdout='', stderr='empty validation command')
        elif profile.safety_mode != 'danger-full-access' and parsed[0] not in ALLOWED_SCRIPT_PREFIXES:
            process = subprocess.CompletedProcess(args=test_script, returncode=1, stdout='', stderr='blocked command prefix for safety mode')
        else:
            process = subprocess.run(parsed, cwd=root, shell=False, text=True, capture_output=True)
    artifact = SessionArtifact(
        session_id=session_id,
        goal=storage.read_json(storage.sessions / f'{session_id}.json').get('goal', ''),
        phase='validate',
        status='passed' if process.returncode == 0 else 'failed',
        artifacts={
            'command': test_script,
            'returncode': process.returncode,
            'stdout_tail': (process.stdout or '').splitlines()[-20:],
            'stderr_tail': (process.stderr or '').splitlines()[-20:],
        },
        created_at=storage.now(),
    )
    storage.write_json(storage.sessions / f'{session_id}.json', artifact.__dict__)
    return artifact


def recover_session(storage: MarcoStorage, session_id: str) -> SessionArtifact:
    current = storage.read_json(storage.sessions / f'{session_id}.json')
    artifact = SessionArtifact(
        session_id=session_id,
        goal=current.get('goal', ''),
        phase='recover',
        status='ready',
        artifacts={
            'recovery_steps': [
                'Review latest failed validation output',
                'Rollback pending patch if necessary',
                'Resume with focused patch plan',
            ],
            'previous_phase': current.get('phase'),
            'previous_status': current.get('status'),
        },
        created_at=storage.now(),
    )
    storage.write_json(storage.sessions / f'{session_id}.json', artifact.__dict__)
    return artifact


def list_sessions(storage: MarcoStorage) -> list[SessionArtifact]:
    entries: list[SessionArtifact] = []
    for path in sorted(storage.sessions.glob('*.json')):
        data = storage.read_json(path)
        entries.append(SessionArtifact(**data))
    return entries


def resume_session(storage: MarcoStorage, session_id: str) -> SessionArtifact:
    data = storage.read_json(storage.sessions / f'{session_id}.json')
    return SessionArtifact(**data)
