"""Host error semantics tests with a register fixture; not controller proof."""
import unittest
from sinara_slow.directions import Directions, BASE, APPLY, ACTIVE, STATUS, CLEAR
from sinara_slow.errors import ControlError

class Registers:
    def __init__(self):
        self.values = {160:0xAAAA, 161:0x5555, 162:4, STATUS:6}
        self.writes = []
        self.failure = None
    def read(self, address): return self.values.get(address, 0)
    def write(self, address, value):
        self.writes.append((address,value)); self.values[address] = value
        if address == APPLY:
            if self.failure is not None: self.values[STATUS] = self.failure
            else:
                for offset, target in enumerate(ACTIVE): self.values[target] = self.values[BASE+offset]
        if address == CLEAR: self.values[STATUS] &= ~24

class DirectionsTests(unittest.TestCase):
    def test_words_and_mask(self):
        r = Registers(); c = Directions(r)
        self.assertEqual(c.configure(0x123456789ABC), 0x123456789ABC)
        self.assertEqual(r.writes, [(BASE,0x1234),(BASE+1,0x5678),(BASE+2,0x9ABC),(APPLY,1)])
    def test_wrong_abi_and_bad_parameters_do_not_write(self):
        for mask in (-1,1<<48,True):
            r=Registers()
            with self.assertRaises(ControlError): Directions(r).configure(mask)
            self.assertEqual(r.writes,[])
        r=Registers();r.values[162]=3
        with self.assertRaises(ControlError): Directions(r).configure(0)
        self.assertEqual(r.writes,[])
    def test_busy_and_sticky_errors(self):
        for status in (1,2,14,22):
            r=Registers();r.values[STATUS]=status
            with self.assertRaises(ControlError): Directions(r).configure(0)
            self.assertEqual(r.writes,[])
        r.values[STATUS]=30;Directions(r).clear_errors()
        self.assertEqual(r.values[STATUS],6)
    def test_timeout_never_reapplies(self):
        r=Registers();r.failure=3
        ticks=iter([0,1])
        with self.assertRaises(ControlError) as caught:
            Directions(r,clock=lambda:next(ticks),sleep=lambda _:None).configure(1,timeout=0.01)
        self.assertEqual(caught.exception.code,'TIMEOUT')
        self.assertTrue(caught.exception.uncertain)
        self.assertEqual(sum(a==APPLY for a,v in r.writes),1)
    def test_rejected_apply(self):
        r=Registers();r.failure=14
        with self.assertRaises(ControlError) as caught: Directions(r).configure(0)
        self.assertEqual(caught.exception.code,'BUSY')

    def test_read_failure_after_apply_has_uncertain_outcome(self):
        class FailedRead(Registers):
            def read(self, address):
                if any(a == APPLY for a, _ in self.writes):
                    raise ControlError('TRANSPORT', 'connection lost')
                return super().read(address)
        r = FailedRead()
        with self.assertRaises(ControlError) as caught: Directions(r).configure(1)
        self.assertTrue(caught.exception.uncertain)
        self.assertEqual(sum(a == APPLY for a, _ in r.writes), 1)

    def test_lost_apply_reply_has_uncertain_outcome(self):
        class LostReply(Registers):
            def write(self, address, value):
                super().write(address, value)
                if address == APPLY:
                    raise ControlError('TRANSPORT', 'reply lost after commit')
        r = LostReply()
        with self.assertRaises(ControlError) as caught:
            Directions(r).configure(0x123456789ABC)
        self.assertEqual(caught.exception.code, 'TRANSPORT')
        self.assertTrue(caught.exception.uncertain)
        self.assertEqual([r.values[a] for a in ACTIVE], [0x1234, 0x5678, 0x9ABC])
        self.assertEqual(sum(a == APPLY for a, _ in r.writes), 1)
