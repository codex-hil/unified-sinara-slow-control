#pragma once
// Portable GPIO/SPI driver: no RTIO, ESPHome, HAL or transport dependency.
#include <array>
#include <cstdint>

namespace sinara {
enum class SamplerResult { OK, INVALID_CONFIG, NOT_READY, BUSY, IO_ERROR };

// Implementations enforce I/O timeouts; lock covers CNV and the entire frame.
// Delay is a MINIMUM, not an exact timing promise. No operation is retried.
class SamplerRegisters {
 public:
  virtual ~SamplerRegisters() = default;
  virtual bool acquire() = 0;
  virtual void release() = 0;
  virtual bool read(uint32_t address, uint16_t &value) = 0;
  virtual bool write(uint32_t address, uint16_t value) = 0;
  virtual void delay_us(uint32_t duration) = 0;
};
struct SamplerRoute {
  uint32_t output, input, oe;
  // Logical EEM pair indices. Board/adapter profile supplies physical routing.
  uint8_t adc_clk=0, adc_miso=1, sdr=2, cnv=3;
  uint8_t pgia_clk=4, pgia_mosi=5, pgia_miso=6, pgia_latch=7;
  // Explicit electrical capabilities; do not infer these from logical OE.
  uint16_t output_capable=0, input_capable=0;
};

class Sampler {
 public:
  explicit Sampler(SamplerRegisters &bus, SamplerRoute route) : bus_(bus), route_(route) {}
  void set_revision(bool corrected_fs) { corrected_fs_=corrected_fs; }
  SamplerResult initialize(const std::array<uint16_t,8> &gains) {
    if (!valid_route() || !valid_gains(gains)) return SamplerResult::INVALID_CONFIG;
    if (!bus_.acquire()) return SamplerResult::BUSY;
    ready_=false; gains_known_=false;
    value_known_=false;
    uint16_t oe=0;
    // Release only owned lines, stage idle levels, then enable outputs.
    bool ok=bus_.read(route_.oe,oe) && bus_.read(route_.output,value_);
    value_known_=ok;
    if (ok) ok=bus_.write(route_.oe, oe & ~owned_mask());
    if (ok) {
      value_=(value_ & ~owned_mask()) | bit(route_.sdr) | bit(route_.pgia_latch);
      ok=bus_.write(route_.output,value_) &&
         bus_.write(route_.oe,(oe & ~owned_mask()) | output_mask());
    }
    ready_=ok;
    auto result=ok ? write_gains_locked(gains) : SamplerResult::IO_ERROR;
    if (result!=SamplerResult::OK) cleanup();
    bus_.release();
    return result;
  }
  SamplerResult set_gains(const std::array<uint16_t,8> &gains) {
    if (!valid_gains(gains)) return SamplerResult::INVALID_CONFIG;
    if (!ready_) return SamplerResult::NOT_READY;
    if (!bus_.acquire()) return SamplerResult::BUSY;
    value_known_=bus_.read(route_.output,value_);
    auto result=value_known_ ? write_gains_locked(gains) : SamplerResult::IO_ERROR;
    if (result!=SamplerResult::OK) { gains_known_=false; cleanup(); }
    bus_.release();
    return result;
  }
  SamplerResult sample(std::array<int16_t,8> &raw, std::array<float,8> &volts) {
    if (!ready_ || !gains_known_) return SamplerResult::NOT_READY;
    if (!bus_.acquire()) return SamplerResult::BUSY;
    std::array<int16_t,8> pending{};
    bool ok=bus_.read(route_.output,value_);
    value_known_=ok;
    if (ok) ok=drive(route_.cnv,true);
    if (ok) bus_.delay_us(1);  // >=30 ns CNV high, slow-control implementation.
    if (ok) ok=drive(route_.cnv,false);
    if (ok) bus_.delay_us(1);  // >=450 ns conversion wait after falling CNV.
    for (int channel=7; channel>=0 && ok; --channel) {
      uint16_t word=0;
      for (unsigned i=0; i<16 && ok; ++i) {
        bus_.delay_us(1);
        ok=drive(route_.adc_clk,true);
        uint16_t input=0;
        if (ok) ok=bus_.read(route_.input,input);
        if (ok) word=uint16_t((word<<1) | ((input>>route_.adc_miso)&1));
        if (ok) bus_.delay_us(1);
        if (ok) ok=drive(route_.adc_clk,false);
      }
      pending[channel]=word & 0x8000 ? int32_t(word)-65536 : word;
    }
    if (!ok) { ready_=false; cleanup(); }
    bus_.release();
    if (!ok) return SamplerResult::IO_ERROR;
    // Publish nothing until the complete eight-channel frame succeeds.
    raw=pending;
    for (unsigned i=0;i<8;++i)
      volts[i]=raw[i] * (corrected_fs_ ? 20.48f : 20.0f) / 65536.0f / gains_[i];
    return SamplerResult::OK;
  }
  bool ready() const { return ready_ && gains_known_; }
 private:
  static uint16_t bit(uint8_t n) { return uint16_t(1u<<n); }
  uint16_t output_mask() const {
    return bit(route_.adc_clk)|bit(route_.sdr)|bit(route_.cnv)|bit(route_.pgia_clk)|
           bit(route_.pgia_mosi)|bit(route_.pgia_latch);
  }
  uint16_t owned_mask() const { return output_mask()|bit(route_.adc_miso)|bit(route_.pgia_miso); }
  bool valid_route() const {
    if (route_.output==route_.input || route_.output==route_.oe || route_.input==route_.oe) return false;
    uint16_t seen=0;
    for (auto n: {route_.adc_clk,route_.adc_miso,route_.sdr,route_.cnv,
                  route_.pgia_clk,route_.pgia_mosi,route_.pgia_miso,route_.pgia_latch}) {
      if (n>=16 || (seen & bit(n))) return false;
      seen|=bit(n);
    }
    return (output_mask() & ~route_.output_capable)==0 &&
           ((bit(route_.adc_miso)|bit(route_.pgia_miso)) & ~route_.input_capable)==0;
  }
  static int gain_code(uint16_t gain) {
    switch(gain) {case 1:return 0;case 10:return 1;case 100:return 2;case 1000:return 3;default:return -1;}
  }
  static bool valid_gains(const std::array<uint16_t,8> &gains) {
    for (auto gain:gains) if (gain_code(gain)<0) return false;
    return true;
  }
  bool drive(uint8_t pin,bool high) {
    value_=high ? value_|bit(pin) : value_ & ~bit(pin);
    return bus_.write(route_.output,value_);
  }
  SamplerResult write_gains_locked(const std::array<uint16_t,8> &gains) {
    gains_known_=false;
    uint16_t word=0;
    for (unsigned i=0;i<8;++i) word|=uint16_t(gain_code(gains[i])<<(2*i));
    bool ok=drive(route_.pgia_clk,false) && drive(route_.pgia_latch,false);
    for (int i=15;i>=0 && ok;--i) {
      ok=drive(route_.pgia_mosi,(word>>i)&1);
      if (ok) bus_.delay_us(1);
      if (ok) ok=drive(route_.pgia_clk,true);
      if (ok) bus_.delay_us(1);
      if (ok) ok=drive(route_.pgia_clk,false);
    }
    if (ok) ok=drive(route_.pgia_latch,true);
    if (!ok) return SamplerResult::IO_ERROR;
    // Conservative policy; not a hardware-qualified settling specification.
    bus_.delay_us(10000);
    gains_=gains; gains_known_=true;
    return SamplerResult::OK;
  }
  void cleanup() {
    ready_=false;
    if (!value_known_) return;
    bus_.delay_us(1);
    // Best effort idle only, never replay a frame after an uncertain write.
    value_ &= ~(bit(route_.adc_clk)|bit(route_.cnv)|bit(route_.pgia_clk));
    value_ |= bit(route_.pgia_latch)|bit(route_.sdr);
    bus_.write(route_.output,value_);
  }
  SamplerRegisters &bus_;
  SamplerRoute route_;
  uint16_t value_=0;
  std::array<uint16_t,8> gains_{};
  bool ready_=false,gains_known_=false,corrected_fs_=true,value_known_=false;
};

// Same driver and GPIO ABI, distinct address units. Transport remains existing
// firmware/stm-service (STM) or LiteXRegisters (Kasli), never a new wire protocol.
inline SamplerRoute stm_sampler_route(uint8_t slot,uint16_t out_caps,uint16_t in_caps) {
  SamplerRoute r{uint32_t(slot)*20,uint32_t(slot)*20+1,uint32_t(slot)*20+2};
  r.output_capable=out_caps; r.input_capable=in_caps;
  if (slot>7) r.input=r.output;  // Fails validation without any I/O.
  return r;
}
inline SamplerRoute kasli_sampler_route(uint32_t output,uint32_t input,uint32_t oe,
                                      uint16_t out_caps,uint16_t in_caps) {
  SamplerRoute r{output,input,oe};
  r.output_capable=out_caps; r.input_capable=in_caps;
  if ((output|input|oe)&3) r.input=r.output;
  return r;
}
}  // namespace sinara
