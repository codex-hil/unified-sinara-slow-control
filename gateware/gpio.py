"""Controller-independent GPIO CSRs for a reviewed board-specific SoC.

Not a complete Kasli target. Requires differential I/O buffers for EEM,
proper clock/power sequencing and generated CSR addresses. No RTIO.
"""
from migen import Module, Signal
from litex.soc.interconnect.csr import AutoCSR, CSRStorage, CSRStatus


class SlowGPIO(Module, AutoCSR):
    def __init__(self, width=16):
        self.output = CSRStorage(width, name='output')
        self.input = CSRStatus(width, name='input')
        self.oe = CSRStorage(width, name='oe')
        self.pins_in = Signal(width)
        self.pins_out = Signal(width)
        self.pins_oe = Signal(width)
        self.comb += [self.input.status.eq(self.pins_in),
                      self.pins_out.eq(self.output.storage),
                      self.pins_oe.eq(self.oe.storage)]


class SlowIdentity(Module, AutoCSR):
    def __init__(self):
        self.abi = CSRStatus(32, name='abi')
        self.comb += self.abi.status.eq(0x53434731)
