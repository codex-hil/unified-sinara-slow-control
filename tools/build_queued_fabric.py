"""Elaborate shared SCF5 RTL and manifest, without Vivado/programming."""
from pathlib import Path
import argparse,json,sys,hashlib
ROOT=Path(__file__).resolve().parents[1]
for p in ['src','gateware','references/migen','references/misoc','work/upstream-stm/deps/misoc','references/litex']:sys.path.insert(0,str(ROOT/p))
from sinara_slow.fabric import load_profile,build_id
from queued_targets import make_fabric,STMQueuedCore
from migen.fhdl import verilog
p=argparse.ArgumentParser(description=__doc__);p.add_argument('profile');p.add_argument('--output');args=p.parse_args()
profile=load_profile(args.profile);target=profile['target'];out=Path(args.output) if args.output else ROOT/'work/queued-fabric'/target
out.mkdir(parents=True,exist_ok=True)
d=STMQueuedCore(profile) if target=='stm_ecp5' else make_fabric(profile)
fabric=d.fabric if target=='stm_ecp5' else d
io=set(fabric.inputs+fabric.outputs+fabric.oes+[fabric.trigger_external,fabric.trigger_stm,fabric.ready,fabric.interlock_ok])
if target=='stm_ecp5':
 io.update([d.qspi.sck,d.qspi.cs_n,d.qspi.dq_i,d.qspi.dq_o,d.qspi.dq_oe,
            fabric.directions.sck,fabric.directions.mosi,fabric.directions.latch])
else:io.update([fabric.bus.adr,fabric.bus.dat_w,fabric.bus.dat_r,fabric.bus.we,fabric.bus.cyc,fabric.bus.stb,fabric.bus.ack,fabric.bus.err,fabric.bus.sel])
v=verilog.convert(d,ios=io,name='sinara_queued_'+target);path=out/'fabric.v';path.write_text(str(v))
manifest=dict(abi='SCF5',version=5,build_id=f'{build_id(profile):016x}',profile=profile,
    verilog_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    source_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'gateware').glob('*.py')},
    hardware_tested=False,programming_ready=False,physical_pad_wrapper='not instantiated',
    qspi_max_sck_hz=profile['sys_clk_hz']//16 if target=='stm_ecp5' else None)
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(path);print(json.dumps({k:manifest[k] for k in ('abi','build_id','hardware_tested','programming_ready')},indent=2))
