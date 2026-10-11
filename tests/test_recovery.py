"""Recovery contracts established before extracting the execution pipeline."""
import errno
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from photosort.core import Organizer, rename_exclusive


class PowerLoss(BaseException):
    """Bypass normal exception handling, like termination of the worker."""


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.source, self.target, self.job = [self.base / p for p in ('source', 'target', 'job')]
        self.source.mkdir()
        self.photo = self.source / 'photo.jpg'
        self.photo.write_bytes(b'original media' * 100)
        os.utime(self.photo, (1710000000, 1710000000))
        self.plan = Organizer(self.job).plan(self.source, self.target)
        self.destination = Path(self.plan['files'][0]['destination'])
        self.plan_bytes = (self.job / 'plan.json').read_bytes()
        self.identity = hashlib.sha256(json.dumps(self.plan, sort_keys=True).encode()).hexdigest()

    def tearDown(self):
        self.temp.cleanup()

    def cross_device(self, source, target):
        if source == self.photo:
            raise OSError(errno.EXDEV, 'forced cross-device move')
        return rename_exclusive(source, target)

    def assert_finished(self):
        Organizer(self.job).apply()
        self.assertFalse(self.photo.exists())
        self.assertEqual(self.destination.read_bytes(), b'original media' * 100)
        self.assertEqual((self.job / 'plan.json').read_bytes(), self.plan_bytes)
        journal = (self.job / 'journal.jsonl').read_bytes()
        Organizer(self.job).apply()
        self.assertEqual((self.job / 'journal.jsonl').read_bytes(), journal)
        self.assertEqual(json.loads((self.job / 'progress.json').read_text())['stage'], 'complete')

    def crash_after_record(self, state):
        real_fsync = os.fsync
        def fsync(fd):
            real_fsync(fd)
            journal = self.job / 'journal.jsonl'
            if journal.exists():
                lines = journal.read_bytes().splitlines()
                if lines and json.loads(lines[-1])['status'] == state:
                    raise PowerLoss(state)
        with patch('photosort.core.rename_exclusive', self.cross_device), patch('os.fsync', fsync):
            with self.assertRaises(PowerLoss):
                Organizer(self.job).apply()

    def test_recover_after_copy_ready_record(self):
        self.crash_after_record('copy_ready')
        self.assertTrue(self.photo.exists())
        self.assertFalse(self.destination.exists())
        with patch('photosort.core.rename_exclusive', self.cross_device):
            self.assert_finished()

    def test_recover_after_published_copy_record(self):
        self.crash_after_record('copied')
        self.assertTrue(self.photo.exists() and self.destination.exists())
        self.assert_finished()

    def test_recover_after_publish_before_copied_record(self):
        def rename(source, target):
            self.cross_device(source, target)
            if source.suffix == '.part':
                raise PowerLoss('published before copied')
        with patch('photosort.core.rename_exclusive', rename):
            with self.assertRaises(PowerLoss):
                Organizer(self.job).apply()
        self.assertTrue(self.photo.exists() and self.destination.exists())
        self.assertEqual(json.loads((self.job/'journal.jsonl').read_text().splitlines()[-1])['status'], 'copy_ready')
        self.assert_finished()

    def test_recover_after_source_unlink_before_moved_record(self):
        real_unlink = Path.unlink
        def unlink(path, *args, **kwargs):
            real_unlink(path, *args, **kwargs)
            if path == self.photo:
                raise PowerLoss('source unlinked')
        with patch('photosort.core.rename_exclusive', self.cross_device), patch.object(Path, 'unlink', unlink):
            with self.assertRaises(PowerLoss):
                Organizer(self.job).apply()
        self.assertFalse(self.photo.exists())
        self.assert_finished()

    def test_recover_after_same_device_rename_before_moved_record(self):
        def rename(source, target):
            rename_exclusive(source, target)
            raise PowerLoss('renamed')
        with patch('photosort.core.rename_exclusive', rename):
            with self.assertRaises(PowerLoss):
                Organizer(self.job).apply()
        self.assertFalse(self.photo.exists())
        self.assert_finished()

    def test_changed_published_copy_retains_source(self):
        self.crash_after_record('copied')
        self.destination.write_bytes(b'corrupt destination')
        with self.assertRaises(ValueError):
            Organizer(self.job).apply()
        self.assertEqual(self.photo.read_bytes(), b'original media' * 100)
        self.assertEqual(self.destination.read_bytes(), b'corrupt destination')

    def test_incomplete_last_journal_line_is_backed_up_and_recovered(self):
        self.crash_after_record('copied')
        partial = b'{"status": "mov'
        with (self.job/'journal.jsonl').open('ab') as stream:
            stream.write(partial)
        self.assert_finished()
        self.assertEqual((self.job/'partial-journal.txt').read_bytes(), partial)

    def test_corruption_inside_journal_stops_without_changing_files(self):
        self.crash_after_record('copied')
        journal = self.job / 'journal.jsonl'
        data = b'not-json\n' + journal.read_bytes()
        journal.write_bytes(data)
        with self.assertRaises(ValueError):
            Organizer(self.job).apply()
        self.assertTrue(self.photo.exists())
        self.assertEqual(journal.read_bytes(), data)
        self.assertFalse((self.job/'partial-journal.txt').exists())

    def test_complete_last_event_without_newline_survives_resume(self):
        self.crash_after_record('copied')
        journal = self.job / 'journal.jsonl'
        original = journal.read_bytes()
        journal.write_bytes(original.rstrip(b'\n'))
        self.assert_finished()
        events = [json.loads(line) for line in journal.read_bytes().splitlines()]
        self.assertEqual([e['status'] for e in events],
                         ['intent', 'copying', 'copy_ready', 'copied', 'moved'])
        self.assertTrue(journal.read_bytes().startswith(original))
        self.assertFalse((self.job/'partial-journal.txt').exists())

    def test_newline_repair_is_durable_and_idempotent(self):
        from photosort.journal import Journal
        event = dict(self.plan['files'][0], status='intent', plan_id=self.identity)
        journal = self.job / 'journal.jsonl'
        data = json.dumps(event).encode()
        journal.write_bytes(data)
        replay = Journal(journal, self.identity)
        with patch('photosort.journal.os.fsync', wraps=os.fsync) as sync:
            replay.replay()
            self.assertEqual(sync.call_count, 1)
            replay.replay()
            self.assertEqual(sync.call_count, 1)
        self.assertEqual(journal.read_bytes(), data+b'\n')
        self.assertEqual(replay.prior[str(self.photo)], event)

    def test_journal_from_another_plan_is_rejected(self):
        event = dict(self.plan['files'][0], status='intent', plan_id='wrong-plan')
        (self.job/'journal.jsonl').write_text(json.dumps(event)+'\n')
        with self.assertRaises(ValueError):
            Organizer(self.job).apply()
        self.assertTrue(self.photo.exists())
        self.assertFalse(self.destination.exists())

    def test_running_lock_blocks_second_worker_and_is_preserved(self):
        lock = self.job / 'running.lock'
        lock.mkdir()
        with self.assertRaises(RuntimeError):
            Organizer(self.job).apply()
        self.assertTrue(lock.is_dir() and self.photo.exists())
        self.assertFalse(self.destination.exists())
        lock.rmdir()
        self.assert_finished()

    def test_destination_appearing_after_preflight_is_never_overwritten(self):
        def rename(source, target):
            target.write_bytes(b'concurrent file')
            return rename_exclusive(source, target)
        with patch('photosort.core.rename_exclusive', rename):
            with self.assertRaises(FileExistsError):
                Organizer(self.job).apply()
        self.assertTrue(self.photo.exists())
        self.assertEqual(self.destination.read_bytes(), b'concurrent file')

    def test_version_one_plan_without_new_fields_can_resume(self):
        # Legacy schema: omit optional fields introduced by later releases.
        legacy = dict(self.plan)
        legacy.pop('skipped_resources')
        legacy.pop('source_directories')
        self.plan_bytes = json.dumps(legacy, ensure_ascii=False, indent=2).encode()
        (self.job/'plan.json').write_bytes(self.plan_bytes)
        self.assert_finished()
