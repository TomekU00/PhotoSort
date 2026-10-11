"""The SSH payload must run without the installed PhotoSort package."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile
from photosort.remote import bundle


class RemoteBundleTests(unittest.TestCase):
    def test_uploaded_sources_plan_apply_and_resume_without_site_packages(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            app = base/'app'
            with zipfile.ZipFile(io.BytesIO(bundle())) as archive:
                for module in ('filesystem.py', 'journal.py', 'planning.py', 'tasks.py'):
                    self.assertIn('photosort/'+module, archive.namelist())
                archive.extractall(app)
            source = base/'source'
            source.mkdir()
            (source/'photo.jpg').write_bytes(b'remote photo')
            (source/'keep.txt').write_text('keep')
            job, target = base/'job', base/'target'
            env = {key: value for key, value in os.environ.items()
                   if key.upper() not in ('PYTHONPATH','PYTHONHOME')}
            env['PYTHONUTF8'] = '1'
            def run(*args):
                result = subprocess.run([sys.executable, '-S', str(app/'__main__.py'), *map(str,args)],
                                        cwd=base, env=env, capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            run('plan',source,target,'--job',job)
            plan = (job/'plan.json').read_bytes()
            self.assertTrue((source/'photo.jpg').exists())
            run('apply','--job',job)
            journal = (job/'journal.jsonl').read_bytes()
            run('apply','--job',job)
            self.assertEqual((job/'plan.json').read_bytes(), plan)
            self.assertEqual((job/'journal.jsonl').read_bytes(), journal)
            self.assertFalse((source/'photo.jpg').exists())
            self.assertTrue((source/'keep.txt').exists())
            self.assertEqual(json.loads((job/'progress.json').read_text())['stage'],'complete')
