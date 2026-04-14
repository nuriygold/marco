from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.marco_v3.server_auth import AuthConfig
from src.marco_v3.server_workspaces import add_workspace


class PatchWorkflowTests(unittest.TestCase):
    """End-to-end: propose → show → reject bad confirm → apply with confirm → rollback.

    Every mutation must also land in the audit log.
    """

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

        add_workspace('testws', self.repo, registry_path=self.registry)

        self._audit_patch = mock.patch('src.marco_v3.server_audit.AUDIT_PATH', self.audit)
        self._audit_patch.start()
        self.addCleanup(self._audit_patch.stop)

        from fastapi.testclient import TestClient

        from src.marco_v3.server import create_app

        self.client = TestClient(create_app(registry_path=self.registry, auth=AuthConfig(token='t', secret='s')))
        self.headers = {'Authorization': 'Bearer t'}

    def _propose(self):
        return self.client.post(
            '/api/patches/propose',
            json={'name': 'bump', 'target': 'sample.py', 'find': '1', 'replace': '2'},
            headers=self.headers,
        )

    def test_full_workflow_with_typed_confirm(self) -> None:
        # Propose
        res = self._propose()
        self.assertEqual(res.status_code, 200, res.text)
        patch_id = res.json()['patch_id']
        self.assertEqual(res.json()['status'], 'pending')

        # Show diff
        res = self.client.get(f'/api/patches/{patch_id}', headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertIn('sample.py', res.json()['diff'])

        # Apply with wrong confirm_name → rejected
        res = self.client.post(
            f'/api/patches/{patch_id}/apply',
            json={'confirm_name': 'wrong'},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual((self.repo / 'sample.py').read_text(), 'value = 1\n', 'file must not change on rejected apply')

        # Apply with correct confirm_name
        res = self.client.post(
            f'/api/patches/{patch_id}/apply',
            json={'confirm_name': 'bump'},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()['status'], 'applied')
        self.assertIn('value = 2', (self.repo / 'sample.py').read_text())

        # Rollback
        res = self.client.post(f'/api/patches/{patch_id}/rollback', headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['status'], 'rolled_back')
        self.assertIn('value = 1', (self.repo / 'sample.py').read_text())

        # Audit log
        res = self.client.get('/api/audit', headers=self.headers)
        entries = res.json()['entries']
        actions = [e['action'] for e in entries]
        self.assertIn('patch.propose', actions)
        self.assertIn('patch.apply', actions)
        self.assertIn('patch.rollback', actions)
        self.assertIn('patch.apply.rejected', actions)

    def test_propose_validates_required_fields(self) -> None:
        res = self.client.post('/api/patches/propose', json={'name': 'x'}, headers=self.headers)
        self.assertEqual(res.status_code, 400)

    def test_propose_missing_find_text(self) -> None:
        res = self.client.post(
            '/api/patches/propose',
            json={'name': 'bad', 'target': 'sample.py', 'find': 'nopresent', 'replace': 'x'},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 400)


if __name__ == '__main__':
    unittest.main()
