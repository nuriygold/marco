from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.marco_v3.autonomy import create_plan, resume_session
from src.marco_v3.config import MarcoProfile
from src.marco_v3.memory import add_entry, recall
from src.marco_v3.patches import apply_patch, propose_patch, rollback_patch
from src.marco_v3.repo_intel import discover_env_vars, discover_scripts, scan_repository
from src.marco_v3.scaffold import scaffold_component, scaffold_page, scaffold_route, scaffold_service
from src.marco_v3.storage import MarcoStorage


class MarcoV3MVPTests(unittest.TestCase):
    def test_repo_scan_counts_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'src').mkdir()
            (root / 'src/main.py').write_text('print("hi")\n')
            (root / 'README.md').write_text('# test\n')
            scan = scan_repository(root)
            self.assertEqual(scan.file_count, 2)
            self.assertIn('.py', scan.by_extension)

    def test_patch_propose_apply_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / 'sample.py'
            target.write_text('value = 1\n')
            storage = MarcoStorage(root)
            proposal = propose_patch(storage, root, name='bump', target='sample.py', find_text='1', replace_text='2')
            self.assertEqual(proposal.status, 'pending')

            profile = MarcoProfile(pause_before_mutation=False)
            applied = apply_patch(storage, root, profile, proposal.patch_id, force=True)
            self.assertEqual(applied.status, 'applied')
            self.assertIn('2', target.read_text())

            rolled = rollback_patch(storage, root, proposal.patch_id)
            self.assertEqual(rolled.status, 'rolled_back')
            self.assertIn('1', target.read_text())

    def test_memory_notebook_recall(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = MarcoStorage(root)
            add_entry(storage, kind='note', key='db.pool', topic='database', text='pool size is 10')
            add_entry(storage, kind='decision', key='auth.jwt', topic='security', text='JWT chosen for service auth')
            hits = recall(storage, 'pool database')
            self.assertTrue(hits)
            self.assertEqual(hits[0].key, 'db.pool')

    def test_script_and_env_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'package.json').write_text(json.dumps({'scripts': {'test': 'pytest -q', 'build': 'npm run lint'}}))
            (root / 'app.py').write_text('import os\nos.getenv("API_KEY")\n')
            scripts = discover_scripts(root)
            env_vars = discover_env_vars(root)
            self.assertTrue(any(s.name == 'test' for s in scripts))
            self.assertIn('API_KEY', env_vars)

    def test_scaffold_generators_create_expected_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'src').mkdir()
            page = scaffold_page(root, 'home')
            component = scaffold_component(root, 'hero')
            route = scaffold_route(root, 'home')
            service = scaffold_service(root, 'auth')
            self.assertTrue((root / page.path).exists())
            self.assertTrue((root / component.path).exists())
            self.assertTrue((root / route.path).exists())
            self.assertTrue((root / service.path).exists())

    def test_session_persistence_and_resume(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'src').mkdir()
            (root / 'src/main.py').write_text('print("ok")\n')
            storage = MarcoStorage(root)
            planned = create_plan(root, storage, 'add health endpoint')
            resumed = resume_session(storage, planned.session_id)
            self.assertEqual(resumed.session_id, planned.session_id)
            self.assertEqual(resumed.phase, 'plan')


if __name__ == '__main__':
    unittest.main()
