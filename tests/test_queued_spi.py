"""Actual MiSoC bit engine/queue simulations; never physical hardware."""
import sys
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
for p in ['gateware','work/upstream-stm/deps/misoc','references/misoc','references/migen','references/litex']:
    sys.path.insert(0,str(ROOT/p))
from migen.sim import run_simulation
from queued_spi import QueuedSPI,command,WRITE,READ,XFER,DELAY,WAIT_TRIGGER,PULSE
from control_signals import ControlSignals
from fabric_pinmux import validate_routes
from queued_fabric import QueuedFabric,MAGIC

class QueuedTests(unittest.TestCase):
    def test_complete_frame_and_cs_all_modes(self):
        for mode in range(4):
            d=QueuedSPI(depth=8)
            def bench():
                yield d.enable.eq(1);yield d.cpol.eq(mode>>1);yield d.cpha.eq(mode&1)
                yield d.miso.eq(1)
                def push(word):
                    yield d.tx_data.eq(word);yield d.tx_write.eq(1);yield
                    yield d.tx_write.eq(0);yield
                yield from push(command(XFER,selector=2,length=5,tag=42))
                yield from push(0x78563412)
                for _ in range(20):
                    self.assertFalse((yield d.selected));yield
                yield from push(0x9a)
                cs_edges=0;oldcs=0;clock_edges=0;oldclk=mode>>1;bits=[];times=[]
                for tick in range(600):
                    cs=(yield d.selected);clk=(yield d.clk)
                    cs_edges+=cs!=oldcs
                    if cs and clk!=oldclk:
                        clock_edges+=1
                        if (clk==(mode>>1))==bool(mode&1):
                            bits.append((yield d.mosi));times.append(tick)
                    oldcs=cs;oldclk=clk
                    if cs:self.assertEqual((yield d.select_out),11)
                    if (yield d.completed):break
                    yield
                else:self.fail('queue timeout')
                self.assertEqual(cs_edges,2);self.assertEqual(clock_edges,80)
                expected=[(byte>>bit)&1 for byte in [0x12,0x34,0x56,0x78,0x9a] for bit in range(7,-1,-1)]
                self.assertEqual(bits,expected)
                self.assertTrue(all(b-a==6 for a,b in zip(times,times[1:])),times)
                self.assertEqual((yield d.last_tag),42)
                self.assertEqual((yield d.rx_level),5)
                for i in range(5):
                    value=(yield d.rx_data)
                    self.assertEqual(value&255,255);self.assertEqual((value>>8)&255,42)
                    self.assertEqual((value>>16)&1,i==4)
                    yield d.rx_read.eq(1);yield
                    yield d.rx_read.eq(0);yield
            run_simulation(d,bench())
    def test_abort_requires_flush_and_no_replay(self):
        d=QueuedSPI(depth=8,mode='parallel',selects=4,address_setup=3)
        def bench():
            yield d.enable.eq(1)
            for w in [command(WRITE,selector=9,length=1),0xa5]:
                yield d.tx_data.eq(w);yield d.tx_write.eq(1);yield
                yield d.tx_write.eq(0);yield
            for _ in range(50):
                if (yield d.selected):break
                self.assertEqual((yield d.enable_n),1);yield
            self.assertEqual((yield d.select_out),9)
            yield d.permit.eq(0);yield;yield
            self.assertFalse((yield d.selected));self.assertEqual((yield d.fault),2)
            yield d.permit.eq(1)
            for _ in range(30):self.assertFalse((yield d.selected));yield
            yield d.flush.eq(1);yield;yield d.flush.eq(0);yield;yield
            self.assertEqual((yield d.fault),0);self.assertEqual((yield d.tx_level),0)
        run_simulation(d,bench())
    def test_pin_constraints(self):
        for route in [dict(clk=8),dict(selects=[3,4,5,8]),dict(trigger=0),dict(mode='parallel',selects=[3,4,5,7])]:
            with self.assertRaises(ValueError):validate_routes(route)
        validate_routes(dict(trigger=15,ready=14,interlock=13))
    def test_interlock_and_barrier(self):
        d=ControlSignals(8)
        def bench():
            yield d.interlock_mask.eq(3);yield d.raw_good.eq(1)
            for _ in range(5):yield
            self.assertFalse((yield d.permit));self.assertTrue((yield d.tripped))
            yield d.raw_good.eq(3)
            for _ in range(5):yield
            self.assertFalse((yield d.permit))
            yield d.clear.eq(1);yield;yield d.clear.eq(0);yield
            self.assertTrue((yield d.permit))
            yield d.trigger_mask.eq(3);yield d.slot_waiting.eq(1);yield
            yield d.software_trigger.eq(1);yield;yield d.software_trigger.eq(0);yield
            self.assertTrue((yield d.trigger_rejected));self.assertFalse((yield d.trigger))
            yield d.slot_waiting.eq(3);yield d.width.eq(3);yield;yield
            yield d.software_trigger.eq(1);yield;yield d.software_trigger.eq(0)
            pulses=0
            for _ in range(8):
                pulses+=(yield d.trigger);yield
            self.assertEqual(pulses,3)
            yield d.raw_good.eq(1)
            for _ in range(5):yield
            self.assertFalse((yield d.permit))
        run_simulation(d,bench())
    def test_wishbone_once_and_slot_isolation(self):
        d=QueuedFabric(depth=8,direction_half_period=1)
        def bench():
            b=d.bus
            def access(word,value=None,hold=0,sel=15):
                yield b.adr.eq(word);yield b.dat_w.eq(0 if value is None else value)
                yield b.we.eq(value is not None);yield b.sel.eq(sel);yield b.cyc.eq(1);yield b.stb.eq(1)
                for _ in range(8):
                    yield
                    if (yield b.ack):break
                else:self.fail('Wishbone timeout')
                result=(yield b.dat_r);error=(yield b.err)
                for _ in range(hold):yield
                yield b.stb.eq(0);yield b.cyc.eq(0);yield;yield
                return result,error
            v,e=yield from access(0);self.assertEqual(v,MAGIC);self.assertFalse(e)
            v,e=yield from access(64+2,command(WRITE,0,1),hold=5);self.assertFalse(e)
            self.assertEqual((yield d.spi[0].tx_level),1)
            self.assertEqual((yield d.spi[1].tx_level),0)
            _,e=yield from access(64+2,0xaa,sel=1);self.assertTrue(e)
            self.assertEqual((yield d.spi[0].tx_level),1)
            _,e=yield from access(64+11,1);self.assertFalse(e)
            self.assertEqual((yield d.spi[0].tx_level),0)
        run_simulation(d,bench())

    def test_sessions_pulses_and_invalid_commands(self):
        from queued_spi import CS_ASSERT,CS_RELEASE
        d=QueuedSPI(depth=8)
        def bench():
            yield d.enable.eq(1);yield d.miso.eq(1)
            def push(word):
                yield d.tx_data.eq(word);yield d.tx_write.eq(1);yield
                yield d.tx_write.eq(0);yield
            def done(n):
                for _ in range(200):
                    if (yield d.completed)==n:return
                    yield
                self.fail('session timeout')
            yield from push(command(CS_ASSERT,selector=1,tag=1))
            yield from done(1)
            self.assertTrue((yield d.session));self.assertTrue((yield d.selected))
            for _ in range(10):self.assertTrue((yield d.selected));yield
            yield from push(command(WRITE,selector=1,length=1,tag=2));yield from push(0xa5)
            yield from done(2);self.assertTrue((yield d.selected))
            yield from push(command(CS_RELEASE,tag=3));yield from done(3)
            self.assertFalse((yield d.selected));self.assertFalse((yield d.session))
            yield from push(command(PULSE,length=3,tag=4))
            count=0
            for _ in range(15):
                count+=(yield d.pulse);yield
            self.assertEqual(count,3)
            yield from push(0xf0000000)
            for _ in range(10):yield
            self.assertEqual((yield d.fault),1);self.assertFalse((yield d.selected))
        run_simulation(d,bench())

    def test_readback_capture_before_fifo_pop(self):
        d=QueuedFabric(depth=8,direction_half_period=1)
        def bench():
            b=d.bus
            def access(word,value=None):
                yield b.adr.eq(word);yield b.dat_w.eq(value or 0);yield b.we.eq(value is not None)
                yield b.sel.eq(15);yield b.cyc.eq(1);yield b.stb.eq(1)
                for _ in range(10):
                    yield
                    if (yield b.ack):break
                else:self.fail('no ack')
                self.assertFalse((yield b.err));value=(yield b.dat_r)
                yield b.cyc.eq(0);yield b.stb.eq(0);yield;yield
                return value
            for _ in range(15):yield
            yield d.inputs[0].eq(4)
            yield from access(64,1)
            yield from access(66,command(READ,length=2,tag=17))
            for _ in range(200):
                if (yield d.spi[0].completed):break
                yield
            else:self.fail('read timeout')
            first=yield from access(67);last=yield from access(67)
            self.assertEqual(first,0x11ff);self.assertEqual(last,0x111ff)
        run_simulation(d,bench())

    def test_session_watchdog_and_ready_input_mask(self):
        from queued_spi import CS_ASSERT
        d=QueuedSPI(depth=8,session_timeout=12)
        def bench():
            yield d.enable.eq(1);yield d.tx_data.eq(command(CS_ASSERT,0));yield d.tx_write.eq(1);yield
            yield d.tx_write.eq(0)
            for _ in range(40):yield
            self.assertEqual((yield d.fault),3);self.assertFalse((yield d.selected))
        run_simulation(d,bench())
        s=ControlSignals(2)
        def ready_bench():
            yield s.trigger_mask.eq(3);yield s.slot_waiting.eq(3);yield s.ready_mask.eq(2)
            for _ in range(5):yield
            self.assertFalse((yield s.ready))
            yield s.raw_ready.eq(2)
            for _ in range(5):yield
            self.assertTrue((yield s.ready))
        run_simulation(s,ready_bench())

    def test_two_slot_barrier_and_simultaneous_trigger_outputs(self):
        routes=[dict(clk=0,mosi=1,miso=2,selects=[3,4,5,6],mode='direct',trigger=15,interlock=13) for _ in range(8)]
        d=QueuedFabric(routes=routes,depth=8,direction_half_period=1)
        def bench():
            b=d.bus
            def write(a,v):
                yield b.adr.eq(a);yield b.dat_w.eq(v);yield b.we.eq(1);yield b.sel.eq(15);yield b.cyc.eq(1);yield b.stb.eq(1)
                for _ in range(10):
                    yield
                    if (yield b.ack):break
                self.assertFalse((yield b.err))
                yield b.stb.eq(0);yield b.cyc.eq(0);yield;yield
            for i in [0,1]:yield d.inputs[i].eq(1<<13)
            for _ in range(15):yield
            yield from write(4,3);yield from write(6,3);yield from write(7,3);yield from write(8,4)
            for _ in range(12):yield
            yield from write(64+64+5,10)
            for i,data in [(0,0xa5),(1,0x5a)]:
                for w in [3<<16|i,command(WRITE,selector=0,length=1,tag=i+1),data,command(WAIT_TRIGGER,tag=9)]:
                    yield from write(16,w)
                yield from write(64+i*64,1)
            for _ in range(500):
                if (yield d.ready):break
                yield
            else:self.fail('barrier never ready')
            self.assertEqual((yield d.spi[0].completed),1);self.assertEqual((yield d.spi[1].completed),1)
            yield d.trigger_external.eq(1)
            pulses=[]
            for _ in range(12):
                a=((yield d.outputs[0])>>15)&1;c=((yield d.outputs[1])>>15)&1
                self.assertEqual(a,c);pulses.append(a)
                yield
            self.assertEqual(sum(pulses),3)
            for _ in range(8):yield
            self.assertEqual((yield d.spi[0].completed),2);self.assertEqual((yield d.spi[1].completed),2)
            self.assertEqual((yield d.safety.trigger_count),1)
        run_simulation(d,bench())

    def test_parallel_address_hold_and_encoded_idle(self):
        from queued_spi import CS_ASSERT,CS_RELEASE
        for mode,selects,selector in [('parallel',4,15),('encoded',3,5)]:
            d=QueuedSPI(depth=8,mode=mode,selects=selects)
            def bench():
                yield d.enable.eq(1)
                def push(w):
                    yield d.tx_data.eq(w);yield d.tx_write.eq(1);yield
                    yield d.tx_write.eq(0);yield
                yield from push(command(CS_ASSERT,selector))
                for _ in range(15):yield
                self.assertTrue((yield d.selected));self.assertEqual((yield d.select_out),selector)
                yield from push(command(CS_RELEASE))
                for _ in range(15):yield
                self.assertFalse((yield d.selected))
                self.assertEqual((yield d.select_out),selector if mode=='parallel' else 0)
            run_simulation(d,bench())
