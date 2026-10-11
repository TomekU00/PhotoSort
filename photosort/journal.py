"""Version-one journal replay and durable append, without schema changes."""
import hashlib
import json
import os
from contextlib import contextmanager


def plan_identity(plan):
    return hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()


class Journal:
    def __init__(self, path, identity):
        self.path = path
        self.identity = identity
        self.prior = {}
        self.log = None

    def replay(self):
        self.prior = {}
        if self.path.exists():
            with self.path.open('rb') as f:
                cut = None
                missing_newline = False
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
                        (self.path.parent/'partial-journal.txt').write_bytes(line)
                        cut = offset
                        break
                    if event['plan_id'] != self.identity:
                        raise ValueError('Dziennik należy do innego planu')
                    self.prior[event['source']] = event
                    missing_newline = not line.endswith(b'\n')
            if cut is not None or missing_newline:
                with self.path.open('r+b') as f:
                    if cut is not None:
                        f.truncate(cut)
                    else:
                        # A complete JSON event can survive without its separator.
                        # Repair it durably before writer() appends another event.
                        f.seek(0, os.SEEK_END)
                        f.write(b'\n')
                    f.flush()
                    os.fsync(f.fileno())

    @contextmanager
    def writer(self):
        with self.path.open('a', encoding='utf-8') as log:
            self.log = log
            try:
                yield self
            finally:
                self.log = None

    def record(self, item, status, **extra):
        event = dict(item, status=status, plan_id=self.identity, **extra)
        self.log.write(json.dumps(event, ensure_ascii=False)+'\n')
        self.log.flush()
        os.fsync(self.log.fileno())
        self.prior[item['source']] = event
