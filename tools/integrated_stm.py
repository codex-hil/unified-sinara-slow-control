"""Generate an isolated ABI-v4 target from the archived upstream baseline."""
from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'work/upstream-stm/gateware/stm_sys_board_hdl.py'


def namespace(slot_mappings=None):
    """Optional zero-based slot -> logical SPI mapping, fixed at elaboration."""
    slot_mappings = dict(slot_mappings or {})
    if any(type(i) is not int or not 0 <= i < 8 for i in slot_mappings):
        raise ValueError("slot mapping index must be 0..7")
    source = SOURCE.read_text()
    source = source.replace('class SlotController(Module, AutoCSR):\n    def __init__(self):',
                            'class SlotController(Module, AutoCSR):\n    def __init__(self, mapping=None):')
    source = source.replace('SlotController())',
                            'SlotController(mapping=' + repr(slot_mappings) + '.get(i)))')
    start = source.index('        spi_if_signals =')
    end = source.index('        self.comb += self.io_interrupt', start)
    source = source[:start] + '''        from pinmux import SlotPinMux
        self.upper_oe = Signal(8)
        self.direction_busy = Signal()
        self.submodules.pinmux = SlotPinMux(spi_interface, mapping=mapping)
        self.slot = self.pinmux.slot
        self.comb += [self.pinmux.output.eq(self.output.storage),
                      self.pinmux.oe.eq(Cat(self.oe.storage[:8], self.upper_oe)),
                      self.pinmux.offline.eq(self.spi_master.offline.storage),
                      self.input.status.eq(self.pinmux.input)]
''' + source[end:]
    source = source.replace('(~self.oe.storage[i])', '(~self.slot[i].oe) & ~self.direction_busy')
    source = source.replace('self.gate_rev.status.eq(0x0003)', 'self.gate_rev.status.eq(0x0004)')
    start = source.index('        self.submodules.csrs =')
    end = source.index('        # SPI Slave', start)
    source = source[:start] + '''        from slow_fabric import SlowControlFabric
        legacy_csrs = self.get_csrs()
        self.submodules.fabric = SlowControlFabric(
            [getattr(self, "logic{}".format(i)) for i in range(8)],
            legacy_csrs, self.csr_bus, serial=True)
''' + source[end:]
    start = source.index('        # short circuit between spi4')
    end = source.index('        clk_stm =', start)
    source = source[:start] + '''        # No STM SPI4 passthrough: the fabric owns the direction chain.
        mlvds_dir_spi = platform.request("spi_dir_ctrl")
        self.comb += [mlvds_dir_spi.clk.eq(self.fabric.direction.core.sck),
                      mlvds_dir_spi.mosi.eq(self.fabric.direction.core.mosi),
                      mlvds_dir_spi.cs.eq(self.fabric.direction.core.latch)]
''' + source[end:]
    out = ROOT / 'work/integrated-stm'
    out.mkdir(parents=True, exist_ok=True)
    generated = out / 'stm_sys_board_hdl.py'
    generated.write_text(source)
    ns = {'__name__': 'integrated_stm'}
    exec(compile(source, str(generated), 'exec'), ns)
    ns['upstream_sha256'] = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    return ns


def logical(serial=True, half_period=50, settle_cycles=4, slot_mappings=None):
    """Same slot+CSR fabric as STM, without board primitives or IO pads."""
    from migen import Module
    from misoc.interconnect import csr_bus
    from misoc.interconnect.csr import AutoCSR, CSRStatus
    from slow_fabric import SlowControlFabric
    ns = namespace(slot_mappings)
    class Logical(Module, AutoCSR):
        def __init__(self):
            for i in range(8):
                setattr(self, 'logic'+str(i), ns['SlotController'](mapping=(slot_mappings or {}).get(i)))
                self.submodules += getattr(self, 'logic'+str(i))
            self.id = CSRStatus(16, name='id')
            self.id2 = CSRStatus(16, name='id2')
            self.gate_rev = CSRStatus(16, name='gate_rev')
            self.comb += [self.id.status.eq(0xAAAA), self.id2.status.eq(0x5555), self.gate_rev.status.eq(4)]
            self.bus = csr_bus.Interface(data_width=16, address_width=15)
            self.submodules.fabric = SlowControlFabric(
                [getattr(self, 'logic'+str(i)) for i in range(8)], self.get_csrs(),
                self.bus, serial=serial, half_period=half_period, settle_cycles=settle_cycles)
    return Logical()
