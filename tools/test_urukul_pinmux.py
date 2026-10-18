"""Offline CSR/master/pinmux Urukul test. No physical IO or RF enable."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / p) for p in ('src', 'gateware', 'tools', 'work/upstream-stm/gateware')]
from migen.sim import run_simulation
from integrated_stm import logical, namespace
from stm_sys_board import Platform

results = {}
for serial, controller in ((True, 'stm'), (False, 'kasli')):
    d = logical(serial, half_period=1, slot_mappings={0: 'urukul_eem0'})
    addresses = d.fabric.register_map()['legacy']
    slot = d.logic0
    def bench():
        captured = []
        previous = 0
        expected_cs = None
        def tick():
            nonlocal previous
            clk = (yield slot.slot[0].o)
            if expected_cs is not None:
                # IO_UPDATE/reset are unowned GPIO, not extra chip selects.
                assert (yield slot.slot[6].oe) == 0
                assert (yield slot.slot[7].oe) == 0
                assert (yield slot.slot[2].oe) == 0
                if clk and not previous:
                    cs = sum([(yield slot.slot[3].o),
                              (yield slot.slot[4].o) << 1,
                              (yield slot.slot[5].o) << 2])
                    assert cs == expected_cs, (cs, expected_cs)
                    captured.append((yield slot.slot[1].o))
            previous = clk
            yield
        def write(name, value):
            yield d.bus.adr.eq(addresses['logic0_spi_master_' + name + '0'])
            yield d.bus.dat_w.eq(value)
            yield d.bus.we.eq(1)
            yield from tick()
            yield d.bus.we.eq(0)
            for _ in range(3): yield from tick()
        for _ in range(250): yield from tick()
        assert (yield d.fabric.direction.core.valid)
        yield slot.slot[2].i.eq(1)
        # All three decoded address bits active high, SPI mode 0, MSB first.
        for name, value in [('cs_polarity', 7), ('div', 7), ('length', 7), ('offline', 0)]:
            yield from write(name, value)
        # CFG write/status read, then a complete attenuator chain write.
        for cs, payload in [(1, bytes(3)), (2, bytes.fromhex('ff035faf')),
                            (4, bytes(3))]:
            captured.clear()
            expected_cs = cs
            yield from write('cs', cs)
            for index, byte in enumerate(payload):
                yield from write('end', int(index == len(payload)-1))
                yield from write('data', byte << 8)
                for _ in range(100): yield from tick()
            assert (yield slot.spi_master.idle.status)
            assert captured == [int(bit) for byte in payload for bit in f'{byte:08b}']
            for line in (3, 4, 5): assert (yield slot.slot[line].o) == 0
            assert (yield slot.spi_master.data.storage) == 255
            expected_cs = None
        yield from write('offline', 1)
        for _ in range(5): yield from tick()
        for line in range(8): assert (yield slot.slot[line].oe) == 0
    run_simulation(d, bench())
    results[controller + '_csr_master_urukul_routes'] = 'PASS'

# Confirm the profile reaches the real STM target's slot construction too.
ns = namespace({0: 'urukul_eem0'})
p = Platform()
b = ns['STMSysBoard'](p)
assert b.logic0.pinmux.spi_mask.reset.value == 0x3f
assert b.logic1.pinmux.spi_mask.reset.value == 0x0f
p.build(b, build_name='stm_urukul', build_dir=str(ROOT/'work/builds/stm-urukul'), run=False)
results.update(stm_target_elaboration='PASS', hardware_tested=False,
               scope='CPLD8/attenuation only; logical EEM map; no physical adapter validation')
(ROOT/'evidence/urukul-pinmux-tests.json').write_text(json.dumps(results, indent=2)+'\n')
print(json.dumps(results, indent=2))
