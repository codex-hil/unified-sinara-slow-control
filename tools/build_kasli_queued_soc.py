"""Reuse qualified SMP4/DDR/LiteEth SoC; attach SCF5, never load hardware.

Default elaboration only. Pin routing remains separate until a reviewed
Kasli-DIOT carrier map is supplied; no RTIO or Linux images are added.
"""
from pathlib import Path
import argparse,importlib.util,sys,json,hashlib
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--source',default='/srv/codex-hil-data/projects/kasli-v11-linux/variants/smp4-eth/target.py')
p.add_argument('--profile',default=str(ROOT/'examples/fabric-kasli.yaml'))
p.add_argument('--output',default=str(ROOT/'work/kasli-queued-soc'))
args=p.parse_args();source=Path(args.source).resolve();before=hashlib.sha256(source.read_bytes()).hexdigest()
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'gateware'),str(ROOT/'references/misoc'),str(ROOT/'work/upstream-stm/deps/misoc')]
from sinara_slow.fabric import load_profile,build_id
profile=load_profile(args.profile)
spec=importlib.util.spec_from_file_location('qualified_kasli_smp4_ethernet',source)
reference=importlib.util.module_from_spec(spec);spec.loader.exec_module(reference)
from queued_targets import attach_kasli
from litex.soc.integration.builder import Builder
soc=reference.LinuxSoC('vivado')
fabric=attach_kasli(soc,profile)
soc.add_constant('SINARA_FABRIC_BASE',0x81000000)
soc.add_constant('SINARA_FABRIC_ABI',5)
soc.add_constant('SINARA_FABRIC_ID_LO',build_id(profile)&0xffffffff)
soc.add_constant('SINARA_FABRIC_ID_HI',build_id(profile)>>32)
out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
builder=Builder(soc,output_dir=str(out),compile_software=False,
    csr_csv=str(out/'csr.csv'),csr_json=str(out/'csr.json'))
builder.build(build_name='kasli_esphome_scf5',run=False)
if hashlib.sha256(source.read_bytes()).hexdigest()!=before:raise RuntimeError('concurrent upstream source change')
report=dict(source=str(source),source_sha256=before,cpu_count=4,ethernet='reused LiteEth1000BASE-X',
    cpu_variant='reused linux-capable VexRiscv; Linux software not built/loaded',base_address='0x81000000',
    fabric_id=f'{build_id(profile):016x}',profile=str(Path(args.profile)),
    physical_slow_control_pads='not connected: reviewed Kasli-DIOT carrier map required',
    hardware_tested=False,programming_ready=False,elaboration='PASS')
(ROOT/'evidence/scf5-kasli-soc.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
