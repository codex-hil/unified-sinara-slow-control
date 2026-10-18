import threading
import time
from .errors import ControlError, ValidationError
from .transports import ABI_MAGIC, SerialWishbone, LiteXRegisters
from .config import validate


class GPIOBackend:
    """Mode-0 SPI through actual controller GPIO registers.

    Slow host bit-banging intentionally favors reuse and inspectability.
    Not suited to DDS timing, coherent update or active experiments.
    Explicit exclusive GPIO ownership and pin map are mandatory.
    """
    simulated = False

    def __init__(self, registers, profile):
        validate(profile, 'connection')
        self.regs, self.profile = registers, profile
        self.simulated = getattr(registers, 'simulated', False)
        self.lock = threading.RLock()
        self.ready = set()
        if registers.identify() != ABI_MAGIC:
            raise ControlError('INCOMPATIBLE_ABI', 'expected sinara-gpio-v1; upstream STM gateware is incompatible')

    def _addresses(self, module):
        try:
            binding = self.profile['bindings'][module]
        except KeyError as exc:
            raise ValidationError('unknown module binding') from exc
        names = self.profile['csr_map']
        return binding, {n: names[f"gpio{binding['endpoint']}_{n}"] for n in ('output', 'input', 'oe')}

    def spi(self, module, cs, data):
        if type(cs) is not int or not 1 <= cs <= 7 or not isinstance(data, bytes) or len(data) not in (3, 4):
            raise ValidationError('SPI operation outside demonstrator limits')
        with self.lock:
            b, a = self._addresses(module)
            deadline = time.monotonic() + self.profile['timeout_s']
            def check():
                if time.monotonic() > deadline:
                    raise ControlError('TIMEOUT', 'SPI deadline exceeded', uncertain=True)
            output_mask = sum(1 << p for p in (b['mosi'], b['clk'], *b['cs']))
            # Preserve unrelated pins. Initial activation drives all SPI outputs low.
            value = self.regs.read(a['output']) & ~output_mask
            self.regs.write(a['output'], value)
            if module not in self.ready:
                self.regs.write(a['oe'], (self.regs.read(a['oe']) & ~(1 << b['miso'])) | output_mask)
                self.ready.add(module)
            base = value
            for i, pin in enumerate(b['cs']):
                value |= ((cs >> i) & 1) << pin
            received = bytearray()
            try:
                check()
                self.regs.write(a['output'], value)
                for byte in data:
                    rx = 0
                    for bit in range(7, -1, -1):
                        check()
                        value = (value & ~(1 << b['mosi'])) | ((byte >> bit & 1) << b['mosi'])
                        self.regs.write(a['output'], value)
                        self.regs.write(a['output'], value | (1 << b['clk']))
                        rx = (rx << 1) | ((self.regs.read(a['input']) >> b['miso']) & 1)
                        self.regs.write(a['output'], value)
                    received.append(rx)
                check()
                return bytes(received)
            finally:
                # Best effort: never replay an uncertain write.
                self.regs.write(a['output'], base)

    def health(self):
        return {'abi_ok': self.regs.identify() == ABI_MAGIC, 'simulated': self.simulated,
                'autonomous_safe_state': False}

    def close(self):
        self.regs.close()


class STMBackend(GPIOBackend):
    def __init__(self, registers, profile):
        if profile['controller'] != 'stm_sys_board':
            raise ValidationError('wrong controller for STM backend')
        super().__init__(registers, profile)


class KasliBackend(GPIOBackend):
    def __init__(self, registers, profile):
        if profile['controller'] != 'kasli':
            raise ValidationError('wrong controller for Kasli backend')
        super().__init__(registers, profile)


def connect(profile):
    validate(profile, 'connection')
    if profile['use'] != 'hardware':
        raise ValidationError('simulation connection profile cannot be used for hardware operations')
    if profile['controller'] == 'stm_sys_board':
        try:
            import serial
            port = serial.Serial(profile['address'], 115200, timeout=profile['timeout_s'],
                                 write_timeout=profile['timeout_s'], exclusive=True)
        except ImportError as exc:
            raise ControlError('UNSUPPORTED', 'pyserial dependency unavailable') from exc
        except OSError as exc:
            raise ControlError('TRANSPORT', str(exc)) from exc
        registers = SerialWishbone(port)
        factory = STMBackend
    else:
        try:
            from litex import RemoteClient
        except ImportError as exc:
            raise ControlError('UNSUPPORTED', 'LiteX dependency unavailable') from exc
        if 'abi' not in profile['csr_map']:
            raise ValidationError('Kasli needs explicit ABI CSR address')
        client = RemoteClient(host=profile['address'], port=profile.get('port', 1234),
                              csr_csv=None, timeout=profile['timeout_s'], raise_on_timeout=True)
        try:
            client.open()
            client.socket.settimeout(profile['timeout_s'])
        except OSError as exc:
            raise ControlError('TRANSPORT', str(exc)) from exc
        registers = LiteXRegisters(client, profile['csr_map']['abi'])
        factory = KasliBackend
    try:
        return factory(registers, profile)
    except Exception:
        registers.close()
        raise
