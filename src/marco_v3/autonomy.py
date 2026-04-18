from __future__ import annotations

import json
import importlib
import shlex
import subprocess
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable

from .config import ALLOWED_SCRIPT_PREFIXES, SHELL_META, MarcoProfile
from .repo_intel import discover_scripts, where_edit
from .storage import MarcoStorage


def _llm_module():
    """Resolve llm lazily.

    Uses importlib so tests can inject ``src.marco_v3.llm`` in ``sys.modules``
    without mutating the package-level ``src.marco_v3.llm`` export.
    """
    return importlib.import_module('src.marco_v3.llm')


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SessionArtifact:
    session_id: str
    goal: str
    phase: str          # plan | execute | validate | recover | completed
    status: str         # ready | running | passed | failed | completed
    artifacts: dict[str, object]
    created_at: str
    step_progress: list[dict[str, object]] = field(default_factory=list)
    phase_history: list[dict[str, str]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionArtifact:
        data = dict(data)
        data.setdefault('step_progress', [])
        data.setdefault('phase_history', [])
        return cls(**data)


def _new_session_id() -> str:
    return uuid.uuid4().hex[:12]


def _make_blocked_process(command: str, reason: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=command, returncode=1, stdout='', stderr=reason)


def _transition(
    storage: MarcoStorage,
    session_id: str,
    phase: str,
    status: str,
    artifacts: dict[str, Any],
    step_progress: list[dict[str, Any]] | None = None,
) -> SessionArtifact:
    """Create a new phase transition and persist it, preserving history."""
    current = storage.read_json(storage.sessions / f'{session_id}.json')
    old_history: list[dict[str, str]] = current.get('phase_history', [])
    new_history = old_history + [{'phase': phase, 'status': status, 'timestamp': storage.now()}]
    artifact = SessionArtifact(
        session_id=session_id,
        goal=current.get('goal', ''),
        phase=phase,
        status=status,
        artifacts=artifacts,
        created_at=current.get('created_at', storage.now()),
        step_progress=step_progress if step_progress is not None else current.get('step_progress', []),
        phase_history=new_history,
    )
    storage.write_json(storage.sessions / f'{session_id}.json', asdict(artifact))
    return artifact


# ---------------------------------------------------------------------------
# Execution tools (used exclusively inside execute_plan)
# ---------------------------------------------------------------------------

EXECUTION_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        'type': 'function',
        'function': {
            'name': 'apply_patch_now',
            'description': (
                'Propose AND immediately apply a find-replace patch to a file in the workspace. '
                'Use this to write or modify code. The patch is checkpointed so it can be rolled back. '
                'find must match exactly once in the target file.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'target': {'type': 'string', 'description': 'File path relative to workspace root'},
                    'name': {'type': 'string', 'description': 'Short kebab-case patch name'},
                    'find': {'type': 'string', 'description': 'Exact text to find (must match once). Use empty string to append to new file.'},
                    'replace': {'type': 'string', 'description': 'Replacement text'},
                },
                'required': ['target', 'name', 'find', 'replace'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'write_file',
            'description': (
                'Write a complete new file to the workspace. Use this to create files from scratch. '
                'Will overwrite if the file already exists.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'path': {'type': 'string', 'description': 'File path relative to workspace root'},
                    'content': {'type': 'string', 'description': 'Full file content to write'},
                },
                'required': ['path', 'content'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'run_safe_command',
            'description': (
                'Run a shell command in the workspace directory. '
                'Only allowed prefixes: python, python3, pytest, npm, pnpm, yarn, make, cargo, go, uv, poetry. '
                'Shell metacharacters (|, &, ;, >, <, $, `) are blocked. 30-second timeout.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'command': {'type': 'string', 'description': 'Command to run (no shell metacharacters)'},
                },
                'required': ['command'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'mark_step_done',
            'description': 'Mark a plan step as completed successfully.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'step_index': {'type': 'integer', 'description': 'Zero-based index of the step'},
                    'detail': {'type': 'string', 'description': 'What was done'},
                },
                'required': ['step_index'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'mark_step_failed',
            'description': 'Mark a plan step as failed with a reason.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'step_index': {'type': 'integer', 'description': 'Zero-based index of the step'},
                    'detail': {'type': 'string', 'description': 'Why it failed'},
                },
                'required': ['step_index'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'find_files',
            'description': 'Find files in the workspace by glob pattern.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'pattern': {'type': 'string'},
                    'limit': {'type': 'integer', 'default': 50},
                },
                'required': ['pattern'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'read_file',
            'description': 'Read the contents of a file in the workspace.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'path': {'type': 'string', 'description': 'File path relative to workspace root'},
                },
                'required': ['path'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'lookup_content',
            'description': 'Search file contents for a substring.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'needle': {'type': 'string'},
                    'limit': {'type': 'integer', 'default': 20},
                },
                'required': ['needle'],
            },
        },
    },
]

RECOVERY_TOOL_SCHEMAS: list[dict[str, Any]] = [
    *EXECUTION_TOOL_SCHEMAS,
    {
        'type': 'function',
        'function': {
            'name': 'rollback_patch',
            'description': 'Roll back a previously applied patch by its patch_id.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'patch_id': {'type': 'string'},
                },
                'required': ['patch_id'],
            },
        },
    },
]

EXECUTION_SYSTEM_PROMPT = """\
You are Marco, a practical technical operator. You are executing a development plan step by step.

For each step in the plan:
1. Use the available tools to implement it (write_file, apply_patch_now, run_safe_command).
2. Read existing files first before patching them.
3. When a step is done, call mark_step_done with the step index.
4. If a step cannot be completed, call mark_step_failed with the reason.

Rules:
- Implement real, working code — not stubs or placeholders.
- Use write_file to create new files from scratch.
- Use apply_patch_now for targeted edits to existing files.
- Use run_safe_command to install dependencies or run setup steps.
- Read files before patching them so the find text is accurate.
- Mark every step explicitly as done or failed before finishing.
- Be concise in your reasoning; prefer tool calls over long explanations.
"""

RECOVERY_SYSTEM_PROMPT = """\
You are Marco, a practical technical operator. A session validation failed. \
Your job is to diagnose the failure from the error output and fix it.

For each problem you identify:
1. Explain briefly what went wrong (one sentence).
2. Fix it using apply_patch_now, write_file, or run_safe_command.
3. Mark fixed steps as done with mark_step_done.

Rules:
- Read files before patching them.
- If a patch caused the failure, use rollback_patch first.
- Focus on the specific errors in the stderr/stdout, not generic advice.
- After fixing, say what you did and what the user should validate next.
"""


def _dispatch_execution_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    root: Path,
    storage: MarcoStorage,
    profile: MarcoProfile,
    step_progress: list[dict[str, Any]],
) -> dict[str, Any]:
    """Execute a single tool call during autonomous execute/recover."""
    from .patches import propose_patch, apply_patch, rollback_patch as _rollback_patch
    from .repo_intel import find_files, lookup_content

    args = arguments or {}

    if name == 'write_file':
        rel = args.get('path') or ''
        content = args.get('content') or ''
        if not rel:
            return {'error': 'path is required'}
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')
        return {'written': rel, 'bytes': len(content)}

    if name == 'apply_patch_now':
        target = args.get('target') or ''
        patch_name = args.get('name') or ''
        find_text = args.get('find') or ''
        replace_text = args.get('replace')
        if not target or not patch_name or replace_text is None:
            return {'error': 'target, name, and replace are required'}
        try:
            proposal = propose_patch(storage, root, name=patch_name, target=target,
                                     find_text=find_text, replace_text=replace_text)
            applied = apply_patch(storage, root, profile, proposal.patch_id, force=True)
            return {'applied': patch_name, 'patch_id': applied.patch_id, 'target': target}
        except (FileNotFoundError, ValueError) as exc:
            return {'error': str(exc)}

    if name == 'run_safe_command':
        command = args.get('command') or ''
        if not command:
            return {'error': 'command is required'}
        if any(token in command for token in SHELL_META):
            return {'error': f'blocked: shell metacharacter in command'}
        parsed = shlex.split(command)
        if not parsed:
            return {'error': 'empty command'}
        if parsed[0] not in ALLOWED_SCRIPT_PREFIXES:
            return {'error': f'blocked: "{parsed[0]}" is not an allowed command prefix'}
        try:
            proc = subprocess.run(parsed, cwd=root, shell=False, text=True,
                                  capture_output=True, timeout=30)
            return {
                'returncode': proc.returncode,
                'stdout': proc.stdout[-3000:] if proc.stdout else '',
                'stderr': proc.stderr[-1000:] if proc.stderr else '',
            }
        except subprocess.TimeoutExpired:
            return {'error': 'command timed out after 30 seconds'}

    if name == 'mark_step_done':
        idx = args.get('step_index')
        detail = args.get('detail', '')
        if idx is None or not (0 <= idx < len(step_progress)):
            return {'error': f'invalid step_index {idx}'}
        step_progress[idx]['status'] = 'done'
        step_progress[idx]['detail'] = detail
        return {'marked_done': idx}

    if name == 'mark_step_failed':
        idx = args.get('step_index')
        detail = args.get('detail', '')
        if idx is None or not (0 <= idx < len(step_progress)):
            return {'error': f'invalid step_index {idx}'}
        step_progress[idx]['status'] = 'failed'
        step_progress[idx]['detail'] = detail
        return {'marked_failed': idx}

    if name == 'find_files':
        pattern = args.get('pattern') or ''
        limit = int(args.get('limit') or 50)
        if not pattern:
            return {'error': 'pattern is required'}
        return {'matches': find_files(root, pattern, limit=limit)}

    if name == 'read_file':
        rel = args.get('path') or ''
        if not rel:
            return {'error': 'path is required'}
        target = root / rel
        if not target.exists():
            return {'error': f'file not found: {rel}'}
        try:
            return {'content': target.read_text(encoding='utf-8')[:8000]}
        except OSError as exc:
            return {'error': str(exc)}

    if name == 'lookup_content':
        needle = args.get('needle') or ''
        limit = int(args.get('limit') or 20)
        if not needle:
            return {'error': 'needle is required'}
        return {'matches': lookup_content(root, needle, limit=limit)}

    if name == 'rollback_patch':
        patch_id = args.get('patch_id') or ''
        if not patch_id:
            return {'error': 'patch_id is required'}
        try:
            rolled = _rollback_patch(storage, root, patch_id)
            return {'rolled_back': rolled.patch_id, 'name': rolled.name}
        except FileNotFoundError as exc:
            return {'error': str(exc)}

    return {'error': f'unknown tool: {name}'}


def _run_llm_loop(
    messages: list[dict[str, Any]],
    tool_schemas: list[dict[str, Any]],
    *,
    root: Path,
    storage: MarcoStorage,
    profile: MarcoProfile,
    step_progress: list[dict[str, Any]],
    emit: Callable[[str, Any], None],
    max_iterations: int,
) -> list[dict[str, Any]]:
    """Run the LLM tool-calling loop. Returns the final messages list."""
    llm = _llm_module()

    for _ in range(max_iterations):
        response = llm.chat_completion(
            messages=messages,
            tools=tool_schemas,
            tool_choice='auto',
            max_tokens=4096,
        )
        choice = (response.get('choices') or [{}])[0]
        msg = choice.get('message') or {}
        tool_calls = msg.get('tool_calls') or []

        if not tool_calls:
            # LLM is done
            messages.append({'role': 'assistant', 'content': msg.get('content') or ''})
            break

        messages.append({
            'role': 'assistant',
            'content': msg.get('content'),
            'tool_calls': tool_calls,
        })

        for tc in tool_calls:
            fn = tc.get('function') or {}
            tool_name = fn.get('name') or ''
            raw_args = fn.get('arguments') or '{}'
            try:
                parsed_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except Exception:
                parsed_args = {}

            result = _dispatch_execution_tool(
                tool_name, parsed_args,
                root=root, storage=storage, profile=profile,
                step_progress=step_progress,
            )
            emit('tool', {'name': tool_name, 'result': result})
            messages.append({
                'role': 'tool',
                'tool_call_id': tc.get('id'),
                'name': tool_name,
                'content': json.dumps(result)[:12000],
            })

    return messages


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_plan(root: Path, storage: MarcoStorage, goal: str) -> SessionArtifact:
    edits = where_edit(root, goal, limit=5)
    steps = [
        'Inspect repo and constraints',
        'Identify edit targets',
        'Implement scoped changes',
        'Validate with existing scripts/tests',
        'Prepare rollback and recovery notes',
    ]
    now = storage.now()
    artifact = SessionArtifact(
        session_id=_new_session_id(),
        goal=goal,
        phase='plan',
        status='ready',
        artifacts={'steps': steps, 'where_edit': edits},
        created_at=now,
        step_progress=[],
        phase_history=[{'phase': 'plan', 'status': 'ready', 'timestamp': now}],
    )
    storage.write_json(storage.sessions / f'{artifact.session_id}.json', asdict(artifact))
    return artifact


def execute_plan(
    root: Path,
    storage: MarcoStorage,
    profile: MarcoProfile,
    session_id: str,
    *,
    emit: Callable[[str, Any], None] = lambda event, data: None,
) -> SessionArtifact:
    llm = _llm_module()

    if not llm.is_configured():
        raise RuntimeError(
            'No LLM provider configured. Set MARCO_LLM_PROVIDER and the '
            'corresponding API key in /etc/marco/marco.env, then restart.'
        )

    data = storage.read_json(storage.sessions / f'{session_id}.json')
    ai_plan = data.get('artifacts', {}).get('ai_plan') or {}
    raw_steps: list[str] = (
        ai_plan.get('steps')
        or data.get('artifacts', {}).get('steps')
        or ['Implement the goal']
    )
    edit_targets: list[str] = ai_plan.get('edit_targets') or []
    validation_hint: str = ai_plan.get('validation') or ''

    # Build initial step_progress
    step_progress: list[dict[str, Any]] = [
        {'step': s, 'status': 'pending', 'detail': '', 'index': i}
        for i, s in enumerate(raw_steps)
    ]

    # Transition to execute/running
    artifact = _transition(storage, session_id, 'execute', 'running',
                           artifacts={'actions': ['execution started'], 'edit_targets': edit_targets},
                           step_progress=step_progress)
    emit('start', {'session_id': session_id, 'steps': len(raw_steps)})

    # Build execution prompt
    steps_text = '\n'.join(f'{i}. {s}' for i, s in enumerate(raw_steps))
    targets_text = ', '.join(edit_targets) if edit_targets else 'to be determined'
    goal = data.get('goal', '')

    messages: list[dict[str, Any]] = [
        {'role': 'system', 'content': EXECUTION_SYSTEM_PROMPT},
        {
            'role': 'user',
            'content': (
                f'Goal: {goal}\n\n'
                f'Plan steps (use mark_step_done/mark_step_failed for each):\n{steps_text}\n\n'
                f'Expected edit targets: {targets_text}\n\n'
                f'Validation hint: {validation_hint or "run the project tests"}\n\n'
                'Execute each step using the available tools. '
                'Read files before patching. Write real, working code.'
            ),
        },
    ]

    try:
        _run_llm_loop(
            messages, EXECUTION_TOOL_SCHEMAS,
            root=root, storage=storage, profile=profile,
            step_progress=step_progress, emit=emit,
            max_iterations=15,
        )
    except Exception as exc:
        emit('error', {'message': str(exc)})
        return _transition(storage, session_id, 'execute', 'failed',
                           artifacts={'error': str(exc)},
                           step_progress=step_progress)

    # Determine final status
    failed = [s for s in step_progress if s['status'] == 'failed']
    pending = [s for s in step_progress if s['status'] == 'pending']
    final_status = 'failed' if (failed or pending) else 'passed'

    artifact = _transition(
        storage, session_id, 'execute', final_status,
        artifacts={
            'steps_done': sum(1 for s in step_progress if s['status'] == 'done'),
            'steps_failed': len(failed),
            'steps_pending': len(pending),
            'edit_targets': edit_targets,
        },
        step_progress=step_progress,
    )
    emit('done', asdict(artifact))
    return artifact


def validate_session(
    root: Path,
    storage: MarcoStorage,
    profile: MarcoProfile,
    session_id: str,
) -> SessionArtifact:
    scripts = discover_scripts(root)
    test_script = next(
        (item.command for item in scripts if 'test' in item.name.lower()),
        profile.default_test_command,
    )
    if any(token in test_script for token in SHELL_META) and profile.safety_mode != 'danger-full-access':
        process = _make_blocked_process(test_script, 'blocked unsafe shell metacharacters')
    else:
        parsed = shlex.split(test_script)
        if not parsed:
            process = _make_blocked_process(test_script, 'empty validation command')
        elif profile.safety_mode != 'danger-full-access' and parsed[0] not in ALLOWED_SCRIPT_PREFIXES:
            process = _make_blocked_process(test_script, 'blocked command prefix for safety mode')
        else:
            process = subprocess.run(parsed, cwd=root, shell=False, text=True, capture_output=True)

    passed = process.returncode == 0
    validate_artifacts = {
        'command': test_script,
        'returncode': process.returncode,
        'stdout_tail': (process.stdout or '').splitlines()[-20:],
        'stderr_tail': (process.stderr or '').splitlines()[-20:],
    }
    artifact = _transition(storage, session_id, 'validate',
                           'passed' if passed else 'failed',
                           artifacts=validate_artifacts)
    if passed:
        artifact = complete_session(storage, session_id)
    return artifact


def recover_session(
    root: Path,
    storage: MarcoStorage,
    profile: MarcoProfile,
    session_id: str,
    *,
    emit: Callable[[str, Any], None] = lambda event, data: None,
) -> SessionArtifact:
    llm = _llm_module()

    if not llm.is_configured():
        # Graceful fallback: static recovery tips (old behaviour)
        return _recover_static(storage, session_id)

    data = storage.read_json(storage.sessions / f'{session_id}.json')
    prev_artifacts = data.get('artifacts', {})
    step_progress: list[dict[str, Any]] = list(data.get('step_progress', []))

    # Build context from validation failure
    stderr = '\n'.join(prev_artifacts.get('stderr_tail', []))
    stdout = '\n'.join(prev_artifacts.get('stdout_tail', []))
    command = prev_artifacts.get('command', '')
    returncode = prev_artifacts.get('returncode', -1)
    goal = data.get('goal', '')

    # Build step summary for context
    steps_summary = '\n'.join(
        f'{s["index"]}. [{s["status"].upper()}] {s["step"]} — {s["detail"]}'
        for s in step_progress
    ) if step_progress else '(no step progress recorded)'

    emit('start', {'session_id': session_id})

    messages: list[dict[str, Any]] = [
        {'role': 'system', 'content': RECOVERY_SYSTEM_PROMPT},
        {
            'role': 'user',
            'content': (
                f'Goal: {goal}\n\n'
                f'Validation command: {command}\n'
                f'Return code: {returncode}\n\n'
                f'STDERR:\n{stderr or "(empty)"}\n\n'
                f'STDOUT (tail):\n{stdout or "(empty)"}\n\n'
                f'Step progress:\n{steps_summary}\n\n'
                'Diagnose the failure and fix it using the available tools.'
            ),
        },
    ]

    try:
        _run_llm_loop(
            messages, RECOVERY_TOOL_SCHEMAS,
            root=root, storage=storage, profile=profile,
            step_progress=step_progress, emit=emit,
            max_iterations=8,
        )
    except Exception as exc:
        emit('error', {'message': str(exc)})

    artifact = _transition(
        storage, session_id, 'recover', 'ready',
        artifacts={
            'recovery_note': 'LLM-driven recovery complete — re-run validate to check.',
            'previous_phase': data.get('phase'),
            'previous_status': data.get('status'),
        },
        step_progress=step_progress,
    )
    emit('done', asdict(artifact))
    return artifact


def _recover_static(storage: MarcoStorage, session_id: str) -> SessionArtifact:
    """Fallback recovery when LLM is not configured."""
    current = storage.read_json(storage.sessions / f'{session_id}.json')
    return _transition(
        storage, session_id, 'recover', 'ready',
        artifacts={
            'recovery_steps': [
                'Review latest failed validation output',
                'Rollback pending patch if necessary',
                'Resume with focused patch plan',
            ],
            'previous_phase': current.get('phase'),
            'previous_status': current.get('status'),
        },
    )


def complete_session(storage: MarcoStorage, session_id: str) -> SessionArtifact:
    return _transition(
        storage, session_id, 'completed', 'completed',
        artifacts={'completed_reason': 'validation passed'},
    )


def list_sessions(storage: MarcoStorage) -> list[SessionArtifact]:
    entries: list[SessionArtifact] = []
    for path in sorted(storage.sessions.glob('*.json')):
        data = storage.read_json(path)
        entries.append(SessionArtifact.from_dict(data))
    return entries


def resume_session(storage: MarcoStorage, session_id: str) -> SessionArtifact:
    data = storage.read_json(storage.sessions / f'{session_id}.json')
    return SessionArtifact.from_dict(data)
