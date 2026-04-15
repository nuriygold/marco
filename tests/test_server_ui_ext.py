"""Tests for the UI shell additions: /help page, workspace candidates, console smoke."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.marco_v3.server_auth import AuthConfig
from src.marco_v3.server_workspaces import add_workspace


class UiShellTestBase(unittest.TestCase):
    def setUp(self) -> None:
        try:
            from fastapi.testclient import TestClient  # noqa: F401
        except ImportError:
            self.skipTest('fastapi not installed')

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.home = root / 'home'
        self.home.mkdir()
        self.registry = self.home / '.marco' / 'workspaces.json'
        self.audit = self.home / '.marco' / 'audit.log'

        self.repo = root / 'repo'
        self.repo.mkdir()
        (self.repo / '.git').mkdir()
        (self.repo / 'sample.py').write_text('x = 1\n')
        add_workspace('testws', self.repo, registry_path=self.registry)

        self._audit_patch = mock.patch('src.marco_v3.server_audit.AUDIT_PATH', self.audit)
        self._audit_patch.start()
        self.addCleanup(self._audit_patch.stop)

        from fastapi.testclient import TestClient

        from src.marco_v3.server import create_app

        self.app = create_app(registry_path=self.registry, auth=AuthConfig(token='t', secret='s'))
        self.client = TestClient(self.app)
        self.headers = {'Authorization': 'Bearer t'}


class HelpPageTests(UiShellTestBase):
    def test_help_renders(self) -> None:
        res = self.client.get('/help', headers=self.headers)
        self.assertEqual(res.status_code, 200)
        body = res.text
        self.assertIn('Command cheat sheet', body)
        self.assertIn('Console phrasings', body)
        self.assertIn('CLI equivalents', body)
        self.assertIn('Replay guided tour', body)


class ConsoleSmokeTests(UiShellTestBase):
    def test_console_renders_single_scroll(self) -> None:
        res = self.client.get('/console', headers=self.headers)
        self.assertEqual(res.status_code, 200)
        body = res.text
        # Transcript container is present.
        self.assertIn('marco-chat-transcript', body)
        # Composer is marked sticky via class.
        self.assertIn('marco-console-composer', body)
        # The old fixed-height wrapper is gone.
        self.assertNotIn('calc(100dvh', body)


class WorkspaceCandidatesTests(UiShellTestBase):
    def _mk_repo(self, parent: Path, name: str) -> Path:
        p = parent / name
        p.mkdir()
        (p / '.git').mkdir()
        return p

    def test_candidates_detected(self) -> None:
        scan_root = Path(self.tmp.name) / 'scan'
        scan_root.mkdir()
        alpha = self._mk_repo(scan_root, 'alpha')
        bravo = self._mk_repo(scan_root, 'bravo')
        # Non-git directory — should be skipped.
        (scan_root / 'not_a_repo').mkdir()

        with mock.patch.dict(os.environ, {'MARCO_WORKSPACE_ROOT': str(scan_root)}):
            res = self.client.get('/api/workspaces/candidates', headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        names = [c['name'] for c in data['candidates']]
        paths = [c['path'] for c in data['candidates']]
        self.assertIn('alpha', names)
        self.assertIn('bravo', names)
        self.assertNotIn('not_a_repo', names)
        self.assertIn(str(alpha.resolve()), paths)
        self.assertIn(str(bravo.resolve()), paths)

    def test_registered_paths_excluded(self) -> None:
        scan_root = Path(self.tmp.name) / 'scan'
        scan_root.mkdir()
        existing = self._mk_repo(scan_root, 'already-here')
        add_workspace('already-here', existing, registry_path=self.registry)
        self._mk_repo(scan_root, 'fresh')

        with mock.patch.dict(os.environ, {'MARCO_WORKSPACE_ROOT': str(scan_root)}):
            res = self.client.get('/api/workspaces/candidates', headers=self.headers)
        self.assertEqual(res.status_code, 200)
        names = [c['name'] for c in res.json()['candidates']]
        self.assertIn('fresh', names)
        self.assertNotIn('already-here', names)

    def test_missing_root_returns_empty(self) -> None:
        with mock.patch.dict(os.environ, {'MARCO_WORKSPACE_ROOT': '/does/not/exist/at/all'}):
            res = self.client.get('/api/workspaces/candidates', headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['candidates'], [])


class DashboardStillRendersTests(UiShellTestBase):
    def test_dashboard_renders_with_nautical_shell(self) -> None:
        res = self.client.get('/', headers=self.headers)
        self.assertEqual(res.status_code, 200)
        body = res.text
        # Logo + sidebar chrome present.
        self.assertIn('Marco', body)
        self.assertIn('marco-sidebar', body)
        self.assertIn('Start tutorial', body)
        # Help link in nav.
        self.assertIn('Cheat sheet', body)
        # Add-workspace modal trigger present.
        self.assertIn('Add workspace', body)


class ValidatePathTests(UiShellTestBase):
    def test_existing_dir_returns_exists_true(self) -> None:
        res = self.client.post(
            '/api/validate-path', json={'path': str(self.repo)}, headers=self.headers
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['exists'])
        self.assertTrue(data['is_git'])

    def test_missing_path_returns_exists_false(self) -> None:
        res = self.client.post(
            '/api/validate-path', json={'path': '/does/not/exist/9x9'}, headers=self.headers
        )
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json()['exists'])

    def test_empty_path_rejected(self) -> None:
        res = self.client.post('/api/validate-path', json={'path': ''}, headers=self.headers)
        self.assertEqual(res.status_code, 400)


class CloneWorkspaceTests(UiShellTestBase):
    def test_non_https_url_rejected(self) -> None:
        res = self.client.post(
            '/api/workspaces/clone',
            json={'url': 'git@github.com:user/repo.git', 'name': 'test'},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 400)

    def test_random_https_url_rejected(self) -> None:
        res = self.client.post(
            '/api/workspaces/clone',
            json={'url': 'https://example.com/repo.git', 'name': 'test'},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 400)

    def test_missing_fields_rejected(self) -> None:
        res = self.client.post(
            '/api/workspaces/clone',
            json={'url': 'https://github.com/user/repo.git'},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 400)

    def test_clone_invokes_git(self) -> None:
        import subprocess as _sp

        # The endpoint clones into Path.home() / '.marco' / 'clones' / <name>.
        # We intercept subprocess.run and actually create that directory so that
        # add_workspace's existence check passes.
        clone_root = Path.home() / '.marco' / 'clones'
        dest = clone_root / 'marco-test-clone-deleteme'

        git_called: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            git_called.append(cmd)
            dest.mkdir(parents=True, exist_ok=True)
            (dest / '.git').mkdir(exist_ok=True)
            return _sp.CompletedProcess(cmd, returncode=0, stdout='', stderr='')

        try:
            with mock.patch('subprocess.run', side_effect=fake_run):
                res = self.client.post(
                    '/api/workspaces/clone',
                    json={'url': 'https://github.com/user/myrepo.git', 'name': 'marco-test-clone-deleteme'},
                    headers=self.headers,
                )
            self.assertEqual(res.status_code, 200, res.text)
            self.assertTrue(any('git' in str(c) for c in git_called), 'git was never called')
            data = res.json()
            self.assertEqual(data['name'], 'marco-test-clone-deleteme')
        finally:
            # Clean up the real directory we created.
            import shutil
            if dest.exists():
                shutil.rmtree(dest, ignore_errors=True)
            # Remove the workspace we registered so it doesn't pollute other tests.
            from src.marco_v3.server_workspaces import remove_workspace
            remove_workspace('marco-test-clone-deleteme')


if __name__ == '__main__':
    unittest.main()
