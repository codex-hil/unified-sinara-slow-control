#!/usr/bin/env python3
"""Offline-only integrated target builds. Never opens programmer or network."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
from datetime import datetime, timezone
ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('target', choices=['stm', 'kasli'])
parser.add_argument('--seed', type=int, default=3)
parser.add_argument('--timing-weight', type=int, default=20)
parser.add_argument('--timing-ripup', action='store_true', default=True)
parser.add_argument('--no-timing-ripup', action='store_false', dest='timing_ripup')
args = parser.parse_args()
report = {'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in sorted((ROOT/'gateware').glob('*.py'))},
          'target': args.target, 'hardware_tested': False, 'timestamp': datetime.now(timezone.utc).isoformat()}
env = os.environ.copy()
env['PATH'] = '/srv/codex-hil-data/toolchains/gatemate/oss-cad-suite/bin:' + env['PATH']
log = ROOT/'evidence'/('integrated-'+args.target+'-build.log')

def run(command, cwd, output):
    result = subprocess.run(command, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f'exit {result.returncode}: {command[0]}')

try:
    with log.open('w') as output:
        if args.target == 'stm':
            cwd = ROOT/'work/builds/stm-integrated'
            run(['yosys', '-l', 'stm_sys_board.rpt', 'stm_sys_board.ys'], cwd, output)
            report['synthesis'] = 'PASS'
            run(['nextpnr-ecp5', '--json', 'stm_sys_board.json', '--lpf', 'stm_sys_board.lpf',
                 '--textcfg', 'stm_sys_board-strict.config', '--85k', '--package', 'CABGA554',
                 '--speed', '6', '--seed', str(args.seed),
                 '--placer-heap-timingweight', str(args.timing_weight)] +
                 (['--tmg-ripup'] if args.timing_ripup else []), cwd, output)
            report.update(place_and_route='PASS', seed=args.seed, timing_weight=args.timing_weight, timing_ripup=args.timing_ripup)
            run(['ecppack', 'stm_sys_board-strict.config', '--bit', 'stm_sys_board-strict.bit'], cwd, output)
            bit = cwd/'stm_sys_board-strict.bit'
            report['bitstream'] = str(bit.relative_to(ROOT))
            report['bitstream_sha256'] = hashlib.sha256(bit.read_bytes()).hexdigest()
            report['limitations'] = 'Unreviewed inherited physical mapping. Not authorized for programming. No hardware or QSPI x4 validation.'
        else:
            cwd = ROOT/'work/builds/kasli-fabric'
            cwd.mkdir(parents=True, exist_ok=True)
            source = ROOT/'work/integrated-stm/kasli-fabric.v'
            (cwd/'synth.tcl').write_text(f'''read_verilog {{{source}}}
synth_design -top kasli_fabric -part xc7a100tfgg484-2 -mode out_of_context
create_clock -name sys -period 16.000 [get_ports sys_clk]
opt_design
place_design
route_design
report_utilization -file utilization.rpt
report_timing_summary -file timing.rpt
report_drc -file drc.rpt
write_checkpoint -force routed.dcp
set setup [get_timing_paths -delay_type max -max_paths 1]
set hold [get_timing_paths -delay_type min -max_paths 1]
set sf [open result.txt w]
puts $sf [get_property SLACK $setup]
puts $sf [get_property SLACK $hold]
close $sf
if {{[get_property SLACK $setup] < 0 || [get_property SLACK $hold] < 0}} {{error "timing failed"}}
''')
            run(['/home/codex-hil/.local/bin/vivado', '-mode', 'batch', '-source', 'synth.tcl'], cwd, output)
            report.update(synthesis='PASS', out_of_context_route='PASS', timing=dict(zip(['setup_slack_ns', 'hold_slack_ns'],
                                          map(float, (cwd/'result.txt').read_text().split()))),
                          limitations='Logical eight-slot fabric only. No SoC/EEM IO constraints or bitstream. 62.5 MHz constraint; no external IO timing proof.')
    if args.target == 'stm':
        values = re.findall(r"Max frequency for clock.*clk100.*?: ([0-9.]+) MHz", log.read_text())
        if values: report['sys_mhz'] = float(values[-1])
    report['result'] = 'PASS'
except Exception as error:
    report.update(result='FAIL', error=str(error))
finally:
    (ROOT/'evidence'/('integrated-'+args.target+'-build.json')).write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))
if report['result'] != 'PASS': raise SystemExit(1)
