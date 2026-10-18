"""Simulate unchanged upstream SPI2WB with a behavioral primitive and WB RAM."""
from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work/upstream-stm/gateware"))
from migen import Module, ClockDomain
from migen.fhdl import verilog
from misoc.interconnect import wishbone
from spi2wb import SPI2WB


class Platform:
    def add_source(self, path):
        pass


def main():
    m = Module()
    m.clock_domains.cd_sys = ClockDomain("sys")
    m.clock_domains.cd_sck1 = ClockDomain("sck1", reset_less=True)
    bus = wishbone.Interface(data_width=16, adr_width=15)
    m.submodules.bridge = d = SPI2WB(Platform(), bus, address_width=15)
    ports = [("sys_clk", m.cd_sys.clk), ("rst", m.cd_sys.rst), ("sck", m.cd_sck1.clk),
             ("mosi", d.sdi), ("miso", d.sdo), ("selected", d.sel),
             ("adr", bus.adr), ("dat_w", bus.dat_w), ("dat_r", bus.dat_r),
             ("cyc", bus.cyc), ("stb", bus.stb), ("we", bus.we), ("ack", bus.ack)]
    for name, signal in ports:
        signal.name_override = name
    out = ROOT / "work/builds/stm-bridge-sim"
    out.mkdir(parents=True, exist_ok=True)
    (out / "bridge.v").write_text(str(verilog.convert(m, ios={s for _, s in ports}, name="bridge")))
    subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(out / "test.vvp"),
                    str(ROOT / "tests/stm_bridge_tb.v"), str(out / "bridge.v"),
                    str(ROOT / "work/upstream-stm/gateware/counter.v")], check=True)
    subprocess.run(["vvp", str(out / "test.vvp")], check=True)


if __name__ == "__main__":
    main()
