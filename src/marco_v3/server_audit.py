"""Audit log for Marco server mutations.

Every mutating action (patch apply/rollback/propose, memory writes, script
executions, session transitions) appends one JSONL entry to
``~/.marco/audit.log``. The audit page renders the tail.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


AUDIT_PATH = Path.home() / '.marco' / 'audit.log'


@dataclass(frozen=True)
class AuditEntry:
    ts: str
    workspace: str
    actor: str
    action: str
    params: dict[str, Any]
    result: str
    patch_id: str | None = None


def record(
    action: str,
    *,
    workspace: str,
    params: dict[str, Any] | None = None,
    result: str = 'ok',
    patch_id: str | None = None,
    actor: str = 'rudolph',
    path: Path = AUDIT_PATH,
) -> AuditEntry:
    entry = AuditEntry(
        ts=datetime.now(timezone.utc).isoformat(),
        workspace=workspace,
        actor=actor,
        action=action,
        params=params or {},
        result=result,
        patch_id=patch_id,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as f:
        f.write(json.dumps(asdict(entry)) + '\n')
    return entry


def tail(limit: int = 200, path: Path = AUDIT_PATH) -> list[AuditEntry]:
    if not path.exists():
        return []
    entries: list[AuditEntry] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        data = json.loads(line)
        entries.append(AuditEntry(**data))
    return list(reversed(entries))[:limit]
