"""Synthetic probe log fixtures only; never mark them as hardware results."""
import unittest
from sinara_slow.hil_capture import validate_probe_capture


def fixture(abi=4):
    lines = ['INFO HIL_PROBE: read-only ECP5, no module initialization']
    for round_number in range(8):
        for address, value in ((160, 0xAAAA), (161, 0x5555), (162, abi)):
            lines.append(f'INFO HIL_PROBE: round {round_number} adr {address} value {value:04x}')
    lines.extend([f'INFO HIL_PROBE: ID_STABILITY PASS ABI {abi}',
                  'INFO HIL_PROBE: complete; idling, no CSR writes'])
    return '\n'.join(lines)


class CaptureTests(unittest.TestCase):
    def test_complete_runs_and_ansi(self):
        for abi in (3, 4):
            result = validate_probe_capture('\x1b[32m' + fixture(abi) + '\x1b[0m', abi)
            self.assertEqual(len(result['records']), 24)
            self.assertFalse(result['hardware_validated'])
    def test_wrong_values_even_with_pass_marker(self):
        with self.assertRaises(ValueError):
            validate_probe_capture(fixture().replace('value aaaa', 'value aaab', 1), 4)
    def test_missing_duplicate_reordered_and_restart(self):
        lines = fixture().splitlines()
        bad = [lines[:-1], lines[:3]+lines[4:], lines[:2]+[lines[1]]+lines[3:],
               [lines[0], lines[2], lines[1]]+lines[3:]]
        for capture in ['\n'.join(x) for x in bad] + [fixture()+'\n'+fixture()]:
            with self.assertRaises(ValueError): validate_probe_capture(capture, 4)
    def test_error_and_malformed_read(self):
        for replacement in ('QSPI read error round 0 adr 160',
                            'round 0 adr 160 value aaaa GARBAGE',
                            'round 0 adr 160 value xyz'):
            capture = fixture().replace('round 0 adr 160 value aaaa', replacement)
            with self.assertRaises(ValueError): validate_probe_capture(capture, 4)
    def test_wrong_abi_and_pass_only(self):
        for capture in (fixture(3), 'HIL_PROBE: ID_STABILITY PASS ABI 4'):
            with self.assertRaises(ValueError): validate_probe_capture(capture, 4)
