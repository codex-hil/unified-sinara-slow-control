"""Shared synchronized interlock AND, ready barrier and trigger fanout."""
from migen import Module, Signal, If, Cat
from migen.genlib.cdc import MultiReg

class ControlSignals(Module):
    def __init__(self, slots=8):
        self.raw_good=Signal(slots);self.interlock_mask=Signal(slots)
        self.active_low=Signal(slots);self.clear=Signal()
        self.raw_ready=Signal(slots);self.ready_mask=Signal(slots);self.ready_active_low=Signal(slots)
        self.interlock_ok=Signal();self.tripped=Signal();self.permit=Signal()
        self.slot_waiting=Signal(slots);self.trigger_mask=Signal(slots)
        self.trigger_raw=Signal();self.trigger_source_stm=Signal()
        self.stm_trigger_raw=Signal();self.software_trigger=Signal()
        self.width=Signal(16,reset=1);self.ready=Signal();self.trigger=Signal()
        self.trigger_rejected=Signal();self.trigger_count=Signal(32)
        good=Signal(slots);card_ready=Signal(slots);external=Signal();stm=Signal();previous=Signal();valid=Signal(3)
        self.specials += [MultiReg(self.raw_good,good),MultiReg(self.raw_ready,card_ready),MultiReg(self.trigger_raw,external),MultiReg(self.stm_trigger_raw,stm)]
        source=Signal();request=Signal();timer=Signal(16)
        self.comb += [source.eq((external & ~self.trigger_source_stm)|(stm & self.trigger_source_stm)),
            request.eq((source & ~previous)|self.software_trigger),
            self.interlock_ok.eq((self.interlock_mask==0) | (valid[2] & ((((good ^ self.active_low) | ~self.interlock_mask) & ((1<<slots)-1))==((1<<slots)-1)))),
            self.permit.eq(self.interlock_ok & ~self.tripped),
            self.ready.eq((self.trigger_mask!=0) & ((self.slot_waiting & self.trigger_mask)==self.trigger_mask) & self.permit & (timer==0) & ((((card_ready ^ self.ready_active_low) | ~self.ready_mask) & ((1<<slots)-1))==((1<<slots)-1))),
            self.trigger.eq((timer!=0) & self.permit)]
        self.sync += [valid.eq(Cat(1,valid[:2])),previous.eq(source),
            If(~self.interlock_ok,self.tripped.eq(1)).Elif(self.clear,self.tripped.eq(0)),
            If(self.clear,self.trigger_rejected.eq(0)),
            If(~self.permit,timer.eq(0)).Elif(request,
                If(self.ready & (self.width!=0),timer.eq(self.width),self.trigger_count.eq(self.trigger_count+1))
                .Else(self.trigger_rejected.eq(1)))
            .Elif(timer!=0,timer.eq(timer-1))]
