from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class MarcoStorage:
    def __init__(self, root: Path) -> None:
        self.root = root / '.marco'
        self.sessions = self.root / 'sessions'
        self.memory = self.root / 'memory'
        self.patches = self.root / 'patches'
        self.checkpoints = self.root / 'checkpoints'
        self.logs = self.root / 'logs'
        for path in (self.sessions, self.memory, self.patches, self.checkpoints, self.logs):
            path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def now() -> str:
        return datetime.now(UTC).isoformat()

    def write_json(self, path: Path, data: dict[str, Any]) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2))
        return path

    def read_json(self, path: Path) -> dict[str, Any]:
        return json.loads(path.read_text())

    def write_dataclass(self, path: Path, payload: Any) -> Path:
        return self.write_json(path, asdict(payload))

    def append_jsonl(self, path: Path, payload: dict[str, Any]) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(payload) + '\n')
        return path

    def read_jsonl(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
        return rows
