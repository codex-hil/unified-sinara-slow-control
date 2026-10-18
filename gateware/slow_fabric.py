"""Shared MiSoC slot fabric, word-addressed 16-bit ABI v4.

Legacy slot bank stays at 0; direction bank starts at 0x800. The six
upper-byte groups share one direction transaction. No physical pads here.
"""
from functools import reduce
from operator import and_
from migen import Module, Signal, If
from misoc.interconnect import csr_bus
from direction_csr import DirectionCSR
from csr_bank import RegisteredSelectCSRBank

DIRECTION_BASE = 0x800
ABI_VERSION = 4


class SlowControlFabric(Module):
    def __init__(self, slots, legacy_csrs, bus, serial=True,
                 half_period=50, settle_cycles=4):
        if len(slots) != 8 or len(bus.dat_w) != 16:
            raise ValueError("ABI v4 requires eight slots and a 16-bit CSR bus")
        self.submodules.direction = direction = DirectionCSR(
            48, serial=serial, half_period=half_period, settle_cycles=settle_cycles)
        self.write_blocked = Signal()
        self.status = Signal(5)
        core = direction.core
        self.legacy_bus = legacy = csr_bus.Interface.like(bus)
        self.direction_bus = directions = csr_bus.Interface.like(bus)
        self.submodules.legacy_bank = RegisteredSelectCSRBank(
            legacy_csrs, address=0, bus=legacy, align_bits=0)
        # Bit4 of direction_status reports blocked legacy writes, cleared with
        # the same clear_rejected strobe. Readback never clears status.
        self.comb += [self.status.eq(direction.status.status),
                      direction.status.status[4].eq(self.write_blocked)]
        self.submodules.direction_bank = csr_bus.CSRBank(
            direction.get_csrs(), address=1, bus=directions, align_bits=0)
        blocked = core.busy | core.apply
        self.comb += [legacy.adr.eq(bus.adr), legacy.dat_w.eq(bus.dat_w),
                      legacy.we.eq(bus.we & ~blocked),
                      directions.adr.eq(bus.adr), directions.dat_w.eq(bus.dat_w),
                      directions.we.eq(bus.we),
                      bus.dat_r.eq(legacy.dat_r | directions.dat_r),
                      core.quiescent.eq(reduce(and_, [
                          s.spi_master.idle.status & ~s.spi_master.data.re
                          for s in slots]))]
        self.sync += If(direction.clear_rejected.re & direction.clear_rejected.r[0],
                        self.write_blocked.eq(0))
        self.sync += If(bus.we & (bus.adr[11:] == 0) & blocked,
                        self.write_blocked.eq(1))
        for i, slot in enumerate(slots):
            self.comb += [slot.upper_oe.eq(core.oe[8*i:8*i+8] if i < 6 else slot.oe.storage[8:]),
                          slot.direction_busy.eq(core.busy)]

    def register_map(self):
        return {"abi_version": ABI_VERSION, "address_units": "16-bit words",
                "legacy": {c.name: i for i, c in enumerate(self.legacy_bank.simple_csrs)},
                "direction": {c.name: DIRECTION_BASE+i for i, c in enumerate(self.direction_bank.simple_csrs)}}
