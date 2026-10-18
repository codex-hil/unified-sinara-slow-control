#!/usr/bin/env python3
"""Prepare/check offline HIL manifest only. No programming or connections."""
from pathlib import Path
import hashlib
import json
import shutil
from datetime import datetime, timezone
ROOT = Path(__file__).resolve().parents[1]

def load(name):
    path = ROOT/'evidence'/name
    return json.loads(path.read_text()) if path.exists() else {'result':'NOT_RUN'}

def artifact(path, expected):
    p = (ROOT/path).resolve()
    if not p.is_relative_to(ROOT): raise ValueError('artifact outside project')
    actual = hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
    return {'path':path,'sha256':actual,'expected_sha256':expected,'verified':actual is not None and actual == expected}

baseline = load('stm-upstream-build-result.json')
probe = load('hil-probe-build.json')
candidate = load('integrated-stm-build.json')
artifacts = [artifact(a['path'],a['sha256']) for a in baseline.get('artifacts',[])]
if probe.get('result') == 'PASS': artifacts.append(artifact(probe['elf'],probe['elf_sha256']))
if candidate.get('result') == 'PASS': artifacts.append(artifact(candidate['bitstream'],candidate['bitstream_sha256']))
kit = ROOT/'work/hil-kit/2026-10-14'
kit.mkdir(parents=True, exist_ok=True)
for entry in artifacts:
    if entry['verified']:
        source = ROOT/entry['path']
        frozen = kit/(source.stem + '-' + entry['sha256'][:12] + source.suffix)
        if not frozen.exists(): shutil.copyfile(source, frozen)
        if hashlib.sha256(frozen.read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError('frozen artifact checksum mismatch')
        entry['frozen_path'] = str(frozen.relative_to(ROOT))
current = candidate.get('source_sha256',{})
source_match = bool(current) and all((ROOT/p).exists() and hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==v for p,v in current.items())
report = {'timestamp':datetime.now(timezone.utc).isoformat(), 'hardware_tested':False,
          'target':'STM System Board v1.1, excludes v1.0/v1.2 ESP32 variant',
          'artifacts':artifacts, 'candidate_build':candidate.get('result','NOT_RUN'),
          'candidate_sources_match':source_match,
          'programming_ready':False,
          'blockers':['Actual PCB/JTAG/SWD identities and inherited pin map not reviewed',
                      'Physical connection and hardware action authorization pending',
                      'No working bidirectional host register service deployed; probe is read-only RTT',
                      'Direction turnarounds and external SPI IO timing not verified'],
          'first_test':'Empty slots; volatile FPGA image only where supported; read-only RTT CSR IDs x8 with hil_probe after review',
          'next_test':'ABI4 boot zero mask; scope SCK/RCLK/OE, approved single-line direction/output test with passive fixture',
          'forbidden_by_this_manifest':['Automatic programming','Persistent FPGA/STM flash write','Unknown attached module output drive'],
          'kasli':load('integrated-kasli-build.json')}
(kit/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
(ROOT/'evidence/hil-manifest.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'manifest':'evidence/hil-manifest.json','artifacts_verified':all(a['verified'] for a in artifacts),
                  'candidate_build':report['candidate_build'],'programming_ready':False},indent=2))
if not artifacts or not all(a['verified'] for a in artifacts): raise SystemExit(1)
