#pragma once

#include "esphome/components/spi/spi.h"
#include "esphome/core/component.h"

#include <cstddef>
#include <vector>

namespace esphome {
namespace addrspi2 {

class ADDRSPI2Channel;

class ADDRSPI2SPIDelegate : public spi::SPIDelegate {
 public:
  ADDRSPI2SPIDelegate(uint8_t address, spi::SPIDelegate *delegate) : address_(address), delegate_(delegate) {}

  void begin_transaction() override;
  void end_transaction() override;
  uint8_t transfer(uint8_t data) override;
  void transfer(uint8_t *ptr, size_t length) override;
  void transfer(const uint8_t *txbuf, uint8_t *rxbuf, size_t length) override;
  void write(uint16_t data, size_t num_bits) override;
  void write16(uint16_t data) override;
  void write_array16(const uint16_t *data, size_t length) override;
  void write_array(const uint8_t *ptr, size_t length) override;
  void read_array(uint8_t *ptr, size_t length) override;
  void write_cmd_addr_data(size_t cmd_bits, uint32_t cmd, size_t addr_bits, uint32_t address, const uint8_t *data,
                           size_t length, uint8_t bus_width) override;
  bool is_ready() override;

 protected:
  void exchange_(const uint8_t *tx, uint8_t *rx, size_t length);
  bool active_{false};
  bool frame_sent_{false};
  uint8_t address_;
  spi::SPIDelegate *delegate_;
};

class ADDRSPI2Component : public Component,
                          public spi::SPIDevice<spi::BIT_ORDER_MSB_FIRST, spi::CLOCK_POLARITY_LOW,
                                                spi::CLOCK_PHASE_LEADING, spi::DATA_RATE_1MHZ> {
 public:
  void setup() override;
  void dump_config() override;
  float get_setup_priority() const override { return setup_priority::IO; }

  void set_shared_device(bool shared) { shared_device_ = shared; }
  void set_max_data_rate(uint32_t rate) { max_data_rate_ = rate; }
  void register_channel(ADDRSPI2Channel *channel) { this->channels_.push_back(channel); }
  spi::SPIDelegate *register_upstream_device(spi::SPIClient *device, spi::SPIMode mode, spi::SPIBitOrder bit_order,
                                             uint32_t data_rate, GPIOPin *cs_pin, bool release_device, bool write_only);
  void unregister_upstream_device(spi::SPIClient *device);

  void write_transaction(uint8_t address, const uint8_t *payload, size_t length);
  void transfer_transaction(uint8_t address, const uint8_t *tx_payload, uint8_t *rx_payload, size_t length);

 protected:
  bool shared_device_{false};
  uint32_t max_data_rate_{0};
  static const size_t STACK_PAYLOAD_SIZE = 16;

  std::vector<ADDRSPI2Channel *> channels_;
};

class ADDRSPI2Channel : public spi::SPIComponent {
 public:
  void set_parent(ADDRSPI2Component *parent) { this->parent_ = parent; }
  void set_address(uint8_t address) { this->address_ = address; }

  void setup() override {}
  void dump_config() override;
  spi::SPIDelegate *register_device(spi::SPIClient *device, spi::SPIMode mode, spi::SPIBitOrder bit_order,
                                    uint32_t data_rate, GPIOPin *cs_pin, bool release_device, bool write_only) override;
  void unregister_device(spi::SPIClient *device) override;

  uint8_t get_address() const { return this->address_; }
  void write_transaction(const uint8_t *payload, size_t length);
  void transfer_transaction(const uint8_t *tx_payload, uint8_t *rx_payload, size_t length);

 protected:
  ADDRSPI2Component *parent_{nullptr};
  uint8_t address_{0};
};

}  // namespace addrspi2
}  // namespace esphome
