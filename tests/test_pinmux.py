"""Logical routing/OE tests. No physical LVDS/transceiver validation."""
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
for p in ["references/migen", "gateware"]:
    sys.path.insert(0, str(ROOT / p))
from migen import TSTriple
from migen.sim import run_simulation
from pinmux import SlotPinMux
from sinara_slow.pinmaps import spi_mapping


class SPI:
    def __init__(self):
        self.clk, self.mosi, self.miso = (TSTriple() for _ in range(3))
        self.cs_spi = TSTriple(16)


class PinMuxTests(unittest.TestCase):
    def test_default_and_remapped_routes(self):
        for mapping in [spi_mapping('urukul_eem0'), None, {"clk": 7, "mosi": 5, "miso": 4, "cs": [3, 8, 9]}]:
            s = SPI()
            d = SlotPinMux(s, mapping=mapping)
            m = mapping or {"clk": 0, "mosi": 1, "miso": 2, "cs": [3]}
            def bench():
                self.assertEqual((yield d.offline), 1)
                yield d.output.eq(0xA55A)
                yield d.oe.eq(0xFFFF)
                yield s.clk.o.eq(1)
                yield s.mosi.o.eq(0)
                yield s.miso.o.eq(1)
                yield s.clk.oe.eq(1)
                yield s.mosi.oe.eq(1)
                yield s.miso.oe.eq(0)
                yield s.cs_spi.o.eq(0b101)
                yield s.cs_spi.oe.eq(1)
                for i, p in enumerate(d.slot):
                    yield p.i.eq((0x965A >> i) & 1)
                yield
                for i, p in enumerate(d.slot):
                    self.assertEqual((yield p.o), (0xA55A >> i) & 1)
                    self.assertEqual((yield p.oe), 1)
                self.assertEqual((yield d.input), 0x965A)
                yield d.offline.eq(0)
                yield
                for name, value, oe in [("clk", 1, 1), ("mosi", 0, 1), ("miso", 1, 0)]:
                    p = d.slot[m[name]]
                    self.assertEqual((yield p.o), value)
                    self.assertEqual((yield p.oe), oe)
                    self.assertEqual((yield getattr(s, name).i), (0x965A >> m[name]) & 1)
                for bit, line in enumerate(m["cs"]):
                    self.assertEqual((yield d.slot[line].o), (0b101 >> bit) & 1)
                yield d.spi_mask.eq(0)
                yield
                self.assertEqual((yield d.slot[m["miso"]].oe), 1)
                self.assertEqual((yield d.slot[m["clk"]].o), (0xA55A >> m["clk"]) & 1)
            run_simulation(d, bench())

    def test_bad_mapping_rejected(self):
        for m in [{"clk": 0, "mosi": 0, "miso": 2, "cs": [3]},
                  {"clk": 0, "mosi": 1, "miso": 16, "cs": [3]},
                  {"clk": 0, "mosi": 1, "miso": 2, "cs": []}]:
            with self.assertRaises(ValueError):
                SlotPinMux(SPI(), mapping=m)
