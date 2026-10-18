#pragma once
#include "esphome/components/spi/spi.h"
#include "esphome/core/component.h"
namespace esphome::sinara_bus {
// Behavioral MAX31865 simulation only. No physical transport or fictitious driver.
class SimDelegate : public spi::SPIDelegate {
 public:
  SimDelegate(uint32_t rate, spi::SPIBitOrder order, spi::SPIMode mode, GPIOPin *cs, uint8_t slot, uint8_t port)
      : SPIDelegate(rate,order,mode,cs), slot_(slot), port_(port) {
    // Synthetic PT100=100 ohm; Rref430 ohm. Rounded ADC code7620.
    regs_[1] = (7620 << 1) >> 8; regs_[2] = (7620 << 1) & 255;
  }
  void begin_transaction() override {
    if (active_) { ESP_LOGE("sinara_bus", "Nested transaction rejected"); return; }
    active_=true; first_=true;
    ESP_LOGD("sinara_bus", "SIM SPI begin slot=%u port=%u mode=%u hz=%u",slot_,port_,mode_,data_rate_);
    SPIDelegate::begin_transaction();
  }
  void end_transaction() override { SPIDelegate::end_transaction(); active_=false; }
  uint8_t transfer(uint8_t value) override {
    if (!active_) { ESP_LOGE("sinara_bus", "Transfer outside transaction"); return 0; }
    if(first_) { first_=false; writing_=value & 128; reg_=value & 127; return 0; }
    if(reg_>=8) return 0;
    if(writing_) {
      regs_[reg_]=value;
      if(reg_==0) { regs_[0] &= ~uint8_t(0x2e); regs_[7]=0; } // modeled conversion/fault completion
      ++reg_; return 0;
    }
    return regs_[reg_++];
  }
 protected:
  uint8_t regs_[8]{},slot_,port_,reg_{0};
  bool active_{false},first_{true},writing_{false};
};
class AddressedSPI : public spi::SPIBus {
 public:
  uint8_t slot=0, port=0;
  bool is_hw() override { return false; }
  spi::SPIDelegate *get_delegate(uint32_t rate, spi::SPIBitOrder order, spi::SPIMode mode, GPIOPin *cs, bool release, bool write_only) override {
    return new SimDelegate(rate,order,mode,cs,slot,port);
  }
};
class AddressedBus : public Component {
 public:
  void set_route(uint8_t slot,uint8_t port) { spi_.slot=slot;spi_.port=port; }
  bool gpio_read(uint8_t n) { return gpio_[n]; }
  void gpio_write(uint8_t n,bool v) { gpio_[n]=v; ESP_LOGD("sinara_bus","SIM GPIO slot=%u port=%u line=%u value=%u",spi_.slot,spi_.port,n,v); }
  spi::SPIBus *get_spi_bus() { return &spi_; }
  void dump_config() override { ESP_LOGCONFIG("sinara_bus", "SIMULATION ONLY: addressed SPI slot=%u port=%u",spi_.slot,spi_.port); }
 protected:
  AddressedSPI spi_;
  bool gpio_[16]{};
};
class SimGPIO : public GPIOPin {
 public:
  void set_bus(AddressedBus *b) { bus_=b; }
  void set_number(uint8_t n) { number_=n; }
  void set_inverted(bool v) { inverted_=v; }
  void set_flags(gpio::Flags f) { flags_=f; }
  void setup() override {}
  void pin_mode(gpio::Flags f) override {flags_=f;}
  gpio::Flags get_flags() const override {return flags_;}
  bool digital_read() override {return bus_->gpio_read(number_) != inverted_;}
  void digital_write(bool v) override {bus_->gpio_write(number_,v != inverted_);}
 protected:
  AddressedBus *bus_{nullptr}; uint8_t number_{0}; bool inverted_{false}; gpio::Flags flags_{};
};
}
