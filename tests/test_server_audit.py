from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.marco_v3.server_audit import record, tail


class AuditLogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'audit.log'

    def test_empty_tail(self) -> None:
        self.assertEqual(tail(path=self.path), [])

    def test_record_and_tail_newest_first(self) -> None:
        record('patch.propose', workspace='marco', params={'name': 'x'}, path=self.path)
        record('patch.apply', workspace='marco', params={'name': 'x'}, patch_id='abc', path=self.path)
        entries = tail(path=self.path)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].action, 'patch.apply')
        self.assertEqual(entries[0].patch_id, 'abc')
        self.assertEqual(entries[1].action, 'patch.propose')


if __name__ == '__main__':
    unittest.main()
