from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


DEFAULT_CONFIG_PATH = Path('.marco/config.json')


@dataclass(frozen=True)
class MarcoProfile:
    name: str = 'default'
    safety_mode: str = 'workspace-write'
    pause_before_mutation: bool = True
    default_test_command: str = 'python3 -m unittest discover -s tests -v'
    default_depth: int = 3
    personalization: dict[str, str] = field(default_factory=dict)


DEFAULT_PROFILE = MarcoProfile(
    personalization={
        'identity': 'Marco serves Rudolph as a practical technical operator.',
        'tone': 'Direct, calm, execution-first.',
    }
)


def load_profile(cwd: Path) -> MarcoProfile:
    path = cwd / DEFAULT_CONFIG_PATH
    if not path.exists():
        return DEFAULT_PROFILE
    data = json.loads(path.read_text())
    return MarcoProfile(
        name=data.get('name', DEFAULT_PROFILE.name),
        safety_mode=data.get('safety_mode', DEFAULT_PROFILE.safety_mode),
        pause_before_mutation=bool(data.get('pause_before_mutation', DEFAULT_PROFILE.pause_before_mutation)),
        default_test_command=data.get('default_test_command', DEFAULT_PROFILE.default_test_command),
        default_depth=int(data.get('default_depth', DEFAULT_PROFILE.default_depth)),
        personalization=dict(data.get('personalization', DEFAULT_PROFILE.personalization)),
    )


def ensure_profile(cwd: Path) -> Path:
    path = cwd / DEFAULT_CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(json.dumps(asdict(DEFAULT_PROFILE), indent=2))
    return path
