from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.marco_v3.server_auth import AuthConfig
from src.marco_v3.server_workspaces import add_workspace


class ServerTestBase(unittest.TestCase):
    """Base class: spins up a FastAPI TestClient against temp workspace + registry."""

    def setUp(self) -> None:
        try:
            from fastapi.testclient import TestClient  # noqa: F401
        except ImportError:
            self.skipTest('fastapi not installed')

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / 'home'
        self.home.mkdir()
        self.registry = self.home / '.marco' / 'workspaces.json'
        self.audit = self.home / '.marco' / 'audit.log'

        # Create a fake repo that will be the workspace root.
        self.repo = Path(self.tmp.name) / 'repo'
        self.repo.mkdir()
        (self.repo / 'sample.py').write_text('value = 1\n')
        (self.repo / 'README.md').write_text('# sample\n')
        (self.repo / 'package.json').write_text('{"scripts": {"test": "echo test"}}')

        add_workspace('testws', self.repo, registry_path=self.registry)

        # Patch the module-level audit path so mutations route to our temp file.
        self._audit_patch = mock.patch('src.marco_v3.server_audit.AUDIT_PATH', self.audit)
        self._audit_patch.start()
        self.addCleanup(self._audit_patch.stop)

        from fastapi.testclient import TestClient

        from src.marco_v3.server import create_app

        self.app = create_app(registry_path=self.registry, auth=AuthConfig(token='t', secret='s'))
        self.client = TestClient(self.app)
        self.headers = {'Authorization': 'Bearer t'}


class ReadOnlyEndpointsTests(ServerTestBase):
    def test_unauthorized_rejected(self) -> None:
        res = self.client.get('/api/status')
        self.assertEqual(res.status_code, 401)

    def test_healthz_public(self) -> None:
        res = self.client.get('/healthz')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['status'], 'ok')

    def test_status(self) -> None:
        res = self.client.get('/api/status', headers=self.headers)
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body['workspace'], 'testws')
        self.assertGreaterEqual(body['file_count'], 3)

    def test_find_and_lookup(self) -> None:
        res = self.client.get('/api/find?pattern=*.py', headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertIn('sample.py', res.json()['matches'])

        res = self.client.get('/api/lookup?q=value', headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(any('sample.py' in m['file'] for m in res.json()['matches']))

    def test_scripts_discovery(self) -> None:
        res = self.client.get('/api/scripts', headers=self.headers)
        self.assertEqual(res.status_code, 200)
        names = [s['name'] for s in res.json()['scripts']]
        self.assertIn('test', names)


class MemoryEndpointsTests(ServerTestBase):
    def test_add_and_list_note(self) -> None:
        res = self.client.post(
            '/api/note',
            json={'key': 'k1', 'topic': 't1', 'text': 'some detail'},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200)
        res = self.client.get('/api/notes', headers=self.headers)
        self.assertEqual(res.status_code, 200)
        entries = res.json()['entries']
        self.assertTrue(any(e['key'] == 'k1' for e in entries))

    def test_recall_finds_entry(self) -> None:
        self.client.post(
            '/api/decision',
            json={'key': 'auth.jwt', 'topic': 'security', 'text': 'JWT chosen'},
            headers=self.headers,
        )
        res = self.client.get('/api/recall?q=jwt', headers=self.headers)
        self.assertEqual(res.status_code, 200)
        matches = res.json()['matches']
        self.assertTrue(matches)
        self.assertEqual(matches[0]['key'], 'auth.jwt')


class WorkspaceEndpointsTests(ServerTestBase):
    def test_list_and_switch(self) -> None:
        other_repo = Path(self.tmp.name) / 'other'
        other_repo.mkdir()
        add_workspace('other', other_repo, registry_path=self.registry)

        res = self.client.get('/api/workspaces', headers=self.headers)
        self.assertEqual(res.status_code, 200)
        names = [ws['name'] for ws in res.json()['workspaces']]
        self.assertIn('testws', names)
        self.assertIn('other', names)

        res = self.client.post('/api/workspaces/active', json={'name': 'other'}, headers=self.headers)
        self.assertEqual(res.status_code, 200)
        res = self.client.get('/api/workspaces', headers=self.headers)
        self.assertEqual(res.json()['active'], 'other')

    def test_add_unknown_path_rejected(self) -> None:
        res = self.client.post(
            '/api/workspaces',
            json={'name': 'bogus', 'path': '/does/not/exist'},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 400)


if __name__ == '__main__':
    unittest.main()
