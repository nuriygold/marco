"""SSE streaming helper.

Wraps a callable that produces text lines into a Server-Sent Events stream.
The server uses this for long-running commands: ``execute``, ``validate``,
``recover``, and ``run-script --execute``.
"""

from __future__ import annotations

import asyncio
import json
import shlex
from pathlib import Path
from typing import AsyncIterator, Callable


def _sse(event: str, data: object) -> str:
    payload = data if isinstance(data, str) else json.dumps(data)
    # Split multi-line strings into separate `data:` lines per the spec.
    lines = '\n'.join(f'data: {chunk}' for chunk in payload.splitlines() or [payload])
    return f'event: {event}\n{lines}\n\n'


async def stream_subprocess(command: str, cwd: Path) -> AsyncIterator[str]:
    """Run ``command`` in ``cwd`` and yield SSE-formatted events.

    Emits: ``start`` → zero or more ``line`` events → ``end`` (with returncode).
    """
    yield _sse('start', {'command': command, 'cwd': str(cwd)})
    parts = shlex.split(command)
    if not parts:
        yield _sse('end', {'returncode': 1, 'error': 'empty command'})
        return
    proc = await asyncio.create_subprocess_exec(
        *parts,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    assert proc.stdout is not None
    try:
        async for raw in proc.stdout:
            line = raw.decode('utf-8', errors='replace').rstrip('\n')
            yield _sse('line', line)
    finally:
        returncode = await proc.wait()
        yield _sse('end', {'returncode': returncode})


async def stream_sync_callable(producer: Callable[[], object]) -> AsyncIterator[str]:
    """Stream a single synchronous producer as an SSE sequence (start/result/end)."""
    yield _sse('start', {})
    try:
        result = await asyncio.to_thread(producer)
        yield _sse('result', result)
        yield _sse('end', {'returncode': 0})
    except Exception as exc:  # noqa: BLE001
        yield _sse('error', {'message': str(exc)})
        yield _sse('end', {'returncode': 1})


def format_sse(event: str, data: object) -> str:
    """Exposed for tests."""
    return _sse(event, data)
