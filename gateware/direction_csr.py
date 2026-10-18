"""MiSoC CSR wrapper, new ABI; never append silently to upstream CSR map."""
from migen import Module, Signal, If
from misoc.interconnect.csr import AutoCSR, CSRStorage, CSRStatus, CSR
from direction import DirectionController


class DirectionCSR(Module, AutoCSR):
    def __init__(self, width=48, serial=True, half_period=50, settle_cycles=4):
        self.requested = CSRStorage(width, name="direction_requested")
        self.apply = CSR(1, name="direction_apply")
        self.active = CSRStatus(width, name="direction_active")
        self.status = CSRStatus(5, name="direction_status")
        self.status_bits = Signal(4)
        self.clear_rejected = CSR(1, name="direction_clear_rejected")
        self.submodules.core = core = DirectionController(
            width, serial=serial, half_period=half_period, settle_cycles=settle_cycles)
        rejected = Signal()
        # An apply pulse when busy/not quiescent is rejected, never queued.
        self.comb += [core.requested.eq(self.requested.storage),
                      core.apply.eq(self.apply.re & self.apply.r[0]),
                      self.active.status.eq(core.active),
                      self.status.status[:4].eq(self.status_bits),
                      self.status_bits[0].eq(core.busy),
                      self.status_bits[1].eq(core.valid),
                      self.status_bits[2].eq(core.ready),
                      self.status_bits[3].eq(rejected)]
        self.sync += If(self.clear_rejected.re & self.clear_rejected.r[0], rejected.eq(0))
        self.sync += If(core.apply & ~core.ready, rejected.eq(1))
        # core.quiescent must be connected to the controller's arbitration logic.
