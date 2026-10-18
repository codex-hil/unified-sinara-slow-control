#!/usr/bin/env python3
"""Check saved RTT text only; never connects to a debugger or board."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from sinara_slow.hil_capture import validate_probe_capture


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('--expected-abi', type=int, choices=(3, 4), required=True)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = {'capture_check': 'FAIL', 'hardware_validated': False}
    try:
        data = args.capture.read_bytes()
        report['capture_sha256'] = hashlib.sha256(data).hexdigest()
        report.update(validate_probe_capture(data.decode('utf-8'), args.expected_abi))
    except (OSError, ValueError) as error:
        report['error'] = str(error)
    output = json.dumps(report, indent=2) + '\n'
    if args.report:
        args.report.write_text(output)
    print(output, end='')
    return 0 if report['capture_check'] == 'PASS' else 1

if __name__ == '__main__':
    raise SystemExit(main())
