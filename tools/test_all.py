"""Bounded offline tests; no programming, physical ports or lab network."""
import json
import os
from pathlib import Path
import subprocess
import sys
import datetime

ROOT=Path(__file__).resolve().parents[1]
commands=[['python3','-m','unittest','discover','-s','tests','-v'],
          ['cargo','test','--manifest-path','firmware/stm-service/Cargo.toml'],
          ['cargo','test','--manifest-path','firmware/flash-serprog/Cargo.toml'],
          ['cargo','build','--example','stdio_simulator','--manifest-path','firmware/stm-service/Cargo.toml'],
          ['python3','tools/check_reference.py'],
          ['python3','tools/test_rust_wire.py']]
env=os.environ.copy();env['PYTHONPATH']=str(ROOT/'src')
results=[]
for i,command in enumerate(commands):
    result=subprocess.run(command,cwd=ROOT,env=env,text=True,capture_output=True,timeout=120)
    log=ROOT/'evidence'/f'test-{i+1}.log';log.write_text(result.stdout+result.stderr)
    results.append({'command':command,'exit_code':result.returncode,'log':str(log.relative_to(ROOT))})
    print(f'{result.returncode}: {" ".join(command)}')
report={'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'hardware_tested':False,'results':results}
(ROOT/'evidence/test-results.json').write_text(json.dumps(report,indent=2)+'\n')
sys.exit(any(r['exit_code'] for r in results))
