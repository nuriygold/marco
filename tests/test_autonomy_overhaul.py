"""Tests for the overhauled Marco v3 autonomy system.

Covers:
- SessionArtifact backward compatibility (from_dict with missing fields)
- step_progress and phase_history tracking
- execute_plan: LLM-driven tool dispatch, step marking, safety checks
- recover_session: LLM fallback and static fallback
- complete_session terminal state
- _dispatch_execution_tool: write_file, apply_patch_now, run_safe_command, mark_step_*, read_file
"""

from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import MagicMock

import sys
from unittest.mock import MagicMock

# llm.py imports httpx at module level, which isn't installed in this env.
# Inject a mock module into sys.modules so autonomy's `from . import llm` resolves.
_mock_llm = MagicMock()
_mock_llm.is_configured.return_value = False  # default: not configured
sys.modules.setdefault('src.marco_v3.llm', _mock_llm)

from src.marco_v3.autonomy import (
    SessionArtifact,
    _dispatch_execution_tool,
    _transition,
    complete_session,
    create_plan,
    execute_plan,
    list_sessions,
    recover_session,
    resume_session,
    validate_session,
)
from src.marco_v3.config import MarcoProfile
from src.marco_v3.storage import MarcoStorage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tmp_workspace():
    """Return a TemporaryDirectory context manager with a dummy file."""
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    (root / 'README.md').write_text('# Test\n')
    return tmp, root


def _profile() -> MarcoProfile:
    return MarcoProfile(safety_mode='workspace-write', pause_before_mutation=False)


def _tool_call(name: str, args: dict, call_id: str = 'c1') -> dict:
    return {
        'id': call_id,
        'type': 'function',
        'function': {'name': name, 'arguments': json.dumps(args)},
    }


def _llm_response(tool_calls=None, content='done'):
    """Build a minimal chat_completion response."""
    msg = {'content': content, 'tool_calls': tool_calls or []}
    return {'choices': [{'message': msg}], 'usage': {}}


def _tool_msg(tool_call_id: str, name: str, result: dict) -> dict:
    return {'role': 'tool', 'tool_call_id': tool_call_id, 'name': name,
            'content': json.dumps(result)}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class SessionArtifactCompatTests(unittest.TestCase):

    def test_from_dict_fills_missing_new_fields(self):
        """Old session JSON without step_progress/phase_history deserializes cleanly."""
        old = {
            'session_id': 'abc123',
            'goal': 'test goal',
            'phase': 'plan',
            'status': 'ready',
            'artifacts': {},
            'created_at': '2026-01-01T00:00:00+00:00',
        }
        art = SessionArtifact.from_dict(old)
        self.assertEqual(art.step_progress, [])
        self.assertEqual(art.phase_history, [])
        self.assertEqual(art.session_id, 'abc123')

    def test_from_dict_preserves_existing_new_fields(self):
        data = {
            'session_id': 'xyz',
            'goal': 'g',
            'phase': 'execute',
            'status': 'running',
            'artifacts': {},
            'created_at': '2026-01-01T00:00:00+00:00',
            'step_progress': [{'step': 'do X', 'status': 'done'}],
            'phase_history': [{'phase': 'plan', 'status': 'ready', 'timestamp': 't'}],
        }
        art = SessionArtifact.from_dict(data)
        self.assertEqual(len(art.step_progress), 1)
        self.assertEqual(len(art.phase_history), 1)

    def test_create_plan_includes_history_and_progress(self):
        tmp, root = _tmp_workspace()
        with tmp:
            storage = MarcoStorage(root)
            art = create_plan(root, storage, 'build something')
            self.assertEqual(art.step_progress, [])
            self.assertEqual(len(art.phase_history), 1)
            self.assertEqual(art.phase_history[0]['phase'], 'plan')

    def test_list_sessions_works_on_old_json(self):
        """list_sessions must not crash on old JSON without the new fields."""
        tmp, root = _tmp_workspace()
        with tmp:
            storage = MarcoStorage(root)
            old = {
                'session_id': 'old001',
                'goal': 'old goal',
                'phase': 'plan',
                'status': 'ready',
                'artifacts': {},
                'created_at': '2026-01-01T00:00:00+00:00',
            }
            storage.write_json(storage.sessions / 'old001.json', old)
            sessions = list_sessions(storage)
            self.assertEqual(len(sessions), 1)
            self.assertEqual(sessions[0].step_progress, [])

    def test_resume_session_works_on_old_json(self):
        tmp, root = _tmp_workspace()
        with tmp:
            storage = MarcoStorage(root)
            old = {
                'session_id': 'old002',
                'goal': 'g',
                'phase': 'plan',
                'status': 'ready',
                'artifacts': {},
                'created_at': '2026-01-01T00:00:00+00:00',
            }
            storage.write_json(storage.sessions / 'old002.json', old)
            art = resume_session(storage, 'old002')
            self.assertEqual(art.step_progress, [])


class TransitionTests(unittest.TestCase):

    def test_transition_appends_history(self):
        tmp, root = _tmp_workspace()
        with tmp:
            storage = MarcoStorage(root)
            plan = create_plan(root, storage, 'goal')
            session_id = plan.session_id

            art2 = _transition(storage, session_id, 'execute', 'running', artifacts={})
            self.assertEqual(art2.phase, 'execute')
            self.assertEqual(len(art2.phase_history), 2)
            self.assertEqual(art2.phase_history[0]['phase'], 'plan')
            self.assertEqual(art2.phase_history[1]['phase'], 'execute')

    def test_complete_session_sets_terminal_state(self):
        tmp, root = _tmp_workspace()
        with tmp:
            storage = MarcoStorage(root)
            plan = create_plan(root, storage, 'goal')
            art = complete_session(storage, plan.session_id)
            self.assertEqual(art.phase, 'completed')
            self.assertEqual(art.status, 'completed')


# ---------------------------------------------------------------------------
# Execution tool dispatch
# ---------------------------------------------------------------------------

class ExecutionToolDispatchTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'hello.txt').write_text('hello world\n')
        self.storage = MarcoStorage(self.root)
        self.profile = _profile()

    def tearDown(self):
        self.tmp.cleanup()

    def _dispatch(self, name, args, step_progress=None):
        return _dispatch_execution_tool(
            name, args,
            root=self.root, storage=self.storage, profile=self.profile,
            step_progress=step_progress or [],
        )

    def test_write_file_creates_new_file(self):
        result = self._dispatch('write_file', {'path': 'newdir/new.txt', 'content': 'abc'})
        self.assertIn('written', result)
        self.assertTrue((self.root / 'newdir/new.txt').exists())
        self.assertEqual((self.root / 'newdir/new.txt').read_text(), 'abc')

    def test_write_file_requires_path(self):
        result = self._dispatch('write_file', {'content': 'x'})
        self.assertIn('error', result)

    def test_read_file_returns_content(self):
        result = self._dispatch('read_file', {'path': 'hello.txt'})
        self.assertIn('content', result)
        self.assertIn('hello world', result['content'])

    def test_read_file_missing(self):
        result = self._dispatch('read_file', {'path': 'nope.txt'})
        self.assertIn('error', result)

    def test_apply_patch_now_applies_and_returns_patch_id(self):
        result = self._dispatch('apply_patch_now', {
            'target': 'hello.txt',
            'name': 'test-patch',
            'find': 'hello world',
            'replace': 'goodbye world',
        })
        self.assertIn('applied', result)
        self.assertEqual((self.root / 'hello.txt').read_text(), 'goodbye world\n')

    def test_apply_patch_now_returns_error_on_missing_text(self):
        result = self._dispatch('apply_patch_now', {
            'target': 'hello.txt',
            'name': 'bad-patch',
            'find': 'nonexistent text xyz',
            'replace': 'new',
        })
        self.assertIn('error', result)

    def test_run_safe_command_allowed(self):
        result = self._dispatch('run_safe_command', {'command': 'python3 --version'})
        self.assertIn('returncode', result)
        self.assertEqual(result['returncode'], 0)

    def test_run_safe_command_blocks_disallowed_prefix(self):
        result = self._dispatch('run_safe_command', {'command': 'rm -rf /tmp/test'})
        self.assertIn('error', result)
        self.assertIn('blocked', result['error'])

    def test_run_safe_command_blocks_shell_meta(self):
        result = self._dispatch('run_safe_command', {'command': 'python3 -c "x=1" | cat'})
        self.assertIn('error', result)
        self.assertIn('blocked', result['error'])

    def test_mark_step_done(self):
        progress = [{'step': 'step 0', 'status': 'pending', 'detail': '', 'index': 0}]
        result = self._dispatch('mark_step_done', {'step_index': 0, 'detail': 'done!'}, progress)
        self.assertEqual(result['marked_done'], 0)
        self.assertEqual(progress[0]['status'], 'done')
        self.assertEqual(progress[0]['detail'], 'done!')

    def test_mark_step_failed(self):
        progress = [{'step': 'step 0', 'status': 'pending', 'detail': '', 'index': 0}]
        result = self._dispatch('mark_step_failed', {'step_index': 0, 'detail': 'oops'}, progress)
        self.assertEqual(result['marked_failed'], 0)
        self.assertEqual(progress[0]['status'], 'failed')

    def test_mark_step_invalid_index(self):
        progress = [{'step': 'step 0', 'status': 'pending', 'detail': '', 'index': 0}]
        result = self._dispatch('mark_step_done', {'step_index': 99}, progress)
        self.assertIn('error', result)

    def test_unknown_tool_returns_error(self):
        result = self._dispatch('totally_unknown', {})
        self.assertIn('error', result)


# ---------------------------------------------------------------------------
# execute_plan
# ---------------------------------------------------------------------------

class ExecutePlanTests(unittest.TestCase):

    def setUp(self):
        _mock_llm.reset_mock()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'README.md').write_text('# Project\n')
        self.storage = MarcoStorage(self.root)
        self.profile = _profile()

    def tearDown(self):
        self.tmp.cleanup()

    def _make_session_with_ai_plan(self, steps=None):
        plan = create_plan(self.root, self.storage, 'build a thing')
        # Inject an AI plan into the session
        data = self.storage.read_json(self.storage.sessions / f'{plan.session_id}.json')
        data['artifacts']['ai_plan'] = {
            'goal': 'build a thing',
            'steps': steps or ['Create README section', 'Write a script'],
            'edit_targets': ['README.md'],
            'validation': 'python3 --version',
        }
        self.storage.write_json(self.storage.sessions / f'{plan.session_id}.json', data)
        return plan.session_id

    def test_execute_marks_all_steps_done(self):
        session_id = self._make_session_with_ai_plan(steps=['Step A', 'Step B'])
        _mock_llm.is_configured.return_value = True
        _mock_llm.chat_completion.side_effect = [
            _llm_response(tool_calls=[
                _tool_call('mark_step_done', {'step_index': 0, 'detail': 'A done'}, 'c1'),
                _tool_call('mark_step_done', {'step_index': 1, 'detail': 'B done'}, 'c2'),
            ]),
            _llm_response(content='All steps complete.'),
        ]

        events = []
        artifact = execute_plan(self.root, self.storage, self.profile, session_id,
                                emit=lambda e, d: events.append((e, d)))

        self.assertEqual(artifact.status, 'passed')
        self.assertTrue(any(e == 'start' for e, _ in events))
        self.assertTrue(any(e == 'done' for e, _ in events))
        self.assertTrue(all(s['status'] == 'done' for s in artifact.step_progress))

    def test_execute_status_failed_when_step_failed(self):
        session_id = self._make_session_with_ai_plan(steps=['Step A'])
        _mock_llm.is_configured.return_value = True
        _mock_llm.chat_completion.side_effect = [
            _llm_response(tool_calls=[
                _tool_call('mark_step_failed', {'step_index': 0, 'detail': 'could not do it'}, 'c1'),
            ]),
            _llm_response(content='Step failed.'),
        ]

        artifact = execute_plan(self.root, self.storage, self.profile, session_id)
        self.assertEqual(artifact.status, 'failed')
        self.assertEqual(artifact.step_progress[0]['status'], 'failed')

    def test_execute_emits_tool_events(self):
        session_id = self._make_session_with_ai_plan(steps=['Write file'])
        _mock_llm.is_configured.return_value = True
        _mock_llm.chat_completion.side_effect = [
            _llm_response(tool_calls=[
                _tool_call('write_file', {'path': 'out.txt', 'content': 'hello'}, 'c1'),
            ]),
            _llm_response(content='done'),
        ]

        events = []
        execute_plan(self.root, self.storage, self.profile, session_id,
                     emit=lambda e, d: events.append((e, d)))

        tool_events = [(e, d) for e, d in events if e == 'tool']
        self.assertTrue(len(tool_events) >= 1)
        self.assertEqual(tool_events[0][1]['name'], 'write_file')

    def test_execute_writes_phase_history(self):
        session_id = self._make_session_with_ai_plan(steps=['Step A'])
        _mock_llm.is_configured.return_value = True
        _mock_llm.chat_completion.side_effect = [
            _llm_response(tool_calls=[
                _tool_call('mark_step_done', {'step_index': 0}, 'c1'),
            ]),
            _llm_response(content='done'),
        ]

        artifact = execute_plan(self.root, self.storage, self.profile, session_id)
        phases = [h['phase'] for h in artifact.phase_history]
        self.assertIn('plan', phases)
        self.assertIn('execute', phases)

    def test_execute_raises_when_llm_not_configured(self):
        _mock_llm.is_configured.return_value = False
        plan = create_plan(self.root, self.storage, 'goal')
        with self.assertRaises(RuntimeError):
            execute_plan(self.root, self.storage, self.profile, plan.session_id)

    def test_execute_terminates_at_iteration_limit(self):
        """LLM that always returns tool calls should be capped at max_iterations."""
        session_id = self._make_session_with_ai_plan(steps=['Infinite step'])
        _mock_llm.is_configured.return_value = True
        # Always return a tool call, never a final message
        _mock_llm.chat_completion.return_value = _llm_response(tool_calls=[
            _tool_call('mark_step_done', {'step_index': 0}, 'c1'),
        ])
        _mock_llm.chat_completion.side_effect = None

        artifact = execute_plan(self.root, self.storage, self.profile, session_id)
        self.assertIsNotNone(artifact)

    def test_execute_actually_writes_file(self):
        session_id = self._make_session_with_ai_plan(steps=['Create hello.py'])
        _mock_llm.is_configured.return_value = True
        _mock_llm.chat_completion.side_effect = [
            _llm_response(tool_calls=[
                _tool_call('write_file', {'path': 'hello.py', 'content': 'print("hi")\n'}, 'c1'),
                _tool_call('mark_step_done', {'step_index': 0, 'detail': 'created'}, 'c2'),
            ]),
            _llm_response(content='done'),
        ]

        execute_plan(self.root, self.storage, self.profile, session_id)
        self.assertTrue((self.root / 'hello.py').exists())
        self.assertIn('print', (self.root / 'hello.py').read_text())


# ---------------------------------------------------------------------------
# recover_session
# ---------------------------------------------------------------------------

class RecoverSessionTests(unittest.TestCase):

    def setUp(self):
        _mock_llm.reset_mock()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'app.py').write_text('x = 1\n')
        self.storage = MarcoStorage(self.root)
        self.profile = _profile()

    def tearDown(self):
        self.tmp.cleanup()

    def _make_failed_session(self):
        plan = create_plan(self.root, self.storage, 'build app')
        sid = plan.session_id
        # Inject a failed validate state
        data = self.storage.read_json(self.storage.sessions / f'{sid}.json')
        data['phase'] = 'validate'
        data['status'] = 'failed'
        data['artifacts'] = {
            'command': 'python3 -m unittest discover -s tests -v',
            'returncode': 1,
            'stdout_tail': [],
            'stderr_tail': ['ImportError: No module named foo'],
        }
        data['step_progress'] = [{'step': 'install deps', 'status': 'failed',
                                   'detail': 'module missing', 'index': 0}]
        self.storage.write_json(self.storage.sessions / f'{sid}.json', data)
        return sid

    def test_recover_uses_llm_when_configured(self):
        sid = self._make_failed_session()
        _mock_llm.is_configured.return_value = True
        _mock_llm.chat_completion.side_effect = [
            _llm_response(tool_calls=[
                _tool_call('mark_step_done', {'step_index': 0, 'detail': 'fixed'}, 'c1'),
            ]),
            _llm_response(content='Fixed the import.'),
        ]

        events = []
        artifact = recover_session(self.root, self.storage, self.profile, sid,
                                   emit=lambda e, d: events.append((e, d)))

        self.assertEqual(artifact.phase, 'recover')
        self.assertTrue(any(e == 'start' for e, _ in events))
        self.assertTrue(any(e == 'done' for e, _ in events))
        # The LLM should have received the stderr context
        call_messages = _mock_llm.chat_completion.call_args_list[0][1].get('messages') \
            or _mock_llm.chat_completion.call_args_list[0][0][0]
        user_msg = next(m for m in call_messages if m['role'] == 'user')
        self.assertIn('ImportError', user_msg['content'])

    def test_recover_falls_back_to_static_when_no_llm(self):
        sid = self._make_failed_session()
        _mock_llm.is_configured.return_value = False

        artifact = recover_session(self.root, self.storage, self.profile, sid)
        self.assertEqual(artifact.phase, 'recover')
        self.assertIn('recovery_steps', artifact.artifacts)
        self.assertIsInstance(artifact.artifacts['recovery_steps'], list)

    def test_recover_can_fix_file_via_patch(self):
        sid = self._make_failed_session()
        _mock_llm.is_configured.return_value = True
        _mock_llm.chat_completion.side_effect = [
            _llm_response(tool_calls=[
                _tool_call('apply_patch_now', {
                    'target': 'app.py', 'name': 'fix-x',
                    'find': 'x = 1', 'replace': 'x = 2',
                }, 'c1'),
                _tool_call('mark_step_done', {'step_index': 0, 'detail': 'patched'}, 'c2'),
            ]),
            _llm_response(content='done'),
        ]

        recover_session(self.root, self.storage, self.profile, sid)
        self.assertEqual((self.root / 'app.py').read_text(), 'x = 2\n')


# ---------------------------------------------------------------------------
# validate_session -> auto-complete
# ---------------------------------------------------------------------------

class ValidateSessionTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.storage = MarcoStorage(self.root)
        self.profile = _profile()

    def tearDown(self):
        self.tmp.cleanup()

    def test_validate_pass_auto_completes(self):
        plan = create_plan(self.root, self.storage, 'test goal')
        # Use a command guaranteed to pass
        profile = MarcoProfile(
            safety_mode='workspace-write',
            pause_before_mutation=False,
            default_test_command='python3 --version',
        )
        artifact = validate_session(self.root, self.storage, profile, plan.session_id)
        self.assertEqual(artifact.phase, 'completed')
        self.assertEqual(artifact.status, 'completed')

    def test_validate_fail_stays_failed(self):
        plan = create_plan(self.root, self.storage, 'test goal')
        profile = MarcoProfile(
            safety_mode='workspace-write',
            pause_before_mutation=False,
            default_test_command='python3 -c "raise SystemExit(1)"',
        )
        artifact = validate_session(self.root, self.storage, profile, plan.session_id)
        self.assertEqual(artifact.phase, 'validate')
        self.assertEqual(artifact.status, 'failed')


if __name__ == '__main__':
    unittest.main()
