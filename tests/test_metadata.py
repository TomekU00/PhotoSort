import json
from datetime import datetime
from pathlib import Path
import tempfile
import unittest

import pytz
from photosort.metadata import capture, quicktime_date


def atom(kind, payload):
    return (len(payload)+8).to_bytes(4, 'big') + kind + payload


def movie(stamp, version=0):
    width = 8 if version == 1 else 4
    payload = bytes([version, 0, 0, 0]) + stamp.to_bytes(width, 'big') + bytes(16)
    return atom(b'moov', atom(b'mvhd', payload))


class QuickTimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'clip.mp4'

    def tearDown(self):
        self.temp.cleanup()

    def test_zero_date_falls_back_to_sidecar_for_both_versions(self):
        side = Path(str(self.path)+'.json')
        side.write_text(json.dumps({'photoTakenTime': {'timestamp': '946684800'}}))
        for version in (0, 1):
            with self.subTest(version=version):
                self.path.write_bytes(movie(0, version))
                self.assertIsNone(quicktime_date(self.path))
                date, method, warnings = capture(self.path, 1710000000, 'UTC',
                                                 {str(side).casefold(): str(side)})
                self.assertEqual(date, datetime(2000, 1, 1, tzinfo=pytz.UTC))
                self.assertEqual(method, 'Google photoTakenTime')
                self.assertEqual(warnings, [])

    def test_zero_date_without_sidecar_uses_mtime(self):
        self.path.write_bytes(movie(0))
        date, method, _ = capture(self.path, 1710000000, 'Europe/Warsaw', {})
        self.assertEqual(date.timestamp(), 1710000000)
        self.assertEqual(method, 'mtime')

    def test_valid_creation_dates_are_preserved_for_both_versions(self):
        expected = datetime(2024, 3, 9, 16, 0, 0)
        stamp = int((expected-datetime(1904, 1, 1)).total_seconds())
        for version in (0, 1):
            with self.subTest(version=version):
                self.path.write_bytes(movie(stamp, version))
                date, method, _ = capture(self.path, 0, 'UTC', {})
                self.assertEqual(date, expected)
                self.assertTrue(method.startswith('QuickTime'))

    def test_unsupported_version_and_truncated_atom_do_not_supply_date(self):
        # A following atom must never complete a truncated timestamp.
        for payload in (movie(1, 2), atom(b'moov', atom(b'mvhd', b'\0'*4)
                                        + atom(b'free', b'1234567890123456'))):
            with self.subTest(payload=payload):
                self.path.write_bytes(payload)
                self.assertIsNone(quicktime_date(self.path))
