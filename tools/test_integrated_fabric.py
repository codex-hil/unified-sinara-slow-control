"""Actual 16-bit CSR bus + MiSoC masters + 595 model; no PCB actions."""
from pathlib import Path
import sys
import json
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'gateware'), str(ROOT/'work/upstream-stm/gateware')]
from migen import Module
from migen.sim import run_simulation
from misoc.interconnect import csr_bus
from misoc.interconnect.csr import AutoCSR, CSRStatus
from slow_fabric import SlowControlFabric
from integrated_stm import namespace
from stm_sys_board import Platform
from migen.fhdl import verilog

ns = namespace()
from integrated_stm import logical

results = {}
for serial in (True, False):
    d = logical(serial, half_period=1, settle_cycles=20)
    mapping = d.fabric.register_map()
    legacy = mapping['legacy']; direction = mapping['direction']
    assert legacy['id'] == 160 and legacy['id2'] == 161 and legacy['gate_rev'] == 162
    def bench():
        core = d.fabric.direction.core
        clk_before = latch_before = shift = latches = 0
        stored = None
        spi_prev = 0
        spi_bits = []
        def tick():
            nonlocal clk_before, latch_before, shift, stored, latches, spi_prev
            clk, latch = (yield core.sck), (yield core.latch)
            if clk and not clk_before:
                shift = ((shift << 1) | (yield core.mosi)) & ((1 << 48)-1)
            if latch and not latch_before:
                stored = shift; latches += 1
            clk_before, latch_before = clk, latch
            for i in range(6):
                slot = getattr(d, 'logic'+str(i))
                actual = 0
                for bit in range(8):
                    actual |= (yield slot.slot[8+bit].oe) << bit
                expected = 0 if (yield core.busy) else ((yield core.active) >> (8*i)) & 255
                assert actual == expected
            spi_clk = (yield d.logic0.slot[0].o)
            if spi_clk and not spi_prev and not (yield d.logic0.spi_master.offline.storage):
                assert (yield d.logic0.slot[3].o) == 0
                spi_bits.append((yield d.logic0.slot[1].o))
            spi_prev = spi_clk
            yield
        def wait_idle():
            for _ in range(400):
                if not (yield core.busy): return
                yield from tick()
            raise AssertionError('direction timeout')
        def write(address, value):
            yield d.bus.adr.eq(address); yield d.bus.dat_w.eq(value); yield d.bus.we.eq(1)
            yield from tick()
            yield d.bus.we.eq(0)
            yield from tick()
            yield from tick()
        def read(address):
            yield d.bus.adr.eq(address)
            yield from tick(); yield from tick(); yield from tick()
            return (yield d.bus.dat_r)
        def request(mask):
            for n, word in enumerate([mask >> 32, mask >> 16, mask]):
                yield from write(direction['direction_requested'+str(2-n)], word & 65535)
            yield from write(direction['direction_apply'], 1)
        yield d.logic0.slot[2].i.eq(1)
        yield from wait_idle()
        assert (yield from read(160)) == 0xAAAA
        assert (yield from read(161)) == 0x5555
        assert (yield from read(162)) == 4
        if serial: assert stored == 0 and latches == 1
        mask = 0x123456789ABC
        yield from write(legacy['logic0_output0'], 0xA55A)
        assert (yield d.logic0.output.storage) == 0xA55A, ('initial', (yield d.logic0.output.storage))
        yield from request(mask)
        assert (yield core.busy)
        yield from write(legacy['logic0_output0'], 0xFFFF)
        yield from write(legacy['logic0_spi_master_data0'], 0xFFFF)
        assert (yield d.logic0.output.storage) == 0xA55A, ('blocked', (yield d.logic0.output.storage), serial)
        assert (yield d.logic0.spi_master.idle.status)
        yield from wait_idle()
        assert (yield core.active) == mask
        if serial: assert stored == mask and latches == 2
        assert (yield from read(direction['direction_status'])) & 16
        yield from write(direction['direction_clear_rejected'], 1)
        assert not ((yield from read(direction['direction_status'])) & 24)
        # Old GPIO OE upper bits no longer control the six translators.
        yield from write(legacy['logic0_oe0'], 0xFFFF)
        assert (yield d.logic0.upper_oe) == 0xBC
        # IRQ input direction follows actual OE, not stale legacy upper OE bits.
        yield from write(legacy['logic0_interrupt_mask0'], 1 << 8)
        yield d.logic0.slot[8].i.eq(1)
        for _ in range(5): yield from tick()
        assert (yield d.logic0.interrupt.status) & (1 << 8)
        yield from write(legacy['logic0_interrupt_clear0'], 1 << 8)
        for _ in range(5): yield from tick()
        assert not ((yield d.logic0.interrupt.status) & (1 << 8))
        # Begin a real multi-transfer SPI transaction, deliberately keep CS active.
        for name, value in [('offline', 0), ('cs', 1), ('div', 3), ('length', 7), ('end', 0), ('data', 0xA500)]:
            yield from write(legacy['logic0_spi_master_'+name+'0'], value)
        for _ in range(100): yield from tick()
        assert not (yield d.logic0.spi_master.idle.status)
        prior_latches = latches
        yield from request(0)
        assert (yield from read(direction['direction_status'])) & 8
        assert (yield core.active) == mask and latches == prior_latches
        # Final transfer ends the existing SPI transaction.
        yield from write(legacy['logic0_spi_master_end0'], 1)
        yield from write(legacy['logic0_spi_master_data0'], 0x5A00)
        for _ in range(100): yield from tick()
        assert (yield d.logic0.spi_master.idle.status)
        assert spi_bits == [int(b) for b in '1010010101011010']
        assert (yield from read(legacy['logic0_spi_master_data0'])) == 0xFF
        yield from write(direction['direction_clear_rejected'], 1)
        yield from request(0)
        yield d.logic0.slot[8].i.eq(0)
        for _ in range(5): yield from tick()
        assert not ((yield d.logic0.interrupt.status) & (1 << 8))
        yield from wait_idle()
        assert (yield core.active) == 0
        if serial: assert stored == 0 and latches == 3
    run_simulation(d, bench())
    results['serial' if serial else 'direct'] = 'PASS'
# Real full STM target with actual upstream pads; no physical validity claim.
p = Platform(); board = ns['STMSysBoard'](p)
p.build(board, build_name='stm_sys_board', build_dir=str(ROOT/'work/builds/stm-integrated'), run=False)
(ROOT/'evidence/integrated-csr-map.json').write_text(json.dumps(board.fabric.register_map(), indent=2)+'\n')
# A complete eight-slot fabric with the direct backend, clock/reset + logical IO.
d = logical(False, half_period=1, settle_cycles=20)
ports = set(d.bus.flatten())
for i in range(8):
    ports.update(s for triple in getattr(d, 'logic'+str(i)).slot for s in (triple.i, triple.o, triple.oe))
(ROOT/'work/integrated-stm/kasli-fabric.v').write_text(str(verilog.convert(d, ios=ports, name='kasli_fabric')))
results.update(stm_full_target_elaboration='PASS', kasli_eight_slot_logical_hdl='PASS',
               hardware_tested=False, upstream_sha256=ns['upstream_sha256'],
               limitations='Physical mapping inherited, not reviewed for programming. Kasli logical fabric only; no EEM pads/host SoC.')
(ROOT/'evidence/integrated-fabric-tests.json').write_text(json.dumps(results, indent=2)+'\n')
print(json.dumps(results, indent=2))
