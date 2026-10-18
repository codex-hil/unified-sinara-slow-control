"""Compile only: isolated Rust maintenance image for STM v1.1 SPI flash."""
from pathlib import Path
import os,shutil,subprocess,json,hashlib
ROOT=Path(__file__).resolve().parents[1]
copy=ROOT/'work/flash-service-firmware'
if not copy.exists():shutil.copytree(ROOT/'work/upstream-stm/firmware',copy)
shutil.copyfile(ROOT/'firmware/hil/flash_serprog.rs',copy/'src/bin/flash_serprog.rs')
s= (copy/'Cargo.toml').read_text()
if '[dependencies.sinara-flash-serprog]' not in s:
 s+='\n[dependencies.sinara-flash-serprog]\npath = "../../firmware/flash-serprog"\n'
 (copy/'Cargo.toml').write_text(s)
tool=ROOT/'work/toolchains/rust/toolchains/1.88.0-x86_64-unknown-linux-gnu/bin'
env=os.environ.copy();env.update(CARGO_HOME=str(ROOT/'work/cargo'),CARGO_TARGET_DIR=str(ROOT/'work/builds/hil-probe'),RUSTC=str(tool/'rustc'),TMPDIR=str(ROOT/'work/tmp'))
with (ROOT/'evidence/flash-service-build.log').open('w') as log:
 r=subprocess.run([str(tool/'cargo'),'build','--offline','--release','--bin','flash_serprog'],cwd=copy,env=env,stdout=log,stderr=subprocess.STDOUT)
report={'result':'PASS' if r.returncode==0 else 'FAIL','hardware_tested':False,'protocol_core_sha256':hashlib.sha256((ROOT/'firmware/flash-serprog/src/lib.rs').read_bytes()).hexdigest(),'source_sha256':hashlib.sha256((ROOT/'firmware/hil/flash_serprog.rs').read_bytes()).hexdigest(),
        'limitations':'Maintenance image resets FPGA on startup. Not installed. GPIO mapping, flash access, UART and DONE timeout need HIL. Blocking SPI HAL may stall on peripheral faults.'}
if r.returncode==0:
 elf=ROOT/'work/builds/hil-probe/thumbv7em-none-eabihf/release/flash_serprog'
 report.update(elf=str(elf.relative_to(ROOT)),elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest())
 frozen=ROOT/'work/flash-kit'/('flash_serprog-'+report['elf_sha256'][:12]+'.elf')
 frozen.parent.mkdir(parents=True,exist_ok=True)
 if not frozen.exists():shutil.copyfile(elf,frozen)
 assert hashlib.sha256(frozen.read_bytes()).hexdigest()==report['elf_sha256']
 report['frozen_elf']=str(frozen.relative_to(ROOT))
(ROOT/'evidence/flash-service-build.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2));raise SystemExit(r.returncode)
