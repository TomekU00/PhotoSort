import errno
import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from photosort.core import Organizer, folder_for, rename_exclusive

class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.src, self.dst, self.job = [self.base/p for p in ('source', 'target', 'job')]
        self.src.mkdir()
        self.dst.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def create(self, name, payload=b'content'):
        p = self.src/name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(payload)
        os.utime(p, (1710000000, 1710000000))
        return p

    def test_extension_filter_keeps_companions_and_unselected_sources(self):
        photo = self.create('capture.JPG')
        sidecar = self.create('capture.JPG.json', b'{"photoTakenTime":{"timestamp":"1710000000"}}')
        video = self.create('clip.mp4')
        text = self.create('note.txt')
        org = Organizer(self.job)
        plan = org.plan(self.src, self.dst, extensions='.JPG')
        self.assertEqual({Path(r['source']).name for r in plan['files']}, {'capture.JPG', 'capture.JPG.json'})
        self.assertEqual(plan['config']['extensions'], ['jpg'])
        org.apply()
        self.assertFalse(photo.exists() or sidecar.exists())
        self.assertTrue(video.exists() and text.exists())

    def test_only_media_selected_and_other_formats_retained(self):
        for name in ('photo.jpg','raw.cr3','clip.mp4','sound.mp3','document.pdf','notes.txt','archive.zip','data.json','unknown.weird','NOEXT'):
            self.create(name)
        plan = Organizer(self.job).plan(self.src, self.dst)
        self.assertEqual({Path(r['source']).name for r in plan['files']}, {'photo.jpg','raw.cr3','clip.mp4','sound.mp3'})
        Organizer(self.job).apply()
        self.assertTrue((self.src/'document.pdf').exists())
        self.assertTrue((self.src/'data.json').exists())
        for invalid in ('pdf','zip','json','@none','@other'):
            with self.assertRaises(ValueError):
                Organizer(self.base/('bad-'+invalid)).plan(self.src,self.dst,extensions=invalid)

    def test_audio_scope_excludes_images(self):
        self.create('sound.mp3')
        self.create('photo.jpg')
        plan = Organizer(self.job).plan(self.src,self.dst,scope='audio')
        self.assertEqual([Path(r['source']).name for r in plan['files']], ['sound.mp3'])

    def test_extension_filter_is_immutable_and_old_plan_still_loads(self):
        self.create('note.jpg')
        org = Organizer(self.job)
        original = org.plan(self.src, self.dst)
        self.assertNotIn('extensions', original['config'])
        self.assertEqual(org.plan(self.src, self.dst), original)
        with self.assertRaises(ValueError):
            org.plan(self.src, self.dst, extensions='txt')
        with self.assertRaises(ValueError):
            Organizer(self.base/'empty-selection').plan(self.src, self.dst, extensions=[])

    def test_plan_does_not_move_and_preserves_collisions(self):
        a = self.create('one/file.jpg', b'one')
        b = self.create('two/file.jpg', b'two')
        org = Organizer(self.job)
        plan = org.plan(self.src, self.dst)
        self.assertTrue(a.exists() and b.exists())
        self.assertEqual(len({p['destination'] for p in plan['files']}), 2)
        org.apply()
        self.assertFalse(a.exists() or b.exists())
        self.assertEqual({Path(p['destination']).read_bytes() for p in plan['files']}, {b'one', b'two'})
        org.apply()  # completed job is resumable

    def test_cross_filesystem_copy_and_resume(self):
        src = self.create('file.jpg', b'content'*100)
        org = Organizer(self.job)
        plan = org.plan(self.src, self.dst)
        real = rename_exclusive
        def cross(source, target):
            if source == src:
                raise OSError(errno.EXDEV, 'forced cross-device move')
            return real(source, target)
        with patch('photosort.core.rename_exclusive', cross):
            org.apply()
        self.assertFalse(src.exists())
        self.assertEqual(Path(plan['files'][0]['destination']).read_bytes(), b'content'*100)
        org.apply()

    def test_corrupt_copy_retains_source(self):
        src = self.create('file.jpg', b'original')
        org = Organizer(self.job)
        org.plan(self.src, self.dst)
        real = rename_exclusive
        def cross(source, target):
            if source == src:
                raise OSError(errno.EXDEV, 'forced cross-device move')
            return real(source, target)
        real_copy = __import__('shutil').copystat
        def corrupt(source, target):
            target.write_bytes(b'corrupt!')
            real_copy(source, target)
        with patch('photosort.core.rename_exclusive', cross), patch('photosort.core.shutil.copystat', corrupt):
            with self.assertRaises(ValueError):
                org.apply()
        self.assertEqual(src.read_bytes(), b'original')

    def test_new_destination_never_overwritten(self):
        src = self.create('file.jpg')
        org = Organizer(self.job)
        plan = org.plan(self.src, self.dst)
        dest = Path(plan['files'][0]['destination'])
        dest.parent.mkdir(parents=True)
        dest.write_bytes(b'other')
        with self.assertRaises(FileExistsError):
            org.apply()
        self.assertTrue(src.exists())
        self.assertEqual(dest.read_bytes(), b'other')

    def test_partial_copy_can_resume(self):
        src = self.create('file.jpg', b'content'*100)
        org = Organizer(self.job)
        plan = org.plan(self.src, self.dst)
        real = rename_exclusive
        def cross(source, target):
            if source == src:
                raise OSError(errno.EXDEV, 'forced cross-device move')
            return real(source, target)
        def stop_after_copy_started():
            journal = self.job/'journal.jsonl'
            return journal.exists() and '"status": "copying"' in journal.read_text()
        with patch('photosort.core.rename_exclusive', cross):
            with self.assertRaises(InterruptedError):
                Organizer(self.job, stop=stop_after_copy_started).apply()
            self.assertTrue(src.exists())
            Organizer(self.job).apply()
        self.assertEqual(Path(plan['files'][0]['destination']).read_bytes(), b'content'*100)
        self.assertFalse(src.exists())

    def test_changed_source_not_moved(self):
        src = self.create('file.jpg')
        org = Organizer(self.job)
        org.plan(self.src, self.dst)
        src.write_bytes(b'changed-longer')
        with self.assertRaises(ValueError):
            org.apply()
        self.assertTrue(src.exists())

    def test_sidecar_in_json_subdirectory_keeps_photo_date(self):
        photo = self.create('album/img.jpg', b'not-a-real-jpeg')
        side = self.create('album/json/img.jpg.json', json.dumps({'photoTakenTime': {'timestamp': '946684800'}}).encode())
        org = Organizer(self.job)
        plan = org.plan(self.src, self.dst, scope='photos')
        self.assertEqual(len(plan['files']), 2)
        self.assertEqual({Path(p['destination']).parent for p in plan['files']}, {self.dst/'2000'/'01'})

    def test_reject_equal_roots_parent_target_and_path_escape(self):
        with self.assertRaises(ValueError):
            Organizer(self.job).plan(self.src, self.src)
        with self.assertRaises(ValueError):
            Organizer(self.job).plan(self.src, self.base)
        with self.assertRaises(ValueError):
            folder_for(datetime.now(), '../../%Y')

    def test_nested_destination_excluded_and_preserved(self):
        target = self.src/'posegregowane'
        target.mkdir()
        existing = target/'2024'/'03'/'file.jpg'
        existing.parent.mkdir(parents=True)
        existing.write_bytes(b'already sorted')
        source = self.create('file.jpg', b'new photo data')
        self.create('subfolder/other.jpg', b'other')
        org = Organizer(self.job)
        plan = org.plan(self.src, target)
        self.assertEqual(len(plan['files']), 2)
        self.assertIn(str(target), plan['skipped'])
        self.assertTrue(all(target in Path(r['destination']).parents for r in plan['files']))
        org.apply()
        self.assertFalse(source.exists())
        self.assertEqual(existing.read_bytes(), b'already sorted')
        org.apply()
        new_plan = Organizer(self.base/'second-job').plan(self.src, target)
        self.assertEqual(new_plan['files'], [])

    def test_new_nested_destination_can_be_created(self):
        target = self.src/'new'/'posegregowane'
        source = self.create('photo.jpg')
        org = Organizer(self.job)
        plan = org.plan(self.src, target)
        self.assertEqual(len(plan['files']), 1)
        org.apply()
        self.assertFalse(source.exists())
        self.assertTrue(Path(plan['files'][0]['destination']).is_file())

    def test_cleanup_removes_empty_source_and_nested_folders(self):
        self.create('nested/deep/photo.jpg')
        (self.src/'already-empty').mkdir()
        org = Organizer(self.job)
        org.plan(self.src,self.dst)
        org.apply()
        self.assertFalse(self.src.exists())
        cleanup = json.loads((self.job/'cleanup.json').read_text(encoding='utf-8'))
        self.assertIn(str(self.src),cleanup['removed'])
        org.apply()  # resume remains valid after source directories were removed

    def test_cleanup_retains_nonmedia_and_folder_with_unmoved_file(self):
        self.create('nested/photo.jpg')
        keep = self.create('nested/document.pdf')
        org = Organizer(self.job)
        org.plan(self.src,self.dst)
        org.apply()
        self.assertTrue(keep.exists())
        self.assertTrue(self.src.exists())

    def test_multiple_scopes_match_union_and_exclude_unselected(self):
        for name in ('photo.jpg','clip.mp4','music.mp3'):
            self.create(name)
        plan = Organizer(self.job).plan(self.src,self.dst,scope='video,audio')
        self.assertEqual({Path(r['source']).name for r in plan['files']},{'clip.mp4','music.mp3'})
        with self.assertRaises(ValueError):
            Organizer(self.base/'no-scope').plan(self.src,self.dst,scope='')

    def test_pause_before_move_retains_source(self):
        src = self.create('file.jpg')
        org = Organizer(self.job)
        org.plan(self.src, self.dst)
        with self.assertRaises(InterruptedError):
            Organizer(self.job, stop=lambda: True).apply()
        self.assertTrue(src.exists())

if __name__ == '__main__':
    unittest.main()
