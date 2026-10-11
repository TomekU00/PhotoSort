"""Conservative directory-based application resource exclusions."""
from pathlib import Path
import os

RESOURCE_DIRS = {
    'program files', 'program files (x86)', 'windows', 'node_modules',
    '.venv', 'venv', '.git', '__pycache__', '.pytest_cache', '.mypy_cache',
    '.npm', '.nuget', '.gradle',
}

def resource_reason(directory):
    directory = Path(directory)
    for part in directory.parts:
        name = part.casefold()
        if name in RESOURCE_DIRS:
            return 'Zasoby aplikacji: katalog ' + part
        if name.endswith(('.app', '.lrdata')):
            return 'Pakiet aplikacji lub podglądy Lightroom: ' + part
    names = set()
    with os.scandir(directory) as entries:
        for entry in entries:
            name = entry.name.casefold()
            if (name == 'pyvenv.cfg' or name.endswith(('.exe', '.dll'))) and entry.is_file(follow_symlinks=False):
                names.add(name)
    if 'pyvenv.cfg' in names:
        return 'Środowisko Python (pyvenv.cfg)'
    if any(n.endswith('.exe') for n in names) and any(n.endswith('.dll') for n in names):
        return 'Katalog programu zawierający EXE i DLL'
    return None
