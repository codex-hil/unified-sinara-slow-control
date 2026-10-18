"""Direction transaction core; synchronous request must be held until ready.

The wrapper owns port quiescence, GPIO output values and physical pad mapping.
A serial chain is initialized to all-input after reset. No external readback.
"""
from migen import Module, Signal, FSM, NextState, NextValue, Cat, If, Constant


class DirectionController(Module):
    def __init__(self, width, serial=True, half_period=50, settle_cycles=4):
        if width < 1 or half_period < 1 or settle_cycles < 1:
            raise ValueError("positive width and timing parameters required")
        self.requested = Signal(width)
        self.apply = Signal()
        self.quiescent = Signal(reset=1)
        self.ready = Signal()
        self.busy = Signal()
        self.done = Signal()
        self.active = Signal(width)
        self.valid = Signal()
        self.oe = Signal(width)
        self.sck = Signal()
        self.mosi = Signal()
        self.latch = Signal()
        pending = Signal(width)
        shift = Signal(width)
        left = Signal(max=width + 1)
        timer = Signal(max=max(half_period, settle_cycles) + 1)
        self.submodules.fsm = fsm = FSM(reset_state="BOOT")
        self.comb += [self.ready.eq(fsm.ongoing("IDLE") & self.quiescent),
                      self.busy.eq(~fsm.ongoing("IDLE")),
                      self.mosi.eq(shift[width - 1])]
        launch = "LOW" if serial else "SETTLE"
        fsm.act("BOOT", NextValue(pending, 0), NextValue(shift, 0),
                NextValue(left, width), NextValue(timer, half_period - 1 if serial else settle_cycles - 1),
                NextState(launch))
        fsm.act("IDLE", NextValue(self.done, 0),
                # Caller must not start another SPI transfer while busy.
                If(self.apply & self.quiescent,
                    NextValue(self.oe, 0),
                    NextValue(pending, self.requested), NextValue(shift, self.requested),
                    NextValue(left, width),
                    NextValue(timer, half_period - 1 if serial else settle_cycles - 1),
                    NextState(launch)))
        fsm.act("LOW", If(timer == 0, NextValue(timer, half_period - 1), NextValue(self.sck, 1), NextState("HIGH"))
                .Else(NextValue(timer, timer - 1)))
        fsm.act("HIGH",
                If(timer == 0, NextValue(self.sck, 0),
                   If(left == 1, NextValue(timer, half_period - 1), NextState("PRE_LATCH"))
                   .Else(NextValue(left, left - 1), NextValue(shift, Cat(Constant(0, 1), shift[:-1])),
                         NextValue(timer, half_period - 1), NextState("LOW")))
                .Else(NextValue(timer, timer - 1)))
        fsm.act("PRE_LATCH", If(timer == 0, NextValue(timer, half_period - 1), NextValue(self.latch, 1), NextState("LATCH"))
                .Else(NextValue(timer, timer - 1)))
        fsm.act("LATCH",
                If(timer == 0, NextValue(self.latch, 0), NextValue(timer, settle_cycles - 1), NextState("SETTLE"))
                .Else(NextValue(timer, timer - 1)))
        fsm.act("SETTLE", If(timer == 0, NextValue(self.active, pending), NextValue(self.oe, pending),
                NextValue(self.valid, 1), NextValue(self.done, 1), NextState("IDLE"))
                .Else(NextValue(timer, timer - 1)))
