"""Reproduce isolated source checkouts and pinned schematic PDFs on chosen disk."""
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
manifest=json.loads((ROOT/'evidence/source-commits.json').read_text())
for name,info in manifest.items():
    destination=ROOT/'references'/name
    if destination.exists():
        actual=subprocess.check_output(['git','-C',str(destination),'rev-parse','HEAD'],text=True).strip()
        if actual!=info['commit']:
            raise RuntimeError(f'{name}: existing checkout differs; leaving it untouched')
        continue
    destination.parent.mkdir(exist_ok=True)
    subprocess.run(['git','init',str(destination)],check=True)
    subprocess.run(['git','-C',str(destination),'remote','add','origin',info['origin']],check=True)
    subprocess.run(['git','-C',str(destination),'fetch','--depth=1','origin',info['commit']],check=True)
    if info['checkout']=='sparse':
        # Hardware designs are large; root metadata is enough alongside release PDFs.
        patterns=['/*.md']
        if name=='misoc':patterns+=['/misoc/']
        subprocess.run(['git','-C',str(destination),'config','core.sparseCheckout','true'],check=True)
        (destination/'.git/info/sparse-checkout').write_text('\n'.join(patterns)+'\n')
    subprocess.run(['git','-C',str(destination),'checkout','--detach',info['commit']],check=True)
# Supplemental branch evidence used by source-level regression check.
extra={'stm-gateware':('46f14f81d6a29c664f72d8c7373f4d346b43970d',
                      ['stm_sys_board_hdl.py','spi2wb.py','stm_sys_board.py'])}
for repo,(commit,names) in extra.items():
    destination=ROOT/'references'/repo
    subprocess.run(['git','-C',str(destination),'fetch','--depth=1','origin',commit],check=True)
    for name in names:
        text=subprocess.check_output(['git','-C',str(destination),'show',commit+':'+name],text=True)
        (ROOT/'evidence'/('tpr-'+name)).write_text(text)
for name,info in json.loads((ROOT/'evidence/pdf-sources.json').read_text()).items():
    destination=ROOT/'evidence'/name
    if not destination.exists():urllib.request.urlretrieve(info['url'],destination)
    if hashlib.sha256(destination.read_bytes()).hexdigest()!=info['sha256']:
        raise RuntimeError(f'{name}: PDF hash mismatch')
print('Pinned references and PDF hashes verified')
