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

    def test_fault_discards_burst_and_new_cs_recovers(self):
        # A failed write is ambiguous: discard remaining words in that CS,
        # do not replay it, and permit a new transaction after explicit clear.
        from migen import Signal
        for fault_mode,expected_error in [(0,3),(2,2)]:
            with self.subTest(fault_mode=fault_mode):
                d=Module();d.submodules.bridge=b=QSPIWishbone(timeout_cycles=16)
                mode=Signal(2,reset=fault_mode)
                d.comb += [b.bus.ack.eq(b.bus.cyc & (mode==1)),
                           b.bus.err.eq(b.bus.cyc & (mode==2))]
                issued=[]
                def monitor():
                    previous=False
                    while True:
                        pending=(yield b.bus.cyc)
                        if pending and not previous:
                            issued.append(((yield b.bus.adr),(yield b.bus.dat_w)))
                        previous=pending
                        yield
                from migen.sim import passive
                def bench():
                    def wait(n=8):
                        for _ in range(n):yield
                    def nibble(value):
                        yield b.sck.eq(0);yield b.dq_i.eq(value);yield from wait()
                        yield b.sck.eq(1);yield from wait()
                    def word(value):
                        for shift in range(28,-1,-4):yield from nibble((value>>shift)&15)
                    def begin():
                        yield b.sck.eq(0);yield b.cs_n.eq(0);yield from wait()
                        yield from word(0x02000040)
                    def end():
                        yield b.cs_n.eq(1);yield from wait()
                        self.assertEqual((yield b.dq_oe),0)
                    yield from wait()
                    yield from begin()
                    yield from word(0x12345678)
                    yield from word(0xdeadbeef)
                    yield from end()
                    self.assertEqual((yield b.error),expected_error)
                    self.assertEqual(issued,[(0x10,0x12345678)])
                    yield mode.eq(1);yield b.clear_error.eq(1);yield
                    yield b.clear_error.eq(0);yield from wait()
                    self.assertEqual((yield b.error),0)
                    # A partial word is never submitted to Wishbone.
                    yield from begin();yield from nibble(0xa);yield from nibble(0xb)
                    yield from end()
                    self.assertEqual(len(issued),1)
                    yield from begin();yield from word(0xa5a55a5a);yield from end()
                    self.assertEqual(issued,[(0x10,0x12345678),(0x10,0xa5a55a5a)])
                    self.assertEqual((yield b.error),0)
                run_simulation(d,[bench(),passive(monitor)()])
