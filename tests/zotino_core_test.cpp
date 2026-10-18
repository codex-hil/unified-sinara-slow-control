#include "zotino_core.h"
#include <cassert>
#include <vector>
#include <limits>
using namespace sinara;
struct Model:SamplerRegisters {
  uint16_t out=0x8000,oe=0x8000,ctrl=0;bool held=false;int calls=0,fail_at=-1;unsigned bits=0,loads=0;uint32_t shift=0,reply=0;
  std::array<uint16_t,32> staged{},dac{};std::vector<uint32_t> frames;std::vector<unsigned> leds;
  bool kasli=false;
  bool step(){return ++calls!=fail_at;}
  bool acquire()override{if(held)return false;held=true;return true;}
  void release()override{held=false;}
  bool read(uint32_t a,uint16_t &v)override{if(!step())return false;if(a==(kasli?0x1000:0) || (!kasli&&a==140))v=out;else if(a==(kasli?0x1008:2) || (!kasli&&a==142))v=oe;else v=((reply>>(24-std::min(std::max(bits,1u),24u)))&1)<<2;return true;}
  bool write(uint32_t a,uint16_t v)override{
    if(!step())return false;
    if(a==(kasli?0x1008:2) || (!kasli&&a==142)){oe=v;return true;}
    bool active=!(v&8),old_active=!(out&8);
    if(active&&!old_active){bits=0;shift=0;}
    if(active&&(out&1)&&!(v&1)){shift=(shift<<1)|((v>>1)&1);++bits;}
    if(!active&&old_active&&bits==24){frames.push_back(shift);unsigned addr=(shift>>16)&63;
      if((shift>>22)==3&&addr>=8&&addr<40)staged[addr-8]=shift;
      if((shift>>16)==1)ctrl=shift;
      reply=(shift>>16)==5 ? ((shift&0xffff)==0x8080?ctrl:staged[((shift&0xffff)>>7)-8]):0;
    }
    if(!(v&16)&&(v&1)&&!(out&1)){led_shift=(led_shift<<1)|((v>>1)&1);}
    if((v&16)&&!(out&16))leds.push_back(led_shift&255);
    if((v&32)&&!(out&32)){++loads;dac=staged;}
    out=v;return true;
  }
  unsigned led_shift=0;
  void delay_us(uint32_t)override{}
};
int main(){
  uint16_t code=77;assert(Zotino::voltage_to_mu(-10,code)&&code==0);assert(Zotino::voltage_to_mu(0,code)&&code==32768);assert(Zotino::voltage_to_mu(10-20.0/65536,code)&&code==65535);assert(!Zotino::voltage_to_mu(10,code));assert(!Zotino::voltage_to_mu(std::numeric_limits<double>::quiet_NaN(),code));
  for(unsigned slot:{0u,7u}){
    Model m;Zotino z(m,stm_zotino_route(slot,0xbb,0x44));assert(z.initialize()==ZotinoResult::OK);assert(z.ready());assert((m.oe&0xff)==0xbb);assert(m.out&0x8000);assert(m.oe&0x8000);
    assert(m.frames[0]==0x022000&&m.frames[1]==0x032000);
    uint8_t channels[]={0,31};uint16_t values[]={0,65535};unsigned loads=m.loads;
    assert(z.set_dac_mu(channels,values,2)==ZotinoResult::OK);assert(m.frames[m.frames.size()-2]==0xc80000);assert(m.frames.back()==0xe7ffff);assert(m.loads==loads+1&&m.dac[31]==65535);
    uint16_t read=17;assert(z.read_dac_mu(31,read)==ZotinoResult::OK&&read==65535);
    assert(z.set_leds(0xa5)==ZotinoResult::OK&&m.leds.back()==0xa5);assert(m.out&8);assert(m.out&16);
    channels[1]=0;int before=m.calls;assert(z.set_dac_mu(channels,values,2)==ZotinoResult::INVALID_CONFIG&&m.calls==before);
    m.held=true;assert(z.set_voltage(0,0)==ZotinoResult::BUSY);m.held=false;
  }
  Model baseline;Zotino good(baseline,stm_zotino_route(0,0xbb,0x44));assert(good.initialize()==ZotinoResult::OK);int init_calls=baseline.calls;
  for(int n=1;n<=init_calls;++n){Model m;m.fail_at=n;Zotino z(m,stm_zotino_route(0,0xbb,0x44));assert(z.initialize()==ZotinoResult::IO_ERROR);assert(!z.ready()&&!m.held);}
  int before=baseline.calls;assert(good.set_voltage(0,0)==ZotinoResult::OK);int write_calls=baseline.calls-before;
  for(int n=1;n<=write_calls;++n){Model m;Zotino z(m,stm_zotino_route(0,0xbb,0x44));assert(z.initialize()==ZotinoResult::OK);m.fail_at=m.calls+n;assert(z.set_voltage(0,0)==ZotinoResult::IO_ERROR);assert(!z.ready()&&!m.held);assert(z.set_voltage(0,0)==ZotinoResult::NOT_READY);}
  Model kasli;kasli.kasli=true;Zotino kz(kasli,kasli_zotino_route(0x1000,0x1004,0x1008,0xbb,0x44));assert(kz.initialize()==ZotinoResult::OK);assert(kz.set_voltage(31,1.25)==ZotinoResult::OK);assert(kasli.dac[31]==36864);
  Model absent;absent.ctrl=0xffff;Zotino az(absent,stm_zotino_route(0,0xbb,0x44));assert(az.initialize()==ZotinoResult::DEVICE_ERROR&&!az.ready());
  Model reader;Zotino rz(reader,stm_zotino_route(0,0xbb,0x44));assert(rz.initialize()==ZotinoResult::OK);before=reader.calls;uint16_t read=0;assert(rz.read_dac_mu(0,read)==ZotinoResult::OK);int read_calls=reader.calls-before;
  for(int n=1;n<=read_calls;++n){Model m;Zotino z(m,stm_zotino_route(0,0xbb,0x44));assert(z.initialize()==ZotinoResult::OK);m.fail_at=m.calls+n;uint16_t unchanged=123;assert(z.read_dac_mu(0,unchanged)==ZotinoResult::IO_ERROR);assert(unchanged==123&&!m.held&&!z.ready());}
  assert(Zotino::voltage_to_mu(0.5*20/65536,code)&&code==32768);
  assert(Zotino::voltage_to_mu(1.5*20/65536,code)&&code==32770);
  Model wrong;auto route=stm_zotino_route(0,0xbb,0x44);route.mosi=route.clk;Zotino overlap(wrong,route);assert(overlap.initialize()==ZotinoResult::INVALID_CONFIG&&wrong.calls==0);
  auto no_caps=stm_zotino_route(0,0,0);Zotino caps(wrong,no_caps);assert(caps.initialize()==ZotinoResult::INVALID_CONFIG&&wrong.calls==0);
  Zotino unaligned(wrong,kasli_zotino_route(1,4,8,0xbb,0x44));assert(unaligned.initialize()==ZotinoResult::INVALID_CONFIG&&wrong.calls==0);
  Model bad;Zotino invalid(bad,stm_zotino_route(8,0xbb,0x44));assert(invalid.initialize()==ZotinoResult::INVALID_CONFIG&&bad.calls==0);
}
