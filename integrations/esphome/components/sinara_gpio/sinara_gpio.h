#pragma once
#include "esphome/components/sinara_gpio_endpoint/sinara_gpio_endpoint.h"
#ifdef USE_SPI
#include "esphome/components/spi/spi.h"
#endif
namespace esphome::sinara_gpio {
class GPIOProvider : public Component {
 public:
  void set_endpoint(sinara_gpio_endpoint::GPIOEndpoint *endpoint) { endpoint_=endpoint; }
  float get_setup_priority() const override { return setup_priority::BUS + 1; }
  void setup() override {
    if (!endpoint_->bind_gpio()) { mark_failed(); return; }
  }
  bool healthy() const { return !is_failed() && !endpoint_->is_failed(); }
  bool begin() {
    if (transaction_ || !healthy() || !endpoint_->acquire()) return error();
    transaction_=true;return true;
  }
  void end() { if (transaction_) { endpoint_->release(); transaction_=false; } }
#ifdef USE_SPI
  spi::SPIBus *make_spi_bus(GPIOPin *clk, GPIOPin *mosi, GPIOPin *miso);
#endif
  bool set(uint8_t line, bool value, bool output) {
    if (!healthy() || (!transaction_ && !endpoint_->acquire())) return error();
    const auto r=endpoint_->route();
    uint16_t latch=0,oe=0;
    const uint16_t bit=uint16_t(1u<<line);
    bool ok=endpoint_->read(r.oe,oe);
    if (output) {
      ok=ok && (r.output_capable&bit) && endpoint_->read(r.output,latch);
      // Preload data before enabling output; preserve all unrelated bits.
      latch=value ? latch|bit : latch&~bit;
      ok=ok && endpoint_->write(r.output,latch) && endpoint_->write(r.oe,oe|bit);
    } else {
      ok=ok && (r.input_capable&bit) && endpoint_->write(r.oe,oe&~bit);
    }
    if (!transaction_) endpoint_->release();
    return ok ? true : error();
  }
  bool read(uint8_t line) {
    if (!healthy() || (!transaction_ && !endpoint_->acquire())) { error(); return false; }
    uint16_t value=0;
    bool ok=endpoint_->read(endpoint_->route().input,value);
    if (!transaction_) endpoint_->release();
    if (!ok) { error(); return false; }
    return value&(1u<<line);
  }
 private:
  bool error() {
    if (is_failed()) return false;
    status_set_error(LOG_STR("FPGA GPIO unavailable; restart required"));
    mark_failed();return false;
  }
  sinara_gpio_endpoint::GPIOEndpoint *endpoint_{};
  bool transaction_{};
};
#ifdef USE_SPI
// Existing ESPHome bitbang implementation; retain transaction ownership and
// turn an unavailable GPIO transport into an invalid all-ones sensor frame.
class GuardedDelegate : public spi::SPIDelegateBitBash {
 public:
  GuardedDelegate(GPIOProvider &owner,uint32_t hz,spi::SPIBitOrder order,spi::SPIMode mode,
                  GPIOPin *cs,GPIOPin *clk,GPIOPin *mosi,GPIOPin *miso)
      : spi::SPIDelegateBitBash(hz,order,mode,cs,clk,mosi,miso),owner_(owner) {}
  void begin_transaction() override {
    active_=owner_.begin();
    if (active_) {
      clk_pin_->digital_write(clock_polarity_);
      spi::SPIDelegate::begin_transaction();
    }
  }
  void end_transaction() override {
    if (active_) { spi::SPIDelegate::end_transaction();owner_.end();active_=false; }
  }
  uint8_t transfer(uint8_t data) override {
    if (!active_ || !owner_.healthy()) return 0xff;
    const uint8_t value=spi::SPIDelegateBitBash::transfer(data);
    return owner_.healthy() ? value : 0xff;
  }
  void transfer(const uint8_t *tx,uint8_t *rx,size_t length) override {
    for (size_t i=0;i<length;++i) {
      uint8_t value=transfer(tx ? tx[i] : 0);
      if (rx) rx[i]=value;
    }
    if (rx && !owner_.healthy()) std::memset(rx,0xff,length);
  }
  void transfer(uint8_t *data,size_t length) override { transfer(data,data,length); }
  void read_array(uint8_t *data,size_t length) override {
    spi::SPIDelegate::read_array(data,length);
    if (!owner_.healthy()) std::memset(data,0xff,length);
  }
  bool is_ready() override { return owner_.healthy(); }
 private:
  GPIOProvider &owner_;
  bool active_{};
};
class GuardedBus : public spi::SPIBus {
 public:
  GuardedBus(GPIOProvider &owner,GPIOPin *clk,GPIOPin *mosi,GPIOPin *miso)
      : SPIBus(clk,mosi,miso),owner_(owner) {}
  spi::SPIDelegate *get_delegate(uint32_t hz,spi::SPIBitOrder order,spi::SPIMode mode,
                               GPIOPin *cs,bool release,bool write_only) override {
    if (!initialized_) {
      clk_pin_->setup();clk_pin_->digital_write(true);sdo_pin_->setup();sdi_pin_->setup();
      initialized_=true;
    }
    return new GuardedDelegate(owner_,hz,order,mode,cs,clk_pin_,sdo_pin_,sdi_pin_);
  }
 private:
  GPIOProvider &owner_;
  bool initialized_{};
};
inline spi::SPIBus *GPIOProvider::make_spi_bus(GPIOPin *clk,GPIOPin *mosi,GPIOPin *miso) {
  if (!mosi) mosi=new spi::NullPin();
  if (!miso) miso=new spi::NullPin();
  return new GuardedBus(*this,clk,mosi,miso);
}
#endif
class FPGAPin : public GPIOPin {
 public:
  void set_provider(GPIOProvider *provider) { provider_=provider; }
  void set_line(uint8_t line) { line_=line; }
  void set_inverted(bool inverted) { inverted_=inverted; }
  void set_flags(gpio::Flags flags) { flags_=flags; }
  void setup() override {
    // For OUTPUT, first digital_write preloads latch and then enables OE.
    if (!(flags_&gpio::FLAG_OUTPUT)) provider_->set(line_,false,false);
  }
  void pin_mode(gpio::Flags flags) override { flags_=flags; setup(); }
  gpio::Flags get_flags() const override { return flags_; }
  bool digital_read() override { return provider_->read(line_)!=inverted_; }
  void digital_write(bool value) override {
    if (flags_&gpio::FLAG_OUTPUT) provider_->set(line_,value!=inverted_,true);
  }
 protected:
  GPIOProvider *provider_{};
  uint8_t line_{};
  bool inverted_{};
  gpio::Flags flags_{};
};
}
