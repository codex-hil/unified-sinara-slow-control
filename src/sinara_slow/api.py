from .config import validate, validate_pair, attenuation_code
import copy
from .devices import compile_config, safe_operations
from .errors import ControlError


class SlowControl:
    def __init__(self, backend, config):
        self.backend = backend
        self.config = validate(config)
        validate_pair(self.config, backend.profile)
        self.state = 'unconfigured'
        self.applied = None
        self.readback_verified = False

    def _module(self, module):
        for item in self.config['modules']:
            if item['id'] == module:
                return item
        raise ControlError('NOT_FOUND', module)

    def discover(self):
        return {'source': 'declared', 'modules': [m['id'] for m in self.config['modules']],
                'physical_discovery': False}

    def identify(self, module):
        self._module(module)
        # Urukul reads status while simultaneously writing CFG=0: invasive,
        # not a read-only probe. The connection profile requires exclusive ownership.
        raw = int.from_bytes(self.backend.spi(module, 1, bytes(3)), 'big')
        revision = raw >> 16 & 0x7f
        if revision != 8:
            raise ControlError('IDENTITY_MISMATCH', f'{module}: CPLD protocol {revision}, expected 8')
        return {'type': 'urukul', 'cpld_protocol': revision, 'raw_status': raw,
                'board_revision': 'not_identifiable', 'simulated': self.backend.simulated}

    def read(self, module, parameter):
        if parameter == 'status':
            return self.identify(module)
        if parameter == 'attenuation':
            self._module(module)
            # Urukul shift-register read replaces the chain with zeros.
            # Restore immediately and never treat a failed re-latch as success.
            with self.backend.lock:
                data = self.backend.spi(module, 2, bytes(4))
                self.backend.spi(module, 2, data)
            word = int.from_bytes(data, 'big')
            return [(255 - (word >> (8*i) & 255)) / 8 for i in range(4)]
        raise ControlError('UNSUPPORTED', 'DDS reads are not implemented')

    def write(self, module, parameter, value):
        if parameter != 'attenuation':
            raise ControlError('UNSUPPORTED', 'only a complete four-channel attenuation vector is writable')
        self._module(module)
        if not isinstance(value, list) or len(value) != 4:
            raise ControlError('INVALID_CONFIG', 'four attenuation strings in channel order required')
        candidate = copy.deepcopy(self.config)
        target = next(m for m in candidate['modules'] if m['id'] == module)
        for channel in target['channels']:
            channel['attenuation'] = value[channel['id']]
        candidate = validate(candidate)
        with self.backend.lock:
            self.config = candidate
            return self.configure()

    def configure(self):
        with self.backend.lock:
            return self._configure()

    def _configure(self):
        self.state = 'configuring'
        self.applied = None
        self.readback_verified = False
        try:
            for op in compile_config(self.config):
                if op.kind == 'identify':
                    self.identify(op.module)
                else:
                    self.backend.spi(op.module, op.cs, op.data)
                    if op.cs == 2:
                        actual = self.read(op.module, 'attenuation')
                        expected = [(255-attenuation_code(c['attenuation']))/8
                                    for c in sorted(self._module(op.module)['channels'],key=lambda c:c['id'])]
                        if actual != expected:
                            raise ControlError('READBACK_MISMATCH', f'{op.module}: {actual} != {expected}')
        except Exception as exc:
            failures = self._safe_all()
            self.state = 'fault'
            if isinstance(exc, ControlError):
                raise ControlError(exc.code, f'{exc}; safe-state failures: {failures}', uncertain=exc.uncertain) from exc
            raise ControlError('HARDWARE', f'{exc}; safe-state failures: {failures}', uncertain=True) from exc
        self.readback_verified = True
        self.state = 'configured_registers_verified'
        self.applied = self.config
        return self.status()

    def _safe_all(self):
        failures = []
        for module in self.config['modules']:
            for op in safe_operations(module):
                try:
                    self.backend.spi(op.module, op.cs, op.data)
                except Exception as exc:
                    failures.append({'module': module['id'], 'error': str(exc)})
        return failures

    def reset(self):
        failures = self._safe_all()
        self.applied = None
        self.readback_verified = False
        self.state = 'fault' if failures else 'safe_commanded_unverified'
        return {'state': self.state, 'failures': failures, 'physical_reset': False}

    def status(self):
        return {'state': self.state, 'simulated': self.backend.simulated,
                'verified_readback': self.readback_verified, 'rf_state_measured': False, 'autonomous_safe_state': False}

    def health(self):
        return self.backend.health()
