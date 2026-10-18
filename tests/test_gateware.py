import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for name in ['references/migen','references/litex','gateware']:sys.path.insert(0,str(ROOT/name))
try:
    from migen.sim import run_simulation
    from gpio import SlowGPIO, SlowIdentity
    AVAILABLE=True
except ImportError:
    AVAILABLE=False


@unittest.skipUnless(AVAILABLE,'reference Migen/LiteX checkout required')
class GatewareTests(unittest.TestCase):
    def test_pin_directions_and_values(self):
        d=SlowGPIO()
        def bench():
            self.assertEqual((yield d.pins_oe),0)
            yield d.output.storage.eq(0x1234)
            yield d.oe.storage.eq(0x55)
            yield d.pins_in.eq(0xabcd)
            yield
            self.assertEqual((yield d.pins_out),0x1234)
            self.assertEqual((yield d.pins_oe),0x55)
            self.assertEqual((yield d.input.status),0xabcd)
        run_simulation(d,bench())

    def test_abi(self):
        d=SlowIdentity()
        def bench():
            yield
            self.assertEqual((yield d.abi.status),0x53434731)
        run_simulation(d,bench())
