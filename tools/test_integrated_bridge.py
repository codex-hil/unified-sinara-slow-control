"""Upstream SPI2WB -> WB2CSR -> ABI-v4 fabric -> behavioral 595 chain."""
from pathlib import Path
import sys
import json
import subprocess
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'gateware'), str(ROOT/'work/upstream-stm/gateware')]
from migen import Module, ClockDomain
from migen.fhdl import verilog
from misoc.interconnect import wishbone, wishbone2csr
from spi2wb import SPI2WB
from integrated_stm import logical
class Platform:
    def add_source(self, path): pass
m = Module()
m.clock_domains.cd_sys = ClockDomain('sys')
m.clock_domains.cd_sck1 = ClockDomain('sck1', reset_less=True)
m.submodules.logical = d = logical()
wb = wishbone.Interface(data_width=16, adr_width=15)
m.submodules.wb2csr = wishbone2csr.WB2CSR(bus_wishbone=wb, bus_csr=d.bus)
m.submodules.bridge = b = SPI2WB(Platform(), wb, address_width=15)
core = d.fabric.direction.core
ports = [('sys_clk',m.cd_sys.clk), ('rst',m.cd_sys.rst), ('sck',m.cd_sck1.clk),
         ('mosi',b.sdi),('miso',b.sdo),('selected',b.sel),('dir_sck',core.sck),
         ('dir_mosi',core.mosi),('dir_latch',core.latch),('active',core.active),
         ('upper_oe',d.logic0.upper_oe),('adr',wb.adr),('cyc',wb.cyc),('stb',wb.stb),('we',wb.we),('ack',wb.ack)]
for name,s in ports: s.name_override = name
out = ROOT/'work/builds/integrated-bridge-sim'; out.mkdir(parents=True,exist_ok=True)
(out/'bridge.v').write_text(str(verilog.convert(m, ios={s for _,s in ports}, name='bridge')))
subprocess.run(['iverilog','-g2012','-s','tb','-o',str(out/'test.vvp'),
               str(ROOT/'tests/integrated_bridge_tb.v'),str(out/'bridge.v'),
               str(ROOT/'work/upstream-stm/gateware/counter.v')], check=True)
subprocess.run(['vvp',str(out/'test.vvp')],check=True)
(ROOT/'evidence/integrated-bridge-tests.json').write_text(json.dumps({
    'result':'PASS','hardware_tested':False,'serial_clock_mhz':25,'header_bits':16,'dummy_cycles':5,
    'chain_bits':48,'register_bank':'actual CSR, no RAM substitute',
    'limitations':'Behavioral FD1P3BX, no pad delays/metastability; upstream bridge startup and duplicate-read issues retained.'},indent=2)+'\n')
