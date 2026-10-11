from pathlib import Path
import unittest
from photosort.planning import attach_companions


class CountedRows(list):
    def __init__(self, values):
        super().__init__(values)
        self.visits = 0

    def __iter__(self):
        for row in super().__iter__():
            self.visits += 1
            yield row


class CompanionTests(unittest.TestCase):
    def row(self, name):
        return dict(path=str(Path('album')/name), size=10, mtime=1710000000)

    def test_shared_edit_keeps_first_claimant_and_original_records(self):
        raw, jpeg, edit = [self.row(n) for n in ('image.cr3', 'image.jpg', 'image.xmp')]
        rows = [raw, jpeg, edit]
        lookup = {r['path'].casefold(): r['path'] for r in rows}
        selected = [raw, jpeg]
        companions = attach_companions(rows, selected, lookup)
        self.assertEqual(companions, {edit['path']: raw['path']})
        self.assertEqual(selected, rows)
        self.assertIs(selected[-1], edit)

    def test_takeout_sidecars_and_case_insensitive_lookup_are_preserved(self):
        photo, side, supplemental = [self.row(n) for n in
            ('image.JPG', 'json/image.JPG.JSON', 'image.JPG.supplemental-metadata.json')]
        rows = [photo, side, supplemental]
        selected = [photo]
        companions = attach_companions(rows, selected,
                                       {r['path'].casefold(): r['path'] for r in rows})
        self.assertEqual(companions, {side['path']: photo['path'], supplemental['path']: photo['path']})
        self.assertEqual({r['path'] for r in selected}, {r['path'] for r in rows})

    def test_large_takeout_collection_does_not_rescan_rows_per_sidecar(self):
        for count in (100, 1000):
            with self.subTest(count=count):
                photos = [self.row('photo-{}.jpg'.format(n)) for n in range(count)]
                sidecars = [self.row('photo-{}.jpg.json'.format(n)) for n in range(count)]
                values = photos + sidecars
                lookup = {r['path'].casefold(): r['path'] for r in values}
                rows = CountedRows(values)
                selected = list(photos)
                companions = attach_companions(rows, selected, lookup)
                self.assertEqual(len(companions), count)
                self.assertEqual(len(selected), 2*count)
                # Count actual traversal, avoiding machine-dependent timing limits.
                self.assertLessEqual(rows.visits, 2*len(rows))
