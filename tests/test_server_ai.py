from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import httpx

from src.marco_v3.server_auth import AuthConfig
from src.marco_v3.server_workspaces import add_workspace

# Preserve the real httpx.Client constructor before tests replace it.
_REAL_HTTPX_CLIENT = httpx.Client


def _make_mock_httpx_client(responder):
    """Create an httpx.Client with a MockTransport that calls responder(request) -> httpx.Response.

    Uses the preserved real constructor so this still works when tests patch httpx.Client.
    """
    return _REAL_HTTPX_CLIENT(transport=httpx.MockTransport(responder))


class AIEndpointsTestBase(unittest.TestCase):
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


class AIStatusTests(AIEndpointsTestBase):
    def test_not_configured(self) -> None:
        with mock.patch.dict('os.environ', {}, clear=True):
            res = self.client.get('/api/ai/status', headers=self.headers)
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertFalse(body['configured'])
        self.assertNotIn('deployment', body)

    def test_configured(self) -> None:
        env = {'AZURE_OPENAI_API_KEY': 'k', 'AZURE_OPENAI_ENDPOINT': 'https://x.cognitiveservices.azure.com'}
        with mock.patch.dict('os.environ', env, clear=True):
            res = self.client.get('/api/ai/status', headers=self.headers)
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body['configured'])
        # Default is gpt-5.3-chat — tuned for Rudolph's Azure deployment.
        self.assertTrue(body['deployment'])  # just confirm it's set; exact value is overridable
        self.assertNotIn('api_key', body)


class AIPlanTests(AIEndpointsTestBase):
    def test_requires_goal(self) -> None:
        res = self.client.post('/api/ai/plan', json={}, headers=self.headers)
        self.assertEqual(res.status_code, 400)

    def test_503_when_not_configured(self) -> None:
        with mock.patch.dict('os.environ', {}, clear=True):
            res = self.client.post(
                '/api/ai/plan',
                json={'goal': 'refactor auth'},
                headers=self.headers,
            )
        self.assertEqual(res.status_code, 503)

    def test_success_creates_session_with_ai_plan(self) -> None:
        plan_content = json.dumps({
            'goal': 'refactor auth',
            'steps': ['step 1', 'step 2'],
            'edit_targets': ['sample.py'],
            'risks': ['regression'],
            'validation': 'run tests',
        })
        env = {'AZURE_OPENAI_API_KEY': 'k', 'AZURE_OPENAI_ENDPOINT': 'https://x.openai.azure.com'}
        fake_response = {'choices': [{'message': {'content': plan_content}}]}

        with mock.patch.dict('os.environ', env, clear=True):
            with mock.patch('src.marco_v3.llm.chat_completion', return_value=fake_response):
                res = self.client.post(
                    '/api/ai/plan',
                    json={'goal': 'refactor auth'},
                    headers=self.headers,
                )

        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertIn('session_id', body)
        self.assertEqual(body['artifacts']['ai_source'], 'azure-openai')
        self.assertEqual(body['artifacts']['ai_plan']['steps'], ['step 1', 'step 2'])


class AIPatchSuggestionTests(AIEndpointsTestBase):
    def test_requires_description_and_target(self) -> None:
        res = self.client.post(
            '/api/ai/patch-suggestion',
            json={'target': 'sample.py'},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 400)

    def test_rejects_nonexistent_target(self) -> None:
        env = {'AZURE_OPENAI_API_KEY': 'k', 'AZURE_OPENAI_ENDPOINT': 'https://x.openai.azure.com'}
        with mock.patch.dict('os.environ', env, clear=True):
            res = self.client.post(
                '/api/ai/patch-suggestion',
                json={'target': 'does-not-exist.py', 'description': 'x'},
                headers=self.headers,
            )
        self.assertEqual(res.status_code, 400)

    def test_success_stages_proposal(self) -> None:
        suggestion = json.dumps({
            'name': 'bump',
            'target': 'sample.py',
            'find': 'value = 1',
            'replace': 'value = 42',
            'rationale': 'bump the value',
        })
        env = {'AZURE_OPENAI_API_KEY': 'k', 'AZURE_OPENAI_ENDPOINT': 'https://x.openai.azure.com'}

        # Mock at the llm.chat_completion level — patching httpx.Client globally
        # also hijacks the TestClient's internal transport, which we don't want.
        fake_response = {'choices': [{'message': {'content': suggestion}}]}

        with mock.patch.dict('os.environ', env, clear=True):
            with mock.patch('src.marco_v3.llm.chat_completion', return_value=fake_response):
                res = self.client.post(
                    '/api/ai/patch-suggestion',
                    json={'target': 'sample.py', 'description': 'bump value to 42'},
                    headers=self.headers,
                )

        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertIsNotNone(body['created_proposal'])
        self.assertEqual(body['created_proposal']['status'], 'pending')
        self.assertEqual(body['suggestion']['find'], 'value = 1')

        # Confirm the patch was actually staged (listable via normal endpoint).
        res = self.client.get('/api/patches', headers=self.headers)
        self.assertEqual(res.status_code, 200, res.text)
        patches = res.json()['patches']
        self.assertEqual(len(patches), 1)
        self.assertEqual(patches[0]['name'], 'bump')


if __name__ == '__main__':
    unittest.main()
