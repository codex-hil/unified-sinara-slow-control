"""External shift/storage register model, not PCB validation."""
import sys
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]
for p in ['references/migen', 'gateware']:
    sys.path.insert(0, str(ROOT / p))
from migen.sim import run_simulation
from direction import DirectionController


class DirectionTests(unittest.TestCase):
    def test_chain_and_transactions(self):
        for serial in (True, False):
            d = DirectionController(48, serial=serial, half_period=2, settle_cycles=3)
            def bench():
                shifted = 0
                stored = None
                prev_clk = prev_latch = 0
                edges = latches = 0
                def check():
                    nonlocal shifted, stored, prev_clk, prev_latch, edges, latches
                    clk, latch = (yield d.sck), (yield d.latch)
                    if clk and not prev_clk:
                        shifted = ((shifted << 1) | (yield d.mosi)) & ((1 << 48) - 1)
                        edges += 1
                    if latch and not prev_latch:
                        stored = shifted
                        latches += 1
                    prev_clk, prev_latch = clk, latch
                    if (yield d.busy):
                        self.assertEqual((yield d.oe), 0)
                def wait_ready():
                    for _ in range(1000):
                        yield from check()
                        if (yield d.ready): return
                        yield
                    self.fail('bounded transaction timed out')
                yield from wait_ready()
                self.assertEqual((yield d.active), 0)
                self.assertEqual((yield d.valid), 1)
                if serial:
                    self.assertEqual(stored, 0)
                    self.assertEqual(edges, 48)
                for mask in (0x123456789ABC, 0xFFFFFFFFFFFF, 0):
                    previous = (yield d.active)
                    yield d.quiescent.eq(0)
                    yield d.requested.eq(mask)
                    yield d.apply.eq(1)
                    yield
                    yield
                    self.assertEqual((yield d.ready), 0)
                    self.assertEqual((yield d.active), previous)
                    yield d.quiescent.eq(1)
                    yield
                    yield
                    self.assertEqual((yield d.busy), 1)
                    yield d.apply.eq(0)
                    # Pending is a snapshot; changing input while busy cannot corrupt it.
                    yield d.requested.eq(~mask & ((1 << 48) - 1))
                    yield from wait_ready()
                    self.assertEqual((yield d.active), mask)
                    self.assertEqual((yield d.oe), mask)
                    if serial: self.assertEqual(stored, mask)
                if serial:
                    self.assertEqual(edges, 192)
                    self.assertEqual(latches, 4)
                else:
                    self.assertEqual(edges, 0)
                    self.assertEqual(latches, 0)
            run_simulation(d, bench())

    def test_parameters(self):
        for args in [(0, 1, 1), (8, 0, 1), (8, 1, 0)]:
            with self.assertRaises(ValueError):
                DirectionController(args[0], half_period=args[1], settle_cycles=args[2])
