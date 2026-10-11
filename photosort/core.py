"""Immutable plans and durable, exclusive, verified file moves."""
import errno
import hashlib
import json
import os
import shutil
import time
from pathlib import Path
from .extensions import GROUPS, normalize_extensions, matches, scope_categories
from .metadata import PHOTOS, VIDEOS, SIDECARS, capture
from .resources import resource_reason
from .filesystem import save, syncdir, rename_exclusive, FileMover, cleanup_empty_directories
from .journal import Journal, plan_identity

SKIP = {'@eadir', '#recycle', '$recycle.bin', 'system volume information'}

def folder_for(date, pattern):
    if not pattern or len(pattern) > 120:
        raise ValueError('Nieprawidłowy format folderów')
    import re
    if re.search(r'%(?![Ymd%])', pattern):
        raise ValueError('Dozwolone znaczniki: %Y, %m, %d')
    text = date.strftime(pattern).replace('\\', '/')
    parts = text.split('/')
    if any(not p or p in ('.', '..') or any(c in p for c in ':<>"|?*') for p in parts):
        raise ValueError('Format musi tworzyć względną ścieżkę folderu')
    return Path(*parts)

class Organizer:
    def __init__(self, job, notify=None, stop=None):
        self.job = Path(job).expanduser().resolve()
        self.job.mkdir(parents=True, exist_ok=True)
        self.notify = notify or (lambda s: None)
        self.stop = stop or (lambda: False)
        self.started = time.monotonic()

    def status(self, stage, done, total, **extra):
        elapsed = time.monotonic() - self.started
        speed = done / elapsed if elapsed else 0
        value = dict(stage=stage, done=done, total=total,
                     percent=round(100*done/total, 2) if total else 0,
                     files_per_second=round(speed, 2),
                     eta_seconds=round((total-done)/speed) if speed else None,
                     seconds=round(elapsed, 1), errors=0, **extra)
        save(self.job/'progress.json', value)
        self.notify(value)

    def lock(self):
        p = self.job/'running.lock'
        try:
            p.mkdir()
        except FileExistsError:
            raise RuntimeError('Zadanie zablokowane: proces działa albo pozostał lock po awarii. Sprawdź proces przed usunięciem lock.')
        return p

    def plan(self, source, target, pattern='%Y/%m', scope='multimedia', timezone='Europe/Warsaw', extensions=None, skip_app_resources=False, exclude_dirs=None):
        from datetime import datetime
        source, target = Path(source).expanduser().resolve(), Path(target).expanduser().resolve()
        if not source.is_dir():
            raise ValueError('Źródło nie jest katalogiem')
        # A destination inside source is supported and excluded from traversal.
        # Reject identical roots and a destination containing the source.
        try:
            source.relative_to(target)
        except ValueError:
            pass
        else:
            raise ValueError('Źródło i cel nie mogą być identyczne; cel nie może zawierać źródła')
        folder_for(datetime.now(), pattern)
        categories = scope_categories(scope)
        extensions = normalize_extensions(extensions)
        config = dict(source=str(source), target=str(target), pattern=pattern, scope=scope, timezone=timezone)
        exclusions = []
        for value in exclude_dirs or []:
            p = Path(value).expanduser()
            p = (source/p if not p.is_absolute() else p).resolve()
            try:
                p.relative_to(source)
            except ValueError:
                raise ValueError('Pomijany katalog musi znajdować się w źródle: '+str(p))
            exclusions.append(p)
        if skip_app_resources:
            config['skip_app_resources'] = True
        if exclusions:
            config['exclude_dirs'] = sorted({str(p) for p in exclusions})
        if extensions is not None:
            config['extensions'] = extensions
        if (self.job/'plan.json').exists():
            plan = json.loads((self.job/'plan.json').read_text(encoding='utf-8'))
            if plan['config'] != config:
                raise ValueError('To zadanie ma już inny plan. Utwórz nowe zadanie.')
            return plan
        lock = self.lock()
        try:
            rows, skipped, skipped_resources = [], [], []
            source_directories = [str(source)]
            stack = [source]
            self.status('scanning', 0, 0)
            while stack:
                if self.stop():
                    raise InterruptedError('Przerwano planowanie')
                directory = stack.pop()
                reason = None
                for excluded in exclusions:
                    try:
                        directory.relative_to(excluded)
                        reason = 'Katalog pominięty przez użytkownika'
                        break
                    except ValueError:
                        pass
                if not reason and skip_app_resources:
                    reason = resource_reason(directory)
                if reason:
                    skipped.append(str(directory))
                    skipped_resources.append(dict(path=str(directory), reason=reason))
                    if str(directory) in source_directories:
                        source_directories.remove(str(directory))
                    continue
                with os.scandir(directory) as entries:
                    for e in entries:
                        if e.name.casefold() in SKIP or e.is_symlink():
                            skipped.append(e.path)
                        elif e.is_dir(follow_symlinks=False):
                            resolved = Path(e.path).resolve()
                            try:
                                resolved.relative_to(target)
                                inside_target = True
                            except ValueError:
                                inside_target = False
                            if inside_target or resolved == self.job:
                                skipped.append(e.path)
                            else:
                                stack.append(Path(e.path))
                                source_directories.append(str(resolved))
                        elif e.is_file(follow_symlinks=False):
                            s = e.stat(follow_symlinks=False)
                            rows.append(dict(path=e.path, size=s.st_size, mtime=s.st_mtime))
                self.status('scanning', len(rows), 0)
            rows.sort(key=lambda r: r['path'].casefold())
            lookup = {r['path'].casefold(): r['path'] for r in rows}
            selected, dates, warnings = [], {}, []
            for n, r in enumerate(rows, 1):
                if self.stop():
                    raise InterruptedError('Przerwano planowanie')
                p = Path(r['path'])
                ext = p.suffix.lower().lstrip('.')
                included = (('photos' in categories and ext in PHOTOS) or
                            ('video' in categories and ext in VIDEOS) or
                            ('audio' in categories and ext in GROUPS['Dźwięk']))
                if included and matches(p, extensions):
                    date, method, errs = capture(p, r['mtime'], timezone, lookup)
                    dates[r['path']] = (date, method)
                    selected.append(r)
                    if errs:
                        warnings.append(dict(path=r['path'], errors=errs))
                if n % 16 == 0 or n == len(rows):
                    self.status('dates', n, len(rows))
            selected_paths = {r['path'] for r in selected}
            companions = {}
            # Exact JSON names, the Takeout json/ subdirectory, and basename edits.
            for r in list(selected):
                p = Path(r['path'])
                if p.suffix.lower().lstrip('.') not in PHOTOS | VIDEOS:
                    continue
                candidates = [str(p)+'.'+x for x in SIDECARS]
                candidates += [str(p.with_suffix('.'+x)) for x in SIDECARS-{'json'}]
                candidates += [str(p.parent/'json'/(p.name+'.'+x)) for x in ('json', 'supplemental-metadata.json')]
                candidates += [str(p)+'.supplemental-metadata.json']
                for candidate in candidates:
                    match = lookup.get(candidate.casefold())
                    if match:
                        # Shared RAW/JPEG edit file: deterministic first claimant.
                        companions.setdefault(match, r['path'])
                        if match not in selected_paths:
                            selected.append(next(row for row in rows if row['path'] == match))
                            selected_paths.add(match)
            groups = {}
            for r in selected:
                p = Path(companions.get(r['path'], r['path']))
                groups.setdefault((str(p.parent), p.stem.casefold()), []).append(r)
            reserved, files = set(), []
            for key, group in sorted(groups.items()):
                suffix, number = '', 0
                while True:
                    proposals = []
                    for r in group:
                        anchor = companions.get(r['path'], r['path'])
                        date, method = dates[anchor]
                        p = Path(r['path'])
                        stem, ext = p.stem, p.suffix
                        if r['path'] in companions:
                            original = Path(anchor)
                            if p.name.startswith(original.name+'.'):
                                name = original.stem+suffix+original.suffix+p.name[len(original.name):]
                            else:
                                name = original.stem+suffix+ext
                        else:
                            name = stem+suffix+ext
                        dst = target/folder_for(date, pattern)/name
                        proposals.append((r, dst, method))
                    keys = [str(dst).casefold() for _, dst, _ in proposals]
                    if len(set(keys)) != len(keys):
                        raise ValueError('Niejednoznaczne pliki towarzyszące lub nazwy różniące się wielkością liter: '+str(key))
                    if all(k not in reserved and not dst.exists() for k, (_, dst, _) in zip(keys, proposals)):
                        break
                    number += 1
                    suffix = '__'+hashlib.sha256(repr(key).encode()).hexdigest()[:12]+('_'+str(number) if number > 1 else '')
                for r, dst, method in proposals:
                    reserved.add(str(dst).casefold())
                    files.append(dict(source=r['path'], destination=str(dst), size=r['size'], mtime=r['mtime'], date_source=method))
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
