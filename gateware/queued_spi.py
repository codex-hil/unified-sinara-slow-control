"""Portable queued SPI engine; MiSoC SPIMachine, no RTIO or pad primitives.

32-bit command: opcode[31:28], selector[27:24], tag[23:16], length[15:0].
WRITE/XFER payload is little-endian packed bytes following the header.
A complete command and RX capacity are required before CS assertion.
"""
from migen import Module, Signal, If, FSM, NextState, NextValue, Mux, Cat, ResetInserter
from migen.genlib.fifo import SyncFIFO
from migen.fhdl.specials import Memory

def compatible_fifo(width, depth):
    fifo=SyncFIFO(width, depth)
    # Pinned Migen has read_capable=False in SyncFIFO, but its simulator
    # MemoryToArray still dereferences dat_r. An unused read signal keeps
    # that instance simulatable; synthesis removes the unused read output.
    for memory in fifo._fragment.specials:
        if isinstance(memory,Memory):
            for port in memory.ports:
                if port.dat_r is None:port.dat_r=Signal(width)
    return fifo
from misoc.cores.spi2 import SPIMachine

WRITE, READ, XFER, DELAY, WAIT_TRIGGER, PULSE, CS_ASSERT, CS_RELEASE = range(1, 9)


def command(opcode, selector=0, length=0, tag=0):
    if opcode not in range(1,9) or not 0 <= selector < 16 or not 0 <= tag < 256 or not 0 <= length < 65536:
        raise ValueError('invalid command fields')
    return opcode<<28 | selector<<24 | tag<<16 | length


class QueuedSPI(Module):
    def __init__(self, depth=64, mode='direct', selects=4, address_setup=2, session_timeout=100000000, pulse_available=True):
        if session_timeout<1:raise ValueError('invalid session timeout')
        if depth < 4 or depth > 4096 or mode not in ('direct','parallel','encoded','none'):
            raise ValueError('invalid queue configuration')
        if not 0 <= selects <= 4 or address_setup < 1:
            raise ValueError('invalid selector configuration')
        if mode in ('direct','parallel','encoded') and not selects:
            raise ValueError('address mode needs address lines')
        self.tx_data=Signal(32);self.tx_write=Signal();self.tx_ready=Signal()
        self.rx_data=Signal(32);self.rx_read=Signal();self.rx_ready=Signal()
        self.tx_level=Signal(max=depth+1);self.rx_level=Signal(max=depth+1)
        self.enable=Signal();self.permit=Signal(reset=1);self.flush=Signal()
        self.divider=Signal(8,reset=4);self.cpol=Signal();self.cpha=Signal()
        self.trigger=Signal();self.waiting=Signal();self.pulse=Signal();self.session=Signal()
        self.busy=Signal();self.fault=Signal(4);self.completed=Signal(16)
        self.last_tag=Signal(8);self.selector=Signal(4)
        self.clk=Signal();self.mosi=Signal();self.miso=Signal();self.selected=Signal()
        self.select_out=Signal(4,reset=15);self.enable_n=Signal(reset=1)
        clear=Signal();reset=Signal()
        self.submodules.tx=tx=ResetInserter()(compatible_fifo(32,depth))
        self.submodules.rx=rx=ResetInserter()(compatible_fifo(32,depth))
        self.submodules.spi=spi=ResetInserter()(SPIMachine(data_width=8,div_width=8))
        self.submodules.fsm=fsm=ResetInserter()(FSM(reset_state='HEADER'))
        self.comb += [reset.eq(self.flush | ~self.permit | (self.busy & ~self.enable)),clear.eq(self.flush),
            tx.reset.eq(clear),rx.reset.eq(clear),spi.reset.eq(reset),fsm.reset.eq(reset),
            tx.din.eq(self.tx_data),tx.we.eq(self.tx_write & tx.writable & ~self.flush),
            self.tx_ready.eq(tx.writable & ~self.flush),self.tx_level.eq(tx.level),
            self.rx_data.eq(rx.dout),self.rx_ready.eq(rx.readable),rx.re.eq(self.rx_read & rx.readable),
            self.rx_level.eq(rx.level),self.busy.eq(~fsm.ongoing('HEADER') | self.session)]
        op=Signal(4);length=Signal(16);tag=Signal(8);remaining=Signal(16)
        selector=Signal(4);held_selector=Signal(4);session_timer=Signal(max=session_timeout+1)
        payload_words=Signal(16);word=Signal(32);byte_index=Signal(2)
        timer=Signal(16);mosi=Signal();clk=Signal();cs=Signal();sample=Signal()
        # Snapshot transaction parameters; changing divider cannot corrupt a frame.
        divider=Signal(8);cpol=Signal();cpha=Signal()
        continuing=Signal()
        active=self.enable & self.permit & (self.fault==0)
        self.comb += [continuing.eq(fsm.ongoing("SHIFT") & spi.readable & active & (remaining>1)),
            spi.end.eq(Mux(continuing,remaining==2,remaining==1)),spi.length.eq(7),spi.cg.div.eq(divider),spi.clk_phase.eq(cpha),
            spi.reg.pdo.eq(Mux(op==READ,0,Mux(continuing,Mux(byte_index==3,tx.dout[:8],word[8:16]),word[:8]))),spi.reg.sdi.eq(sample),
            self.mosi.eq(Mux(active,spi.reg.sdo,0)),self.clk.eq(Mux(active,clk,self.cpol)),
            self.selector.eq(Mux(self.session,held_selector,selector)),self.selected.eq((cs | self.session) & active),self.enable_n.eq(~self.selected),
            self.waiting.eq(fsm.ongoing('WAIT') & active)]
        self.sync += [If(spi.reg.sample,sample.eq(self.miso)),
            If(reset | fsm.ongoing("HEADER"),clk.eq(self.cpol),cs.eq(0)).Elif(spi.ce,clk.eq(spi.clk_next ^ cpol),cs.eq(spi.cs_next))]
        if mode=='direct':
            self.comb += self.select_out.eq(Mux(self.selected,~(1<<self.selector),15))
            valid_selector=(tx.dout[24:28] < selects) if selects else 0
        elif mode=='encoded':
            self.comb += self.select_out.eq(Mux(self.selected,self.selector,0))
            valid_selector=(tx.dout[24:28] < (1<<selects)) & (tx.dout[24:28]!=0)
        elif mode=='parallel':
            address_latch=Signal(4)
            self.sync += If(fsm.ongoing('PREPARE') & ((op<=XFER)|(op==CS_ASSERT)),address_latch.eq(selector))
            self.comb += self.select_out.eq(address_latch)
            valid_selector=tx.dout[24:28] < (1<<selects)
        else:
            self.comb += self.select_out.eq(0)
            valid_selector=tx.dout[24:28]==0
        fault_set=Signal(4)
        self.sync += If(self.flush,self.fault.eq(0),self.completed.eq(0),self.last_tag.eq(0)).Else(
            If((~self.permit & (self.enable | self.busy)) | (self.busy & ~self.enable),self.fault.eq(2))
            .Elif(self.session & (session_timer==session_timeout),self.fault.eq(3))
            .Elif(fault_set!=0,self.fault.eq(fault_set)),
            If(fsm.ongoing('DONE'),self.completed.eq(self.completed+1),self.last_tag.eq(tag)))
        self.sync += If(reset | (self.fault!=0),self.session.eq(0),session_timer.eq(0)).Else(
            If(fsm.ongoing('DONE') & (op==CS_ASSERT),self.session.eq(1),held_selector.eq(selector),session_timer.eq(0)),
            If(fsm.ongoing('DONE') & (op==CS_RELEASE),self.session.eq(0)),
            If(self.session,session_timer.eq(session_timer+1)))
        fsm.act('HEADER',
            If(active & tx.readable,
                tx.re.eq(1),NextValue(op,tx.dout[28:32]),NextValue(length,tx.dout[:16]),
                NextValue(tag,tx.dout[16:24]),NextValue(selector,tx.dout[24:28]),
                NextValue(payload_words,(tx.dout[:16]+3)>>2),
                NextValue(divider,self.divider),NextValue(cpol,self.cpol),NextValue(cpha,self.cpha),
                If((tx.dout[28:32]<WRITE) | (tx.dout[28:32]>CS_RELEASE) |
                   ((tx.dout[28:32]<=XFER) & ((tx.dout[:16]==0) | ~valid_selector | (self.divider<2))) |
                   (((tx.dout[28:32]==WRITE) | (tx.dout[28:32]==XFER)) & (tx.dout[:16]>(depth-1)*4)) |
                   (((tx.dout[28:32]==READ) | (tx.dout[28:32]==XFER)) & (tx.dout[:16]>depth)) |
                   (((tx.dout[28:32]>=DELAY)&(tx.dout[28:32]<=PULSE)) & (tx.dout[24:28]!=0)) |
                   ((tx.dout[28:32]==WAIT_TRIGGER) & (tx.dout[:16]!=0)) |
                   (((tx.dout[28:32]==PULSE) | (tx.dout[28:32]==DELAY)) & (tx.dout[:16]==0)) |
                   ((tx.dout[28:32]==PULSE) & int(not pulse_available)) |
                   ((tx.dout[28:32]==CS_ASSERT) & (self.session | ~valid_selector | (tx.dout[:16]!=0))) |
                   ((tx.dout[28:32]==CS_RELEASE) & (~self.session | (tx.dout[:16]!=0))) |
                   (self.session & (tx.dout[28:32]<=XFER) & (tx.dout[24:28]!=held_selector)) |
                   (self.session & (tx.dout[28:32]==WAIT_TRIGGER)),
                    fault_set.eq(1),NextState('ERROR')).Else(NextState('PREPARE'))))
        fsm.act('PREPARE',If(active,
            If(op==CS_ASSERT,NextValue(timer,address_setup-1),NextState('SELECT_WAIT')).Elif(op==CS_RELEASE,NextState('DONE')).Elif(op==WAIT_TRIGGER,NextState('WAIT')).Elif((op==DELAY)|(op==PULSE),
                NextValue(timer,length-1),NextState('TIMER')).Elif(
                ((op==READ) | (tx.level>=payload_words)) &
                ((op==WRITE) | ((depth-rx.level)>=length)),
                NextValue(remaining,length),NextValue(byte_index,0),NextValue(timer,address_setup-1),
                If(op!=READ,tx.re.eq(1),NextValue(word,tx.dout)).Else(NextValue(word,0)),
                NextState('ADDRESS'))))
        fsm.act('SELECT_WAIT',If(timer==0,NextState('DONE')).Else(NextValue(timer,timer-1)))
        fsm.act('ADDRESS',If(timer==0,NextState('LOAD')).Else(NextValue(timer,timer-1)))
        fsm.act('LOAD',If(active,spi.load.eq(1),NextState('SHIFT')))
        fsm.act('SHIFT',If(spi.readable & active,
            If(op!=WRITE,rx.we.eq(1),rx.din.eq(Cat(spi.reg.pdi,tag,remaining==1))),
            If(remaining==1,NextState('FINISH')).Else(
                spi.load.eq(1),NextValue(remaining,remaining-1),NextValue(byte_index,byte_index+1),
                If(op!=READ,
                    If(byte_index==3,tx.re.eq(1),NextValue(word,tx.dout))
                    .Else(NextValue(word,word>>8))),NextState('SHIFT'))))
        fsm.act('FINISH',If(spi.idle & active,NextState('DONE')))
        fsm.act('WAIT',If(self.trigger & active,NextState('DONE')))
        fsm.act('TIMER',self.pulse.eq((op==PULSE) & active),
            If(timer==0,NextState('DONE')).Else(NextValue(timer,timer-1)))
        fsm.act('DONE',NextState('HEADER'))
        fsm.act('ERROR')
