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
        # Legacy path (backwards compat shim).
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

    def test_add_and_list_note_new_path(self) -> None:
        # New unambiguous path at /api/memory/{kind}.
        res = self.client.post(
            '/api/memory/note',
            json={'key': 'mem1', 'topic': 't1', 'text': 'via new path'},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200)
        res = self.client.get('/api/memory/notes', headers=self.headers)
        self.assertEqual(res.status_code, 200)
        entries = res.json()['entries']
        self.assertTrue(any(e['key'] == 'mem1' for e in entries))

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


class WorkspacePreflightTests(ServerTestBase):
    """Tests for POST /api/workspaces/clone/preflight."""

    def test_preflight_rejected_non_https_host(self) -> None:
        res = self.client.post(
            '/api/workspaces/clone/preflight',
            json={'url': 'https://evil.example.com/repo.git'},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn('GitHub', res.json()['detail'])

    def test_preflight_missing_url(self) -> None:
        res = self.client.post(
            '/api/workspaces/clone/preflight',
            json={},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 400)

    def test_preflight_success(self) -> None:
        """Mocks subprocess so git ls-remote appears to succeed."""
        completed = mock.MagicMock()
        completed.returncode = 0
        completed.stdout = 'ref: refs/heads/main\tHEAD\nabc123\tHEAD\n'
        completed.stderr = ''

        with mock.patch('subprocess.run', return_value=completed):
            res = self.client.post(
                '/api/workspaces/clone/preflight',
                json={'url': 'https://github.com/user/repo.git'},
                headers=self.headers,
            )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body['ok'])
        self.assertEqual(body['default_branch'], 'main')

    def test_preflight_unreachable_repo(self) -> None:
        """git ls-remote exits non-zero → 422."""
        completed = mock.MagicMock()
        completed.returncode = 128
        completed.stdout = ''
        completed.stderr = 'ERROR: Repository not found.'

        with mock.patch('subprocess.run', return_value=completed):
            res = self.client.post(
                '/api/workspaces/clone/preflight',
                json={'url': 'https://github.com/nobody/nonexistent.git'},
                headers=self.headers,
            )
        self.assertEqual(res.status_code, 422)
        self.assertIn('Cannot reach', res.json()['detail'])

    def test_preflight_timeout(self) -> None:
        """git ls-remote times out → 504."""
        import subprocess

        with mock.patch('subprocess.run', side_effect=subprocess.TimeoutExpired(cmd='git', timeout=10)):
            res = self.client.post(
                '/api/workspaces/clone/preflight',
                json={'url': 'https://github.com/user/slow.git'},
                headers=self.headers,
            )
        self.assertEqual(res.status_code, 504)


class WorkspaceCloneCleanupTests(ServerTestBase):
    """Tests that clone failure leaves no partial directory behind."""

    def test_clone_failure_cleans_up_dest(self) -> None:
        """When git clone returns non-zero the dest directory is removed."""
        import subprocess

        completed = mock.MagicMock()
        completed.returncode = 1
        completed.stdout = ''
        completed.stderr = 'fatal: repository not found'

        # Track rmtree calls to verify cleanup happens.
        original_rmtree = __import__('shutil').rmtree
        rmtree_calls: list[str] = []

        def _spy_rmtree(path, **kwargs):
            rmtree_calls.append(str(path))
            original_rmtree(path, **kwargs)

        with mock.patch('subprocess.run', return_value=completed), \
             mock.patch('shutil.rmtree', side_effect=_spy_rmtree):
            res = self.client.post(
                '/api/workspaces/clone',
                json={'name': 'myclone', 'url': 'https://github.com/user/repo.git'},
                headers=self.headers,
            )

        self.assertEqual(res.status_code, 422)
        # rmtree must have been called (cleanup of partial dest).
        self.assertTrue(any('myclone' in p for p in rmtree_calls))

    def test_clone_timeout_cleans_up_dest(self) -> None:
        """When git clone times out the dest directory is also cleaned up."""
        import subprocess

        rmtree_calls: list[str] = []
        original_rmtree = __import__('shutil').rmtree

        def _spy_rmtree(path, **kwargs):
            rmtree_calls.append(str(path))
            # Don't actually call original since dest was never created.

        with mock.patch('subprocess.run', side_effect=subprocess.TimeoutExpired(cmd='git', timeout=120)), \
             mock.patch('shutil.rmtree', side_effect=_spy_rmtree):
            res = self.client.post(
                '/api/workspaces/clone',
                json={'name': 'slowclone', 'url': 'https://github.com/user/repo.git'},
                headers=self.headers,
            )

        self.assertEqual(res.status_code, 504)
        self.assertTrue(any('slowclone' in p for p in rmtree_calls))


if __name__ == '__main__':
    unittest.main()
