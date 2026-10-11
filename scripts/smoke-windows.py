"""Exercise the extracted Windows delivery with no source checkout on sys.path."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

archive = Path(sys.argv[1]).resolve()
expected = Path(str(archive) + '.sha256').read_text().split()[0]
assert hashlib.sha256(archive.read_bytes()).hexdigest() == expected
with tempfile.TemporaryDirectory(prefix='PhotoSort package ') as directory:
    base = Path(directory).resolve()
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(base)
    package = base / 'PhotoSort'
    exe = package / 'PhotoSort-Terminal.exe'
    env = {key: value for key, value in os.environ.items()
           if key.upper() not in ('PYTHONPATH', 'PYTHONHOME')}
    def run(*args, success=True):
        result = subprocess.run([str(exe), *map(str, args)], cwd=base,
                                env=env, capture_output=True, timeout=120)
        assert (result.returncode == 0) == success, result.stdout + result.stderr
    run('--help')
    source, target, job = [base / name for name in ('source', 'target', 'job')]
    source.mkdir()
    photo = source / 'photo.jpg'
    photo.write_bytes(b'package smoke photo')
    (source / 'photo.jpg.json').write_text('{"photoTakenTime":{"timestamp":"946684800"}}')
    (source / 'keep.txt').write_text('keep')
    run('plan', source, target, '--job', job)
    plan_bytes = (job / 'plan.json').read_bytes()
    plan = json.loads(plan_bytes)
    assert len(plan['files']) == 2 and photo.exists()
    destination = Path(next(row['destination'] for row in plan['files']
                            if Path(row['source']).resolve() == photo.resolve()))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(b'existing destination')
    run('apply', '--job', job, success=False)
    assert photo.exists() and destination.read_bytes() == b'existing destination'
    destination.unlink()  # Only the synthetic collision created by this test.
    run('apply', '--job', job)
    journal = (job / 'journal.jsonl').read_bytes()
    run('apply', '--job', job)
    run('status', '--job', job)
    assert (job / 'plan.json').read_bytes() == plan_bytes
    assert (job / 'journal.jsonl').read_bytes() == journal
    assert destination.read_bytes() == b'package smoke photo' and not photo.exists()
    assert (source / 'keep.txt').exists()
    assert json.loads((job / 'progress.json').read_text())['stage'] == 'complete'
    gui = subprocess.Popen([str(package / 'PhotoSort.exe')], cwd=base, env=env)
    try:
        try:
            gui.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        assert gui.poll() is None, 'GUI exited during startup'
    finally:
        if gui.poll() is None:
            gui.terminate()
        gui.wait(timeout=30)
print('Extracted package: checksum, GUI, CLI, collisions and resume passed')
