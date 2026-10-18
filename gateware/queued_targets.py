"""Integration helpers: identical fabric, different bus/pad wrappers.

No image loading, flash, JTAG, UART or lab network access.
"""
from migen import Module,ClockDomain,Cat,Mux
from migen.fhdl.specials import Tristate
from queued_fabric import QueuedFabric
from qspi_wishbone import QSPIWishbone
from sinara_slow.fabric import build_id


def make_fabric(profile):
    return QueuedFabric(routes=[s['route'] for s in profile['slots']],
        output_capable=[s['output_capable'] for s in profile['slots']],
        input_capable=[s['input_capable'] for s in profile['slots']],
        sys_clk_hz=profile['sys_clk_hz'],depth=profile['fifo_depth'],serial_directions=profile['target']=='stm_ecp5',build_id=build_id(profile))


class STMQueuedCore(Module):
    """Logical ECP5 top: QSPI + fabric +595 outputs, no guessed board pins."""
    def __init__(self,profile):
        if profile['target']!='stm_ecp5':raise ValueError('STM profile required')
        self.submodules.fabric=self.fabric=make_fabric(profile)
        self.submodules.qspi=self.qspi=QSPIWishbone()
        self.comb += self.qspi.bus.connect(self.fabric.bus)
        self.comb += [self.fabric.transport_error.eq(self.qspi.error),self.qspi.clear_error.eq(self.fabric.transport_clear)]


def attach_kasli(soc,profile,origin=0x81000000):
    if profile['target']!='kasli':raise ValueError('Kasli profile required')
    if int(soc.clk_freq)!=profile['sys_clk_hz']:raise ValueError('SoC/profile clock mismatch')
    from platform_adapters import attach_wishbone
    fabric=make_fabric(profile)
    attach_wishbone(soc,fabric,origin)
    return fabric

class STMQueuedBoard(Module):
    """Complete structural wrapper, supplied with reviewed board pad resources.

    Pins/IO standards are supplied by the existing board configuration; no
    package pins, DIO direction controls or STM auxiliary pins are guessed.
    """
    def __init__(self,profile,clock,qspi_pads,pad_slots,direction_pads,
                 external_trigger=None,stm_trigger=None,ready_output=None,inactive=None):
        from platform_adapters import STMTransceiverPads
        self.clock_domains.cd_sys=ClockDomain('sys')
        self.comb += [self.cd_sys.clk.eq(clock),self.cd_sys.rst.eq(0)]
        self.submodules.core=core=STMQueuedCore(profile)
        self.submodules.pads=STMTransceiverPads(core.fabric,pad_slots,direction_pads,inactive)
        self.specials += Tristate(qspi_pads.data,core.qspi.dq_o,core.qspi.dq_oe,core.qspi.dq_i)
        self.comb += [core.qspi.sck.eq(qspi_pads.clk),core.qspi.cs_n.eq(qspi_pads.cs_n)]
        if external_trigger is not None:self.comb += core.fabric.trigger_external.eq(external_trigger)
        if stm_trigger is not None:self.comb += core.fabric.trigger_stm.eq(stm_trigger)
        if ready_output is not None:self.comb += ready_output.eq(core.fabric.ready)
