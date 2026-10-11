"""Planning stages; serialized plans and deterministic naming stay unchanged."""
import hashlib
import os
from pathlib import Path
from .extensions import GROUPS, normalize_extensions, matches, scope_categories
from .metadata import PHOTOS, VIDEOS, SIDECARS, capture
from .resources import resource_reason

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

def prepare_configuration(source, target, pattern, scope, timezone, extensions,
                          skip_app_resources, exclude_dirs):
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
    return source, target, categories, extensions, config, exclusions


def scan_source(source, target, job, exclusions, skip_app_resources, status, stop):
    rows, skipped, skipped_resources = [], [], []
    source_directories = [str(source)]
    stack = [source]
    status('scanning', 0, 0)
    while stack:
        if stop():
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
                    if inside_target or resolved == job or (directory == source and e.name.casefold() == 'duplikaty'):
                        skipped.append(e.path)
                    else:
                        stack.append(Path(e.path))
                        source_directories.append(str(resolved))
                elif e.is_file(follow_symlinks=False):
                    s = e.stat(follow_symlinks=False)
                    rows.append(dict(path=e.path, size=s.st_size, mtime=s.st_mtime))
        status('scanning', len(rows), 0)
    rows.sort(key=lambda r: r['path'].casefold())
    return rows, skipped, skipped_resources, source_directories


def select_media(rows, categories, extensions, timezone, status, stop):
    lookup = {r['path'].casefold(): r['path'] for r in rows}
    selected, dates, warnings = [], {}, []
    for n, r in enumerate(rows, 1):
        if stop():
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
            status('dates', n, len(rows))
    return selected, dates, warnings, lookup


def attach_companions(rows, selected, lookup):
    rows_by_path = {r['path']: r for r in rows}
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
                    selected.append(rows_by_path[match])
                    selected_paths.add(match)
    return companions


def assign_destinations(selected, companions, dates, target, pattern):
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
    return files
