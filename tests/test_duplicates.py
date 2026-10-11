import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from photosort.core import Organizer, rename_exclusive


class DuplicateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.src, self.dst, self.job = [self.base / p for p in ('source', 'target', 'job')]
        self.src.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def file(self, name, content=b'original'):
        p = self.src / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
        os.utime(p, (1710000000, 1710000000))
        return p

    def target(self, plan, name, content=b'original'):
        row = next(i for i in plan['files'] if Path(i['source']).name == name)
        p = Path(row['destination']).parent / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
        return p

    def test_after_plan_companions_and_second_run(self):
        self.file('album/a.jpg')
        self.file('album/a.jpg.json', b'{}')
        org = Organizer(self.job)
        plan = org.plan(self.src, self.dst)
        original_plan = (self.job / 'plan.json').read_bytes()
        target = self.target(plan, 'a.jpg')
        org.apply()
        self.assertEqual(target.read_bytes(), b'original')
        self.assertEqual((self.src / 'Duplikaty/album/a.jpg').read_bytes(), b'original')
        self.assertEqual((self.src / 'Duplikaty/album/a.jpg.json').read_bytes(), b'{}')
        org.apply()
        self.assertEqual((self.job / 'plan.json').read_bytes(), original_plan)
        new = Organizer(self.base / 'next').plan(self.src, self.dst)
        self.assertEqual(new['files'], [])

    def test_existing_before_plan_despite_suffix(self):
        self.file('a.jpg')
        first = Organizer(self.base / 'preview').plan(self.src, self.dst)
        self.target(first, 'a.jpg')
        org = Organizer(self.job)
        plan = org.plan(self.src, self.dst)
        self.assertNotEqual(Path(plan['files'][0]['destination']).name, 'a.jpg')
        org.apply()
        self.assertTrue((self.src / 'Duplikaty/a.jpg').exists())
        self.assertFalse(Path(plan['files'][0]['destination']).exists())

    def test_equal_size_different_content_uses_suffix(self):
        self.file('a.jpg')
        first = Organizer(self.base / 'preview').plan(self.src, self.dst)
        self.target(first, 'a.jpg', b'different'[:8])
        org = Organizer(self.job)
        plan = org.plan(self.src, self.dst)
        org.apply()
        self.assertEqual(Path(plan['files'][0]['destination']).read_bytes(), b'original')
        self.assertFalse((self.src / 'Duplikaty').exists())

    def test_shared_raw_jpeg_sidecar_requires_both_duplicates(self):
        for name in ('a.jpg', 'a.cr3', 'a.xmp'):
            self.file(name)
        org = Organizer(self.job)
        plan = org.plan(self.src, self.dst)
        self.target(plan, 'a.jpg')
        with self.assertRaises(FileExistsError):
            org.apply()
        self.assertTrue((self.src / 'a.xmp').exists())
        self.assertFalse((self.src / 'Duplikaty').exists())

    def test_resume_after_quarantine_rename_before_journal(self):
        self.file('a.jpg')
        org = Organizer(self.job)
        plan = org.plan(self.src, self.dst)
        self.target(plan, 'a.jpg')
        def crash(src, dst):
            rename_exclusive(src, dst)
            raise RuntimeError('power loss after rename')
        with patch('photosort.core.rename_exclusive', crash):
            with self.assertRaises(RuntimeError):
                org.apply()
        org.apply()
        self.assertEqual((self.src / 'Duplikaty/a.jpg').read_bytes(), b'original')
        self.assertEqual(json.loads((self.job / 'progress.json').read_text())['stage'], 'complete')

    def test_quarantine_collision_retains_source(self):
        self.file('a.jpg')
        self.file('Duplikaty/a.jpg', b'previous')
        org = Organizer(self.job)
        plan = org.plan(self.src, self.dst)
        self.target(plan, 'a.jpg')
        with self.assertRaises(FileExistsError):
            org.apply()
        self.assertEqual((self.src / 'a.jpg').read_bytes(), b'original')
        self.assertEqual((self.src / 'Duplikaty/a.jpg').read_bytes(), b'previous')

    def test_duplicate_appearing_after_preflight_is_quarantined(self):
        self.file('a.jpg')
        preview = Organizer(self.job).plan(self.src, self.dst)
        def notify(value):
            if value['stage'] == 'preflight' and value['done'] == value['total']:
                self.target(preview, 'a.jpg')
        Organizer(self.job, notify=notify).apply()
        self.assertEqual((self.src / 'Duplikaty/a.jpg').read_bytes(), b'original')

    def test_shared_raw_jpeg_group_with_two_matches_moves_together(self):
        for name in ('a.jpg', 'a.cr3', 'a.xmp'):
            self.file(name)
        org = Organizer(self.job)
        plan = org.plan(self.src, self.dst)
        for name in ('a.jpg', 'a.cr3'):
            self.target(plan, name)
        org.apply()
        for name in ('a.jpg', 'a.cr3', 'a.xmp'):
            self.assertEqual((self.src / 'Duplikaty' / name).read_bytes(), b'original')
