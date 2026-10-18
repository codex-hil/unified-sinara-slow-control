"""Threaded real Migen Wishbone fabric with synthetic MAX31855 pin models.

Only localhost/PTY fixtures may use this backend; it does not access a board.
"""
from pathlib import Path
import queue,threading,sys,time
ROOT=Path(__file__).resolve().parents[1]
for p in ['src','gateware','references/migen','references/misoc','work/upstream-stm/deps/misoc','references/litex']:sys.path.insert(0,str(ROOT/p))
from migen.sim import run_simulation
from queued_fabric import QueuedFabric
from sinara_slow.fabric import build_id

class RTLModel:
    def __init__(self,profile):
        self.profile=profile;self.requests=queue.Queue();self.stop=False;self.failure=None
        self.operations=[];self.good_mask=255;self.samples=[];self.frames=[];self.active={};self.indices={}
        self.temperatures=[-40.25,0.25,25.0,123.75,-1.0,99.75,200.0,750.0]
        self.fabric=QueuedFabric(routes=[s['route'] for s in profile['slots']],
            output_capable=[s['output_capable'] for s in profile['slots']],
            input_capable=[s['input_capable'] for s in profile['slots']],depth=profile['fifo_depth'],sys_clk_hz=profile['sys_clk_hz'],
            serial_directions=profile['target']=='stm_ecp5',direction_half_period=1,build_id=build_id(profile))
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
    def open(self):pass
    def close(self):pass # LiteX disconnects must not terminate the model.
    def shutdown(self):
        self.stop=True;self.thread.join(4)
        if self.failure:raise self.failure
        if self.thread.is_alive():raise RuntimeError('RTL model did not terminate')
    def _access(self,address,data=None):
        response=queue.Queue();self.requests.put((address,data,response))
        try:ok,value=response.get(timeout=15)
        except queue.Empty:raise RuntimeError(f'RTL request timeout; simulation failure={self.failure}')
        self.operations.append((address,data,ok,value))
        if not ok:raise OSError(f'Wishbone ERR at {address:#x}')
        return value
    def read(self,address,length=None,burst='incr'):
        if length is None:return self._access(address)
        return [self._access(address+4*i) for i in range(length)]
    def write(self,address,data):
        if isinstance(data,list):
            for i,v in enumerate(data):self._access(address+4*i,v)
        else:self._access(address,data)
    def run(self):
        try:run_simulation(self.fabric,self.bench())
        except Exception as e:self.failure=e
    def bench(self):
        d=self.fabric;b=d.bus;pending=None;wait_release=0
        cycles=0
        while not self.stop:
            # Physical model: mode3 MAX31855, four direct CS on lines3..6.
            for slot in range(8):
                out=(yield d.outputs[slot]);oe=(yield d.oes[slot]);clk=out&1
                route=self.profile['slots'][slot]['route']
                if route['mode']=='parallel':
                    enable=route['enable']
                    channel=sum(((out>>pin)&1)<<i for i,pin in enumerate(route['selects'])) if oe&(1<<enable) and not out&(1<<enable) else None
                else:
                    channel=next((i for i,pin in enumerate(route['selects']) if oe&(1<<pin) and not out&(1<<pin)),None)
                old=self.active.get(slot)
                if channel!=old:
                    if old is not None:self.frames.append((slot,old,self.indices.get(slot,0)))
                    if channel is not None:self.indices[slot]=0
                    self.active[slot]=channel
                index=self.indices.get(slot,0)
                if channel is not None and clk and not getattr(self,'clocks',{}).get(slot,0):
                    # Increment after the edge that samples current MISO.
                    self.indices[slot]=index+1
                if not hasattr(self,'clocks'):self.clocks={}
                self.clocks[slot]=clk
                value=(1<<13) if (self.good_mask>>slot)&1 else 0
                if channel is not None:
                    frame=((int(self.temperatures[channel]*4)&0x3fff)<<18)|(400<<4)
                    # Index denotes bit presented during this cycle.
                    value|=((frame>>(31-min(self.indices.get(slot,0),31)))&1)<<2
                yield d.inputs[slot].eq(value)
            if wait_release:
                wait_release-=1
            elif pending is None:
                try:address,value,response=self.requests.get_nowait()
                except queue.Empty:
                    idle=True
                    for q in d.spi:
                        if not (yield q.spi.idle):idle=False
                        if (yield q.busy) and not (yield q.session) and not (yield q.waiting):idle=False
                    if idle:time.sleep(.0005)
                else:
                    pending=(address,value,response)
                    yield b.adr.eq(address>>2);yield b.dat_w.eq(value or 0);yield b.we.eq(value is not None)
                    yield b.sel.eq(15);yield b.cyc.eq(1);yield b.stb.eq(1)
            elif (yield b.ack):
                pending[2].put((not (yield b.err),(yield b.dat_r)))
                yield b.cyc.eq(0);yield b.stb.eq(0);pending=None;wait_release=2
            cycles+=1
            yield
