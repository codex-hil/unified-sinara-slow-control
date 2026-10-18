"""Rebuild the audited host tool only; never connects to hardware."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess
ROOT=Path(__file__).resolve().parents[1]
PIN='fb281f64bf58b547300a38ab9634711ddaf05e39'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--python',default='/home/codex-hil/vector-analyser/.venv/bin/python')
args=parser.parse_args()
source=ROOT/'references/flashrom'
actual=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()
if actual!=PIN:raise SystemExit('flashrom source differs from audited commit; not modifying checkout')
env=os.environ.copy();env['PYTHONPATH']=str(ROOT/'work/flash-tools');env['PATH']=str(ROOT/'work/flash-tools/bin')+':'+env['PATH']
base=[args.python,'-m','mesonbuild.mesonmain']
setup=base+['setup','work/builds/flashrom','references/flashrom','-Dprogrammer=serprog,dummy','-Dtests=disabled','-Ddocumentation=disabled','-Dman-pages=disabled','-Dich_descriptors_tool=disabled']
if (ROOT/'work/builds/flashrom/build.ninja').exists():setup.append('--reconfigure')
with (ROOT/'evidence/flashrom-build.log').open('w') as log:
 for command in [setup,base+['compile','-C','work/builds/flashrom']]:
  subprocess.run(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
binary=ROOT/'work/builds/flashrom/flashrom'
report={'result':'PASS','commit':PIN,'binary':str(binary.relative_to(ROOT)),
        'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),
        'drivers':['serprog','dummy'],'hardware_tested':False}
(ROOT/'evidence/flashrom-tool.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
