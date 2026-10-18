"""Explicit electrical transaction simulation; never used by connect()."""
from .errors import ControlError
from .transports import ABI_MAGIC, FRAME


class GPIORegisterSimulator:
    simulated = True
    def __init__(self, profile):
        self.profile = profile
        self.values = {}
        self.devices = {}
        self.transactions = []
        self.fail_after = None
        self.writes = 0
        for module, binding in profile['bindings'].items():
            self.devices[module] = {'binding': binding, 'bits': [], 'rx_bit': 0,
                                    'cs': 0, 'cfg': None, 'attenuation': None}

    def identify(self):
        return ABI_MAGIC

    def read(self, address):
        for device in self.devices.values():
            b = device['binding']
            if address == self.profile['csr_map'][f"gpio{b['endpoint']}_input"]:
                return device['rx_bit'] << b['miso']
        return self.values.get(address, 0)

    def write(self, address, value):
        self.writes += 1
        if self.fail_after is not None and self.writes >= self.fail_after:
            raise ControlError('TIMEOUT', 'injected controller failure', uncertain=True)
        previous = self.values.get(address, 0)
        self.values[address] = value
        for module, device in self.devices.items():
            b = device['binding']
            if address != self.profile['csr_map'][f"gpio{b['endpoint']}_output"]:
                continue
            cs = sum(((value >> pin) & 1) << i for i, pin in enumerate(b['cs']))
            old_cs = device['cs']
            if old_cs and cs != old_cs:
                bits = device['bits']
                if len(bits) % 8:
                    raise AssertionError('partial SPI transaction')
                data = bytes(sum(bits[j + k] << (7-k) for k in range(8)) for j in range(0, len(bits), 8))
                self.transactions.append((module, old_cs, data))
                if old_cs == 1 and len(data) == 3:
                    device['cfg'] = int.from_bytes(data, 'big')
                elif old_cs == 2 and len(data) == 4:
                    device['attenuation'] = data
                device['bits'] = []
            device['cs'] = cs
            if cs and not (previous >> b['clk'] & 1) and (value >> b['clk'] & 1):
                n = len(device['bits'])
                status = 8 << 16
                if cs == 1 and n < 24:
                    device['rx_bit'] = status >> (23-n) & 1
                elif cs == 2 and n < 32:
                    current = int.from_bytes(device['attenuation'] or bytes(4), 'big')
                    device['rx_bit'] = current >> (31-n) & 1
                else:
                    device['rx_bit'] = 0
                device['bits'].append(value >> b['mosi'] & 1)

    def close(self):
        pass


class GatewaySerialSimulator:
    """Serial framing simulator, deliberately fragments replies."""
    simulated = True

    def __init__(self, registers):
        self.registers, self.pending = registers, bytearray()

    def write(self, frame):
        magic, version, op, seq, addr, value = FRAME.unpack(frame)
        assert (magic, version) == (b'SC', 1)
        if op == 0:
            result = self.registers.identify()
        elif op == 1:
            result = self.registers.read(addr)
        else:
            self.registers.write(addr, value)
            result = 0
        self.pending.extend(FRAME.pack(b'SC', 1, 0, seq, addr, result))
        return len(frame)

    def flush(self):
        pass

    def read(self, count):
        count = min(count, 3)
        part = bytes(self.pending[:count])
        del self.pending[:count]
        return part

    def close(self):
        pass
