#pragma once

#include "esphome/core/component.h"
#include "esphome/components/spi/spi.h"
#include <vector>

namespace esphome {
namespace addrspi {

class ADDRSPIComponent;

// Custom SPI delegate that switches ADDRSPI channel before each SPI operation
class ADDRSPISPIDelegate : public spi::SPIDelegate {
 public:
  ADDRSPISPIDelegate(ADDRSPIComponent *parent, uint8_t channel, spi::SPIDelegate *delegate)
      : parent_(parent), channel_(channel), delegate_(delegate) {}

  bool is_ready() override { return delegate_ && delegate_->is_ready(); }
  void begin_transaction() override;
  void end_transaction() override;
  uint8_t transfer(uint8_t data) override;
  void transfer(uint8_t *ptr, size_t length) override;
  void transfer(const uint8_t *txbuf, uint8_t *rxbuf, size_t length) override;
  void write(uint16_t data, size_t num_bits) override;
  void write16(uint16_t data) override;
  void read_array(uint8_t *data, size_t length) override;
  void write_array(const uint8_t *data, size_t length) override;

 protected:
  ADDRSPIComponent *parent_;
  uint8_t channel_;
  spi::SPIDelegate *delegate_;
};

class ADDRSPIChannel : public spi::SPIComponent {
 public:
  ADDRSPIChannel() = default;

  void set_channel(uint8_t channel) { channel_ = channel; }
  void set_parent(ADDRSPIComponent *parent) { parent_ = parent; }

  void setup() override {}
  void dump_config() override {}

  // Override register_device to return ADDRSPI-specific delegate
  spi::SPIDelegate *register_device(spi::SPIClient *device, spi::SPIMode mode, spi::SPIBitOrder bit_order,
                                    uint32_t data_rate, GPIOPin *cs_pin, bool release_device, bool write_only) override;

 protected:
  uint8_t channel_{0};
  ADDRSPIComponent *parent_{nullptr};
};

class ADDRSPIComponent : public Component,
                         public spi::SPIDevice<spi::BIT_ORDER_MSB_FIRST, spi::CLOCK_POLARITY_LOW,
                                               spi::CLOCK_PHASE_LEADING, spi::DATA_RATE_1KHZ> {
 public:
  ADDRSPIComponent() = default;

  void set_address_pins(std::vector<GPIOPin *> pins) {
    address_pins_ = std::move(pins);
    max_channel_ = (1 << address_pins_.size()) - 1;  // 2^N - 1
  }

  void setup() override;
  void dump_config() override;
  float get_setup_priority() const override { return setup_priority::IO; }

  void select_channel(uint8_t channel);

  uint8_t get_max_channel() const { return max_channel_; }
  uint8_t get_num_address_pins() const { return address_pins_.size(); }

 protected:
  std::vector<GPIOPin *> address_pins_;
  uint8_t max_channel_{0};
  uint8_t current_channel_{255};  // Invalid channel to force first selection

  friend class ADDRSPIChannel;
  friend class ADDRSPISPIDelegate;
};

}  // namespace addrspi
}  // namespace esphome
