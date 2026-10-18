// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "fabric_client.h"
#include "esphome/core/component.h"
#include "esphome/core/hal.h"
#include "esphome/components/spi/spi.h"
#include <string>
namespace esphome::sinara_fpga {
class FPGAComponent : public Component, public sinara::fabric::Bus {
 public:
  FPGAComponent():client_(*this) {}
  ~FPGAComponent() override;
  void set_config(bool stm,uint64_t id,uint32_t base,uint32_t timeout,uint32_t hz,uint16_t depth) {stm_=stm;build_id_=id;base_=base;timeout_=timeout;hz_=hz;depth_=depth;client_.set_timeout(timeout);}
  void set_lock_path(std::string p) {lock_path_=p;}
  void set_serial_path(std::string p) {serial_path_=p;}
  void set_host(std::string h,uint16_t p) {host_=h;port_=p;}
  void set_initialization(bool initialize,uint8_t mask,uint8_t low,uint8_t triggers,uint8_t ready,uint8_t ready_low,uint16_t width,bool stm_trigger) {
    initialize_=initialize;interlocks_=mask;active_low_=low;triggers_=triggers;ready_mask_=ready;ready_low_=ready_low;width_=width;stm_trigger_=stm_trigger;
  }
  float get_setup_priority() const override {return setup_priority::BUS+2;}
  void setup() override;
  void on_shutdown() override;
  bool read(uint32_t address,uint32_t &value) override;
  bool write(uint32_t address,uint32_t value) override;
  uint32_t now_ms() override {return millis();}
  void idle() override {delayMicroseconds(10);}
  spi::SPIBus *make_spi_bus(uint8_t slot,uint8_t selector);
  bool begin(uint8_t slot,uint8_t selector,uint32_t rate,spi::SPIMode mode);
  void end(uint8_t slot);
  bool transfer(uint8_t slot,uint8_t selector,const uint8_t *tx,uint8_t *rx,size_t length);
  size_t chunk_limit() const {return depth_<64?depth_:64;}
  void unsupported(uint8_t slot) {end(slot);error();}
  bool healthy() const {return !is_failed()&&client_.healthy();}
  bool gpio(uint8_t slot,uint8_t line,bool output,bool value);
  bool gpio_read(uint8_t slot,uint8_t line);
 private:
  bool io(bool sending,uint8_t *data,size_t size);
  bool error();
  bool exchange(uint8_t op,uint32_t address,uint32_t value,uint32_t &reply);
  sinara::fabric::Client client_;
  std::string serial_path_,lock_path_,host_;uint16_t port_=1234;
  int fd_=-1,lock_fd_=-1;bool stm_=true,initialize_=false,locked_=false;
  uint8_t interlocks_=0,active_low_=0,triggers_=0,ready_mask_=0,ready_low_=0,selector_=0;bool stm_trigger_=false;uint16_t width_=1,depth_=64;
  uint64_t build_id_=0;uint32_t base_=0,timeout_=1000,hz_=100000000,sequence_=0;
};
class FPGAPin : public GPIOPin {
 public:
  void set_config(FPGAComponent *root,uint8_t slot,uint8_t line,bool inverted,gpio::Flags flags) {root_=root;slot_=slot;line_=line;inverted_=inverted;flags_=flags;}
  void setup() override {if(!(flags_&gpio::FLAG_OUTPUT))root_->gpio(slot_,line_,false,false);}
  void pin_mode(gpio::Flags flags) override {flags_=flags;setup();}
  gpio::Flags get_flags() const override {return flags_;}
  bool digital_read() override {return root_->gpio_read(slot_,line_)!=inverted_;}
  void digital_write(bool value) override {if(flags_&gpio::FLAG_OUTPUT)root_->gpio(slot_,line_,true,value!=inverted_);}
 private:
  FPGAComponent *root_{};uint8_t slot_{},line_{};bool inverted_{};gpio::Flags flags_{};
};
}
