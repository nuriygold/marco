from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.marco_v3 import chat_tools
from src.marco_v3.storage import MarcoStorage


class ToolDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'sample.py').write_text('value = 1\n')
        (self.root / 'README.md').write_text('# sample\n')
        self.storage = MarcoStorage(self.root)
        self.audit_calls: list[tuple[str, dict]] = []

        def audit(action, workspace, params=None, patch_id=None, result='ok'):
            self.audit_calls.append((action, {'workspace': workspace, 'params': params or {}, 'patch_id': patch_id}))

        self.audit = audit

    def _call(self, tool_name, **args):
        return chat_tools.dispatch_tool(
            tool_name, args,
            root=self.root, storage=self.storage,
            audit=self.audit, workspace_name='test',
        )

    def test_workspace_status(self) -> None:
        res = self._call('workspace_status')
        self.assertEqual(res['workspace'], 'test')
        self.assertGreaterEqual(res['file_count'], 2)

    def test_find_files(self) -> None:
        res = self._call('find_files', pattern='*.py')
        self.assertIn('sample.py', res['matches'])

    def test_find_files_requires_pattern(self) -> None:
        self.assertIn('error', self._call('find_files'))

    def test_lookup_content(self) -> None:
        res = self._call('lookup_content', needle='value')
        self.assertTrue(any('sample.py' in m['file'] for m in res['matches']))

    def test_save_memory_note(self) -> None:
        res = self._call('save_memory', kind='note', key='k', topic='t', text='body')
        self.assertEqual(res['saved']['kind'], 'note')
        self.assertEqual(self.audit_calls[0][0], 'memory.add.note')

    def test_save_memory_rejects_invalid_kind(self) -> None:
        res = self._call('save_memory', kind='bogus', key='k', topic='t', text='b')
        self.assertIn('error', res)

    def test_create_plan(self) -> None:
        res = self._call('create_plan', goal='refactor auth')
        self.assertIn('plan', res)
        self.assertEqual(res['plan']['goal'], 'refactor auth')
        self.assertEqual(self.audit_calls[0][0], 'session.plan')

    def test_suggest_patch_stages_proposal(self) -> None:
        res = self._call(
            'suggest_patch',
            target='sample.py', name='bump',
            find='value = 1', replace='value = 42',
        )
        self.assertIn('proposal', res)
        self.assertEqual(res['proposal']['status'], 'pending')
        self.assertEqual(self.audit_calls[0][0], 'patch.propose')
        # File must NOT have been modified.
        self.assertEqual((self.root / 'sample.py').read_text(), 'value = 1\n')

    def test_suggest_patch_rejects_missing_find(self) -> None:
        res = self._call(
            'suggest_patch',
            target='sample.py', name='bad',
            find='notpresent', replace='x',
        )
        self.assertIn('error', res)

    def test_unknown_tool(self) -> None:
        res = self._call('fly_to_mars', destination='mars')
        self.assertIn('error', res)


class ConversationPersistenceTests(unittest.TestCase):
    def test_append_and_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = chat_tools.conversation_path(root, 'abc')
            chat_tools.append_chat_message(path, {'role': 'user', 'content': 'hi'})
            chat_tools.append_chat_message(path, {'role': 'assistant', 'content': 'hello'})
            msgs = chat_tools.load_chat_messages(path)
            self.assertEqual(len(msgs), 2)
            self.assertEqual(msgs[0]['role'], 'user')

    def test_load_nonexistent_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            msgs = chat_tools.load_chat_messages(Path(tmp) / 'nope.jsonl')
            self.assertEqual(msgs, [])


if __name__ == '__main__':
    unittest.main()
