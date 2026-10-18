"""Module-side profile validation; not a physical DIOT adapter test."""
import copy
from pathlib import Path
import unittest
from sinara_slow.config import load, validate
from sinara_slow.errors import ValidationError
from sinara_slow.pinmaps import spi_mapping

ROOT = Path(__file__).resolve().parents[1]


class UrukulPinmapTests(unittest.TestCase):
    def test_reference_eem0(self):
        self.assertEqual(spi_mapping('urukul_eem0'),
                         dict(clk=0, mosi=1, miso=2, cs=[3, 4, 5]))
        mapping = spi_mapping('urukul_eem0')
        mapping['cs'][0] = 15
        self.assertEqual(spi_mapping('urukul_eem0')['cs'], [3, 4, 5])

    def test_mismatch_rejected_for_both_controllers(self):
        for controller in ('stm', 'kasli'):
            profile = load(ROOT / f'examples/{controller}.simulation.yaml', 'connection')
            for key, wrong in [('cs', [5, 4, 3]), ('clk', 6), ('miso', 7)]:
                bad = copy.deepcopy(profile)
                bad['bindings']['rf0'][key] = wrong
                with self.assertRaises(ValidationError):
                    validate(bad, 'connection')
            bad = copy.deepcopy(profile)
            bad['bindings']['rf0']['pinmux'] = 'urukul_eem1'
            with self.assertRaises(ValidationError):
                validate(bad, 'connection')
