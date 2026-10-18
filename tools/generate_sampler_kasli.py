"""Generate 8-pair Sampler GPIO endpoint HDL. Synthetic mapping; no bitstream/HIL."""
import hashlib
import json
import logging
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
for p in ['references/migen','references/litex','src','gateware']:sys.path.insert(0,str(ROOT/p))
from kasli_uart_gpio import KasliUARTGPIO
from sinara_slow.pinmaps import sampler_mapping
from litex.soc.integration.builder import Builder
logging.disable(logging.CRITICAL)
pads={name:[f'eem0:d{i}{"_cc" if i==0 else ""}_{pol}' for pol in ('p','n')]
      for name,i in sampler_mapping().items()}
output=ROOT/'work/sampler-kasli-elaboration'
soc=KasliUARTGPIO('v1.1',pads,'sampler_eem0')
Builder(soc,output_dir=str(output),compile_software=False,
    csr_csv=str(output/'csr.csv'),csr_json=str(output/'csr.json')).build(run=False)
verilog=output/'gateware/kasli_uart_gpio.v'
if not verilog.exists():
    candidates=list((output/'gateware').glob('*.v'))
    verilog=next(p for p in candidates if 'slow_adc_clk' in p.read_text())
text=verilog.read_text()
for name in pads:assert 'slow_'+name in text,name
result={'result':'PASS','hardware_tested':False,'synthesis_run':False,
        'profile':'sampler_eem0','output_pairs':[0,2,3,4,5,7],'input_pairs':[1,6],
        'verilog':str(verilog.relative_to(ROOT)),'sha256':hashlib.sha256(verilog.read_bytes()).hexdigest(),
        'limits':['synthetic EEM mapping, no electrical review','no P&R or physical loading',
                  'CPU-free UARTbone host bring-up, not native ESPHome runtime']}
(ROOT/'evidence/sampler-kasli-elaboration.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
