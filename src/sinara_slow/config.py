import copy
import json
import re
import math
from decimal import Decimal
from importlib.resources import files

import jsonschema
import yaml

from .errors import ValidationError
from .pinmaps import spi_mapping


class StrictLoader(yaml.SafeLoader):
    pass


def _mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            if key in result:
                raise ValidationError(f'duplicate YAML key: {key}')
            result[key] = loader.construct_object(value_node, deep=deep)
        except TypeError as exc:
            raise ValidationError('YAML mapping keys must be scalar') from exc
    return result


StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def load(path, kind='config'):
    try:
        with open(path) as stream:
            document = yaml.load(stream, Loader=StrictLoader)
        return validate(document, kind)
    except (yaml.YAMLError, OSError, RecursionError) as exc:
        raise ValidationError(str(exc)) from exc


def attenuation_code(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]+(?:\.[0-9]+)? dB', value):
        raise ValidationError('attenuation requires an explicit dB unit')
    db = Decimal(value[:-3])
    # Demonstrator restricts physical steps to 0.5 dB (HMC542B in audited schematic).
    if not 0 <= db <= Decimal('31.5') or db % Decimal('0.5'):
        raise ValidationError('attenuation must be 0..31.5 dB in 0.5 dB steps')
    return 255 - int(db * 8)


def validate(document, kind='config'):
    schema = json.loads(files('sinara_slow').joinpath(f'schemas/{kind}-v1.schema.json').read_text())
    try:
        jsonschema.Draft202012Validator(schema).validate(document)
    except jsonschema.ValidationError as exc:
        raise ValidationError(f'{list(exc.path)}: {exc.message}') from exc
    if kind == 'config':
        modules = document['modules']
        for key in ('id', 'slot'):
            if len({m[key] for m in modules}) != len(modules):
                raise ValidationError(f'duplicate module {key}')
        for m in modules:
            if {c['id'] for c in m['channels']} != set(range(4)):
                raise ValidationError('all four distinct channels must be specified')
            for c in m['channels']:
                attenuation_code(c['attenuation'])
    else:
        if not math.isfinite(document['timeout_s']):
            raise ValidationError('timeout must be finite')
        expected = {'stm_sys_board': 'serial_wb', 'kasli': 'litex_remote'}
        if document['transport'] != expected[document['controller']]:
            raise ValidationError('controller/transport mismatch')
        endpoints = set()
        for b in document['bindings'].values():
            if 'pinmux' in b:
                mapping = spi_mapping(b['pinmux'])
                if any(b[k] != v for k, v in mapping.items()):
                    raise ValidationError('SPI pins do not match declared pinmux profile')
            pins = [b['mosi'], b['miso'], b['clk'], *b['cs']]
            if len(set(pins)) != 6:
                raise ValidationError('SPI pins overlap')
            if b['endpoint'] in endpoints:
                raise ValidationError('endpoint shared by modules')
            endpoints.add(b['endpoint'])
            if document['controller'] == 'stm_sys_board' and b['endpoint'] > 7:
                raise ValidationError('STM has eight slots')
            for name in ('output', 'input', 'oe'):
                if f"gpio{b['endpoint']}_{name}" not in document['csr_map']:
                    raise ValidationError('missing explicit CSR address')
        if document['controller'] == 'stm_sys_board':
            for b in document['bindings'].values():
                for offset, name in enumerate(('output','input','oe')):
                    if document['csr_map'][f"gpio{b['endpoint']}_{name}"] != b['endpoint']*20+offset:
                        raise ValidationError('STM gateway requires the reviewed 20-word slot map')
        elif any(address % 4 for address in document['csr_map'].values()):
            raise ValidationError('Kasli CSR addresses must be 32-bit aligned')
        addresses = list(document['csr_map'].values())
        if len(addresses) != len(set(addresses)):
            raise ValidationError('CSR addresses overlap')
    return copy.deepcopy(document)


def validate_pair(config, connection):
    validate(config)
    validate(connection, 'connection')
    if set(connection['bindings']) != {m['id'] for m in config['modules']}:
        raise ValidationError('connection bindings must match module IDs exactly')
