"""ESPHome driver/runtime + STM PTY and real LiteX server/model tests. No HIL."""
import json
import math
import os
from pathlib import Path
import pty
import re
import select
import struct
import subprocess
import sys
import threading
import time
import yaml

ROOT=Path(__file__).resolve().parents[1]
for name in ['references/migen','references/litex']:
    sys.path.insert(0,str(ROOT/name))
from litex.tools.litex_server import RemoteServer

RAW=[-32768,-16384,-1,0,1,16384,32767,1234]
GAINS=[1,10,100,1000,1,10,100,1000]
EXPECTED=[v*20.48/65536/g for v,g in zip(RAW,GAINS)]
WORK=ROOT/'work/sampler-esphome-tests'
WORK.mkdir(parents=True,exist_ok=True)
ENV={**os.environ,'PLATFORMIO_CORE_DIR':str(ROOT/'work/platformio')}

class Model:
    def __init__(self,controller,fault=False):
        self.out,self.inp,self.oe,self.abi=(0,1,2,None) if controller=='stm' else (4096,4100,4104,4112)
        self.reg={self.out:0x8000,self.oe:0x8000}
        self.controller=controller
        self.bit=128;self.shift=0;self.gains=0;self.cnvs=0;self.clocks=0;self.fault=fault
    def open(self): pass
    def close(self): pass
    def read(self,a,length=None,burst='incr'):
        def one(a):
            if a==self.inp:
                if self.fault and self.clocks>=20:
                    if self.controller=='stm':raise OSError('injected ADC transport error')
                    return 65536  # Invalid GPIO word: endpoint must fail closed.
                if self.bit>=128:return 0
                w=RAW[7-self.bit//16]&65535
                return ((w>>(15-self.bit%16))&1)<<1
            if a==self.abi:return 0x53434731
            return self.reg[a]
        return one(a) if length is None else [one(a+4*i) for i in range(length)]
    def write(self,a,data):
        if isinstance(data,list):
            for i,v in enumerate(data):self.write(a+4*i,v)
            return
        assert a in (self.out,self.oe),hex(a)
        if a==self.out:
            old=self.reg[a];v=data
            if not old&8 and v&8:self.bit=0;self.cnvs+=1
            if not old&1 and v&1:self.clocks+=1
            if old&1 and not v&1:self.bit+=1
            if not old&16 and v&16:self.shift=((self.shift<<1)|((v>>5)&1))&65535
            if not old&128 and v&128:self.gains=self.shift
        self.reg[a]=data

class STMFixture:
    def __init__(self,model):
        self.model=model;self.master,self.slave=pty.openpty();self.path=os.ttyname(self.slave)
        self.stop=False;self.error=None;self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
    def run(self):
        pending=bytearray()
        try:
            while not self.stop:
                if not select.select([self.master],[],[],.05)[0]:continue
                try:pending.extend(os.read(self.master,4096))
                except OSError as exc:
                    if exc.errno==5:
                        time.sleep(.01);continue  # PTY slave between client sessions.
                    raise
                while len(pending)>=16:
                    f=bytes(pending[:16]);del pending[:16]
                    magic,ver,op,seq,a,v=struct.unpack('>2sBBIII',f)
                    assert (magic,ver)==(b'SC',1)
                    status=0;result=0
                    try:
                        if op==0:result=0x53434731
                        elif op==1:result=self.model.read(a)
                        elif op==2:self.model.write(a,v)
                        else:raise AssertionError(op)
                    except OSError:status=3
                    os.write(self.master,struct.pack('>2sBBIII',b'SC',1,status,seq,a,result))
        except Exception as exc:
            if not self.stop:self.error=exc
    def close(self):
        self.stop=True;self.thread.join(1);os.close(self.master)
        if self.slave>=0:os.close(self.slave)
        if self.error:raise self.error

class KasliFixture:
    def __init__(self,model):
        self.server=RemoteServer(model,'127.0.0.1',0)
        self.server.open();self.port=self.server.socket.getsockname()[1]
        self.server.start(1)
    def close(self):self.server.close()

def compile_config(path,tag):
    with (ROOT/f'evidence/sampler-{tag}-build.log').open('w') as log:
        subprocess.run(['esphome','compile',str(path)],cwd=ROOT,env=ENV,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
    c=yaml.safe_load(path.read_text());name=c['esphome']['name']
    return Path(c['esphome']['build_path'])/'.pioenvs'/name/'program'

def run(binary,tag,fault=False,inject=None):
    logfile=ROOT/f'evidence/sampler-{tag}-run.log'
    with logfile.open('w') as log:
        p=subprocess.Popen([str(binary)],stdout=log,stderr=subprocess.STDOUT)
        try:
            if inject is not None:
                try:p.wait(timeout=1.3)
                except subprocess.TimeoutExpired:inject()
            p.wait(timeout=2.5)
            raise AssertionError(f'ESPHome exited unexpectedly: {p.returncode}')
        except subprocess.TimeoutExpired:
            p.terminate();p.wait(timeout=3)
    text=logfile.read_text()
    values=re.findall(r'SIMULATED_CH(\d)=(-?\d+\.\d+)',text)
    if fault:
        assert 'Acquisition failed' in text,text
        after=text.split('Acquisition failed',1)[1]
        assert not re.findall(r'SIMULATED_CH(\d)=(-?\d+\.\d+)',after),text
        assert len(re.findall(r'SIMULATED_CH\d=nan',text))==8,text
    else:
        assert {int(c) for c,v in values}==set(range(8)),text
        for c,v in values:assert math.isclose(float(v),EXPECTED[int(c)],rel_tol=1e-6,abs_tol=1e-7),(c,v)
    return len(values)

def main():
    assert subprocess.check_output(['esphome','version'],text=True).strip()=='Version: 2026.9.0'
    results={}
    for controller in ['stm','kasli']:
        source=ROOT/f'integrations/esphome/examples/sampler-{controller}-simulation.yaml'
        binary=compile_config(source,controller+'-simulation')
        results[controller+'_simulation']=run(binary,controller+'-simulation')
        hardware=yaml.safe_load(source.read_text())
        hardware['external_components'][0]['source']['path']=str(ROOT/'integrations/esphome/components')
        name=f'sampler-{controller}-loopback'
        hardware['esphome']={'name':name,'build_path':str(ROOT/'work/builds'/name)}
        ep=hardware['sinara_gpio_endpoint'];ep['mode']='hardware';ep['electrical_profile_reviewed']=True
        ep['lock_path']=str(WORK/(controller+'.lock'))
        # Both fixtures remain alive for their compiled configuration, including
        # reopening the same endpoint for a separate failure/recovery session.
        model=Model(controller)
        fixture=STMFixture(model) if controller=='stm' else KasliFixture(model)
        try:
            if controller=='stm':ep['serial_path']=fixture.path
            else:ep.update(host_address='127.0.0.1',tcp_port=fixture.port)
            config=WORK/(name+'.yaml');config.write_text(yaml.safe_dump(hardware,sort_keys=False))
            binary=compile_config(config,controller+'-loopback')
            if controller=='stm':os.close(fixture.slave);fixture.slave=-1
            results[controller+'_wire_model_then_fault']=run(binary,controller+'-loopback',fault=True,
                inject=lambda:setattr(model,'fault',True))
            assert model.gains==0xe4e4 and model.clocks>=128 and model.reg[model.oe]==0x80bd
        finally:fixture.close()
        # Hardware-mode rejection and bad pinmux must fail before connections.
        for label,modify,expected in [
            ('unreviewed',lambda c:c['sinara_gpio_endpoint'].update(electrical_profile_reviewed=False),'reviewed'),
            ('cross_slot',lambda c:c['sinara_sampler']['pinmux']['cnv'].update(slot=2),'slot'),
            ('line_range',lambda c:c['sinara_sampler']['pinmux']['cnv'].update(line=16),'15'),
            ('pin_overlap',lambda c:c['sinara_sampler']['pinmux'].update(adc_miso={'slot':1,'line':0}),'distinct'),
            ('wrong_direction',lambda c:c['sinara_gpio_endpoint'].update(input_capable=[6]),'capabilities'),
            ('wrong_gain',lambda c:c['sinara_sampler'].update(gains=[2]*8),'valid options'),
            ('duplicate_sensor',lambda c:c['sensor'].append({**c['sensor'][0],'name':'Duplicate channel'}),'already has a sensor'),
            ('shared_endpoint',lambda c:c.update(sinara_sampler=[c['sinara_sampler'],{**c['sinara_sampler'],'id':'sampler1'}]),'exclusive endpoint')]:
            candidate=yaml.safe_load(config.read_text());modify(candidate)
            path=WORK/(controller+'-'+label+'.yaml');path.write_text(yaml.safe_dump(candidate,sort_keys=False))
            p=subprocess.run(['esphome','config',str(path)],capture_output=True,text=True,env=ENV,timeout=20)
            assert p.returncode and expected in (p.stdout+p.stderr),(label,p.stdout,p.stderr)
            results[controller+'_'+label]='PASS'
    (ROOT/'evidence/sampler-esphome-tests.json').write_text(json.dumps({'hardware_tested':False,'results':results,'values_are_synthetic':True},indent=2)+'\n')
    print(json.dumps(results,indent=2))
if __name__=='__main__':main()
