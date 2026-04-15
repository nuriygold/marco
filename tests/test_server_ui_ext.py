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


if __name__ == '__main__':
    unittest.main()
