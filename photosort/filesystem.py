"""Durable writes and exclusive file operations; order is a safety contract."""
import ctypes
import errno
import hashlib
import json
import os
import shutil
import stat
from pathlib import Path

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


class FileMover:
    """Execute one planned file using the persisted journal state."""
    def __init__(self, source_root, target_root, journal, stop, rename=rename_exclusive, sync=syncdir):
        self.source_root = source_root
        self.target_root = target_root
        self.journal = journal
        self.identity = journal.identity
        self.stop = stop
        self.rename = rename
        self.syncdir = sync

    def valid(self, path, item):
        s = path.lstat()
        if not stat.S_ISREG(s.st_mode) or s.st_size != item['size'] or abs(s.st_mtime-item['mtime']) > .002:
            raise ValueError('Plik zmieniony: '+str(path))
        return s

    def digest(self, path):
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

    def linked_intent(self, src, dst, item, event):
        """Recognize an interrupted link/unlink only from persisted identity."""
        if not event or event['status'] not in ('intent', 'linked'):
            return False
        source_stat = self.valid(src, item)
        target_stat = self.valid(dst, item)
        identity = (event.get('device'), event.get('inode'))
        return (source_stat.st_dev, source_stat.st_ino) == identity == (target_stat.st_dev, target_stat.st_ino)

    def preflight(self, item):
        src, dst = Path(item['source']), Path(item['destination'])
        src.parent.resolve().relative_to(self.source_root)
        dst.parent.resolve().relative_to(self.target_root)
        event = self.journal.prior.get(str(src))
        if src.exists():
            self.valid(src, item)
            if dst.exists() and not (event and event['status'] in ('copy_ready', 'copied')
                                     or self.linked_intent(src, dst, item, event)):
                raise FileExistsError(str(dst))
        else:
            if not event:
                raise FileNotFoundError(str(src))
            s = self.valid(dst, item)
            if event.get('sha256'):
                if self.digest(dst) != event['sha256']:
                    raise ValueError('Błąd sumy kontrolnej: '+str(dst))
            elif (s.st_dev, s.st_ino) != (event['device'], event['inode']):
                raise ValueError('Nie można potwierdzić poprzedniego przeniesienia')
            return True
        return False

    def move(self, item):
        src, dst = Path(item['source']), Path(item['destination'])
        if not src.exists():
            return False
        s = self.valid(src, item)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.parent.resolve().relative_to(self.target_root)
        old = self.journal.prior.get(str(src))
        if dst.exists():
            linked = self.linked_intent(src, dst, item, old)
            if not linked and (not old or old['status'] not in ('copy_ready', 'copied')):
                raise FileExistsError(str(dst))
            if old.get('sha256'):
                if self.digest(src) != old['sha256'] or self.digest(dst) != old['sha256']:
                    raise ValueError('Wznowienie: kopia niezgodna')
            elif not linked:
                raise ValueError('Wznowienie: inny plik')
            self.valid(src, item)
            # The crash may have happened immediately after link(), before sync.
            self.syncdir(dst.parent)
            src.unlink()
            self.syncdir(src.parent)
            self.journal.record(item, 'moved', **{k: old[k] for k in ('sha256', 'device', 'inode') if k in old})
        else:
            self.journal.record(item, 'intent', inode=s.st_ino, device=s.st_dev,
                   **({'temporary': old['temporary']} if old and old.get('temporary') else {}))
            try:
                self.rename(src, dst)
            except OSError as e:
                if e.errno != errno.EXDEV and getattr(e, 'winerror', None) != 17:
                    raise
                if shutil.disk_usage(dst.parent).free < item['size'] + 64*1024*1024:
                    raise OSError('Za mało miejsca na następny plik')
                tmp = dst.parent/('.photosort-'+self.identity[:12]+'-'+hashlib.sha256(str(src).encode()).hexdigest()[:16]+'.part')
                if tmp.exists():
                    if not old or old['status'] not in ('intent', 'copying', 'copy_ready') or old.get('temporary') != str(tmp):
                        raise FileExistsError('Nieznany plik tymczasowy: '+str(tmp))
                    self.valid(src, item)
                    tmp.unlink()
                self.journal.record(item, 'copying', temporary=str(tmp), inode=s.st_ino, device=s.st_dev)
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
                self.valid(src, item)
                self.valid(tmp, item)
                checksum = h.hexdigest()
                if self.digest(src) != checksum or self.digest(tmp) != checksum:
                    raise ValueError('Kopia niezgodna; źródło zachowane')
                self.journal.record(item, 'copy_ready', sha256=checksum, temporary=str(tmp))
                self.rename(tmp, dst)
                self.syncdir(dst.parent)
                self.journal.record(item, 'copied', sha256=checksum)
                src.unlink()
                self.syncdir(src.parent)
                self.journal.record(item, 'moved', sha256=checksum)
            else:
                self.syncdir(dst.parent)
                self.syncdir(src.parent)
                d = self.valid(dst, item)
                self.journal.record(item, 'moved', inode=d.st_ino, device=d.st_dev)
        return True


def cleanup_empty_directories(plan, source_root, target_root, stop):
    directories = {Path(p) for p in plan.get('source_directories', [])}
    for item in plan['files']:
        parent = Path(item['source']).parent
        while parent != source_root.parent:
            directories.add(parent)
            if parent == source_root:
                break
            parent = parent.parent
    removed, cleanup_errors = [], []
    for directory in sorted(directories, key=lambda p: len(p.parts), reverse=True):
        if stop():
            raise InterruptedError('Przerwano sprzątanie')
        try:
            directory.relative_to(source_root)
            # Never delete a drive/share/mount root or the destination tree.
            if directory == Path(directory.anchor) or os.path.ismount(directory):
                continue
            try:
                directory.relative_to(target_root)
                continue
            except ValueError:
                pass
            if directory.is_symlink():
                continue
            directory.rmdir()  # Atomic: refuses directories containing any files.
            removed.append(str(directory))
        except FileNotFoundError:
            pass
        except OSError as e:
            if e.errno not in (errno.ENOTEMPTY, errno.EEXIST):
                cleanup_errors.append(dict(path=str(directory), error=str(e)))
    return removed, cleanup_errors
