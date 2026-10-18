"""Actual register transports; no automatic fallback to simulation."""
import socket
import struct
import threading

from .errors import ControlError

ABI_MAGIC = 0x53434731  # SCG1, distinct from upstream ID words
FRAME = struct.Struct('>2sBBIII')


class SerialWishbone:
    """Protocol implemented by firmware/stm-service, NOT upstream firmware.

    Caller owns serial port exclusivity. Timeout after a write has unknown outcome.
    A fresh session must be established after any protocol error.
    """
    def __init__(self, serial_port):
        self.serial = serial_port
        self.simulated = getattr(serial_port, 'simulated', False)
        self.lock = threading.Lock()
        self.sequence = 0
        self.failed = False

    def _exchange(self, command, address=0, value=0):
        with self.lock:
            if self.failed:
                raise ControlError('PROTOCOL', 'transport requires reopening')
            self.sequence = (self.sequence + 1) & 0xffffffff
            frame = FRAME.pack(b'SC', 1, command, self.sequence, address, value)
            try:
                if self.serial.write(frame) != len(frame):
                    raise ControlError('TRANSPORT', 'short write', uncertain=command == 2)
                self.serial.flush()
                reply = bytearray()
                while len(reply) < FRAME.size:
                    part = self.serial.read(FRAME.size - len(reply))
                    if not part:
                        raise ControlError('TIMEOUT', 'controller reply timed out', uncertain=command == 2)
                    reply.extend(part)
                magic, version, status, seq, addr, result = FRAME.unpack(reply)
                if (magic, version, seq, addr) != (b'SC', 1, self.sequence, address):
                    raise ControlError('PROTOCOL', 'reply does not match request', uncertain=command == 2)
                if status:
                    codes = {1: 'UNSUPPORTED', 2: 'INVALID_ADDRESS', 3: 'HARDWARE', 4: 'TIMEOUT'}
                    raise ControlError(codes.get(status, 'PROTOCOL'), 'controller rejected operation', uncertain=command == 2)
                return result
            except ControlError:
                self.failed = True
                raise
            except (OSError, TimeoutError) as exc:
                self.failed = True
                raise ControlError('TRANSPORT', str(exc), uncertain=command == 2) from exc

    def identify(self):
        return self._exchange(0)

    def read(self, address):
        return self._exchange(1, address)

    def write(self, address, value):
        self._exchange(2, address, value)

    def close(self):
        self.serial.close()


class LiteXRegisters:
    def __init__(self, client, abi_address):
        self.client, self.abi_address = client, abi_address
        self.simulated = getattr(client, 'simulated', False)

    def identify(self):
        return self.read(self.abi_address)

    def read(self, address):
        try:
            value = self.client.read(address)
            if type(value) is not int:
                raise ControlError('PROTOCOL', 'invalid CSR response')
            return value
        except (OSError, socket.timeout) as exc:
            raise ControlError('TRANSPORT', str(exc)) from exc

    def write(self, address, value):
        try:
            self.client.write(address, value)
        except (OSError, socket.timeout) as exc:
            raise ControlError('TRANSPORT', str(exc), uncertain=True) from exc

    def close(self):
        self.client.close()
