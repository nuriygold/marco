from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from .storage import MarcoStorage


@dataclass(frozen=True)
class MemoryEntry:
    kind: str
    key: str
    topic: str
    text: str
    created_at: str


MEMORY_FILES = {
    'note': 'notes.jsonl',
    'decision': 'decisions.jsonl',
    'convention': 'conventions.jsonl',
}


def add_entry(storage: MarcoStorage, *, kind: str, key: str, topic: str, text: str) -> MemoryEntry:
    if kind not in MEMORY_FILES:
        raise ValueError(f'Unsupported memory kind: {kind}')
    entry = MemoryEntry(kind=kind, key=key, topic=topic, text=text, created_at=storage.now())
    storage.append_jsonl(storage.memory / MEMORY_FILES[kind], entry.__dict__)
    return entry


def list_entries(storage: MarcoStorage, kind: str, limit: int = 50) -> list[MemoryEntry]:
    if kind not in MEMORY_FILES:
        raise ValueError(f'Unsupported memory kind: {kind}')
    rows = storage.read_jsonl(storage.memory / MEMORY_FILES[kind])
    return [MemoryEntry(**row) for row in rows][-limit:]


def recall(storage: MarcoStorage, query: str, limit: int = 20) -> list[MemoryEntry]:
    all_rows = []
    for path in MEMORY_FILES.values():
        all_rows.extend(storage.read_jsonl(storage.memory / path))

    scored: list[tuple[float, MemoryEntry]] = []
    needle = query.lower()
    for row in all_rows:
        entry = MemoryEntry(**row)
        haystack = f"{entry.key} {entry.topic} {entry.text}".lower()
        ratio = SequenceMatcher(None, needle, haystack).ratio()
        if needle in haystack:
            ratio += 1.0
        if ratio > 0.2:
            scored.append((ratio, entry))
    scored.sort(key=lambda item: (-item[0], item[1].created_at))
    return [entry for _, entry in scored[:limit]]


def remember(storage: MarcoStorage, key: str, topic: str, text: str) -> MemoryEntry:
    return add_entry(storage, kind='note', key=key, topic=topic, text=text)
