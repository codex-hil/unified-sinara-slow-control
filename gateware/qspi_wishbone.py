"""Conservative oversampled QSPI x4 to classic 32-bit Wishbone.

sys_clk >= 16*SCK; SDR mode0. Header: opcode8 + byte address24, MS nibble
first. 0x02 increments write address, 0x32 fixed-address writes, 0x0b single
read with8 dummy SCK. Write bursts are not acknowledged on the QSPI wire:
bridge sticky errors must be read and handled, never silently retried.
"""
from migen import Module, Signal, If, Cat, Mux, Constant
from migen.genlib.cdc import MultiReg
from litex.soc.interconnect import wishbone

class QSPIWishbone(Module):
    def __init__(self, timeout_cycles=256):
        if timeout_cycles<8:raise ValueError('timeout too short')
        self.sck=Signal();self.cs_n=Signal(reset=1);self.dq_i=Signal(4)
        self.dq_o=Signal(4);self.dq_oe=Signal(4)
        self.bus=bus=wishbone.Interface(data_width=32,adr_width=22)
        self.error=Signal(4);self.clear_error=Signal();self.transactions=Signal(32)
        sck=Signal();cs=Signal(reset=1);data=Signal(4);old_sck=Signal();old_cs=Signal(reset=1)
        self.specials += [MultiReg(self.sck,sck),MultiReg(self.cs_n,cs,reset=1),MultiReg(self.dq_i,data)]
        self.sync += [old_sck.eq(sck),old_cs.eq(cs)]
        rise=~old_sck & sck;fall=old_sck & ~sck
        state=Signal(3);nibbles=Signal(4);shift=Signal(32);opcode=Signal(8)
        address=Signal(24);response=Signal(32);response_valid=Signal()
        pending=Signal();reading=Signal();timer=Signal(max=timeout_cycles)
        self.comb += [bus.cyc.eq(pending),bus.stb.eq(pending),bus.sel.eq(15),
                      bus.we.eq(~reading),self.dq_oe.eq(Mux(~self.cs_n & (state==3),15,0))]
        self.sync += [
            If(self.clear_error,self.error.eq(0)),
            If(pending,
                If(bus.ack | bus.err,
                    pending.eq(0),response.eq(Mux(bus.err,0xffffffff,bus.dat_r)),response_valid.eq(1),
                    If(bus.err,self.error.eq(2),If(~reading,state.eq(4))))
                .Elif(timer==timeout_cycles-1,pending.eq(0),response.eq(0xffffffff),response_valid.eq(1),self.error.eq(3),If(~reading,state.eq(4)))
                .Else(timer.eq(timer+1))),
            If(cs,
                state.eq(0),nibbles.eq(0),self.dq_o.eq(0),
                # A completed write may still be finishing on Wishbone.
            ).Elif(old_cs,
                state.eq(0),nibbles.eq(0),shift.eq(0),response_valid.eq(0),
                self.transactions.eq(self.transactions+1))
            .Elif(rise,
                If(state==0,
                    shift.eq(Cat(data,shift[:28])),nibbles.eq(nibbles+1),
                    If(nibbles==7,
                        opcode.eq(shift[20:28]),address.eq(Cat(data,shift[:20])),nibbles.eq(0),
                        If((Cat(data,shift[:20]) & 3)!=0,state.eq(4),self.error.eq(1))
                        .Elif((shift[20:28]==2)|(shift[20:28]==0x32),state.eq(1))
                        .Elif(shift[20:28]==0x0b,
                            If(pending,state.eq(4),self.error.eq(4)).Else(
                                bus.adr.eq(Cat(data,shift[:20])>>2),reading.eq(1),pending.eq(1),timer.eq(0),
                                response_valid.eq(0),state.eq(2)))
                        .Else(state.eq(4),self.error.eq(1))))
                .Elif(state==1,
                    shift.eq(Cat(data,shift[:28])),nibbles.eq(nibbles+1),
                    If(nibbles==7,nibbles.eq(0),
                        If(pending,self.error.eq(4),state.eq(4)).Else(
                            bus.adr.eq(address>>2),bus.dat_w.eq(Cat(data,shift[:28])),
                            reading.eq(0),pending.eq(1),timer.eq(0),
                            If(opcode==2,address.eq(address+4)))))
                .Elif(state==2,
                    nibbles.eq(nibbles+1),
                    If(nibbles==7,
                        nibbles.eq(0),state.eq(3),
                        If(response_valid,shift.eq(response)).Else(shift.eq(0xffffffff),self.error.eq(5))))
                .Elif(state==3,If(nibbles==8,state.eq(4))))
            .Elif(fall & (state==3),
                self.dq_o.eq(shift[28:32]),shift.eq(Cat(Constant(0,4),shift[:28])),
                nibbles.eq(nibbles+1))
        ]
