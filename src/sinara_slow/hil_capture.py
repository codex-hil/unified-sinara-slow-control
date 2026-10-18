"""Offline validation of a single hil_probe RTT run, not hardware attestation."""
import re

ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')
RECORD = re.compile(r'round (\d+) adr (\d+) value ([0-9a-fA-F]{4})')
START = 'read-only ECP5, no module initialization'
END = 'complete; idling, no CSR writes'


def validate_probe_capture(text, expected_abi):
    if type(expected_abi) is not int or expected_abi not in (3, 4):
        raise ValueError('expected ABI must be 3 or 4')
    messages = []
    for line in ANSI.sub('', text).splitlines():
        if 'HIL_PROBE:' not in line:
            continue
        if line.count('HIL_PROBE:') != 1:
            raise ValueError('ambiguous probe message')
        messages.append(line.split('HIL_PROBE:', 1)[1].strip())
    if len(messages) != 27:
        raise ValueError('expected one complete run: start, 24 reads, PASS and completion')
    if messages[0] != START or messages[-1] != END:
        raise ValueError('missing or misplaced start/completion')
    if messages[-2] != f'ID_STABILITY PASS ABI {expected_abi}':
        raise ValueError('missing success marker or wrong ABI')
    values = {160: 0xAAAA, 161: 0x5555, 162: expected_abi}
    records = []
    for index, message in enumerate(messages[1:25]):
        match = RECORD.fullmatch(message)
        if match is None:
            raise ValueError('malformed read or probe error')
        round_number, address = map(int, match.group(1, 2))
        value = int(match.group(3), 16)
        if (round_number, address) != (index // 3, 160 + index % 3):
            raise ValueError('missing, duplicated or out-of-order read')
        if value != values[address]:
            raise ValueError(f'ID mismatch in round {round_number}, address {address}')
        records.append({'round': round_number, 'address': address, 'value': value})
    return {'capture_check': 'PASS', 'abi': expected_abi, 'rounds': 8,
            'records': records, 'hardware_validated': False,
            'limitations': 'Log content only. Board identity, image hashes, capture origin and physical signals must be recorded separately.'}
