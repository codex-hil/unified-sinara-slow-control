"""Offline ESPHome runtime and existing STM PTY/LiteX transport tests; no HIL."""
import copy
import json
import os
from pathlib import Path
import subprocess
import time
import yaml
from test_sampler_esphome import STMFixture,KasliFixture
ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'work/zotino-tests'
WORK.mkdir(parents=True,exist_ok=True)
ENV={**os.environ,'PLATFORMIO_CORE_DIR':str(ROOT/'work/platformio')}
class Model:
    def __init__(self,controller):
        self.out,self.inp,self.oe,self.abi=(0,1,2,None) if controller=='stm' else (4096,4100,4104,4112)
        self.reg={self.out:0x8000,self.oe:0x8000}
        self.shift=self.bits=self.reply=self.ctrl=0
        self.data=[0]*32;self.frames=[];self.leds=[];self.led_shift=0;self.loads=0;self.fault=False
    def open(self):pass
    def close(self):pass
    def read(self,a,length=None,burst='incr'):
        def one(a):
            if self.fault:
                if self.abi is None:raise OSError('injected transport failure')
                return 65536
            if a==self.abi:return 0x53434731
            if a==self.inp:return ((self.reply>>(24-min(max(self.bits,1),24)))&1)<<2
            return self.reg[a]
        return one(a) if length is None else [one(a+4*i) for i in range(length)]
    def write(self,a,data):
        if isinstance(data,list):
            for i,v in enumerate(data):self.write(a+4*i,v)
            return
        assert a in (self.out,self.oe)
        if a==self.out:
            old=self.reg[a];v=data
            if old&8 and not v&8:self.shift=self.bits=0
            if not v&8 and old&1 and not v&1:self.shift=(self.shift<<1)|((v>>1)&1);self.bits+=1
            if not old&8 and v&8 and self.bits==24:
                w=self.shift;self.frames.append(w);addr=(w>>16)&63
                if w>>22==3 and 8<=addr<40:self.data[addr-8]=w&65535
                if w>>16==1:self.ctrl=w&65535
                self.reply=(self.ctrl if w&65535==0x8080 else self.data[((w&65535)>>7)-8]) if w>>16==5 else 0
            if not v&16 and not old&1 and v&1:self.led_shift=(self.led_shift<<1)|((v>>1)&1)
            if not old&16 and v&16:self.leds.append(self.led_shift&255)
            if not old&32 and v&32:self.loads+=1
        self.reg[a]=data

def compile_config(path,tag):
    with (ROOT/f'evidence/zotino-{tag}-build.log').open('w') as log:
        subprocess.run(['esphome','compile',str(path)],env=ENV,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
    c=yaml.safe_load(path.read_text())
    return Path(c['esphome']['build_path'])/'.pioenvs'/c['esphome']['name']/'program'
def run(binary,tag,model=None):
    path=ROOT/f'evidence/zotino-{tag}-run.log'
    with path.open('w') as log:
        p=subprocess.Popen([str(binary)],stdout=log,stderr=subprocess.STDOUT)
        try:
            time.sleep(2.8)
            assert p.poll() is None
            if model:model.fault=True;time.sleep(2.4)
        finally:p.terminate();p.wait(timeout=3)
    text=path.read_text();assert 'SIMULATED_WRITE_OK' in text,text
    if model:
        assert 'Zotino operation failed' in text,text
        assert 'SIMULATED_WRITE_OK' not in text.split('Zotino operation failed',1)[1]

def main():
    results={}
    for controller in ('stm','kasli'):
        source=ROOT/f'integrations/esphome/examples/zotino-{controller}-simulation.yaml'
        binary=compile_config(source,controller+'-simulation');run(binary,controller+'-simulation');results[controller+'_simulation']='PASS'
        c=yaml.safe_load(source.read_text());c['external_components'][0]['source']['path']=str(ROOT/'integrations/esphome/components')
        name='zotino-'+controller+'-loopback';c['esphome']={'name':name,'build_path':str(ROOT/'work/builds'/name)}
        ep=c['sinara_gpio_endpoint'];ep.update(mode='hardware',electrical_profile_reviewed=True,lock_path=str(WORK/(controller+'.lock')))
        m=Model(controller);fixture=STMFixture(m) if controller=='stm' else KasliFixture(m)
        try:
            if controller=='stm':ep['serial_path']=fixture.path
            else:ep.update(host_address='127.0.0.1',tcp_port=fixture.port)
            path=WORK/(name+'.yaml');path.write_text(yaml.safe_dump(c,sort_keys=False))
            binary=compile_config(path,controller+'-loopback')
            if controller=='stm':os.close(fixture.slave);fixture.slave=-1
            run(binary,controller+'-loopback',m)
            assert 0xc89000 in m.frames and m.data[0]==36864 and 0xa5 in m.leds
            assert m.reg[m.oe]==0x80bb
            results[controller+'_transport_model_and_fault']='PASS'
        finally:fixture.close()
        for label,modify,message in [
            ('unreviewed',lambda c:c['sinara_gpio_endpoint'].update(electrical_profile_reviewed=False),'reviewed'),
            ('cross_slot',lambda c:c['sinara_zotino']['pinmux']['ldac_n'].update(slot=2),'slot'),
            ('line_range',lambda c:c['sinara_zotino']['pinmux']['ldac_n'].update(line=16),'15'),
            ('overlap',lambda c:c['sinara_zotino']['pinmux'].update(clk={'slot':1,'line':1}),'distinct'),
            ('direction',lambda c:c['sinara_gpio_endpoint'].update(input_capable=[2]),'capabilities'),
            ('shared',lambda c:c.update(sinara_zotino=[c['sinara_zotino'],{**c['sinara_zotino'],'id':'zotino1'}]),'exclusive'),
            ('duplicate_output',lambda c:c['output'].append({**c['output'][0],'id':'dac1'}),'already has an output'),
            ('mixed_owner',lambda c:c.update(sinara_sampler={'id':'sampler1','endpoint_id':'endpoint0','pinmux':dict(zip(['adc_clk','adc_miso','sdr','cnv','pgia_clk','pgia_mosi','pgia_miso','pgia_latch'],[{'slot':1,'line':i} for i in range(8)]))}),'exclusive'),
            ('channel',lambda c:c['output'][0].update(channel=32),'31')]:
            bad=copy.deepcopy(c);modify(bad)
            if label=='mixed_owner':
                bad['external_components'][0]['components'].append('sinara_sampler')
                bad['sinara_gpio_endpoint'].update(output_capable=list(range(8)),input_capable=list(range(8)))
            path=WORK/(controller+'-'+label+'.yaml');path.write_text(yaml.safe_dump(bad))
            p=subprocess.run(['esphome','config',str(path)],env=ENV,capture_output=True,text=True,timeout=30)
            assert p.returncode and message in p.stdout+p.stderr,(label,p.stdout,p.stderr)
            results[controller+'_'+label]='PASS'
    (ROOT/'evidence/zotino-esphome-tests.json').write_text(json.dumps({'hardware_tested':False,'synthetic_models':True,'results':results},indent=2)+'\n')
    print(json.dumps(results,indent=2))
if __name__=='__main__':main()
