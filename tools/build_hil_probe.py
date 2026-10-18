#!/usr/bin/env python3
"""Build-only read-only CSR probe. Does not run or flash the image."""
from pathlib import Path
import os
import shutil
import subprocess
import hashlib
import json
ROOT = Path(__file__).resolve().parents[1]
snapshot = ROOT/'work/upstream-stm/firmware'
copy = ROOT/'work/hil-probe-firmware'
if not copy.exists(): shutil.copytree(snapshot,copy)
probe = ROOT/'firmware/hil/hil_probe.rs'
shutil.copyfile(probe,copy/'src/bin/hil_probe.rs')
toolchain = ROOT/'work/toolchains/rust/toolchains/1.88.0-x86_64-unknown-linux-gnu/bin'
env = os.environ.copy()
env.update(CARGO_HOME=str(ROOT/'work/cargo'), CARGO_TARGET_DIR=str(ROOT/'work/builds/hil-probe'),
           TMPDIR=str(ROOT/'work/tmp'), RUSTC=str(toolchain/'rustc'))
log = ROOT/'evidence/hil-probe-build.log'
with log.open('w') as output:
    result = subprocess.run([str(toolchain/'cargo'),'build','--locked','--release','--bin','hil_probe'],
                            cwd=copy,env=env,stdout=output,stderr=subprocess.STDOUT)
report = {'result':'PASS' if result.returncode == 0 else 'FAIL', 'exit_code':result.returncode,
          'hardware_tested':False,'rust':'1.88.0','target':'thumbv7em-none-eabihf',
          'probe_source_sha256':hashlib.sha256(probe.read_bytes()).hexdigest(),
          'limitations':'Upstream setup retained; HAL/setup may block. No module init or CSR writes. Not flashed.'}
if result.returncode == 0:
    elf = ROOT/'work/builds/hil-probe/thumbv7em-none-eabihf/release/hil_probe'
    report.update(elf=str(elf.relative_to(ROOT)),elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest())
(ROOT/'evidence/hil-probe-build.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
raise SystemExit(result.returncode)
