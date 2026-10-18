"""Real ESPHome MAX31855 -> transport -> actual Migen FIFO/SPI RTL.

Synthetic card only, PTY and localhost; no physical board connection.
"""
from pathlib import Path
import os,copy,json,subprocess,time,re,yaml,threading,select,pty,struct
from scf5_rtl_model import RTLModel,ROOT
from test_sampler_esphome import KasliFixture
WORK=ROOT/'work/scf5-esphome-tests';WORK.mkdir(exist_ok=True)
class Fixture:
    def __init__(self,model):
        self.model=model;self.master,self.slave=pty.openpty();self.path=os.ttyname(self.slave);self.stop=False;self.failure=None
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
    def run(self):
        pending=bytearray()
        try:
            while not self.stop:
                if not select.select([self.master],[],[],.05)[0]:continue
                try:pending.extend(os.read(self.master,4096))
                except OSError:time.sleep(.01);continue
                while len(pending)>=16:
                    f=bytes(pending[:16]);del pending[:16]
                    magic,version,op,seq,a,value=struct.unpack('>2sBBIII',f)
                    assert magic==b'SC' and version==2
                    status=0;result=0
                    try:
                        if op==1:result=self.model.read(a)
                        elif op==2:self.model.write(a,value)
                        else:status=1
                    except OSError:status=3
                    os.write(self.master,struct.pack('>2sBBIII',b'SC',2,status,seq,a,result))
        except Exception as e:self.failure=e
    def close(self):
        self.stop=True;self.thread.join(2);os.close(self.master);os.close(self.slave)
        if self.failure:raise self.failure

def config(profile,controller,fixture):
    profile_path=WORK/f'{controller}-profile.yaml';profile_path.write_text(yaml.safe_dump(profile,sort_keys=False))
    c={'esphome':{'name':'scf5-max31855','build_path':str(ROOT/'work/builds/scf5-max31855')},'host':{},'logger':{'level':'DEBUG'},
       'external_components':[{'source':{'type':'local','path':str(ROOT/'integrations/esphome/components')},'components':['spi','sinara_fpga']}],
       'sinara_fpga':{'id':'fabric','profile':str(profile_path),'controller':controller,'lock_path':str(WORK/f'{controller}.lock'),'initialize':True,'timeout_ms':10000,'interlock_slots':[1,7]},
       'spi':[{'id':f'tc{i}','fpga_id':'fabric','slot':7,'selector':i,'interface':'hardware'} for i in range(8)],
       'sensor':[{'platform':'max31855','id':f'thermo{i}','name':f'Thermocouple {i}','spi_id':f'tc{i}','cs_pin':{'sinara_fpga':'fabric','number':'7_3','allow_other_uses':True},'update_interval':'never','on_value':{'then':[{'lambda':f'ESP_LOGI("scf5_result","CH{i}=%.2f",x);'}]}} for i in range(8)]}
    # Deterministic first sweep: random polling offsets can starve the final
    # channel in this slow, interpreted RTL simulation (not hardware timing).
    c['esphome']['on_boot']={'priority':-100,'then':[{'component.update':f'thermo{i}'} for i in range(8)]}
    c['interval']=[{'interval':'5s','then':[{'component.update':'thermo0'}]}]
    if controller=='stm_sys_board':c['sinara_fpga']['serial_path']=fixture.path
    else:c['sinara_fpga'].update(host_address='127.0.0.1',tcp_port=fixture.port)
    return c

def main():
    results={}
    for controller,target in [('stm_sys_board','stm_ecp5'),('kasli','kasli')]:
        p=yaml.safe_load((ROOT/f'examples/fabric-{target}.yaml').read_text());p['reviewed']=True;p['fifo_depth']=16;p['sys_clk_hz']=1000000
        p['slots'][6]['route'].update(mode='parallel',selects=[4,5,6],enable=3)
        model=RTLModel(p);fixture=Fixture(model) if target=='stm_ecp5' else KasliFixture(model)
        try:
            c=config(p,controller,fixture);path=WORK/f'{controller}.yaml';path.write_text(yaml.safe_dump(c,sort_keys=False))
            with (ROOT/f'evidence/scf5-{controller}-build.log').open('w') as log:
                subprocess.run(['esphome','compile',str(path)],env={**os.environ,'PLATFORMIO_CORE_DIR':str(ROOT/'work/platformio')},stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
            out=ROOT/f'evidence/scf5-{controller}-run.log'
            with out.open('w') as log:
                proc=subprocess.Popen([str(ROOT/'work/builds/scf5-max31855/.pioenvs/scf5-max31855/program')],stdout=log,stderr=subprocess.STDOUT)
                try:
                    deadline=time.monotonic()+75
                    while time.monotonic()<deadline:
                        text=out.read_text();values=re.findall(r'CH(\d)=(-?\d+\.\d+)',text)
                        if {int(i) for i,v in values}==set(range(8)):break
                        if proc.poll() is not None or 'SCF5 operation failed' in text:raise AssertionError((model.operations[-35:],text))
                        if model.failure:raise model.failure
                        time.sleep(.2)
                    else:raise AssertionError(out.read_text())
                    for i,v in values:assert float(v)==model.temperatures[int(i)],values
                    # Trip slot1 while slot7 reads: AND across enabled slots.
                    model.good_mask&=~1
                    deadline=time.monotonic()+35
                    while time.monotonic()<deadline:
                        text=out.read_text()
                        if re.search(r'CH\d=nan',text):break
                        if model.failure:raise model.failure
                        time.sleep(.2)
                    else:raise AssertionError('interlock did not reach sensor error: '+out.read_text())
                    assert 'SCF5 operation failed' in text,text
                finally:
                    proc.terminate()
                    try:proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=2)
            assert {channel for slot,channel,n in model.frames if slot==6 and n==32}==set(range(8)),model.frames
            results[controller]=dict(result='PASS',values=values,frames=model.frames,interlock_other_slot_nan=True)
        finally:
            fixture.close();model.shutdown()
    report=dict(hardware_tested=False,actual_rtl=True,actual_esphome=True,synthetic_sensor=True,results=results)
    (ROOT/'evidence/scf5-esphome-tests.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
