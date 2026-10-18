"""Compile-only native ABI check; no linking, hardware or BSP validation.

Reuse existing toolchains. STM SDK headers must match the pinned manifest.
No files outside this project's work directory are modified.
"""
from pathlib import Path
import argparse,hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
base='/srv/codex-hil-data/projects/kasli-v11-linux/variants/smp4-eth'
p.add_argument('--riscv-cxx',default=base+'/toolchain/root/usr/bin/riscv64-unknown-elf-g++')
p.add_argument('--arm-cxx',default='/nix/store/c0jm2ghmasw8rljbixrhq3vw4hx2rgk8-clang-20.1.8/bin/clang++')
p.add_argument('--clang-resource',default='/nix/store/diaqxdd3h63sribv98gdh6ml565yrwj3-clang-20.1.8-lib/lib/clang/20')
p.add_argument('--sdk',default=str(ROOT/'work/scf5-stm32-sdk'))
p.add_argument('--libc-config',default=base+'/build/vivado/software/libc')
p.add_argument('--libc-include',default=base+'/vendor/pythondata-software-picolibc/pythondata_software_picolibc/data/libc/include')
a=p.parse_args();sdk=Path(a.sdk)
manifest=json.loads((ROOT/'evidence/scf5-stm32-sdk.json').read_text())
for entry in manifest['files']:
 f=sdk/Path(entry['path']).name
 assert hashlib.sha256(f.read_bytes()).hexdigest()==entry['sha256'],f
out=ROOT/'work/scf5-native';out.mkdir(exist_ok=True)
common=['-std=c++17','-ffreestanding','-fno-exceptions','-fno-rtti','-I'+str(ROOT/'firmware/hal'),'-I'+str(ROOT/'integrations/esphome/components/sinara_fpga')]
commands={
'riscv':[a.riscv_cxx,'-march=rv32ima','-mabi=ilp32','-Wall','-Wextra','-Werror',*common,'-c',str(ROOT/'firmware/hal/compile_riscv.cpp'),'-o',str(out/'compile.o')],
'stm32':[a.arm_cxx,'-resource-dir',a.clang_resource,'--target=arm-none-eabi','-mcpu=cortex-m7','-mthumb',*common,'-I'+str(sdk),'-I'+a.libc_config,'-idirafter',a.libc_include,'-c',str(ROOT/'firmware/hal/compile_stm32.cpp'),'-o',str(out/'stm_compile.o')]}
results={}
for target,command in commands.items():
 r=subprocess.run(command,cwd=ROOT,text=True,capture_output=True,timeout=60)
 (ROOT/f'evidence/scf5-{target}-compile.log').write_text(r.stdout+r.stderr)
 results[target]={'exit_code':r.returncode,'command':command}
 print(target,r.returncode)
report={'hardware_tested':False,'compile_only':True,'linked':False,'results':results,
 'source_hashes':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for folder in ['firmware/hal','integrations/esphome/components/sinara_fpga'] for f in (ROOT/folder).glob('*.h')}}
(ROOT/'evidence/scf5-native-compile.json').write_text(json.dumps(report,indent=2)+'\n')
raise SystemExit(any(r['exit_code'] for r in results.values()))
