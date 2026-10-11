"""Extension presets shared by GUI, CLI and the NAS worker."""
import re
from pathlib import Path

GROUPS = {'Zdjęcia i grafika': ['ai',
                       'avif',
                       'bmp',
                       'eps',
                       'exr',
                       'gif',
                       'hd',
                       'hdr',
                       'heic',
                       'heif',
                       'hif',
                       'icns',
                       'ico',
                       'j2k',
                       'jfif',
                       'jp2',
                       'jpe',
                       'jpeg',
                       'jpf',
                       'jpg',
                       'jpx',
                       'jxl',
                       'jxr',
                       'mpo',
                       'pam',
                       'pbm',
                       'pcx',
                       'pgm',
                       'pic',
                       'png',
                       'pnm',
                       'ppm',
                       'psb',
                       'psd',
                       'svg',
                       'tga',
                       'tif',
                       'tiff',
                       'wdp',
                       'webp'],
 'RAW': ['3fr',
         'arw',
         'bay',
         'cap',
         'cr2',
         'cr3',
         'crw',
         'dcr',
         'dng',
         'eip',
         'erf',
         'fff',
         'iiq',
         'k25',
         'kdc',
         'mef',
         'mos',
         'mrw',
         'nef',
         'nrw',
         'orf',
         'pef',
         'ptx',
         'raf',
         'raw',
         'rw2',
         'rwl',
         'sr2',
         'srf',
         'srw',
         'x3f'],
 'Filmy': ['264',
           '265',
           '3g2',
           '3gp',
           '3gpp',
           '3gpp2',
           'amv',
           'asf',
           'av1',
           'avi',
           'bik',
           'bk2',
           'braw',
           'cine',
           'crm',
           'dav',
           'dif',
           'divx',
           'dv',
           'dvr-ms',
           'f4b',
           'f4p',
           'f4v',
           'flv',
           'gxf',
           'h264',
           'h265',
           'hevc',
           'ivf',
           'm1v',
           'm2p',
           'm2t',
           'm2ts',
           'm2v',
           'm4v',
           'mjpeg',
           'mjpg',
           'mkv',
           'mod',
           'mov',
           'mp4',
           'mpe',
           'mpeg',
           'mpg',
           'mts',
           'mxf',
           'nsv',
           'nut',
           'ogm',
           'ogv',
           'qt',
           'r3d',
           'rec',
           'rm',
           'rmvb',
           'roq',
           'rv',
           'smk',
           'tod',
           'tp',
           'trp',
           'ts',
           'vob',
           'vp8',
           'vp9',
           'vro',
           'webm',
           'wmv',
           'wmx',
           'wtv',
           'wvx',
           'xvid',
           'y4m'],
 'Dźwięk': ['mp3', 'wav', 'flac', 'aac', 'm4a', 'ogg', 'opus', 'wma', 'aiff', 'aif', 'amr', 'f4a']}
KNOWN = {ext for values in GROUPS.values() for ext in values if not ext.startswith('@')}

def normalize_extensions(values):
    if values is None:
        return None
    if isinstance(values, str):
        values = re.split(r'[,;\s]+', values)
    result = sorted({v.strip().lower().lstrip('.') for v in values if v.strip()})
    if not result:
        raise ValueError('Wybierz co najmniej jedno rozszerzenie lub wszystkie pliki.')
    if any(v not in KNOWN for v in result):
        raise ValueError('Wybierz wyłącznie obsługiwane formaty multimedialne, np. jpg, cr3, mp4, mp3.')
    return result

def matches(path, extensions):
    ext = Path(path).suffix.lower().lstrip('.')
    return ext in KNOWN and (extensions is None or ext in extensions)


def scope_categories(scope):
    aliases = {'multimedia': {'photos','video','audio'}, 'all': {'photos','video','audio'},
               'media': {'photos','video'}}
    result = set()
    for token in scope.split(','):
        token = token.strip()
        if token in aliases:
            result.update(aliases[token])
        elif token in ('photos','video','audio'):
            result.add(token)
        else:
            raise ValueError('Wybierz zakres: photos, video, audio lub ich kombinację.')
    return result
