"""Task orchestration: immutable plan, durable execution and status."""
import json
import time
from pathlib import Path
# Keep these imports available for existing callers and fault-injection tests.
from .filesystem import save, syncdir, rename_exclusive, shutil, FileMover, cleanup_empty_directories
from .journal import Journal, plan_identity
from .planning import (folder_for, prepare_configuration, scan_source, select_media,
                       attach_companions, assign_destinations)

class Organizer:
    def __init__(self, job, notify=None, stop=None):
        self.job = Path(job).expanduser().resolve()
        self.job.mkdir(parents=True, exist_ok=True)
        self.notify = notify or (lambda s: None)
        self.stop = stop or (lambda: False)
        self.started = time.monotonic()
        self._last_status_write = None
        self._last_status_stage = None

    def status(self, stage, done, total, **extra):
        now = time.monotonic()
        elapsed = now - self.started
        speed = done / elapsed if elapsed else 0
        value = dict(stage=stage, done=done, total=total,
                     percent=round(100*done/total, 2) if total else 0,
                     files_per_second=round(speed, 2),
                     eta_seconds=round((total-done)/speed) if speed else None,
                     seconds=round(elapsed, 1), errors=0, **extra)
        # Progress is a snapshot, not the recovery journal. Bound disk I/O while
        # preserving stage transitions and the final update of each stage.
        if (stage != self._last_status_stage or self._last_status_write is None
                or now - self._last_status_write >= 1.0
                or (total > 0 and done >= total)):
            save(self.job/'progress.json', value)
            self._last_status_write = now
            self._last_status_stage = stage
        self.notify(value)

    def lock(self):
        p = self.job/'running.lock'
        try:
            p.mkdir()
        except FileExistsError:
            raise RuntimeError('Zadanie zablokowane: proces działa albo pozostał lock po awarii. Sprawdź proces przed usunięciem lock.')
        return p

    def plan(self, source, target, pattern='%Y/%m', scope='multimedia', timezone='Europe/Warsaw', extensions=None, skip_app_resources=False, exclude_dirs=None):
        source, target, categories, extensions, config, exclusions = prepare_configuration(
            source, target, pattern, scope, timezone, extensions, skip_app_resources, exclude_dirs)
        if (self.job/'plan.json').exists():
            plan = json.loads((self.job/'plan.json').read_text(encoding='utf-8'))
            if plan['config'] != config:
                raise ValueError('To zadanie ma już inny plan. Utwórz nowe zadanie.')
            return plan
        lock = self.lock()
        try:
            rows, skipped, skipped_resources, source_directories = scan_source(
                source, target, self.job, exclusions, skip_app_resources, self.status, self.stop)
            selected, dates, warnings, lookup = select_media(
                rows, categories, extensions, timezone, self.status, self.stop)
            companions = attach_companions(rows, selected, lookup)
            files = assign_destinations(selected, companions, dates, target, pattern)
            plan = dict(version=1, config=config, files=files, skipped=skipped, warnings=warnings,
                        skipped_resources=skipped_resources,
                        source_directories=source_directories,
                        bytes=sum(r['size'] for r in files))
            save(self.job/'plan.json', plan)
            self.status('plan_complete', len(files), len(files), bytes=plan['bytes'])
            return plan
        finally:
            lock.rmdir()

    def apply(self):
        plan = json.loads((self.job/'plan.json').read_text(encoding='utf-8'))
        source_root, target_root = (Path(plan['config'][k]).resolve() for k in ('source', 'target'))
        journal = Journal(self.job/'journal.jsonl', plan_identity(plan))
        lock = self.lock()
        done = 0
        total = len(plan['files'])
        try:
            journal.replay()
            mover = FileMover(source_root, target_root, journal, self.stop,
                              rename=rename_exclusive, sync=syncdir)
            self.status('preflight', 0, total)
            for n, item in enumerate(plan['files'], 1):
                if self.stop():
                    raise InterruptedError('Przerwano')
                if mover.preflight(item):
                    done += 1
                if n % 64 == 0 or n == total:
                    self.status('preflight', n, total)
            self.started = time.monotonic()
            initial_done = done
            with journal.writer():
                for item in plan['files']:
                    if self.stop():
                        raise InterruptedError('Przerwano')
                    if not mover.move(item):
                        continue
                    done += 1
                    elapsed = time.monotonic()-self.started
                    speed = (done-initial_done)/elapsed if elapsed else 0
                    self.status('moving', done, total, rate_current=round(speed, 2),
                                eta_current=round((total-done)/speed) if speed else None)
            for n, item in enumerate(plan['files'], 1):
                if Path(item['source']).exists():
                    raise ValueError('Źródło nadal istnieje: '+item['source'])
                mover.valid(Path(item['destination']), item)
                if n % 64 == 0 or n == total:
                    self.status('verifying', n, total)
            save(self.job/'verification.json', dict(files=total, bytes=plan['bytes'], errors=0))
            self.status('cleanup', total, total)
            removed, cleanup_errors = cleanup_empty_directories(plan, source_root, target_root, self.stop)
            save(self.job/'cleanup.json', dict(removed=removed, warnings=cleanup_errors))
            self.status('complete', total, total, removed_empty_directories=len(removed), cleanup_warnings=len(cleanup_errors))
        except InterruptedError:
            self.status('paused', done, total)
            raise
        except Exception as e:
            self.status('failed', done, total, error=str(e))
            raise
        finally:
            lock.rmdir()
