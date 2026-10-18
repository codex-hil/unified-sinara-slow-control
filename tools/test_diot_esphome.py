"""Unchanged ESPHome MAX31855 + pinned addrspi through FPGA GPIO protocols.

All boards/chips are models on PTY/localhost; no physical hardware access.
"""
import copy
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import yaml
from test_sampler_esphome import STMFixture, KasliFixture

ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'work/diot-esphome-tests';WORK.mkdir(exist_ok=True)
SOURCE=ROOT/'integrations/esphome/examples/max31855-diot-simulation.yaml'
ENV={**os.environ,'PLATFORMIO_CORE_DIR':str(ROOT/'work/platformio')}
TEMPERATURES=[-40.25,-1.0,0.0,0.25,25.0,99.75,200.0,750.0]

class ThermocoupleCard:
    def __init__(self,controller):
        self.out,self.inp,self.oe,self.abi=(120,121,122,None) if controller=='stm' else (4096,4100,4104,4112)
        self.reg={self.out:0x8008,self.oe:0x8000}
        self.bit=0;self.clocks=0;self.channel=0;self.risen=False;self.frames=[];self.address_changes=0
        self.active=False;self.reads=0;self.fault=False;self.operations=[]
    def open(self):pass
    def close(self):pass
    def read(self,a,length=None,burst='incr'):
        def one(a):
            self.operations.append(('read',a))
            if a==self.abi:return 0x53434731
            if a==self.inp:
                if self.fault:
                    if self.abi is None:raise OSError('injected GPIO transport fault')
                    return 65536
                self.reads+=1
                # MAX31855 signed14 thermocouple + signed12 cold junction.
                frame=((int(TEMPERATURES[self.channel]*4)&0x3fff)<<18)|(400<<4)
                return ((frame>>(31-min(self.bit,31)))&1)<<2
            return self.reg[a]
        return one(a) if length is None else [one(a+4*i) for i in range(length)]
    def write(self,a,data):
        if isinstance(data,list):
            for i,v in enumerate(data):self.write(a+4*i,v)
            return
        self.operations.append(('write',a,data))
        assert a in (self.out,self.oe),hex(a)
        assert data&0x8000,'Unrelated GPIO15 clobbered'
        if a==self.out:
            old=self.reg[a]
            if (old^data)&0x70:
                assert old&8 and data&8,'Address changed while CS asserted'
                self.address_changes+=1
            if old&8 and not data&8:
                self.channel=(data>>4)&7;self.bit=0;self.clocks=0;self.risen=False;self.active=True
            if self.active:
                if not old&1 and data&1:self.risen=True;self.clocks+=1
                if old&1 and not data&1 and self.risen:
                    self.bit+=1;self.risen=False
            if not old&8 and data&8 and self.active:
                assert self.clocks in (0,32),('Incorrect frame length',self.clocks)
                self.frames.append((self.channel,self.clocks));self.active=False
        self.reg[a]=data

def compile_and_run(config,controller,model,fixture):
    config['external_components'][0]['source']['path']=str(ROOT/'integrations/esphome/components')
    ep=config['sinara_gpio_endpoint']
    ep.update(mode='hardware',electrical_profile_reviewed=True,lock_path=str(WORK/f'{controller}.lock'))
    if controller=='stm':ep['serial_path']=fixture.path
    else:
        ep.update(controller='kasli',host_address='127.0.0.1',tcp_port=fixture.port,
                  output_address=model.out,input_address=model.inp,oe_address=model.oe,abi_address=model.abi)
    path=WORK/f'{controller}.yaml';path.write_text(yaml.safe_dump(config,sort_keys=False))
    with (ROOT/f'evidence/diot-{controller}-build.log').open('w') as log:
        subprocess.run(['esphome','compile',str(path)],cwd=ROOT,env=ENV,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
    if controller=='stm':os.close(fixture.slave);fixture.slave=-1
    binary=ROOT/'work/builds/max31855-diot/.pioenvs/max31855-diot/program'
    with (ROOT/f'evidence/diot-{controller}-run.log').open('w') as log:
        process=subprocess.Popen([str(binary)],stdout=log,stderr=subprocess.STDOUT)
        try:
            time.sleep(6)
            assert process.poll() is None,'ESPHome exited'
            model.fault=True
            time.sleep(4)
            assert process.poll() is None,'ESPHome exited after transport fault'
        finally:
            process.terminate();process.wait(timeout=5)
    text=(ROOT/f'evidence/diot-{controller}-run.log').read_text()
    values=re.findall(r'CH(\d)=(-?\d+\.\d+)',text)
    assert {int(i) for i,_ in values}==set(range(8)),(model.operations[:15],fixture.error if controller=='stm' else '',text)
    for i,value in values:assert math.isclose(float(value),TEMPERATURES[int(i)],abs_tol=.001),(i,value)
    assert {c for c,n in model.frames if n==32}==set(range(8)),model.frames
    assert 'FPGA GPIO unavailable' in text,text
    after=text.split('FPGA GPIO unavailable',1)[1]
    assert not re.findall(r'CH\d=(-?\d+\.\d+)',after),after
    assert {int(i) for i in re.findall(r'CH(\d)=nan',after)}==set(range(8)),after
    assert model.address_changes>=7
    assert model.reg[model.oe]==0x807b,hex(model.reg[model.oe])
    return dict(samples=len(values),frames=len(model.frames),all_eight_addresses=True,
                preserve_unrelated_gpio=True,correct_frame_lengths=True,transport_fault_nan=True)

def main():
    manifest=json.loads((ROOT/'evidence/addressed-spi-upstream/manifest.json').read_text())
    import hashlib
    for file in manifest['files']:
        data=(ROOT/'integrations/esphome'/file['path']).read_bytes()
        assert hashlib.sha256(data).hexdigest()==file['sha256'],'Router source changed'
    config=yaml.safe_load(SOURCE.read_text());results={}
    # Validate rejected GPIO configurations before any connection.
    for case,change in [
        ('unquoted',lambda c:c['spi']['clk_pin'].update(number=700)),
        ('wrong_slot',lambda c:c['spi']['clk_pin'].update(number='6_0')),
        ('line_range',lambda c:c['spi']['clk_pin'].update(number='7_16')),
        ('wrong_direction',lambda c:c['sinara_gpio_endpoint'].update(input_capable=[])),
        ('pullup',lambda c:c['spi']['miso_pin'].update(mode={'input':True,'pullup':True})),
        ('duplicate_channel',lambda c:c['addrspi']['channels'][1].update(channel=0)),
    ]:
        c=copy.deepcopy(config);change(c);c['external_components'][0]['source']['path']=str(ROOT/'integrations/esphome/components')
        path=WORK/f'bad-{case}.yaml';path.write_text(yaml.safe_dump(c,sort_keys=False))
        run=subprocess.run(['esphome','config',str(path)],capture_output=True,text=True,timeout=30)
        if case=='duplicate_channel':
            # Upstream addrspi currently permits duplicates; record the limitation.
            results[case]='UPSTREAM_ACCEPTS' if run.returncode==0 else 'REJECTED'
        else:assert run.returncode!=0,(case,run.stdout,run.stderr);results[case]='REJECTED'
    c=copy.deepcopy(config)
    c['external_components'][0]['source']['path']=str(ROOT/'integrations/esphome/components')
    ep=c['sinara_gpio_endpoint']
    ep.update(slot=1,mode='hardware',electrical_profile_reviewed=True,
              output_address=0,input_address=1,oe_address=2,
              serial_path='/dev/validation-only-no-device',lock_path=str(WORK/'never-opened.lock'))
    ep['output_capable'].append(8)
    def remap(value):
        if isinstance(value,dict):
            if 'sinara_gpio' in value and 'number' in value:
                value['number']=value['number'].replace('7_','1_')
            for child in value.values():remap(child)
        elif isinstance(value,list):
            for child in value:remap(child)
    remap(c)
    c['spi']['clk_pin']['number']='1_8'
    path=WORK/'bad-translator.yaml';path.write_text(yaml.safe_dump(c,sort_keys=False))
    run=subprocess.run(['esphome','config',str(path)],capture_output=True,text=True,timeout=30)
    assert run.returncode!=0 and 'ABI4' in run.stdout+run.stderr,(run.stdout,run.stderr)
    results['stm_upper_translator']='REJECTED'
    for controller in ['stm','kasli']:
        model=ThermocoupleCard(controller)
        fixture=STMFixture(model) if controller=='stm' else KasliFixture(model)
        try:results[controller]=compile_and_run(copy.deepcopy(config),controller,model,fixture)
        finally:fixture.close()
    report=dict(hardware_tested=False,values_are_synthetic=True,driver='unchanged ESPHome MAX31855',
                router='unchanged pinned MODULIQ addrspi',spi='ESPHome software SPI over FPGA GPIO',results=results)
    (ROOT/'evidence/diot-esphome-tests.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
