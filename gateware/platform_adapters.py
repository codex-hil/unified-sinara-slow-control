"""Only physical pad adaptation differs; queued fabric has no platform code."""
from migen import Module, Instance, Signal, If, Mux
from migen.fhdl.specials import Tristate

class SingleEndedPads(Module):
    def __init__(self, fabric, pads):
        if len(pads)!=8 or any(len(p)!=16 for p in pads):raise ValueError('eight16-line slots required')
        for i,p in enumerate(pads):
            self.specials += Tristate(p,fabric.outputs[i],fabric.oes[i],fabric.inputs[i])

class KasliDifferentialPads(Module):
    def __init__(self,fabric,positive,negative,output_masks,input_masks):
        if not all(len(v)==8 for v in [positive,negative,output_masks,input_masks]):raise ValueError('eight slots required')
        for slot in range(8):
            if len(positive[slot])!=16 or len(negative[slot])!=16:raise ValueError('16pairs per slot required')
            if output_masks[slot]&input_masks[slot]:raise ValueError('fixed LVDS direction profile must be unambiguous')
            for line in range(16):
                if (output_masks[slot]>>line)&1:
                    self.specials += Instance('OBUFTDS',i_I=fabric.outputs[slot][line],
                        i_T=~fabric.oes[slot][line],o_O=positive[slot][line],o_OB=negative[slot][line])
                elif (input_masks[slot]>>line)&1:
                    self.specials += Instance('IBUFDS',i_I=positive[slot][line],i_IB=negative[slot][line],
                        o_O=fabric.inputs[slot][line])
                else:self.comb += fabric.inputs[slot][line].eq(0)

class STMTransceiverPads(Module):
    def __init__(self,fabric,pad_slots,direction_pads,inactive=None):
        # Fixed/emulated LVDS and bidirectional MLVDS are explicit per-line kinds.
        self.submodules.io=MixedPads(fabric,pad_slots,inactive)
        self.comb += [direction_pads.clk.eq(fabric.directions.sck),
                      direction_pads.mosi.eq(fabric.directions.mosi),
                      direction_pads.cs.eq(fabric.directions.latch)]


def attach_wishbone(soc,fabric,origin=0x81000000):
    from litex.soc.integration.soc import SoCRegion
    soc.add_module(name='sinara_fabric',module=fabric)
    soc.bus.add_slave(name='sinara_fabric',slave=fabric.bus,
                      region=SoCRegion(origin=origin,size=0x10000,cached=False))

class MixedPads(Module):
    """Per-line SE, fixed LVDS and emulated-LVDS adaptation from a board map.

    Each slot has16 entries: {'p':Signal,'n':optionalSignal,'kind':...}.
    Upper lines need not be differential; no connector numbering is inferred.
    """
    def __init__(self,fabric,slots,inactive=None):
        if len(slots)!=8 or any(len(s)!=16 for s in slots):raise ValueError('eight16-line maps required')
        inactive=[0]*8 if inactive is None else inactive
        for i,slot in enumerate(slots):
            for bit,pad in enumerate(slot):
                kind=pad['kind'];p=pad['p'];n=pad.get('n')
                if kind=='se':
                    self.specials += Tristate(p,fabric.outputs[i][bit],fabric.oes[i][bit],fabric.inputs[i][bit])
                elif kind=='fixed_output':
                    # ECP5 emulated LVDS cannot change physical direction.
                    self.comb += [p.eq(Mux(fabric.oes[i][bit],fabric.outputs[i][bit],(inactive[i]>>bit)&1)),fabric.inputs[i][bit].eq(0)]
                elif kind=='fixed_input':self.comb += fabric.inputs[i][bit].eq(p)
                elif kind=='lvds_output':
                    self.specials += Instance('OBUFTDS',i_I=fabric.outputs[i][bit],i_T=~fabric.oes[i][bit],o_O=p,o_OB=n)
                    self.comb += fabric.inputs[i][bit].eq(0)
                elif kind=='lvds_input':
                    self.specials += Instance('IBUFDS',i_I=p,i_IB=n,o_O=fabric.inputs[i][bit])
                else:raise ValueError('unknown pad kind')
