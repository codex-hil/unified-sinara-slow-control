"""Directed simulation of the unchanged upstream slot controller, not HIL."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work/upstream-stm/gateware"))
from migen.sim import run_simulation
from stm_sys_board_hdl import SlotController

dut = SlotController()
assert len(dut.get_csrs()) == 20


def check():
    # Use GPIO mode; no external pad model or SPI timing claim.
    yield dut.spi_master.offline.storage.eq(1)
    yield dut.output.storage.eq(0xA55A)
    yield dut.oe.storage.eq(0xFFFF)
    yield
    yield
    for i, triple in enumerate(dut.slot):
        assert (yield triple.o) == ((0xA55A >> i) & 1)
        assert (yield triple.oe) == 1
    yield dut.oe.storage.eq(0)
    for i, triple in enumerate(dut.slot):
        yield triple.i.eq((0x5AA5 >> i) & 1)
    yield
    yield
    assert (yield dut.input.status) == 0x5AA5
    yield dut.interrupt_mask.storage.eq(1)
    yield dut.slot[0].i.eq(0)
    for _ in range(5):
        yield
    assert (yield dut.interrupt.status) & 1
    yield dut.interrupt_clear.storage.eq(1)
    for _ in range(3):
        yield
    assert not ((yield dut.interrupt.status) & 1)


run_simulation(dut, check(), clocks={"sys": 10})
print("PASS: unchanged upstream slot CSR count, GPIO output/OE/input, masked edge IRQ and clear")
