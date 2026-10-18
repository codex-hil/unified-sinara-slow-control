"""Real QSPI x4 pins -> Wishbone -> slot FIFO; no board access."""
import sys
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
for p in ['gateware','work/upstream-stm/deps/misoc','references/misoc','references/migen','references/litex']:sys.path.insert(0,str(ROOT/p))
from migen import Module
from migen.sim import run_simulation
from qspi_wishbone import QSPIWishbone
from queued_fabric import QueuedFabric,MAGIC
from queued_spi import command,WRITE

class QSPITests(unittest.TestCase):
    def test_real_x4_read_and_multislot_write_burst(self):
        d=Module();d.submodules.bridge=bridge=QSPIWishbone();d.submodules.fabric=fabric=QueuedFabric(depth=8,direction_half_period=1)
        d.comb += bridge.bus.connect(fabric.bus)
        def bench():
            def wait(n=12):
                for _ in range(n):yield
            def clock(nibble=0,read=False):
                yield bridge.sck.eq(0);yield bridge.dq_i.eq(nibble);yield from wait()
                value=(yield bridge.dq_o) if read else None
                if read:self.assertEqual((yield bridge.dq_oe),15)
                yield bridge.sck.eq(1);yield from wait()
                return value
            def begin(op,address):
                yield bridge.cs_n.eq(1);yield bridge.sck.eq(0);yield from wait()
                yield bridge.cs_n.eq(0);yield from wait()
                header=(op<<24)|address
                for shift in range(28,-1,-4):yield from clock((header>>shift)&15)
            def end():
                yield bridge.cs_n.eq(1);yield from wait()
                self.assertEqual((yield bridge.dq_oe),0)
            yield from begin(0x0b,0)
            for _ in range(8):yield from clock()
            value=0
            for _ in range(8):value=(value<<4)|(yield from clock(read=True))
            self.assertEqual(value,MAGIC)
            yield from end()
            words=[(2<<16)|0,command(WRITE,0,1),0xa5,(2<<16)|7,command(WRITE,1,1),0x5a]
            yield from begin(0x32,0x40)
            for word in words:
                for shift in range(28,-1,-4):yield from clock((word>>shift)&15)
            yield from end()
            self.assertEqual((yield bridge.error),0)
            self.assertEqual((yield fabric.spi[0].tx_level),2)
            self.assertEqual((yield fabric.spi[7].tx_level),2)
            for q in fabric.spi[1:7]:self.assertEqual((yield q.tx_level),0)
            # Unknown opcode and partial word cannot enqueue a command.
            yield from begin(0x99,0x40);yield from clock(3);yield from end()
            self.assertEqual((yield bridge.error),1)
            self.assertEqual((yield fabric.spi[0].tx_level),2)
        run_simulation(d,bench())
