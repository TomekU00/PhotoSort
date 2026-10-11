"""Extension presets shared by GUI, CLI and the NAS worker."""
import re
from pathlib import Path

GROUPS = {'Zdjęcia i grafika': ['ai', 'avif', 'bmp', 'eps', 'exr', 'gif', 'hd', 'hdr', 'heic', 'heif', 'hif', 'icns', 'ico', 'j2k', 'jfif', 'jp2', 'jpe', 'jpeg', 'jpf', 'jpg', 'jpx', 'jxl', 'jxr', 'mpo', 'pam', 'pbm', 'pcx', 'pgm', 'pic', 'png', 'pnm', 'ppm', 'psb', 'psd', 'svg', 'tga', 'tif', 'tiff', 'wdp', 'webp'], 'RAW': ['3fr', 'arw', 'bay', 'cap', 'cr2', 'cr3', 'crw', 'dcr', 'dng', 'eip', 'erf', 'fff', 'iiq', 'k25', 'kdc', 'mef', 'mos', 'mrw', 'nef', 'nrw', 'orf', 'pef', 'ptx', 'raf', 'raw', 'rw2', 'rwl', 'sr2', 'srf', 'srw', 'x3f'], 'Filmy': ['264', '265', '3g2', '3gp', '3gpp', '3gpp2', 'amv', 'asf', 'av1', 'avi', 'bik', 'bk2', 'braw', 'cine', 'crm', 'dav', 'dif', 'divx', 'dv', 'dvr-ms', 'f4b', 'f4p', 'f4v', 'flv', 'gxf', 'h264', 'h265', 'hevc', 'ivf', 'm1v', 'm2p', 'm2t', 'm2ts', 'm2v', 'm4v', 'mjpeg', 'mjpg', 'mkv', 'mod', 'mov', 'mp4', 'mpe', 'mpeg', 'mpg', 'mts', 'mxf', 'nsv', 'nut', 'ogm', 'ogv', 'qt', 'r3d', 'rec', 'rm', 'rmvb', 'roq', 'rv', 'smk', 'tod', 'tp', 'trp', 'ts', 'vob', 'vp8', 'vp9', 'vro', 'webm', 'wmv', 'wmx', 'wtv', 'wvx', 'xvid', 'y4m'], 'Pliki towarzyszące': ['json', 'xmp', 'dop', 'acr', 'aae', 'pp3', 'cos', 'cof', 'nksc'], 'Dźwięk': ['mp3', 'wav', 'flac', 'aac', 'm4a', 'ogg', 'opus', 'wma', 'aiff', 'aif', 'amr', 'f4a'], 'Dokumenty': ['pdf', 'txt', 'html', 'htm', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'rtf', 'csv', 'mobi', 'epub', 'msg'], 'Archiwa i obrazy dysków': ['zip', '7z', 'rar', 'tar', 'gz', 'bz2', 'xz', 'iso', 'dmg', 'arc'], 'Katalogi i ustawienia zdjęć': ['lrcat', 'lrtemplate', 'lnpc', 'dcp', 'dcpr', 'pto', 'pan', 'luminarneo', 'luminarbackup', 'gre', 'msk', 'cube'], 'Pozostałe znane formaty': ['db', 'pyz', 'exe', 'msi', 'log', 'bat', 'as3', 'xml', 'apk', 'aspx', 'torrent', 'sh', 'plist', 'dylib', 'pm', 'pod', 'pl', 'strings', 'xcconfig', 'lua', 'scrpt', 'nib', 'mom', 'omo', 'car', 'pak', 'dat', 'bin', 'asar', 'srt', 'conf', 'cmd', 'jar', 'license', 'properties', 'dll', 'provisionprofile', 'css', 'stringsdict', 'pem', 'sqlite', 'jsonl', 'ini', 'lst', 'sql', 'swf', 'ram'], 'Inne': ['@none', '@other']}
KNOWN = {ext for values in GROUPS.values() for ext in values if not ext.startswith('@')}

def normalize_extensions(values):
    if values is None:
        return None
    if isinstance(values, str):
        values = re.split(r'[,;\s]+', values)
    result = sorted({v.strip().lower().lstrip('.') for v in values if v.strip()})
    if not result:
        raise ValueError('Wybierz co najmniej jedno rozszerzenie lub wszystkie pliki.')
    if any(v not in ('@none', '@other') and not re.fullmatch(r'[a-z0-9_+-]{1,40}', v) for v in result):
        raise ValueError('Nieprawidłowe rozszerzenie; użyj np. jpg, cr3, mp4.')
    return result

def matches(path, extensions):
    if extensions is None:
        return True
    ext = Path(path).suffix.lower().lstrip('.')
    return ext in extensions or (not ext and '@none' in extensions) or (bool(ext) and ext not in KNOWN and '@other' in extensions)
