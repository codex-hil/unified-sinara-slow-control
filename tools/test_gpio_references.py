"""ESPHome GPIO-coordinate validation; no hardware or runtime connections."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import yaml

ROOT = Path(__file__).resolve().parents[1]
results = []
for module in ('sampler', 'zotino'):
    for board in ('stm', 'kasli'):
        path = ROOT / f'integrations/esphome/examples/{module}-{board}-simulation.yaml'
        source = yaml.safe_load(path.read_text())
        for case in ('valid', 'cross_slot', 'out_of_range', 'overlap', 'integer'):
            config = copy.deepcopy(source)
            pins = config[f'sinara_{module}']['pinmux']
            key = next(iter(pins))
            if case == 'cross_slot':
                pins[key]['slot'] = 2
            elif case == 'out_of_range':
                pins[key]['line'] = 16
            elif case == 'overlap':
                pins[key] = copy.deepcopy(list(pins.values())[1])
            elif case == 'integer':
                pins[key] = 0
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', dir=path.parent) as f:
                yaml.safe_dump(config, f)
                f.flush()
                run = subprocess.run([sys.executable, '-m', 'esphome', 'config', f.name],
                                     capture_output=True, text=True, timeout=30)
            passed = (run.returncode == 0) == (case == 'valid')
            results.append(dict(module=module, controller=board, case=case, passed=passed))
            if not passed:
                print(run.stdout, run.stderr)
(ROOT / 'evidence/gpio-reference-validation.json').write_text(
    json.dumps(dict(hardware_tested=False, results=results), indent=2) + '\n')
print(f'{sum(r["passed"] for r in results)}/{len(results)} validation checks passed')
sys.exit(not all(r['passed'] for r in results))
