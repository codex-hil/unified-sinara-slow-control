#pragma once
// Protocol derived from pinned ARTIQ zotino.py/ad53xx.py; no RTIO dependency.
#include "sampler_core.h"
#include <cmath>
#include <cstddef>
namespace sinara {
enum class ZotinoResult { OK, INVALID_CONFIG, NOT_READY, BUSY, IO_ERROR, DEVICE_ERROR };
struct ZotinoRoute {
  uint32_t output, input, oe;
  uint8_t clk=0, mosi=1, miso=2, sync_n=3, led_cs_n=4, ldac_n=5, busy=6, clr_n=7;
  uint16_t output_capable=0, input_capable=0;
};
class Zotino {
 public:
  Zotino(SamplerRegisters &bus, ZotinoRoute route):bus_(bus),r_(route) {}
  static bool voltage_to_mu(double voltage,uint16_t &code,double vref=5.0) {
    if (!std::isfinite(voltage)||!std::isfinite(vref)||vref<=0 || voltage < -2*vref || voltage > 2*vref-4*vref/65536) return false;
    // Explicit ties-to-even, matching Python round independently of host fenv.
    double x=65536*(voltage/(4*vref))+32768, f=std::floor(x), d=x-f;
    code=uint16_t(f+(d>0.5 || (d==0.5 && (uint32_t(f)&1))));return true;
  }
  ZotinoResult initialize() {
    if (!valid()) return ZotinoResult::INVALID_CONFIG;
    if (!bus_.acquire()) return ZotinoResult::BUSY;
    ready_=false;known_=false;uint16_t oe=0;
    bool ok=bus_.read(r_.output,value_) && bus_.read(r_.oe,oe);
    known_=ok;
    if(ok) ok=bus_.write(r_.oe,oe & ~owned());
    if(ok) {value_=(value_ & ~owned())|bit(r_.sync_n)|bit(r_.led_cs_n)|bit(r_.ldac_n)|bit(r_.clr_n);
      ok=bus_.write(r_.output,value_) && bus_.write(r_.oe,(oe & ~owned())|outputs());}
    uint16_t ctrl=0;
    if(ok) ok=frame(0x022000,24,false) && frame(0x032000,24,false) && read_locked(0x8080,ctrl);
    bool device_error=ok && (ctrl==0xffff || (ctrl&0x10));
    if(ok && !device_error) {bus_.delay_us(25);ok=frame(0x010002,24,false) && read_locked(0x8080,ctrl);device_error=ok && ((ctrl&0x17)!=2);bus_.delay_us(15);}
    ready_=ok && !device_error;
    if(!ready_) idle();
    bus_.release();return !ok ? ZotinoResult::IO_ERROR : device_error ? ZotinoResult::DEVICE_ERROR : ZotinoResult::OK;
  }
  // All supplied channels are staged under one lock, then committed by LDAC.
  // Failure makes state unknown; never automatically retry or pulse LDAC.
  ZotinoResult set_dac_mu(const uint8_t *channels,const uint16_t *values,size_t count) {
    if(!channels||!values||count==0||count>32) return ZotinoResult::INVALID_CONFIG;
    uint32_t seen=0;
    for(size_t i=0;i<count;++i) {if(channels[i]>=32 || (seen&(1u<<channels[i]))) return ZotinoResult::INVALID_CONFIG;seen|=1u<<channels[i];}
    auto start=begin();if(start!=ZotinoResult::OK)return start;
    bool ok=true;
    for(size_t i=0;i<count && ok;++i) ok=frame(0xc00000u|(uint32_t(channels[i]+8)<<16)|values[i],24,false);
    if(ok) {bus_.delay_us(2);ok=drive(r_.ldac_n,false);if(ok)bus_.delay_us(1);if(ok)ok=drive(r_.ldac_n,true);}
    return finish(ok);
  }
  ZotinoResult set_voltage(uint8_t channel,double voltage) {
    uint16_t code;if(!voltage_to_mu(voltage,code))return ZotinoResult::INVALID_CONFIG;
    return set_dac_mu(&channel,&code,1);
  }
  ZotinoResult set_leds(uint8_t leds) {auto s=begin();if(s!=ZotinoResult::OK)return s;return finish(frame(leds,8,true));}
  ZotinoResult read_dac_mu(uint8_t channel,uint16_t &value) {
    if(channel>=32)return ZotinoResult::INVALID_CONFIG;
    auto s=begin();if(s!=ZotinoResult::OK)return s;uint16_t pending=0;
    bool ok=read_locked(uint16_t((channel+8)<<7),pending);auto result=finish(ok);if(ok)value=pending;return result;
  }
  bool ready() const {return ready_;}
 private:
  static uint16_t bit(uint8_t n){return uint16_t(1u<<n);}
  uint16_t outputs()const{return bit(r_.clk)|bit(r_.mosi)|bit(r_.sync_n)|bit(r_.led_cs_n)|bit(r_.ldac_n)|bit(r_.clr_n);}
  uint16_t owned()const{return outputs()|bit(r_.miso)|bit(r_.busy);}
  bool valid()const {
    if(r_.output==r_.input||r_.output==r_.oe||r_.input==r_.oe)return false;
    uint16_t seen=0;for(auto n:{r_.clk,r_.mosi,r_.miso,r_.sync_n,r_.led_cs_n,r_.ldac_n,r_.busy,r_.clr_n}){if(n>=16 || (seen&bit(n)))return false;seen|=bit(n);}
    return !(outputs()&~r_.output_capable) && !((bit(r_.miso)|bit(r_.busy))&~r_.input_capable);
  }
  bool drive(uint8_t pin,bool high){value_=high ? value_|bit(pin) : value_&~bit(pin);return bus_.write(r_.output,value_);}
  bool frame(uint32_t word,unsigned bits,bool led,uint32_t *rx=nullptr) {
    uint8_t cs=led?r_.led_cs_n:r_.sync_n;
    if(!drive(r_.clk,false)||!drive(cs,false))return false;
    uint32_t data=0;
    for(int i=int(bits)-1;i>=0;--i){
      if(led && !drive(r_.mosi,(word>>i)&1))return false;
      bus_.delay_us(1);if(!drive(r_.clk,true))return false;
      if(!led && !drive(r_.mosi,(word>>i)&1))return false;
      bus_.delay_us(1);if(!drive(r_.clk,false))return false;
      if(rx){uint16_t input;if(!bus_.read(r_.input,input))return false;data=(data<<1)|((input>>r_.miso)&1);}
    }
    bus_.delay_us(1);if(!drive(cs,true))return false;bus_.delay_us(1);if(rx)*rx=data;return true;
  }
  bool read_locked(uint16_t op,uint16_t &value){uint32_t rx=0;if(!frame(0x050000|op,24,false))return false;bus_.delay_us(1);if(!frame(0,24,false,&rx))return false;value=rx&0xffff;return true;}
  ZotinoResult begin(){if(!ready_)return ZotinoResult::NOT_READY;if(!bus_.acquire())return ZotinoResult::BUSY;known_=bus_.read(r_.output,value_);if(!known_){ready_=false;bus_.release();return ZotinoResult::IO_ERROR;}return ZotinoResult::OK;}
  ZotinoResult finish(bool ok){if(!ok){ready_=false;idle();}bus_.release();return ok?ZotinoResult::OK:ZotinoResult::IO_ERROR;}
  void idle(){if(!known_)return;value_&=~bit(r_.clk);value_|=bit(r_.sync_n)|bit(r_.led_cs_n)|bit(r_.ldac_n)|bit(r_.clr_n);bus_.write(r_.output,value_);}
  SamplerRegisters &bus_;ZotinoRoute r_;uint16_t value_=0;bool ready_=false,known_=false;
};
inline ZotinoRoute stm_zotino_route(uint8_t slot,uint16_t out,uint16_t in){ZotinoRoute r{uint32_t(slot)*20,uint32_t(slot)*20+1,uint32_t(slot)*20+2};r.output_capable=out;r.input_capable=in;if(slot>7)r.input=r.output;return r;}
inline ZotinoRoute kasli_zotino_route(uint32_t out,uint32_t in,uint32_t oe,uint16_t oc,uint16_t ic){ZotinoRoute r{out,in,oe};r.output_capable=oc;r.input_capable=ic;if((out|in|oe)&3)r.input=r.output;return r;}
}
