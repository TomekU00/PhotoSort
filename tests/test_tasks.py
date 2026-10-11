"""Local GUI worker contracts, tested without a Tk event loop."""
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from photosort.tasks import LocalTasks, PlanSettings


class TaskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.source, self.target, self.job = [self.base / x for x in ('source', 'target', 'job')]
        self.source.mkdir()
        (self.source/'photo.jpg').write_bytes(b'photo')
        (self.source/'keep.txt').write_text('keep')
        self.settings = PlanSettings(str(self.job), str(self.source), str(self.target))
        self.tasks = LocalTasks()

    def tearDown(self):
        self.tasks.stopped.set()
        if self.tasks.thread:
            self.tasks.thread.join(timeout=10)
            self.assertFalse(self.tasks.running)
        self.temp.cleanup()

    def finish(self):
        self.tasks.thread.join(timeout=10)
        self.assertFalse(self.tasks.running)
        events = []
        while not self.tasks.events.empty():
            events.append(self.tasks.events.get_nowait())
        self.assertFalse(any(e.get('message', '').startswith('Błąd:') for e in events), events)
        return events

    def test_plan_then_apply_and_resume_share_the_same_persisted_job(self):
        self.assertTrue(self.tasks.start('plan', self.settings))
        self.finish()
        self.assertTrue((self.source/'photo.jpg').exists())
        plan = (self.job/'plan.json').read_bytes()
        self.assertTrue(self.tasks.start('apply', self.settings))
        self.assertIn('complete', [e.get('stage') for e in self.finish()])
        journal = (self.job/'journal.jsonl').read_bytes()
        self.assertTrue((self.source/'keep.txt').exists())
        self.tasks.start('apply', self.settings)
        self.finish()
        self.assertEqual((self.job/'plan.json').read_bytes(), plan)
        self.assertEqual((self.job/'journal.jsonl').read_bytes(), journal)

    def test_second_start_is_rejected_until_worker_finishes(self):
        entered, release = threading.Event(), threading.Event()
        def blocking_worker(*args):
            entered.set()
            release.wait(timeout=10)
        with patch.object(self.tasks, '_work', blocking_worker):
            try:
                self.assertTrue(self.tasks.start('plan', self.settings))
                self.assertTrue(entered.wait(timeout=5))
                self.assertFalse(self.tasks.start('apply', self.settings))
                self.assertFalse(self.tasks.thread.daemon)
            finally:
                release.set()
                self.finish()

    def test_settings_are_immutable_snapshot(self):
        with self.assertRaises(FrozenInstanceError):
            self.settings.source = 'different source'

    def test_worker_reports_pause_without_moving_source(self):
        self.tasks.start('plan', self.settings)
        self.finish()
        real_work = self.tasks._work
        def paused_work(action, settings):
            self.tasks.stopped.set()
            real_work(action, settings)
        with patch.object(self.tasks, '_work', paused_work):
            self.tasks.start('apply', self.settings)
            messages = self.finish()
        self.assertTrue((self.source/'photo.jpg').exists())
        self.assertTrue(any('Zatrzymano' in e.get('message', '') for e in messages))
        self.tasks.start('apply', self.settings)
        self.finish()
        self.assertFalse((self.source/'photo.jpg').exists())
