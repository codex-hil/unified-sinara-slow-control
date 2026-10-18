#pragma once
#include "esphome/core/component.h"
#include "esphome/core/hal.h"
#include "esphome/core/log.h"
#include "sampler_core.h"
#include "zotino_core.h"
#include "register_protocol.h"
#include <string>

namespace esphome::sinara_gpio_endpoint {
class GPIOEndpoint : public Component, public sinara::SamplerRegisters, public sinara::RegisterStream {
 public:
  GPIOEndpoint():stm_protocol_(*this),kasli_protocol_(*this) {}
  ~GPIOEndpoint() override;
  void set_config(bool stm,bool simulated,uint32_t out,uint32_t in,uint32_t oe,uint32_t abi) {
    stm_=stm;simulated_=simulated;route_.output=out;route_.input=in;route_.oe=oe;abi_=abi;
  }
  void set_capabilities(uint16_t out,uint16_t in) {route_.output_capable=out;route_.input_capable=in;}
  void set_timeout(uint32_t ms) {timeout_ms_=ms;}
  void set_serial_path(const std::string &path) {serial_path_=path;}
  void set_host(const std::string &host,uint16_t port) {host_=host;port_=port;}
  void set_lock_path(const std::string &path) {lock_path_=path;}
  sinara::SamplerRoute route() const {return route_;}
  bool bind_gpio() {
    if (claimed_) return false;
    claimed_=true;generic_=true;return true;
  }
  bool bind_sampler(const sinara::SamplerRoute &route) {
    if (claimed_) return false;
    claimed_=true;route_=route;return true;
  }
  bool bind_zotino(const sinara::ZotinoRoute &route) {
    if (claimed_) return false;
    claimed_=true;zotino_=true;zroute_=route;return true;
  }
  float get_setup_priority() const override {return setup_priority::BUS + 2;}
  void setup() override;
  void dump_config() override;
  void on_shutdown() override;
  bool acquire() override {
    if (locked_ || is_failed()) return false;
    locked_=true;started_=millis();return true;
  }
  void release() override {locked_=false;}
  bool read(uint32_t address,uint16_t &value) override;
  bool write(uint32_t address,uint16_t value) override;
  void delay_us(uint32_t us) override {delayMicroseconds(us);}
  bool send(const uint8_t *data,size_t size) override;
  bool receive(uint8_t *data,size_t size) override;
 private:
  int remaining_ms() const {
    const uint32_t elapsed=uint32_t(millis()-started_);
    return elapsed>=timeout_ms_ ? 0 : int(timeout_ms_-elapsed);
  }
  bool expired() const {return remaining_ms()==0;}
  bool io(bool writing,uint8_t *data,size_t size);
  bool fail() {status_set_error(LOG_STR("Register transport failed; reopen required"));mark_failed();return false;}
  void close_fds();
  void model_write(uint16_t value);
  sinara::SamplerRoute route_{};
  sinara::ZotinoRoute zroute_{};
  bool zotino_=false,generic_=false;
  uint32_t zshift_=0,zreply_=0;
  unsigned zbits_=0;
  uint16_t zcontrol_=0;
  std::array<uint16_t,32> zdata_{};
  sinara::STMRegisterProtocol stm_protocol_;
  sinara::KasliRegisterProtocol kasli_protocol_;
  uint32_t abi_=0,timeout_ms_=5000,started_=0;
  bool stm_=true,simulated_=true,locked_=false,claimed_=false;
  int fd_=-1,lock_fd_=-1;
  std::string serial_path_,host_,lock_path_;
  uint16_t port_=1234,output_=0,oe_=0,pgia_shift_=0,pgia_latched_=0;
  unsigned sample_bit_=128;
  static constexpr int16_t MODEL_RAW[8]={-32768,-16384,-1,0,1,16384,32767,1234};
};
}  // namespace esphome::sinara_gpio_endpoint
