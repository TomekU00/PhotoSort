"""Immutable plans and durable, exclusive, verified file moves."""
import ctypes
import errno
import hashlib
import json
import os
import shutil
import stat
import time
from pathlib import Path
from .extensions import normalize_extensions, matches
from .metadata import PHOTOS, VIDEOS, SIDECARS, capture

SKIP = {'@eadir', '#recycle', '$recycle.bin', 'system volume information'}

def save(path, value):
    temp = path.with_suffix('.tmp')
    with temp.open('w', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)
    syncdir(path.parent)

def syncdir(path):
    if os.name == 'nt':
        return
    fd = os.open(str(path), os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

def rename_exclusive(source, target):
    if os.name == 'nt':
        return os.rename(source, target)
    libc = ctypes.CDLL(None, use_errno=True)
    if hasattr(libc, 'renameat2'):
        fn = libc.renameat2
        fn.restype = ctypes.c_int
        if fn(-100, ctypes.c_char_p(os.fsencode(source)), -100, ctypes.c_char_p(os.fsencode(target)), 1):
            n = ctypes.get_errno()
            raise OSError(n, os.strerror(n), str(target))
    else:
        # link is exclusive; unlink only after the new entry is durable.
        os.link(source, target)
        syncdir(target.parent)
        source.unlink()

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

    def plan(self, source, target, pattern='%Y/%m', scope='all', timezone='Europe/Warsaw', extensions=None):
        from datetime import datetime
        source, target = Path(source).expanduser().resolve(), Path(target).expanduser().resolve()
        if not source.is_dir():
            raise ValueError('Źródło nie jest katalogiem')
        for a, b in ((source, target), (target, source)):
            try:
                a.relative_to(b)
            except ValueError:
                continue
            raise ValueError('Źródło i cel muszą być osobnymi, niezagnieżdżonymi katalogami')
        folder_for(datetime.now(), pattern)
        if scope not in ('photos', 'media', 'all'):
            raise ValueError('Nieprawidłowy zakres')
        extensions = normalize_extensions(extensions)
        config = dict(source=str(source), target=str(target), pattern=pattern, scope=scope, timezone=timezone)
        if extensions is not None:
            config['extensions'] = extensions
        if (self.job/'plan.json').exists():
            plan = json.loads((self.job/'plan.json').read_text(encoding='utf-8'))
            if plan['config'] != config:
                raise ValueError('To zadanie ma już inny plan. Utwórz nowe zadanie.')
            return plan
        lock = self.lock()
        try:
            rows, skipped = [], []
            stack = [source]
            self.status('scanning', 0, 0)
            while stack:
                if self.stop():
                    raise InterruptedError('Przerwano planowanie')
                with os.scandir(stack.pop()) as entries:
                    for e in entries:
                        if e.name.casefold() in SKIP or e.is_symlink():
                            skipped.append(e.path)
                        elif e.is_dir(follow_symlinks=False):
                            if Path(e.path).resolve() == self.job:
                                skipped.append(e.path)
                            else:
                                stack.append(Path(e.path))
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
                included = scope == 'all' or ext in PHOTOS or (scope == 'media' and ext in VIDEOS)
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
                        bytes=sum(r['size'] for r in files))
            save(self.job/'plan.json', plan)
            self.status('plan_complete', len(files), len(files), bytes=plan['bytes'])
            return plan
        finally:
            lock.rmdir()

    def apply(self):
        plan = json.loads((self.job/'plan.json').read_text(encoding='utf-8'))
        identity = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()
        source_root, target_root = (Path(plan['config'][k]).resolve() for k in ('source', 'target'))
        journal = self.job/'journal.jsonl'
        lock = self.lock()
        prior, done = {}, 0
        total = len(plan['files'])
        try:
            if journal.exists():
                with journal.open('rb') as f:
                    cut = None
                    while True:
                        offset = f.tell()
                        line = f.readline()
                        if not line:
                            break
                        try:
                            event = json.loads(line)
                        except (ValueError, UnicodeDecodeError):
                            if f.read(1):
                                raise
                            (self.job/'partial-journal.txt').write_bytes(line)
                            cut = offset
                            break
                        if event['plan_id'] != identity:
                            raise ValueError('Dziennik należy do innego planu')
                        prior[event['source']] = event
                if cut is not None:
                    with journal.open('r+b') as f:
                        f.truncate(cut)
            def valid(path, item):
                s = path.lstat()
                if not stat.S_ISREG(s.st_mode) or s.st_size != item['size'] or abs(s.st_mtime-item['mtime']) > .002:
                    raise ValueError('Plik zmieniony: '+str(path))
                return s
            def digest(path):
                h = hashlib.sha256()
                with path.open('rb') as f:
                    while True:
                        if self.stop():
                            raise InterruptedError('Przerwano; źródło zachowane')
                        b = f.read(4*1024*1024)
                        if not b:
                            break
                        h.update(b)
                return h.hexdigest()
            self.status('preflight', 0, total)
            for n, item in enumerate(plan['files'], 1):
                if self.stop():
                    raise InterruptedError('Przerwano')
                src, dst = Path(item['source']), Path(item['destination'])
                src.parent.resolve().relative_to(source_root)
                dst.parent.resolve().relative_to(target_root)
                event = prior.get(str(src))
                if src.exists():
                    valid(src, item)
                    if dst.exists() and not (event and event['status'] in ('copy_ready', 'copied', 'linked')):
                        raise FileExistsError(str(dst))
                else:
                    if not event:
                        raise FileNotFoundError(str(src))
                    s = valid(dst, item)
                    if event.get('sha256'):
                        if digest(dst) != event['sha256']:
                            raise ValueError('Błąd sumy kontrolnej: '+str(dst))
                    elif (s.st_dev, s.st_ino) != (event['device'], event['inode']):
                        raise ValueError('Nie można potwierdzić poprzedniego przeniesienia')
                    done += 1
                if n % 64 == 0 or n == total:
                    self.status('preflight', n, total)
            self.started = time.monotonic()
            initial_done = done
            with journal.open('a', encoding='utf-8') as log:
                def record(item, status, **extra):
                    event = dict(item, status=status, plan_id=identity, **extra)
                    log.write(json.dumps(event, ensure_ascii=False)+'\n')
                    log.flush()
                    os.fsync(log.fileno())
                    prior[item['source']] = event
                for item in plan['files']:
                    if self.stop():
                        raise InterruptedError('Przerwano')
                    src, dst = Path(item['source']), Path(item['destination'])
                    if not src.exists():
                        continue
                    s = valid(src, item)
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    dst.parent.resolve().relative_to(target_root)
                    old = prior.get(str(src))
                    if dst.exists():
                        if not old or old['status'] not in ('copy_ready', 'copied', 'linked'):
                            raise FileExistsError(str(dst))
                        if old.get('sha256'):
                            if digest(src) != old['sha256'] or digest(dst) != old['sha256']:
                                raise ValueError('Wznowienie: kopia niezgodna')
                        elif dst.stat().st_ino != s.st_ino:
                            raise ValueError('Wznowienie: inny plik')
                        valid(src, item)
                        src.unlink()
                        syncdir(src.parent)
                        record(item, 'moved', **{k: old[k] for k in ('sha256', 'device', 'inode') if k in old})
                    else:
                        record(item, 'intent', inode=s.st_ino, device=s.st_dev,
                               **({'temporary': old['temporary']} if old and old.get('temporary') else {}))
                        try:
                            rename_exclusive(src, dst)
                        except OSError as e:
                            if e.errno != errno.EXDEV and getattr(e, 'winerror', None) != 17:
                                raise
                            if shutil.disk_usage(dst.parent).free < item['size'] + 64*1024*1024:
                                raise OSError('Za mało miejsca na następny plik')
                            tmp = dst.parent/('.photosort-'+identity[:12]+'-'+hashlib.sha256(str(src).encode()).hexdigest()[:16]+'.part')
                            if tmp.exists():
                                if not old or old['status'] not in ('intent', 'copying', 'copy_ready') or old.get('temporary') != str(tmp):
                                    raise FileExistsError('Nieznany plik tymczasowy: '+str(tmp))
                                valid(src, item)
                                tmp.unlink()
                            record(item, 'copying', temporary=str(tmp), inode=s.st_ino, device=s.st_dev)
                            h = hashlib.sha256()
                            with src.open('rb') as inp, tmp.open('xb') as out:
                                while True:
                                    if self.stop():
                                        raise InterruptedError('Przerwano kopiowanie; źródło zachowane')
                                    b = inp.read(4*1024*1024)
                                    if not b:
                                        break
                                    out.write(b)
                                    h.update(b)
                                out.flush()
                                os.fsync(out.fileno())
                            shutil.copystat(src, tmp)
                            valid(src, item)
                            valid(tmp, item)
                            checksum = h.hexdigest()
                            if digest(src) != checksum or digest(tmp) != checksum:
                                raise ValueError('Kopia niezgodna; źródło zachowane')
                            record(item, 'copy_ready', sha256=checksum, temporary=str(tmp))
                            rename_exclusive(tmp, dst)
                            syncdir(dst.parent)
                            record(item, 'copied', sha256=checksum)
                            src.unlink()
                            syncdir(src.parent)
                            record(item, 'moved', sha256=checksum)
                        else:
                            syncdir(dst.parent)
                            syncdir(src.parent)
                            d = valid(dst, item)
                            record(item, 'moved', inode=d.st_ino, device=d.st_dev)
                    done += 1
                    # Rate is measured for this run, not previous completed files.
                    elapsed = time.monotonic()-self.started
                    speed = (done-initial_done)/elapsed if elapsed else 0
                    self.status('moving', done, total, rate_current=round(speed, 2),
                                eta_current=round((total-done)/speed) if speed else None)
            for n, item in enumerate(plan['files'], 1):
                if Path(item['source']).exists():
                    raise ValueError('Źródło nadal istnieje: '+item['source'])
                valid(Path(item['destination']), item)
                if n % 64 == 0 or n == total:
                    self.status('verifying', n, total)
            save(self.job/'verification.json', dict(files=total, bytes=plan['bytes'], errors=0))
            self.status('complete', total, total)
        except InterruptedError:
            self.status('paused', done, total)
            raise
        except Exception as e:
            self.status('failed', done, total, error=str(e))
            raise
        finally:
            lock.rmdir()
