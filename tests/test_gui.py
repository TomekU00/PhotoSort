"""Tk wiring tests; headless Linux runners skip only these UI checks."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
try:
    import tkinter as tk
    from photosort.gui import PhotoSortApp
except ImportError:
    tk = None


@unittest.skipIf(tk is None, 'Tkinter unavailable')
class GuiTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(str(error))
        self.root.withdraw()
        self.app = PhotoSortApp(self.root)
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()

    def tearDown(self):
        self.app.stopped.set()
        if self.app.tasks.thread:
            self.app.tasks.thread.join(timeout=10)
            self.assertFalse(self.app.tasks.running)
        self.root.destroy()
        self.temp.cleanup()

    def test_plan_button_uses_snapshot_and_does_not_move_files(self):
        source = self.base/'source'
        source.mkdir()
        (source/'photo.jpg').write_bytes(b'photo')
        self.app.variables['source'].set(str(source))
        self.app.variables['target'].set(str(self.base/'target'))
        self.app.jobvar.set(str(self.base/'job'))
        self.app.start('plan')
        self.app.tasks.thread.join(timeout=10)
        self.assertFalse(self.app.tasks.running)
        plan = json.loads((self.base/'job/plan.json').read_text(encoding='utf-8'))
        self.assertEqual(len(plan['files']), 1)
        self.assertTrue((source/'photo.jpg').exists())
        self.app.poll()
        self.assertIn('Plan:', self.app.label.get())

    def test_open_legacy_job_restores_scope_and_extension_defaults(self):
        job = self.base/'job'
        job.mkdir()
        (job/'plan.json').write_text(json.dumps({'config': {'source': '/source', 'target': '/target',
                                                           'pattern': '%Y', 'scope': 'photos'}}))
        with patch('photosort.gui.filedialog.askdirectory', return_value=str(job)):
            self.app.load()
        self.assertEqual(self.app.chosen_scope(), 'photos')
        self.assertIsNone(self.app.extension_state['values'])
        self.assertFalse(self.app.skip_resources.get())
        self.assertEqual(self.app.jobvar.get(), str(job))

    def test_extensions_dialog_does_not_change_selection_until_save(self):
        self.app.choose_extensions()
        self.root.update_idletasks()
        self.assertIsNone(self.app.extension_state['values'])
        dialogs = [w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel)]
        self.assertEqual(len(dialogs), 1)
        dialogs[0].destroy()
