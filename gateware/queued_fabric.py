"""SCF5 Wishbone fabric shared by ECP5 and Kasli (no CPU/pad primitives).

32-bit word-addressed classic Wishbone. Slot byte base0x100, stride0x100.
An unaccepted/full/invalid write returns ERR with no FIFO side effect.
"""
from functools import reduce
from operator import and_
from migen import Module, Signal, If, Cat, Mux, Constant
from litex.soc.interconnect import wishbone
from queued_spi import QueuedSPI
from fabric_pinmux import FabricPinMux, validate_routes
from control_signals import ControlSignals
from direction import DirectionController

MAGIC=0x53434635
ABI=5
SLOT_BASE=0x100
SLOT_STRIDE=0x100
DEFAULT_ROUTE=dict(clk=0,mosi=1,miso=2,selects=[3,4,5,6],mode='direct')

class QueuedFabric(Module):
    def __init__(self, routes=None, serial_directions=False, depth=64,
                 output_capable=None, input_capable=None, direction_half_period=50, build_id=0, sys_clk_hz=100000000):
        routes=[dict(DEFAULT_ROUTE) for _ in range(8)] if routes is None else routes
        if len(routes)!=8:raise ValueError('eight slot routes required')
        output_capable=[65535]*8 if output_capable is None else list(output_capable)
        input_capable=[65535]*8 if input_capable is None else input_capable
        if len(output_capable)!=8 or len(input_capable)!=8:raise ValueError('eight capability masks required')
        self.bus=bus=wishbone.Interface(data_width=32,adr_width=22)
        self.inputs=[Signal(16,name=f'slot{i+1}_input') for i in range(8)]
        self.outputs=[Signal(16,name=f'slot{i+1}_output') for i in range(8)]
        self.oes=[Signal(16,name=f'slot{i+1}_oe') for i in range(8)]
        self.transport_error=Signal(4);self.transport_clear=Signal()
        self.trigger_external=Signal();self.trigger_stm=Signal();self.ready=Signal();self.interlock_ok=Signal()
        self.submodules.safety=safety=ControlSignals(8)
        self.submodules.directions=direction=DirectionController(48,serial=serial_directions,
            half_period=direction_half_period,settle_cycles=4)
        self.spi=[];self.mux=[];self.controls=[]
        self.comb += [safety.trigger_raw.eq(self.trigger_external),safety.stm_trigger_raw.eq(self.trigger_stm),
                      self.ready.eq(safety.ready),self.interlock_ok.eq(safety.interlock_ok)]
        self.global_enable=Signal(8)
        router_slot=Signal(3);router_left=Signal(16)
        fire=Signal();error=Signal();read_data=Signal(32)
        self.comb += [error.eq(0),read_data.eq(0),fire.eq(bus.cyc & bus.stb & ~bus.ack),
                      self.transport_clear.eq(0),safety.clear.eq(0),safety.software_trigger.eq(0),direction.apply.eq(0)]
        self.sync += If(~bus.cyc | ~bus.stb,bus.ack.eq(0),bus.err.eq(0)).Elif(
            fire,bus.ack.eq(1),bus.err.eq(error),bus.dat_r.eq(read_data))
        all_idle=[];configurable=[];direction_masks=[]
        for i,route in enumerate(routes):
            mode,selects=validate_routes(route)
            for role in ('interlock','ready_input'):
                if route.get(role) is not None:output_capable[i]&=~(1<<route[role])
            q=QueuedSPI(depth=depth,mode=mode,selects=len(selects),session_timeout=sys_clk_hz,pulse_available=route.get('pulse') is not None)
            self.submodules += q
            mux=FabricPinMux(q,route)
            self.submodules += mux
            outputs=[route.get('clk',0),route.get('mosi',1),*selects]
            if mode=='parallel':outputs.append(route.get('enable',7))
            outputs += [route.get(k) for k in ('pulse','trigger','ready')]
            if any(p is not None and not ((output_capable[i]>>p)&1) for p in outputs):
                raise ValueError('route needs an output-capable pad')
            miso=route.get('miso',2)
            if miso is not None and not ((input_capable[i]>>miso)&1):raise ValueError('MISO needs an input-capable pad')
            self.spi.append(q);self.mux.append(mux)
            enable=self.global_enable[i]
            cfg=Signal(10,reset=4);out=Signal(16);oe=Signal(16)
            safe_out=Signal(16);safe_oe=Signal(16)
            self.controls.append(dict(clock=cfg,output=out,oe=oe,safe_output=safe_out,safe_oe=safe_oe))
            all_idle.append(~q.busy);configurable.append(~enable & ~q.busy & (q.tx_level==0))
            extra=sum(1<<route[k] for k in ('pulse','trigger','ready') if route.get(k) is not None)
            requested=Signal(16)
            self.comb += [requested.eq(oe | extra),mux.input.eq(self.inputs[i]),mux.gpio_output.eq(out),
                mux.gpio_oe.eq(oe),mux.safe_output.eq(safe_out),mux.safe_oe.eq(safe_oe),
                mux.spi_enable.eq(enable),mux.permit.eq(safety.permit),
                mux.common_trigger.eq(safety.trigger & safety.trigger_mask[i]),mux.common_ready.eq(safety.ready),
                self.outputs[i].eq(mux.output),q.divider.eq(cfg[:8]),q.cpol.eq(cfg[8]),q.cpha.eq(cfg[9]),
                q.enable.eq(enable),q.permit.eq(safety.permit & direction.valid & ~direction.busy),
                q.trigger.eq(safety.trigger & safety.trigger_mask[i]),safety.slot_waiting[i].eq(q.waiting),
                q.tx_write.eq(0),q.rx_read.eq(0),q.flush.eq(0)]
            if i<6:
                direction_masks.append(requested[8:])
                self.comb += self.oes[i].eq(Mux(direction.busy,0,Cat(mux.oe[:8],mux.oe[8:] & direction.oe[8*i:8*i+8])) & output_capable[i])
            else:self.comb += self.oes[i].eq(Mux(direction.busy,0,mux.oe) & output_capable[i])
            iline=route.get('interlock')
            if iline is not None:
                if type(iline) is not int or not 0<=iline<16:raise ValueError('invalid interlock input')
                if not (input_capable[i]>>iline)&1:raise ValueError('interlock needs input-capable pin')
                claimed=extra | sum(1<<p for p in [route.get('clk',0),route.get('mosi',1),route.get('miso',2),*selects] if p is not None)
                if mode=='parallel':claimed|=1<<route.get('enable',7)
                if claimed&(1<<iline):raise ValueError('interlock overlaps output function')
                self.comb += safety.raw_good[i].eq(self.inputs[i][iline] & ~self.oes[i][iline])
            else:self.comb += safety.raw_good[i].eq(0)
            ready_input=route.get('ready_input')
            if ready_input is not None:
                if not (input_capable[i]>>ready_input)&1:raise ValueError('ready input must be input capable')
                self.comb += safety.raw_ready[i].eq(self.inputs[i][ready_input] & ~self.oes[i][ready_input])
            else:self.comb += safety.raw_ready[i].eq(0)
            base=(SLOT_BASE+i*SLOT_STRIDE)//4
            # Every register access is acknowledged once until STB is released.
            writes={0:If(~q.busy, self.global_enable[i].eq(bus.dat_w[0])),
                    5:cfg.eq(bus.dat_w[:10]),6:out.eq(bus.dat_w[:16]),7:oe.eq(bus.dat_w[:16]),
                    8:safe_out.eq(bus.dat_w[:16]),9:safe_oe.eq(bus.dat_w[:16])}
            for offset,action in writes.items():
                accepted=fire & bus.we & (bus.adr==base+offset) & (bus.sel==15) & ~error
                self.sync += If(accepted,action)
            self.comb += If((bus.adr>=base)&(bus.adr<base+64),
                If(bus.we,
                    If(bus.sel!=15,error.eq(1)).Elif(bus.adr==base+2,
                        error.eq(~q.tx_ready),q.tx_data.eq(bus.dat_w),q.tx_write.eq(fire & q.tx_ready))
                    .Elif(bus.adr==base+11,q.flush.eq(fire & bus.dat_w[0]))
                    .Elif(bus.adr==base,error.eq(q.busy))
                    .Elif((bus.adr==base+5)|(bus.adr==base+7)|(bus.adr==base+8)|(bus.adr==base+9),
                        error.eq(~configurable[-1] |
                            (((bus.adr==base+7)|(bus.adr==base+9)) & ((bus.dat_w & ~output_capable[i])!=0))))
                    .Elif(bus.adr!=base+6,error.eq(1))
                ).Else(
                    If(bus.adr==base,read_data.eq(enable))
                    .Elif(bus.adr==base+1,read_data.eq(Cat(q.tx_ready,q.rx_ready,q.busy,Constant(0,1),q.fault,q.waiting,q.session)))
                    .Elif(bus.adr==base+3,read_data.eq(q.rx_data),q.rx_read.eq(fire & q.rx_ready),error.eq(~q.rx_ready))
                    .Elif(bus.adr==base+4,read_data.eq(q.tx_level | (q.rx_level<<16)))
                    .Elif(bus.adr==base+5,read_data.eq(cfg)).Elif(bus.adr==base+6,read_data.eq(out))
                    .Elif(bus.adr==base+7,read_data.eq(oe)).Elif(bus.adr==base+8,read_data.eq(safe_out))
                    .Elif(bus.adr==base+9,read_data.eq(safe_oe))
                    .Elif(bus.adr==base+10,read_data.eq(q.completed | (q.last_tag<<16)))
                    .Elif(bus.adr==base+12,read_data.eq(0xffffffff if iline is None else iline))
                    .Elif(bus.adr==base+13,read_data.eq(output_capable[i] | (input_capable[i]<<16)))
                    .Elif(bus.adr==base+14,read_data.eq(self.inputs[i]))
                    .Elif(bus.adr==base+15,read_data.eq(depth))
                    .Elif(bus.adr==base+16,read_data.eq(self.outputs[i]))
                    .Elif(bus.adr==base+17,read_data.eq(self.oes[i])).Else(error.eq(1))))
        self.comb += [direction.requested.eq(Cat(*direction_masks)),direction.quiescent.eq(reduce(and_,all_idle))]
        # One fixed-address QSPI write burst can target all slot queues:
        # envelope=(word_count<<16)|slot_index, followed by that many queue words.
        for i,q in enumerate(self.spi):
            self.comb += If((bus.adr==16)&bus.we&(bus.sel==15)&(router_left!=0)&(router_slot==i),
                error.eq(~q.tx_ready),q.tx_data.eq(bus.dat_w),q.tx_write.eq(fire & q.tx_ready))
        self.sync += If(fire & bus.we & (bus.adr==8) & (bus.sel==15) & ~error & bus.dat_w[3],router_left.eq(0))
        self.sync += If(fire & bus.we & (bus.adr==16) & (bus.sel==15) & ~error,
            If(router_left==0,router_slot.eq(bus.dat_w[:3]),router_left.eq(bus.dat_w[16:32]))
            .Else(router_left.eq(router_left-1)))
        all_config=reduce(and_,configurable)
        writable={4:safety.interlock_mask,5:safety.active_low,6:safety.trigger_mask,7:safety.width,9:safety.trigger_source_stm,17:safety.ready_mask,18:safety.ready_active_low}
        for addr,signal in writable.items():
            self.sync += If(fire & bus.we & (bus.adr==addr) & ~error,signal.eq(bus.dat_w))
        self.comb += If(bus.adr<64,
            If(bus.we,
                If(bus.sel!=15,error.eq(1)).Elif(bus.adr==8,
                    safety.clear.eq(fire & ~error & bus.dat_w[0]),safety.software_trigger.eq(fire & ~error & bus.dat_w[1]),
                    direction.apply.eq(fire & bus.dat_w[2] & direction.ready),
                    self.transport_clear.eq(fire & ~error & bus.dat_w[4]),
                    error.eq(bus.dat_w[2] & ~direction.ready))
                .Elif(bus.adr==16,
                    If(router_left==0,error.eq((bus.dat_w[3:16]!=0)|(bus.dat_w[16:32]==0)|(bus.dat_w[16:32]>depth))))
                .Elif((bus.adr==4)|(bus.adr==5)|(bus.adr==6)|(bus.adr==7)|(bus.adr==9)|(bus.adr==17)|(bus.adr==18),error.eq(~all_config))
                .Else(error.eq(1)))
            .Else(
                If(bus.adr==0,read_data.eq(MAGIC)).Elif(bus.adr==1,read_data.eq(ABI))
                .Elif(bus.adr==2,read_data.eq(Cat(safety.permit,safety.ready,safety.tripped,safety.trigger_rejected,direction.busy,direction.valid)))
                .Elif(bus.adr==3,read_data.eq(self.global_enable))
                .Elif(bus.adr==4,read_data.eq(safety.interlock_mask)).Elif(bus.adr==5,read_data.eq(safety.active_low))
                .Elif(bus.adr==6,read_data.eq(safety.trigger_mask)).Elif(bus.adr==7,read_data.eq(safety.width))
                .Elif(bus.adr==17,read_data.eq(safety.ready_mask)).Elif(bus.adr==18,read_data.eq(safety.ready_active_low))
                .Elif(bus.adr==16,read_data.eq((router_left<<16)|router_slot))
                .Elif(bus.adr==9,read_data.eq(safety.trigger_source_stm)).Elif(bus.adr==10,read_data.eq(safety.trigger_count))
                .Elif(bus.adr==11,read_data.eq(self.transport_error))
                .Elif(bus.adr==14,read_data.eq(build_id & 0xffffffff)).Elif(bus.adr==15,read_data.eq(build_id>>32))
                .Elif(bus.adr==12,read_data.eq(direction.active[:32])).Elif(bus.adr==13,read_data.eq(direction.active[32:]))
                .Else(error.eq(1))))
        self.comb += If(bus.adr>=((SLOT_BASE+8*SLOT_STRIDE)//4),error.eq(1))
