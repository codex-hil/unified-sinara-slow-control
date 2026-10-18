"""Build isolated ECP5 candidate and lower its slot logic for Kasli v1.1.

Use upstream-pinned dependencies via PYTHONPATH (see docs/PINMUX.md).
No bitstream, programming, changed upstream files or physical pin assignments.
"""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "gateware"))
sys.path.insert(0, str(ROOT / "work/upstream-stm/gateware"))
from stm_sys_board import Platform
from migen.build.platforms.sinara.kasli import Platform as KasliPlatform
from migen.build.xilinx import common
from migen.fhdl import verilog as verilog_backend

source = (ROOT / "work/upstream-stm/gateware/stm_sys_board_hdl.py").read_text()
start = source.index("        spi_if_signals =")
end = source.index("        self.comb += self.io_interrupt", start)
candidate = source[:start] + '''        from pinmux import SlotPinMux
        self.submodules.pinmux = SlotPinMux(spi_interface)
        self.slot = self.pinmux.slot
        self.comb += [self.pinmux.output.eq(self.output.storage),
                      self.pinmux.oe.eq(self.oe.storage),
                      self.pinmux.offline.eq(self.spi_master.offline.storage),
                      self.input.status.eq(self.pinmux.input)]
''' + source[end:]
out = ROOT / "work/pinmux-stm"
out.mkdir(parents=True, exist_ok=True)
(out / "stm_sys_board_hdl.py").write_text(candidate)
namespace = {"__name__": "pinmux_candidate"}
exec(compile(candidate, str(out / "stm_sys_board_hdl.py"), "exec"), namespace)
platform = Platform()
board = namespace["STMSysBoard"](platform)
platform.build(board, build_name="stm_sys_board", build_dir=str(ROOT / "work/builds/stm-pinmux"), run=False)
slot = namespace["SlotController"]()
assert len(slot.get_csrs()) == 20
assert len(board.get_csrs()) == 163
kasli = KasliPlatform(hw_rev="v1.1")
ios = {signal for p in slot.slot for signal in (p.i, p.o, p.oe)}
overrides = dict(common.xilinx_special_overrides)
overrides.update(common.xilinx_s7_special_overrides)
verilog = verilog_backend.convert(slot, ios=ios, name="shared_slot",
                                 special_overrides=overrides,
                                 attr_translate=kasli.toolchain.attr_translate)
(out / "kasli-shared-slot.v").write_text(str(verilog))
from direction_csr import DirectionCSR
from migen.sim import run_simulation
csr_test = DirectionCSR(8, serial=True, half_period=1, settle_cycles=1)
def csr_bench():
    for _ in range(30):
        yield
    yield csr_test.core.quiescent.eq(0)
    yield csr_test.apply.r.eq(1)
    yield csr_test.apply.re.eq(1)
    yield
    yield
    yield csr_test.apply.re.eq(0)
    yield
    assert (yield csr_test.status.status) & 8
    assert (yield csr_test.active.status) == 0
    yield csr_test.clear_rejected.r.eq(1)
    yield csr_test.clear_rejected.re.eq(1)
    yield
    yield
    yield csr_test.clear_rejected.re.eq(0)
    yield csr_test.core.quiescent.eq(1)
    yield csr_test.requested.storage.eq(0xA5)
    yield
    yield csr_test.apply.re.eq(1)
    yield
    yield csr_test.apply.re.eq(0)
    for _ in range(30):
        yield
    assert (yield csr_test.active.status) == 0xA5
    assert (yield csr_test.status.status) == 6
run_simulation(csr_test, csr_bench())
for target, serial in [("stm", True), ("kasli", False)]:
    wrapper = DirectionCSR(48, serial=serial)
    direction = wrapper.core
    ports = {getattr(direction, name) for name in
             ("requested", "apply", "quiescent", "ready", "busy", "done",
              "active", "valid", "oe", "sck", "mosi", "latch")}
    (out / (target + "-direction.v")).write_text(str(verilog_backend.convert(
        wrapper, ios=ports, name=target + "_direction")))
report = {"direction_serial_and_direct_hdl": "PASS", "direction_csr_simulation": "PASS", "ecp5_full_target_elaboration": "PASS", "kasli_v1_1_slot_lowering": "PASS",
          "stm_register_count": 163, "slot_register_count": 20,
          "hardware_tested": False, "upstream_modified": False,
          "limitations": "Kasli logical slot only, no CSR bridge/pads/bitstream. STM candidate not synthesized or routed."}
(ROOT / "evidence/shared-pinmux-build.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
