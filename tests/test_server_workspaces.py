from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.marco_v3.server_workspaces import (
    add_workspace,
    ensure_workspace_from_cwd,
    get_active,
    load_registry,
    remove_workspace,
    set_active,
)


class WorkspaceRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.registry = Path(self.tmp.name) / 'workspaces.json'
        self.repo = Path(self.tmp.name) / 'repo'
        self.repo.mkdir()
        self.repo2 = Path(self.tmp.name) / 'repo2'
        self.repo2.mkdir()

    def test_add_and_activate(self) -> None:
        ws = add_workspace('alpha', self.repo, registry_path=self.registry)
        self.assertEqual(ws.name, 'alpha')
        active = get_active(registry_path=self.registry)
        self.assertIsNotNone(active)
        assert active is not None
        self.assertEqual(active.name, 'alpha')

    def test_add_rejects_missing_path(self) -> None:
        with self.assertRaises(ValueError):
            add_workspace('x', Path(self.tmp.name) / 'missing', registry_path=self.registry)

    def test_add_rejects_duplicate_name(self) -> None:
        add_workspace('alpha', self.repo, registry_path=self.registry)
        with self.assertRaises(ValueError):
            add_workspace('alpha', self.repo2, registry_path=self.registry)

    def test_add_rejects_duplicate_path(self) -> None:
        add_workspace('alpha', self.repo, registry_path=self.registry)
        with self.assertRaises(ValueError):
            add_workspace('beta', self.repo, registry_path=self.registry)

    def test_switch_active(self) -> None:
        add_workspace('alpha', self.repo, registry_path=self.registry)
        add_workspace('beta', self.repo2, registry_path=self.registry)
        set_active('beta', registry_path=self.registry)
        active = get_active(registry_path=self.registry)
        assert active is not None
        self.assertEqual(active.name, 'beta')

    def test_remove(self) -> None:
        add_workspace('alpha', self.repo, registry_path=self.registry)
        add_workspace('beta', self.repo2, registry_path=self.registry)
        self.assertTrue(remove_workspace('alpha', registry_path=self.registry))
        self.assertFalse(remove_workspace('alpha', registry_path=self.registry))
        registry = load_registry(self.registry)
        self.assertEqual(len(registry.workspaces), 1)
        self.assertEqual(registry.active, 'beta')

    def test_ensure_from_cwd_skips_when_not_git(self) -> None:
        import os

        cwd_before = os.getcwd()
        os.chdir(self.repo)
        try:
            ws = ensure_workspace_from_cwd(registry_path=self.registry)
            self.assertIsNone(ws)
        finally:
            os.chdir(cwd_before)


    def test_ensure_from_cwd_finds_parent_git_repo(self) -> None:
        import os

        (self.repo / '.git').mkdir()
        nested = self.repo / 'nested' / 'deeper'
        nested.mkdir(parents=True)
        cwd_before = os.getcwd()
        os.chdir(nested)
        try:
            ws = ensure_workspace_from_cwd(registry_path=self.registry)
            self.assertIsNotNone(ws)
            assert ws is not None
            self.assertEqual(ws.name, 'repo')
            self.assertEqual(Path(ws.path), self.repo.resolve())
        finally:
            os.chdir(cwd_before)


if __name__ == '__main__':
    unittest.main()
