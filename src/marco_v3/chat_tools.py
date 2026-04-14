"""Tool definitions for the Marco chat orchestrator.

Each tool wraps an existing Marco v3 function and returns a small, JSON-safe
result suitable for feeding back into a chat completion. Mutating tools
(patches, notes) still respect the server's safety model — ``suggest_patch``
stages a pending proposal that the user must review + type-confirm + apply
via the Patches UI; it does NOT apply the patch.

The tool schemas use the OpenAI function-calling format (``type: function``)
and work with both Azure OpenAI GPT-5 and Grok's OpenAI-compatible API.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from .autonomy import create_plan, list_sessions
from .memory import add_entry, list_entries, recall
from .patches import list_patches, propose_patch
from .repo_intel import (
    discover_env_vars,
    discover_routes,
    discover_scripts,
    find_files,
    lookup_content,
    render_tree,
    scan_repository,
)
from .storage import MarcoStorage


# --- OpenAI function schemas ----------------------------------------------

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        'type': 'function',
        'function': {
            'name': 'workspace_status',
            'description': 'Get a summary of the active Marco workspace — file count, top extensions, pending patches, active sessions. Use this as a starting point when the user asks about the repo.',
            'parameters': {'type': 'object', 'properties': {}, 'required': []},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'find_files',
            'description': 'Find files in the workspace by glob pattern (e.g. "**/*.py", "src/*.ts"). Returns matching relative paths.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'pattern': {'type': 'string', 'description': 'Glob pattern'},
                    'limit': {'type': 'integer', 'description': 'Max results', 'default': 50},
                },
                'required': ['pattern'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'lookup_content',
            'description': 'Search file contents in the workspace for a substring. Returns file/line/text hits.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'needle': {'type': 'string', 'description': 'Text to search for (case-insensitive)'},
                    'limit': {'type': 'integer', 'default': 30},
                },
                'required': ['needle'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'list_scripts',
            'description': 'List all runnable scripts discovered in the workspace (package.json, Makefile, pyproject.toml).',
            'parameters': {'type': 'object', 'properties': {}, 'required': []},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'list_routes',
            'description': 'List route-like files in the workspace.',
            'parameters': {
                'type': 'object',
                'properties': {'limit': {'type': 'integer', 'default': 50}},
                'required': [],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'list_env_vars',
            'description': 'List environment variable references discovered in the workspace code.',
            'parameters': {
                'type': 'object',
                'properties': {'limit': {'type': 'integer', 'default': 100}},
                'required': [],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'show_tree',
            'description': 'Render a directory tree for the workspace up to the given depth.',
            'parameters': {
                'type': 'object',
                'properties': {'depth': {'type': 'integer', 'default': 2}},
                'required': [],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'recall_memory',
            'description': 'Fuzzy search across saved notes, decisions, and conventions in Marco memory.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string'},
                    'limit': {'type': 'integer', 'default': 10},
                },
                'required': ['query'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'save_memory',
            'description': 'Save a note, decision, or convention to Marco memory. Use kind="note" for general notes, "decision" for technical choices, "convention" for agreed-upon patterns.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'kind': {'type': 'string', 'enum': ['note', 'decision', 'convention']},
                    'key': {'type': 'string', 'description': 'short unique identifier'},
                    'topic': {'type': 'string'},
                    'text': {'type': 'string'},
                },
                'required': ['kind', 'key', 'topic', 'text'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'create_plan',
            'description': 'Create a new Marco session plan for a development goal. Returns the session_id and steps. Does not execute anything.',
            'parameters': {
                'type': 'object',
                'properties': {'goal': {'type': 'string'}},
                'required': ['goal'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'suggest_patch',
            'description': (
                'Stage a pending patch proposal against a target file. The user then reviews '
                'the diff, types the patch name to confirm, and applies it from the Patches '
                'UI. Does NOT apply the patch. Use this when the user asks for a code change.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'target': {'type': 'string', 'description': 'path relative to workspace root'},
                    'name': {'type': 'string', 'description': 'short kebab-case patch name'},
                    'find': {
                        'type': 'string',
                        'description': 'exact text to find in the file (must match once)',
                    },
                    'replace': {'type': 'string', 'description': 'replacement text'},
                },
                'required': ['target', 'name', 'find', 'replace'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'list_sessions',
            'description': 'List all Marco session artifacts (planned, running, validated, recovered) for the current workspace.',
            'parameters': {'type': 'object', 'properties': {}, 'required': []},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'list_patches',
            'description': 'List all patch proposals for the current workspace with their statuses.',
            'parameters': {'type': 'object', 'properties': {}, 'required': []},
        },
    },
]


# --- Dispatcher -----------------------------------------------------------


def _jsonable(obj: Any) -> Any:
    """Convert dataclasses / objects to JSON-safe primitives."""
    if hasattr(obj, '__dict__') and hasattr(obj, '__dataclass_fields__'):
        return asdict(obj)
    if isinstance(obj, list):
        return [_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    return obj


def dispatch_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    root: Path,
    storage: MarcoStorage,
    audit: Callable[..., Any],
    workspace_name: str,
) -> dict[str, Any]:
    """Execute a tool call and return a JSON-safe result.

    Mutating tools write to the audit log via ``audit(action, workspace, params, ...)``.
    """
    args = arguments or {}

    if name == 'workspace_status':
        scan = scan_repository(root)
        return {
            'workspace': workspace_name,
            'file_count': scan.file_count,
            'total_bytes': scan.total_bytes,
            'top_extensions': dict(list(scan.by_extension.items())[:8]),
            'pending_patches': len([p for p in list_patches(storage) if p.status == 'pending']),
            'sessions': len(list_sessions(storage)),
        }

    if name == 'find_files':
        pattern = args.get('pattern') or ''
        limit = int(args.get('limit') or 50)
        if not pattern:
            return {'error': 'pattern is required'}
        return {'matches': find_files(root, pattern, limit=limit)}

    if name == 'lookup_content':
        needle = args.get('needle') or ''
        limit = int(args.get('limit') or 30)
        if not needle:
            return {'error': 'needle is required'}
        return {'matches': lookup_content(root, needle, limit=limit)[:limit]}

    if name == 'list_scripts':
        return {'scripts': [asdict(s) for s in discover_scripts(root)]}

    if name == 'list_routes':
        limit = int(args.get('limit') or 50)
        return {'routes': [asdict(r) for r in discover_routes(root, limit=limit)]}

    if name == 'list_env_vars':
        limit = int(args.get('limit') or 100)
        return {'env_vars': discover_env_vars(root, limit=limit)}

    if name == 'show_tree':
        depth = int(args.get('depth') or 2)
        return {'lines': render_tree(root, max_depth=depth, max_entries=80)}

    if name == 'recall_memory':
        query = args.get('query') or ''
        limit = int(args.get('limit') or 10)
        if not query:
            return {'error': 'query is required'}
        return {'matches': [asdict(e) for e in recall(storage, query, limit=limit)]}

    if name == 'save_memory':
        kind = args.get('kind') or ''
        key = args.get('key') or ''
        topic = args.get('topic') or ''
        text = args.get('text') or ''
        if kind not in ('note', 'decision', 'convention'):
            return {'error': f'invalid kind: {kind}'}
        if not key or not topic or not text:
            return {'error': 'key, topic, and text are required'}
        entry = add_entry(storage, kind=kind, key=key, topic=topic, text=text)
        audit(f'memory.add.{kind}', workspace=workspace_name, params={'key': key, 'topic': topic, 'via': 'chat'})
        return {'saved': asdict(entry)}

    if name == 'create_plan':
        goal = args.get('goal') or ''
        if not goal:
            return {'error': 'goal is required'}
        artifact = create_plan(root, storage, goal)
        audit('session.plan', workspace=workspace_name, params={'goal': goal, 'session_id': artifact.session_id, 'via': 'chat'})
        return {'plan': asdict(artifact)}

    if name == 'suggest_patch':
        target = args.get('target') or ''
        patch_name = args.get('name') or ''
        find_text = args.get('find') or ''
        replace_text = args.get('replace')
        if not target or not patch_name or not find_text or replace_text is None:
            return {'error': 'target, name, find, and replace are required'}
        try:
            proposal = propose_patch(
                storage, root,
                name=patch_name, target=target,
                find_text=find_text, replace_text=replace_text,
            )
        except (FileNotFoundError, ValueError) as exc:
            return {'error': str(exc)}
        audit(
            'patch.propose',
            workspace=workspace_name,
            params={'name': patch_name, 'target': target, 'via': 'chat'},
            patch_id=proposal.patch_id,
        )
        return {
            'proposal': asdict(proposal),
            'ui_path': f'/patches/{proposal.patch_id}',
            'note': 'Patch is STAGED. Go to the Patches page and type the patch name to confirm and apply.',
        }

    if name == 'list_sessions':
        return {'sessions': [asdict(s) for s in list_sessions(storage)]}

    if name == 'list_patches':
        return {'patches': [asdict(p) for p in list_patches(storage)]}

    return {'error': f'unknown tool: {name}'}


# --- Conversation persistence --------------------------------------------


def conversation_path(storage_root: Path, conversation_id: str) -> Path:
    chats = storage_root / '.marco' / 'chats'
    chats.mkdir(parents=True, exist_ok=True)
    return chats / f'{conversation_id}.jsonl'


def append_chat_message(path: Path, message: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as f:
        f.write(json.dumps(message) + '\n')


def load_chat_messages(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    messages: list[dict[str, Any]] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        messages.append(json.loads(line))
    return messages
