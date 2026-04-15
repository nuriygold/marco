"""Tests for the chat orchestrator endpoint (/api/ai/chat).

Mocks llm.chat_completion at the module level to simulate tool-calling
responses from the LLM, and verifies that the server dispatches tools
correctly and persists transcripts.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.marco_v3 import chat_tools
from src.marco_v3.server_auth import AuthConfig
from src.marco_v3.server_workspaces import add_workspace


def _msg_with_tool_call(tool_name: str, arguments: dict, call_id: str = 'call_1'):
    return {
        'choices': [{
            'message': {
                'role': 'assistant',
                'content': None,
                'tool_calls': [{
                    'id': call_id,
                    'type': 'function',
                    'function': {'name': tool_name, 'arguments': json.dumps(arguments)},
                }],
            },
        }],
    }


def _msg_with_content(content: str):
    return {
        'choices': [{'message': {'role': 'assistant', 'content': content}}],
    }


def _parse_sse_events(text: str) -> list[tuple[str, dict]]:
    """Parse SSE response body into [(event_name, data_dict), …]."""
    events: list[tuple[str, dict]] = []
    current_event: str | None = None
    current_data: list[str] = []
    for line in text.splitlines():
        if line.startswith('event: '):
            current_event = line[7:]
        elif line.startswith('data: '):
            current_data.append(line[6:])
        elif line == '' and current_event is not None:
            raw = '\n'.join(current_data)
            try:
                events.append((current_event, json.loads(raw)))
            except json.JSONDecodeError:
                events.append((current_event, {}))
            current_event = None
            current_data = []
    return events


def _get_done(text: str) -> dict | None:
    """Return the payload of the first 'done' SSE event, or None."""
    for name, data in _parse_sse_events(text):
        if name == 'done':
            return data
    return None


class ChatOrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            from fastapi.testclient import TestClient  # noqa: F401
        except ImportError:
            self.skipTest('fastapi not installed')

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.registry = Path(self.tmp.name) / 'workspaces.json'
        self.audit = Path(self.tmp.name) / 'audit.log'
        self.repo = Path(self.tmp.name) / 'repo'
        self.repo.mkdir()
        (self.repo / 'sample.py').write_text('value = 1\n')
        (self.repo / 'README.md').write_text('# sample\n')
        add_workspace('testws', self.repo, registry_path=self.registry)

        self._audit_patch = mock.patch('src.marco_v3.server_audit.AUDIT_PATH', self.audit)
        self._audit_patch.start()
        self.addCleanup(self._audit_patch.stop)

        from fastapi.testclient import TestClient

        from src.marco_v3.server import create_app

        self.client = TestClient(
            create_app(registry_path=self.registry, auth=AuthConfig(token='t', secret='s'))
        )
        self.headers = {'Authorization': 'Bearer t'}
        self.env = {
            'AZURE_OPENAI_API_KEY': 'k',
            'AZURE_OPENAI_ENDPOINT': 'https://x.cognitiveservices.azure.com',
        }

    def test_requires_message(self) -> None:
        res = self.client.post('/api/ai/chat', json={}, headers=self.headers)
        self.assertEqual(res.status_code, 400)

    def test_503_when_not_configured(self) -> None:
        with mock.patch.dict('os.environ', {}, clear=True):
            res = self.client.post(
                '/api/ai/chat',
                json={'message': 'hi'},
                headers=self.headers,
            )
        self.assertEqual(res.status_code, 503)

    def test_direct_response_no_tools(self) -> None:
        # "hello" is neither heavy nor light → defaults to heavy, bypasses lite gate.
        with mock.patch.dict('os.environ', self.env, clear=True):
            with mock.patch(
                'src.marco_v3.llm.chat_completion',
                return_value=_msg_with_content('Hello Rudolph. How can I help?'),
            ):
                res = self.client.post(
                    '/api/ai/chat',
                    json={'message': 'hello', 'force_heavy': True},
                    headers=self.headers,
                )
        self.assertEqual(res.status_code, 200, res.text)
        done = _get_done(res.text)
        self.assertIsNotNone(done, f'no done event in SSE stream: {res.text!r}')
        self.assertEqual(done['role'], 'assistant')
        self.assertIn('Rudolph', done['content'])
        self.assertEqual(done['tools_used'], [])

    def test_tool_call_then_response(self) -> None:
        # Simulate: user asks, model calls workspace_status, then responds.
        # force_heavy=True bypasses the lite-gate (message contains "what").
        responses = iter([
            _msg_with_tool_call('workspace_status', {}, call_id='c1'),
            _msg_with_content('Your workspace has some files.'),
        ])

        def fake_chat(*args, **kwargs):
            return next(responses)

        with mock.patch.dict('os.environ', self.env, clear=True):
            with mock.patch('src.marco_v3.llm.chat_completion', side_effect=fake_chat):
                res = self.client.post(
                    '/api/ai/chat',
                    json={'message': 'what is in this repo?', 'force_heavy': True},
                    headers=self.headers,
                )
        self.assertEqual(res.status_code, 200, res.text)
        done = _get_done(res.text)
        self.assertIsNotNone(done, f'no done event in SSE stream: {res.text!r}')
        tools = done['tools_used']
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]['name'], 'workspace_status')
        self.assertIn('file_count', tools[0]['result'])

    def test_tool_call_mutating_patch_stages_proposal(self) -> None:
        responses = iter([
            _msg_with_tool_call('suggest_patch', {
                'target': 'sample.py',
                'name': 'bump',
                'find': 'value = 1',
                'replace': 'value = 42',
            }, call_id='c1'),
            _msg_with_content('Staged. Go review it on the Patches page.'),
        ])

        def fake_chat(*args, **kwargs):
            return next(responses)

        with mock.patch.dict('os.environ', self.env, clear=True):
            with mock.patch('src.marco_v3.llm.chat_completion', side_effect=fake_chat):
                res = self.client.post(
                    '/api/ai/chat',
                    json={'message': 'bump sample.py value to 42', 'force_heavy': True},
                    headers=self.headers,
                )
        self.assertEqual(res.status_code, 200, res.text)
        done = _get_done(res.text)
        self.assertIsNotNone(done, f'no done event in SSE stream: {res.text!r}')
        tool_result = done['tools_used'][0]['result']
        self.assertIn('proposal', tool_result)
        self.assertEqual(tool_result['proposal']['status'], 'pending')
        # File untouched — staging must not apply.
        self.assertEqual((self.repo / 'sample.py').read_text(), 'value = 1\n')

    def test_transcript_persisted(self) -> None:
        with mock.patch.dict('os.environ', self.env, clear=True):
            with mock.patch(
                'src.marco_v3.llm.chat_completion',
                return_value=_msg_with_content('ok'),
            ):
                self.client.post(
                    '/api/ai/chat',
                    json={'message': 'first', 'conversation_id': 'session1'},
                    headers=self.headers,
                )

        path = chat_tools.conversation_path(self.repo, 'session1')
        msgs = chat_tools.load_chat_messages(path)
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0]['role'], 'user')
        self.assertEqual(msgs[0]['content'], 'first')
        self.assertEqual(msgs[1]['role'], 'assistant')

    def test_get_conversation(self) -> None:
        path = chat_tools.conversation_path(self.repo, 'loadme')
        chat_tools.append_chat_message(path, {'role': 'user', 'content': 'ping'})
        res = self.client.get('/api/ai/conversations/loadme', headers=self.headers)
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body['conversation_id'], 'loadme')
        self.assertEqual(body['messages'][0]['content'], 'ping')

    def test_delete_conversation(self) -> None:
        path = chat_tools.conversation_path(self.repo, 'killme')
        chat_tools.append_chat_message(path, {'role': 'user', 'content': 'x'})
        self.assertTrue(path.exists())
        res = self.client.delete('/api/ai/conversations/killme', headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertFalse(path.exists())


if __name__ == '__main__':
    unittest.main()
