"""Capture dates with explicit fallback; Python 3.8 compatible."""
import io
import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
import exifread
import pytz

logging.getLogger('exifread').setLevel(logging.ERROR)
PHOTOS = set('jpg jpeg jpe jfif png tif tiff heic heif hif avif webp gif bmp jxl jp2 j2k jpf jpx psd psb dng cr2 cr3 crw nef nrw arw srf sr2 raf orf rw2 rwl raw pef ptx srw x3f 3fr fff iiq k25 kdc dcr erf mef mos mrw bay cap eip mpo jxr wdp hd hdr exr pic pnm ppm pgm pbm pam tga pcx ico icns svg eps ai'.split())
VIDEOS = set('264 265 3g2 3gp 3gpp 3gpp2 amv asf av1 avi bik bk2 braw cine crm dav dif divx dv dvr-ms f4b f4p f4v flv gxf h264 h265 hevc ivf m1v m2p m2t m2ts m2v m4v mjpeg mjpg mkv mod mov mp4 mpe mpeg mpg mts mxf nsv nut ogm ogv qt r3d rec rm rmvb roq rv smk tod tp trp ts vob vp8 vp9 vro webm wmv wmx wtv wvx xvid y4m'.split())
SIDECARS = set('json xmp dop acr aae pp3 cos cof nksc'.split())

def parse(value):
    m = re.search(r'(\d{4})[:-](\d\d)[:-](\d\d)[ T](\d\d):(\d\d):(\d\d)', str(value))
    if m:
        try:
            d = datetime(*map(int, m.groups()))
            if 1900 <= d.year <= datetime.now().year + 1:
                return d
        except ValueError:
            pass

def quicktime_date(path):
    with path.open('rb') as f:
        def walk(end, depth=0):
            while f.tell() + 8 <= end:
                start = f.tell()
                head = f.read(8)
                size, kind = int.from_bytes(head[:4], 'big'), head[4:]
                header = 8
                if size == 1:
                    size, header = int.from_bytes(f.read(8), 'big'), 16
                if size == 0:
                    size = end - start
                if size < header or start + size > end:
                    break
                if kind == b'mvhd':
                    data = f.read(16)
                    if len(data) >= 12:
                        stamp = int.from_bytes(data[4:12] if data[0] == 1 else data[4:8], 'big')
                        d = datetime(1904, 1, 1) + timedelta(seconds=stamp)
                        if 1900 < d.year <= datetime.now().year + 1:
                            return d
                if kind == b'moov' and depth < 3:
                    d = walk(start + size, depth + 1)
                    if d:
                        return d
                f.seek(start + size)
        return walk(path.stat().st_size)

def capture(path, mtime, timezone, lookup):
    warnings = []
    ext = path.suffix.lower().lstrip('.')
    if ext in PHOTOS:
        try:
            with path.open('rb') as f:
                if ext == 'cr3':
                    head = f.read(2 * 1024 * 1024)
                    tags = {}
                    for marker in (b'CMT1', b'CMT2'):
                        pos = head.find(marker)
                        if pos >= 4:
                            size = int.from_bytes(head[pos-4:pos], 'big')
                            if 8 <= size <= len(head)-pos+4:
                                tags.update(exifread.process_file(io.BytesIO(head[pos+4:pos-4+size]), details=False))
                else:
                    tags = exifread.process_file(f, details=False)
            for key in ('EXIF DateTimeOriginal', 'Image DateTimeOriginal', 'EXIF DateTimeDigitized'):
                d = parse(tags.get(key))
                if d:
                    return d, key, warnings
            with path.open('rb') as f:
                head = f.read(2 * 1024 * 1024)
            for key in (b'DateTimeOriginal', b'DateCreated', b'CreateDate'):
                match = re.search(key + rb'[^0-9]{1,8}(\d{4}[:-]\d\d[:-]\d\d[T ]\d\d:\d\d:\d\d)', head)
                if match:
                    d = parse(match.group(1).decode('ascii'))
                    if d:
                        return d, 'XMP ' + key.decode(), warnings
        except Exception as e:
            warnings.append(str(e))
    if ext in ('mp4', 'mov', 'm4v', '3gp', '3g2'):
        try:
            d = quicktime_date(path)
            if d:
                return d, 'QuickTime mvhd (unconverted camera timestamp)', warnings
        except (OSError, ValueError, OverflowError) as e:
            warnings.append(str(e))
    for suffix in ('.json', '.supplemental-metadata.json'):
        for candidate in (str(path) + suffix, str(path.parent/'json'/(path.name+suffix))):
            side = lookup.get(candidate.casefold())
            if side:
                try:
                    data = json.loads(Path(side).read_text(encoding='utf-8'))
                    stamp = data.get('photoTakenTime', {}).get('timestamp')
                    if stamp:
                        return datetime.fromtimestamp(int(stamp), pytz.timezone(timezone)), 'Google photoTakenTime', warnings
                except Exception as e:
                    warnings.append(str(e))
    return datetime.fromtimestamp(mtime, pytz.timezone(timezone)), 'mtime', warnings
