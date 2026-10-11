"""Durable quarantine routes, independent of the immutable sorting plan."""
import json
import stat
from pathlib import Path
from .filesystem import save
from .journal import plan_identity
from .planning import attach_companions
from .metadata import SIDECARS


class DuplicateRoutes:
    def __init__(self, plan, job, journal, mover):
        self.plan, self.journal, self.mover = plan, journal, mover
        self.source = Path(plan['config']['source'])
        self.target = Path(plan['config']['target'])
        self.root = self.source / 'Duplikaty'
        self.path = job / 'duplicates.json'
        self.identity = plan_identity(plan)
        self.routes = {}
        if self.path.exists():
            value = json.loads(self.path.read_text(encoding='utf-8'))
            if value['plan_id'] != self.identity:
                raise ValueError('Raport duplikatów należy do innego planu')
            self.routes = value['routes']
        rows = [dict(path=i['source'], size=i['size'], mtime=i['mtime']) for i in plan['files']]
        media = [r for r in rows if Path(r['path']).suffix.lower().lstrip('.') not in SIDECARS]
        companions = attach_companions(rows, list(media), {r['path'].casefold(): r['path'] for r in rows})
        self.groups = {}
        self.group_for = {}
        for item in plan['files']:
            anchor = Path(companions.get(item['source'], item['source']))
            key = (str(anchor.parent), anchor.stem.casefold())
            self.groups.setdefault(key, []).append(item)
            self.group_for[item['source']] = key
        self.companions = companions

    def identical(self, item, candidate):
        src = Path(item['source'])
        if not src.exists():
            return False
        self.mover.valid(src, item)
        candidate.parent.resolve().relative_to(self.target.resolve())
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            return False
        if not stat.S_ISREG(info.st_mode) or info.st_size != item['size']:
            return False
        before = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
        same = self.mover.digest(src) == self.mover.digest(candidate)
        self.mover.valid(src, item)
        info = candidate.lstat()
        return same and before == (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)

    def prepare(self, item):
        group = self.groups[self.group_for[item['source']]]
        # Once execution starts, the chosen group destinations are immutable.
        if any(i['source'] in self.routes or i['source'] in self.journal.prior for i in group):
            return
        media = [i for i in group if i['source'] not in self.companions]
        matches = {}
        for row in media:
            dst = Path(row['destination'])
            candidates = [dst.parent / Path(row['source']).name, dst]
            match = next((p for p in candidates if self.identical(row, p)), None)
            if match is None:
                return
            matches[row['source']] = str(match)
        if not matches:
            return
        if self.root.is_symlink():
            raise ValueError('Folder Duplikaty nie może być dowiązaniem')
        self.root.resolve().relative_to(self.source.resolve())
        try:
            self.root.resolve().relative_to(self.target.resolve())
        except ValueError:
            pass
        else:
            raise ValueError('Folder Duplikaty nie może znajdować się w celu')
        for row in group:
            destination = self.root / Path(row['source']).relative_to(self.source)
            destination.parent.resolve().relative_to(self.root.resolve())
            if destination.exists() or destination.is_symlink():
                raise FileExistsError('Zajęte miejsce w Duplikaty: ' + str(destination))
        for row in group:
            anchor = self.companions.get(row['source'], row['source'])
            self.routes[row['source']] = dict(destination=str(self.root / Path(row['source']).relative_to(self.source)),
                                             duplicate_of=matches[anchor])
        save(self.path, dict(plan_id=self.identity, routes=self.routes))

    def effective(self, item):
        route = self.routes.get(item['source'])
        if route is None:
            return item
        expected = self.root / Path(item['source']).relative_to(self.source)
        if Path(route['destination']) != expected:
            raise ValueError('Nieprawidłowa ścieżka duplikatu')
        if self.root.is_symlink():
            raise ValueError('Folder Duplikaty nie może być dowiązaniem')
        self.root.resolve().relative_to(self.source.resolve())
        expected.parent.resolve().relative_to(self.root.resolve())
        return dict(item, **route)
