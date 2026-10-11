import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from photosort.core import Organizer
from photosort.filesystem import save


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.job = Path(self.temp.name)/'job'
        self.events = []
        self.clock = patch('photosort.core.time.monotonic', return_value=100.0)
        self.now = self.clock.start()
        self.addCleanup(self.clock.stop)
        self.org = Organizer(self.job, self.events.append)

    def tearDown(self):
        self.temp.cleanup()

    def progress(self):
        return json.loads((self.job/'progress.json').read_text(encoding='utf-8'))

    def test_high_rate_updates_are_bounded_but_notifications_stay_current(self):
        with patch('photosort.core.save', wraps=save) as saved:
            for done in range(100):
                self.now.return_value = 100 + done/100
                self.org.status('moving', done, 1000)
            self.assertEqual(saved.call_count, 1)
            self.assertEqual(self.progress()['done'], 0)
            self.assertEqual(len(self.events), 100)
            self.assertEqual(self.events[-1]['done'], 99)
            self.now.return_value = 101.0
            self.org.status('moving', 100, 1000)
            self.assertEqual(saved.call_count, 2)
            self.assertEqual(self.progress()['done'], 100)

    def test_stage_changes_completion_pause_and_failure_are_immediate(self):
        for stage, done, total in [('moving', 1, 10), ('moving', 10, 10),
                                   ('verifying', 1, 10), ('paused', 1, 10),
                                   ('failed', 1, 10), ('complete', 0, 0)]:
            with self.subTest(stage=stage, done=done):
                self.org.status(stage, done, total)
                result = self.progress()
                self.assertEqual((result['stage'], result['done']), (stage, done))

    def test_unknown_total_scanning_is_also_throttled(self):
        with patch('photosort.core.save', wraps=save) as saved:
            for _ in range(100):
                self.org.status('scanning', 0, 0)
            self.assertEqual(saved.call_count, 1)
            self.org.status('plan_complete', 0, 0)
            self.assertEqual(saved.call_count, 2)

    def test_all_move_events_remain_in_durable_journal(self):
        source, target = self.job.parent/'source', self.job.parent/'target'
        source.mkdir()
        for n in range(5):
            (source/'{}.jpg'.format(n)).write_bytes(b'photo')
        self.org.plan(source, target)
        with patch('photosort.core.save', wraps=save) as saved:
            self.org.apply()
        moving_saves = [call for call in saved.call_args_list
                        if call.args[0].name == 'progress.json' and call.args[1]['stage'] == 'moving']
        self.assertEqual(len(moving_saves), 2)  # First file and stage completion.
        events = [json.loads(line) for line in (self.job/'journal.jsonl').read_text().splitlines()]
        self.assertEqual(len(events), 10)
        self.assertEqual(sum(e['status'] == 'moved' for e in events), 5)
        self.assertEqual(self.progress()['stage'], 'complete')
