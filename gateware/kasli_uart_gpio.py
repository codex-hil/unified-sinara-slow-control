"""Minimal CPU-free Kasli UARTbone GPIO bring-up target (no RTIO).

Intermediate hardware bridge, not the preferred final bare-metal service.
No programming path: this script only generates HDL/CSR files. Pads require
an explicitly reviewed EEM mapping file, using platform connector names.
"""
import argparse
import json
from pathlib import Path

from migen import ClockDomain, Instance, Signal
from migen.genlib.resetsync import AsyncResetSynchronizer
from migen.build.platforms.sinara.kasli import Platform as MigenKasliPlatform
from migen.build.generic_platform import Pins, Subsignal, IOStandard
from litex.gen import LiteXModule
from litex.soc.integration.soc_core import SoCCore
from litex.soc.integration.builder import Builder
from gpio import SlowGPIO, SlowIdentity


class Platform(MigenKasliPlatform):
    def get_verilog(self, *args, **kwargs):
        # LiteX Builder passes an option not accepted by Migen's converter.
        kwargs.pop('hierarchical', None)
        kwargs.pop('build_backend', None)
        return super().get_verilog(*args, **kwargs)


class CRG(LiteXModule):
    def __init__(self, platform, hw_rev):
        self.cd_sys = ClockDomain('sys')
        if hw_rev == 'v1.0':
            clock=platform.request('clk50')
        else:
            pads=platform.request('clk125_gtp')
            clock=Signal()
            self.specials += Instance('IBUFDS_GTE2',i_CEB=0,i_I=pads.p,i_IB=pads.n,o_ODIV2=clock)
            platform.add_period_constraint(pads.p,8.0)
        self.specials += Instance('BUFG', i_I=clock, o_O=self.cd_sys.clk)
        self.specials += AsyncResetSynchronizer(self.cd_sys, 0)


def pad_routes(profile):
    if profile == 'legacy_urukul':
        return {'mosi':0,'cs0':2,'clk':3,'cs1':4,'cs2':5}, {'miso':1}
    if profile == 'sampler_eem0':
        from sinara_slow.pinmaps import sampler_mapping
        routes=sampler_mapping()
        return ({k:v for k,v in routes.items() if k not in ('adc_miso','pgia_miso')},
                {k:routes[k] for k in ('adc_miso','pgia_miso')})
    if profile == 'zotino_eem0':
        from sinara_slow.pinmaps import zotino_mapping
        routes=zotino_mapping()
        return ({k:v for k,v in routes.items() if k not in ('miso','busy')},
                {k:routes[k] for k in ('miso','busy')})
    raise ValueError('unknown GPIO pad profile')


def reviewed_pads(path, profile='legacy_urukul'):
    data=json.loads(Path(path).read_text())
    if data.get('reviewed') is not True:
        raise ValueError('EEM pin map must be explicitly reviewed')
    outputs,inputs=pad_routes(profile)
    if set(data) != {'reviewed','pins'} or set(data['pins']) != set(outputs)|set(inputs):
        raise ValueError('pin map does not match GPIO pad profile')
    pads=data['pins']; used=set()
    for pair in pads.values():
        if not isinstance(pair,list) or len(pair)!=2:
            raise ValueError('each differential signal needs [positive, negative] connector pins')
        for pin in pair:
            if not isinstance(pin,str) or ':' not in pin or pin in used:
                raise ValueError('invalid or overlapping EEM connector pin')
            used.add(pin)
    return pads


class KasliUARTGPIO(SoCCore):
    def __init__(self, hw_rev, pads, pin_profile='legacy_urukul'):
        outputs,inputs=pad_routes(pin_profile)
        if set(pads)!=set(outputs)|set(inputs):
            raise ValueError("pin map does not match GPIO pad profile")
        platform=Platform(hw_rev=hw_rev)
        # Reuse board clock resource; no DDR3/SerDes data path or CPU.
        self.crg=CRG(platform,hw_rev)
        frequency=50_000_000 if hw_rev == 'v1.0' else 62_500_000
        SoCCore.__init__(self,platform,frequency,cpu_type=None,
            integrated_rom_size=0,integrated_sram_size=0,with_uart=False,
            with_uartbone=False,uart_baudrate=115200,with_timer=False,
            csr_data_width=32,ident='Sinara slow GPIO bring-up')
        self.add_uartbone(baudrate=115200)
        self.gpio0=SlowGPIO()
        self.slow_id=SlowIdentity()
        self.csr.add('gpio0');self.csr.add('slow_id')
        platform.add_extension([('slow_'+name,0,Subsignal('p',Pins(pair[0])),
            Subsignal('n',Pins(pair[1])),IOStandard('LVDS_25')) for name,pair in pads.items()])
        # Profile logical pins: mosi=0, miso=1, cs0=2, clk=3, cs1=4, cs2=5.
        # Differential outputs have fixed direction. OE is a software convention.
        for name,bit in outputs.items():
            pair=platform.request('slow_'+name)
            self.specials += Instance('OBUFDS',i_I=self.gpio0.pins_out[bit],o_O=pair.p,o_OB=pair.n)
        for name,bit in inputs.items():
            pair=platform.request('slow_'+name)
            self.specials += Instance('IBUFDS',p_DIFF_TERM='TRUE',i_I=pair.p,i_IB=pair.n,o_O=self.gpio0.pins_in[bit])


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--revision',required=True,choices=['v1.0','v1.1','v2.0','v2.1'])
    p.add_argument('--pin-map',required=True)
    p.add_argument('--pin-profile',choices=['legacy_urukul','sampler_eem0','zotino_eem0'],default='legacy_urukul')
    p.add_argument('--output-dir',default='build/kasli-uart-gpio')
    a=p.parse_args()
    soc=KasliUARTGPIO(a.revision,reviewed_pads(a.pin_map,a.pin_profile),a.pin_profile)
    Builder(soc,output_dir=a.output_dir,compile_software=False,
            csr_csv=str(Path(a.output_dir)/'csr.csv'),csr_json=str(Path(a.output_dir)/'csr.json')).build(run=False)


if __name__=='__main__':main()
