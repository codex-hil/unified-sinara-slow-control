"""Generate HDL for synthetic pins; no physical FPGA access or bitstream."""
import logging
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
for p in ['references/migen','references/litex','gateware']:sys.path.insert(0,str(ROOT/p))
from kasli_uart_gpio import KasliUARTGPIO
from litex.soc.integration.builder import Builder
logging.disable(logging.CRITICAL)
# Synthetic map is deliberately outside examples/*.hardware profiles.
pads={name:[f'eem0:d{i}_p',f'eem0:d{i}_n'] for i,name in enumerate(['mosi','miso','clk','cs0','cs1','cs2'],1)}
for revision in ['v1.0','v1.1','v2.0','v2.1']:
    soc=KasliUARTGPIO(revision,pads)
    output=ROOT/'evidence'/('kasli-'+revision+'-elaboration')
    Builder(soc,output_dir=str(output),compile_software=False,
            csr_csv=str(output/'csr.csv'),csr_json=str(output/'csr.json')).build(run=False)
    print(revision,'HDL generation PASS, synthetic pin mapping')
