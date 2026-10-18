"""Host client for word-addressed 16-bit slow fabric ABI v4.

Caller provides an actual controller register transport and exclusive access.
This is not the SCG1 gateway ABI, and not a LiteX byte-address conversion.
No retry after apply; timeout means the hardware outcome is unknown.
"""
import math
import threading
import time
from .errors import ControlError

BASE = 0x800
REQUESTED = (BASE, BASE + 1, BASE + 2)
APPLY = BASE + 3
ACTIVE = (BASE + 4, BASE + 5, BASE + 6)
STATUS = BASE + 7
CLEAR = BASE + 8


class Directions:
    def __init__(self, word_registers, *, clock=time.monotonic, sleep=time.sleep):
        self.registers = word_registers
        self.clock, self.sleep = clock, sleep
        self.lock = threading.Lock()

    def _read(self, address):
        value = self.registers.read(address)
        if type(value) is not int or not 0 <= value <= 0xFFFF:
            raise ControlError('PROTOCOL', 'invalid 16-bit CSR response')
        return value

    def _identify(self):
        if tuple(self._read(a) for a in (160, 161, 162)) != (0xAAAA, 0x5555, 4):
            raise ControlError('UNSUPPORTED', 'requires slow fabric ABI v4')

    def _active(self):
        value = 0
        for address in ACTIVE:
            value = (value << 16) | self._read(address)
        return value

    def configure(self, mask, *, timeout=0.1):
        if type(mask) is not int or not 0 <= mask < (1 << 48):
            raise ControlError('INVALID_CONFIG', 'direction mask must be a 48-bit integer')
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
            raise ControlError('INVALID_CONFIG', 'timeout must be finite and positive')
        with self.lock:
            self._identify()
            status = self._read(STATUS)
            if status & 24:
                raise ControlError('HARDWARE', 'uncleared rejected or blocked operation')
            if status & 1 or not status & 4 or not status & 2:
                raise ControlError('BUSY', 'direction controller is not initialized and ready')
            for address, shift in zip(REQUESTED, (32, 16, 0)):
                self.registers.write(address, (mask >> shift) & 0xFFFF)
            try:
                self.registers.write(APPLY, 1)
            except ControlError as error:
                # The write may have reached hardware before its reply failed.
                # Do not rely on transports marking this boundary themselves.
                error.uncertain = True
                raise
            deadline = self.clock() + timeout
            while True:
                try:
                    status = self._read(STATUS)
                except ControlError as error:
                    error.uncertain = True
                    raise
                if status & 8:
                    raise ControlError('BUSY', 'direction apply rejected')
                if status & 16:
                    raise ControlError('HARDWARE', 'concurrent slot write blocked', uncertain=True)
                if not status & 1 and status & 2:
                    try:
                        active = self._active()
                    except ControlError as error:
                        error.uncertain = True
                        raise
                    if active != mask:
                        raise ControlError('HARDWARE', 'active mask differs from requested', uncertain=True)
                    return active
                if self.clock() >= deadline:
                    raise ControlError('TIMEOUT', 'direction update timed out; do not retry automatically', uncertain=True)
                self.sleep(min(0.001, max(0, deadline - self.clock())))

    def clear_errors(self):
        with self.lock:
            self._identify()
            self.registers.write(CLEAR, 1)
