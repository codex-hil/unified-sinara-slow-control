#include "sampler_core.h"
#include "register_protocol.h"
#include <cassert>
#include <cmath>
#include <deque>
#include <vector>
#include <algorithm>
using namespace sinara;

struct Model : SamplerRegisters {
  SamplerRoute route;
  uint16_t output=0x8000,oe=0x8000,shift=0,gains=0;
  unsigned index=128,clocks=0,latches=0,cnvs=0,calls=0,fail_at=0;
  uint64_t us=0,cnv_started=0,cnv_ended=0,last_clk=0;
  bool locked=false,deny=false;
  std::array<int16_t,8> data{-32768,-16384,-1,0,1,16384,32767,1234};
  explicit Model(SamplerRoute r):route(r){}
  bool acquire() override {if(locked||deny)return false;locked=true;return true;}
  void release() override {assert(locked);locked=false;}
  bool access() {assert(locked);return ++calls!=fail_at;}
  bool read(uint32_t a,uint16_t &v) override {
    if(!access())return false;
    if(a==route.output)v=output;
    else if(a==route.oe)v=oe;
    else {assert(a==route.input);assert(index<128);uint16_t w=uint16_t(data[7-index/16]);v=((w>>(15-index%16))&1)<<route.adc_miso;}
    return true;
  }
  bool write(uint32_t a,uint16_t v) override {
    if(!access())return false;
    if(a==route.oe){oe=v;return true;}
    assert(a==route.output);
    auto rise=[&](unsigned n){return !(output&(1<<n)) && (v&(1<<n));};
    if(rise(route.cnv)){index=0;cnv_started=us;++cnvs;}
    if((output&(1<<route.cnv)) && !(v&(1<<route.cnv))){assert(us-cnv_started>=1);cnv_ended=us;}
    if(rise(route.adc_clk)){assert(!(v&(1<<route.cnv)));assert(us-cnv_ended>=1);++clocks;last_clk=us;}
    if((output&(1<<route.adc_clk)) && !(v&(1<<route.adc_clk))){assert(us-last_clk>=1);++index;}
    if(rise(route.pgia_clk))shift=uint16_t((shift<<1)|((v>>route.pgia_mosi)&1));
    if(rise(route.pgia_latch)){gains=shift;++latches;}
    output=v;return true;
  }
  void delay_us(uint32_t n) override {us+=n;}
};
const std::array<uint16_t,8> gains{1,10,100,1000,1,10,100,1000};
void basic(SamplerRoute r) {
  Model m(r);Sampler d(m,r);
  std::array<int16_t,8> raw{};std::array<float,8> volts{};
  assert(d.sample(raw,volts)==SamplerResult::NOT_READY);
  assert(d.initialize(gains)==SamplerResult::OK);
  assert(m.gains==0xe4e4);assert(m.oe==uint16_t(0x8000|r.output_capable));assert(m.output&0x8000);
  unsigned l=m.latches;
  for(bool corrected:{true,false}) {
    d.set_revision(corrected);
    assert(d.sample(raw,volts)==SamplerResult::OK);assert(raw==m.data);
    for(unsigned i=0;i<8;++i) assert(std::abs(volts[i]-raw[i]*(corrected?20.48f:20.f)/65536/gains[i])<1e-6);
  }
  assert(m.cnvs==2 && m.clocks==256 && m.latches==l);
  assert(!m.locked);assert((m.output&((1<<r.adc_clk)|(1<<r.cnv)))==0);
  m.deny=true;auto calls=m.calls;
  assert(d.sample(raw,volts)==SamplerResult::BUSY && m.calls==calls);m.deny=false;
  auto bad=gains;bad[0]=2;
  assert(d.set_gains(bad)==SamplerResult::INVALID_CONFIG && m.calls==calls);
  for(auto &v:m.data)v=int16_t(0xaaaa);
  assert(d.sample(raw,volts)==SamplerResult::OK && raw==m.data);
  std::array<uint16_t,8> ones{1,1,1,1,1,1,1,1};
  assert(d.set_gains(ones)==SamplerResult::OK && m.gains==0);
  const std::array<uint16_t,8> asymmetric{100,1000,1,10,1000,100,10,1};
  assert(d.set_gains(asymmetric)==SamplerResult::OK && m.gains==0x1b4e);
}
struct Stream : RegisterStream {
  std::vector<std::vector<uint8_t>> sent;
  std::deque<uint8_t> reply;
  bool failure=false;
  bool send(const uint8_t *p,size_t n) override {sent.emplace_back(p,p+n);return !failure;}
  bool receive(uint8_t *p,size_t n) override {
    if(failure || reply.size()<n)return false;
    for(size_t i=0;i<n;++i){p[i]=reply.front();reply.pop_front();}return true;
  }
  void stm_reply(unsigned seq,unsigned a,unsigned v) {
    uint8_t p[16]={'S','C',1,0};put32(p+4,seq);put32(p+8,a);put32(p+12,v);reply.insert(reply.end(),p,p+16);
  }
  void kasli_reply(unsigned seq,unsigned v) {
    uint8_t p[20]={0x4e,0x6f,0x10,0x44,0,0,0,0,0,15,1,0};put32(p+12,seq);put32(p+16,v);reply.insert(reply.end(),p,p+20);
  }
};
int main() {
  basic(stm_sampler_route(0,0xbd,0x42));basic(stm_sampler_route(7,0xbd,0x42));
  basic(kasli_sampler_route(0x1000,0x1004,0x1008,0xbd,0x42));
  auto r=stm_sampler_route(0,0xbd,0x42);
  auto remapped=r;std::swap(remapped.pgia_miso,remapped.pgia_latch);
  remapped.output_capable=0x7d;remapped.input_capable=0x82;basic(remapped);
  // Exhaust every I/O failure point in initialization: no success/known gains.
  Model count(r);Sampler c(count,r);assert(c.initialize(gains)==SamplerResult::OK);
  for(unsigned i=1;i<=count.calls;++i){Model m(r);m.fail_at=i;Sampler d(m,r);assert(d.initialize(gains)==SamplerResult::IO_ERROR);assert(!d.ready()&&!m.locked);}
  // Every acquisition failure leaves caller's last complete vector untouched.
  std::array<int16_t,8> scratch_raw{};std::array<float,8> scratch_volts{};
  auto before=count.calls;assert(c.sample(scratch_raw,scratch_volts)==SamplerResult::OK);
  const auto sample_calls=count.calls-before;
  for(unsigned i=1;i<=sample_calls;++i){Model m(r);Sampler d(m,r);assert(d.initialize(gains)==SamplerResult::OK);m.fail_at=m.calls+i;
    std::array<int16_t,8> raw;raw.fill(42);std::array<float,8> volts;volts.fill(42);
    auto result=d.sample(raw,volts);
    assert(result==SamplerResult::IO_ERROR);
    if(result==SamplerResult::IO_ERROR){for(auto v:raw)assert(v==42);for(auto v:volts)assert(v==42);assert(!d.ready());}
    assert(!m.locked);
  }
  for(auto invalid:{stm_sampler_route(8,0xbd,0x42),kasli_sampler_route(1,4,8,0xbd,0x42),stm_sampler_route(0,0xbd,0)}) {
    Model m(invalid);Sampler d(m,invalid);assert(d.initialize(gains)==SamplerResult::INVALID_CONFIG && m.calls==0);
  }
  Stream s;STMRegisterProtocol stm(s);s.stm_reply(1,0,GPIO_ABI);assert(stm.identify());
  assert(s.sent[0].size()==16 && s.sent[0][3]==0);
  s.stm_reply(2,140,0);assert(stm.write(140,0xa55a));assert(be32(s.sent.back().data()+12)==0xa55a);
  s.stm_reply(999,140,0);assert(!stm.write(140,0));auto n=s.sent.size();assert(!stm.write(140,0)&&s.sent.size()==n);
  Stream k;KasliRegisterProtocol kasli(k);k.kasli_reply(0,GPIO_ABI);assert(kasli.identify(0x1000));
  assert(k.sent[0]==std::vector<uint8_t>({0x4e,0x6f,0x10,0x44,0,0,0,0,0,15,0,1,0,0,0,0,0,0,16,0}));
  k.kasli_reply(0,0xa55a);assert(kasli.write(0x2000,0xa55a));assert(k.sent[1][10]==1&&be32(k.sent[1].data()+12)==0x2000);
  k.kasli_reply(0,0);assert(!kasli.write(0x2000,123));n=k.sent.size();uint32_t ignored=0;assert(!kasli.read(0x2000,ignored)&&k.sent.size()==n);
}
