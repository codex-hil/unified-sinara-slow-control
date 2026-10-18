#include "esphome/core/log.h"
#include "addrspi.h"

namespace esphome {
namespace addrspi {

static const char *TAG = "addrspi";

void ADDRSPIComponent::setup() {
  ESP_LOGD(TAG, "ADDRSPI setup with %d address pins (%d channels)", address_pins_.size(), max_channel_ + 1);

  // Setup all address pins
  for (size_t i = 0; i < address_pins_.size(); i++) {
    if (address_pins_[i]) {
      address_pins_[i]->setup();
      ESP_LOGV(TAG, "Configured address pin %d", i);
    }
  }

  // Force initial channel selection
  current_channel_ = 255;  // Invalid channel to force selection
  select_channel(0);

  ESP_LOGD(TAG, "ADDRSPI setup complete");
}

void ADDRSPIComponent::dump_config() {
  ESP_LOGCONFIG(TAG, "ADDRSPI:");
  ESP_LOGCONFIG(TAG, "  Address Pins: %d", address_pins_.size());
  ESP_LOGCONFIG(TAG, "  Max Channels: %d", max_channel_ + 1);

  for (size_t i = 0; i < address_pins_.size(); i++) {
    LOG_PIN("  Address Pin %d: ", address_pins_[i]);
  }

  ESP_LOGCONFIG(TAG, "  Current Channel: %d", current_channel_);
}

void ADDRSPIComponent::select_channel(uint8_t channel) {
  if (channel > max_channel_) {
    ESP_LOGE(TAG, "Invalid channel %d (max: %d)", channel, max_channel_);
    return;
  }

  // Distinct nested mux instances may share physical address pins. Their local
  // cached channels cannot establish the current wire levels; reapply every frame.

  ESP_LOGD(TAG, "Selecting channel %d", channel);
  current_channel_ = channel;

  // Generic bit extraction and pin setting
  for (size_t i = 0; i < address_pins_.size(); i++) {
    uint8_t bit_val = (channel >> i) & 1;

    if (address_pins_[i]) {
      address_pins_[i]->digital_write(bit_val);
      ESP_LOGV(TAG, "Set address pin %d to %d", i, bit_val);
    }
  }

  delayMicroseconds(10);  // Address pin settling time
}

// ADDRSPISPIDelegate implementations
void ADDRSPISPIDelegate::begin_transaction() {
  ESP_LOGV("addrspi", "Channel %d: begin_transaction", channel_);
  parent_->select_channel(channel_);
  delegate_->begin_transaction();
}

void ADDRSPISPIDelegate::end_transaction() {
  ESP_LOGV("addrspi", "Channel %d: end_transaction", channel_);
  delegate_->end_transaction();
}

uint8_t ADDRSPISPIDelegate::transfer(uint8_t data) {
  ESP_LOGVV("addrspi", "Channel %d: transfer 0x%02X", channel_, data);
  return delegate_->transfer(data);
}

void ADDRSPISPIDelegate::transfer(uint8_t *ptr, size_t length) { delegate_->transfer(ptr, length); }

void ADDRSPISPIDelegate::transfer(const uint8_t *txbuf, uint8_t *rxbuf, size_t length) {
  delegate_->transfer(txbuf, rxbuf, length);
}

void ADDRSPISPIDelegate::write(uint16_t data, size_t num_bits) { delegate_->write(data, num_bits); }

void ADDRSPISPIDelegate::write16(uint16_t data) { delegate_->write16(data); }

void ADDRSPISPIDelegate::write_array(const uint8_t *data, size_t length) { delegate_->write_array(data, length); }

void ADDRSPISPIDelegate::read_array(uint8_t *data, size_t length) { delegate_->read_array(data, length); }

spi::SPIDelegate *ADDRSPIChannel::register_device(spi::SPIClient *device, spi::SPIMode mode, spi::SPIBitOrder bit_order,
                                                  uint32_t data_rate, GPIOPin *cs_pin, bool release_device,
                                                  bool write_only) {
  ESP_LOGD(TAG, "Channel %d: registering SPI device", channel_);

  if (!parent_) {
    ESP_LOGE(TAG, "Channel %d: parent not set", channel_);
    return nullptr;
  }

  // Register device with the parent SPI bus (ADDRSPIComponent's parent)
  auto *delegate =
      parent_->parent_->register_device(device, mode, bit_order, data_rate, cs_pin, release_device, write_only);
  if (!delegate) {
    ESP_LOGE(TAG, "Channel %d: failed to register device with parent SPI", channel_);
    return nullptr;
  }

  ESP_LOGD(TAG, "Channel %d: registered successfully", channel_);

  // Wrap the delegate in our ADDRSPI-specific delegate
  return new ADDRSPISPIDelegate(parent_, channel_, delegate);
}

}  // namespace addrspi
}  // namespace esphome
