"""Small protocol definitions derived from ARTIQ urukul.py, not RTIO drivers.

Protocol v8 only. CS addresses are decoded by the Urukul CPLD.
No clock-source/DDS initialization, RF enable or deterministic timing.
"""
from dataclasses import dataclass
from .config import attenuation_code


@dataclass(frozen=True)
class Operation:
    module: str
    kind: str
    cs: int
    data: bytes
    expected_protocol: int | None = None


def safe_operations(module):
    return [Operation(module['id'], 'spi', 1, bytes(3)),
            Operation(module['id'], 'spi', 2, bytes([3]) * 4)]


def compile_config(config):
    operations = []
    # Disable every module before configuring any attenuation.
    for module in config['modules']:
        operations.append(safe_operations(module)[0])
    for module in config['modules']:
        operations.append(Operation(module['id'], 'identify', 1, bytes(3), 8))
        word = sum(attenuation_code(c['attenuation']) << (8 * c['id'])
                   for c in module['channels'])
        operations.append(Operation(module['id'], 'spi', 2, word.to_bytes(4, 'big')))
    return operations
