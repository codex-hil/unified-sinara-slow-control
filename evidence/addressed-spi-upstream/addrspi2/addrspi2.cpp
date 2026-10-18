#include "addrspi2.h"

#include "esphome/core/log.h"

#include <algorithm>
#include <cstring>

namespace esphome {
namespace addrspi2 {

static const char *const TAG = "addrspi2";

class InvalidDelegate : public spi::SPIDelegate {
 public:
  bool is_ready() override { return false; }
  uint8_t transfer(uint8_t) override { return 0; }
};
static InvalidDelegate invalid_delegate;

// One native buffer per CS scope. A byte-stream driver cannot transparently
// return RX before the whole native frame is known; reject its second operation.
void ADDRSPI2SPIDelegate::begin_transaction() {
  if (this->active_) {
    ESP_LOGE(TAG, "Nested transaction");
    return;
  }
  this->active_ = true;
  this->frame_sent_ = false;
  this->delegate_->begin_transaction();
}
void ADDRSPI2SPIDelegate::end_transaction() {
  if (this->active_) this->delegate_->end_transaction();
  this->active_ = false;
}
void ADDRSPI2SPIDelegate::exchange_(const uint8_t *tx, uint8_t *rx, size_t length) {
  if (!this->active_ || this->frame_sent_ || length == 0 || length > 4091) {
    ESP_LOGE(TAG, "Use exactly one 1..4091 byte native buffer per transaction");
    if (rx != nullptr) std::memset(rx, 0, length);
    return;
  }
  this->frame_sent_ = true;
  // 1..16-byte native frames allocate nothing. Cap at the IDF delegate's single
  // transfer limit so a long frame cannot silently become multiple bursts.
  alignas(4) uint8_t stack_tx[20] = {}, stack_rx[20] = {};
  std::vector<uint8_t> heap_tx, heap_rx;
  uint8_t *wire_tx = stack_tx, *wire_rx = rx == nullptr ? nullptr : stack_rx;
  if (length > 16) {
    heap_tx.resize((length + 4) & ~size_t(3));
    wire_tx = heap_tx.data();
    if (rx != nullptr) { heap_rx.resize((length + 4) & ~size_t(3)); wire_rx = heap_rx.data(); }
  }
  wire_tx[0] = this->address_;
  if (tx != nullptr) std::memcpy(wire_tx + 1, tx, length);
  this->delegate_->transfer(wire_tx, wire_rx, length + 1);
  if (rx != nullptr) std::memcpy(rx, wire_rx + 1, length);  // discard header RX
}
uint8_t ADDRSPI2SPIDelegate::transfer(uint8_t data) {
  uint8_t rx = 0;
  this->exchange_(&data, &rx, 1);
  return rx;
}
void ADDRSPI2SPIDelegate::transfer(uint8_t *ptr, size_t length) { this->exchange_(ptr, ptr, length); }
void ADDRSPI2SPIDelegate::transfer(const uint8_t *tx, uint8_t *rx, size_t length) {
  this->exchange_(tx, rx, length);
}
void ADDRSPI2SPIDelegate::write(uint16_t data, size_t num_bits) {
  if (num_bits == 8) { uint8_t byte = data; this->write_array(&byte, 1); }
  else if (num_bits == 16) this->write16(data);
  else ESP_LOGE(TAG, "Only byte-aligned native frames are supported");
}
void ADDRSPI2SPIDelegate::write16(uint16_t data) {
  const uint8_t bytes[] = {static_cast<uint8_t>(data >> 8), static_cast<uint8_t>(data)};
  this->write_array(bytes, 2);
}
void ADDRSPI2SPIDelegate::write_array16(const uint16_t *data, size_t length) {
  if (length == 0 || length > 2045 || data == nullptr) { ESP_LOGE(TAG, "Invalid native frame"); return; }
  uint8_t stack[16];
  std::vector<uint8_t> heap;
  uint8_t *bytes = stack;
  if (length > 8) { heap.resize(length * 2); bytes = heap.data(); }
  for (size_t i = 0; i < length; i++) { bytes[2*i] = data[i] >> 8; bytes[2*i+1] = data[i]; }
  this->write_array(bytes, length * 2);
}
void ADDRSPI2SPIDelegate::write_array(const uint8_t *ptr, size_t length) { this->exchange_(ptr, nullptr, length); }
void ADDRSPI2SPIDelegate::read_array(uint8_t *ptr, size_t length) { this->exchange_(nullptr, ptr, length); }
void ADDRSPI2SPIDelegate::write_cmd_addr_data(size_t, uint32_t, size_t, uint32_t, const uint8_t *, size_t, uint8_t) {
  ESP_LOGE(TAG, "Command/address API unsupported; supply one native byte buffer");
}
bool ADDRSPI2SPIDelegate::is_ready() { return this->delegate_ != nullptr && this->delegate_->is_ready(); }

void ADDRSPI2Component::setup() {
  // Shared mode owns one persistent head handle. Legacy mode leaves the
  // explicit helper handle lazy while children register their own handles.
  this->set_release_device(!this->shared_device_);
  if (this->shared_device_) this->set_write_only(false);
  this->spi_setup();
  if (this->shared_device_ && !this->spi_is_ready()) this->mark_failed();
}

void ADDRSPI2Component::dump_config() {
  ESP_LOGCONFIG(TAG, "ADDRSPI2:");
  LOG_PIN("  CS Pin: ", this->cs_);
  ESP_LOGCONFIG(TAG, "  Channels: %u", static_cast<unsigned>(this->channels_.size()));
  for (auto *channel : this->channels_) {
    if (channel != nullptr) {
      ESP_LOGCONFIG(TAG, "    Address: 0x%02X", channel->get_address());
    }
  }
}

spi::SPIDelegate *ADDRSPI2Component::register_upstream_device(spi::SPIClient *device, spi::SPIMode mode,
                                                              spi::SPIBitOrder bit_order, uint32_t data_rate,
                                                              GPIOPin *cs_pin, bool release_device, bool write_only) {
  if (this->parent_ == nullptr) {
    ESP_LOGE(TAG, "ADDRSPI2 has no upstream SPI bus");
    return nullptr;
  }

  if (bit_order != spi::BIT_ORDER_MSB_FIRST || mode != spi::MODE0 ||
      (this->max_data_rate_ != 0 && data_rate > this->max_data_rate_)) {
    ESP_LOGE(TAG, "Serial header router requires MSB first, MODE0 and permitted clock rate");
    return &invalid_delegate;
  }
  // All serial targets share one physical slave. Sharing its handle avoids
  // ESP-IDF's six-device limit when the head and a parallel-only peer coexist.
  if (this->shared_device_) {
    if (this->is_failed() || data_rate != this->data_rate_) {
      ESP_LOGE(TAG, "Shared head handle requires ready hub and identical child data_rate");
      return &invalid_delegate;
    }
    return this->delegate_;
  }
  // Child drivers may still declare cs_pin because many ESPHome SPI schemas require it.
  // The physical transaction must use the ADDRSPI2 hub CS so the address prefix and
  // the downstream payload remain inside one CS-low frame.
  GPIOPin *physical_cs = this->cs_ != nullptr ? this->cs_ : cs_pin;
  return this->parent_->register_device(device, mode, bit_order, data_rate, physical_cs, release_device, write_only);
}

void ADDRSPI2Component::unregister_upstream_device(spi::SPIClient *device) {
  if (this->shared_device_) return;  // Hub retains ownership; child removes only its header wrapper.
  if (this->parent_ == nullptr) {
    ESP_LOGE(TAG, "ADDRSPI2 has no upstream SPI bus");
    return;
  }
  this->parent_->unregister_device(device);
}

void ADDRSPI2Component::write_transaction(uint8_t address, const uint8_t *payload, size_t length) {
  if (length == 0 || length > 4091 || payload == nullptr) {
    ESP_LOGE(TAG, "Write payload is null");
    return;
  }

  alignas(4) uint8_t stack_buffer[20] = {};
  if (length <= STACK_PAYLOAD_SIZE) {
    stack_buffer[0] = address;
    if (length != 0) {
      std::memcpy(&stack_buffer[1], payload, length);
    }
    this->enable();
    if (!this->spi_is_ready()) { this->disable(); return; }
    this->delegate_->write_array(stack_buffer, length + 1);
    this->disable();
    return;
  }

  std::vector<uint8_t> buffer((length + 4) & ~size_t(3));
  buffer[0] = address;
  std::memcpy(&buffer[1], payload, length);
  this->enable();
  if (!this->spi_is_ready()) { this->disable(); return; }
  this->delegate_->write_array(buffer.data(), length + 1);
  this->disable();
}

void ADDRSPI2Component::transfer_transaction(uint8_t address, const uint8_t *tx_payload, uint8_t *rx_payload,
                                             size_t length) {
  if (length == 0 || length > 4091 || tx_payload == nullptr || rx_payload == nullptr) {
    ESP_LOGE(TAG, "Transfer payload is null");
    return;
  }

  alignas(4) uint8_t stack_tx[20] = {};
  alignas(4) uint8_t stack_rx[20] = {};
  if (length <= STACK_PAYLOAD_SIZE) {
    stack_tx[0] = address;
    if (length != 0) {
      std::memcpy(&stack_tx[1], tx_payload, length);
    }
    this->enable();
    if (!this->spi_is_ready()) { this->disable(); return; }
    this->delegate_->transfer(stack_tx, stack_rx, length + 1);
    this->disable();
    if (length != 0) {
      std::memcpy(rx_payload, &stack_rx[1], length);
    }
    return;
  }

  std::vector<uint8_t> tx_buffer((length + 4) & ~size_t(3));
  std::vector<uint8_t> rx_buffer((length + 4) & ~size_t(3));
  tx_buffer[0] = address;
  std::memcpy(&tx_buffer[1], tx_payload, length);
  this->enable();
  if (!this->spi_is_ready()) { this->disable(); return; }
  this->delegate_->transfer(tx_buffer.data(), rx_buffer.data(), length + 1);
  this->disable();
  std::memcpy(rx_payload, &rx_buffer[1], length);
}

void ADDRSPI2Channel::dump_config() {
  ESP_LOGCONFIG(TAG, "ADDRSPI2 Channel:");
  ESP_LOGCONFIG(TAG, "  Address: 0x%02X", this->address_);
}

spi::SPIDelegate *ADDRSPI2Channel::register_device(spi::SPIClient *device, spi::SPIMode mode,
                                                   spi::SPIBitOrder bit_order, uint32_t data_rate, GPIOPin *cs_pin,
                                                   bool release_device, bool write_only) {
  if (this->parent_ == nullptr) {
    ESP_LOGE(TAG, "ADDRSPI2 channel 0x%02X has no parent", this->address_);
    return nullptr;
  }
  if (this->devices_.count(device) != 0) {
    ESP_LOGE(TAG, "ADDRSPI2 channel 0x%02X device already registered", this->address_);
    return this->devices_[device];
  }

  auto *delegate =
      this->parent_->register_upstream_device(device, mode, bit_order, data_rate, cs_pin, release_device, write_only);
  if (delegate == nullptr) {
    ESP_LOGE(TAG, "ADDRSPI2 channel 0x%02X failed to register upstream SPI device", this->address_);
    return nullptr;
  }

  auto *wrapped = new ADDRSPI2SPIDelegate(this->address_, delegate);
  this->devices_[device] = wrapped;
  return wrapped;
}

void ADDRSPI2Channel::unregister_device(spi::SPIClient *device) {
  if (this->devices_.count(device) == 0) {
    ESP_LOGE(TAG, "ADDRSPI2 channel 0x%02X device not registered", this->address_);
    return;
  }

  delete this->devices_[device];
  this->devices_.erase(device);
  if (this->parent_ != nullptr) {
    this->parent_->unregister_upstream_device(device);
  }
}

void ADDRSPI2Channel::write_transaction(const uint8_t *payload, size_t length) {
  if (this->parent_ == nullptr) {
    ESP_LOGE(TAG, "ADDRSPI2 device 0x%02X has no parent", this->address_);
    return;
  }
  this->parent_->write_transaction(this->address_, payload, length);
}

void ADDRSPI2Channel::transfer_transaction(const uint8_t *tx_payload, uint8_t *rx_payload, size_t length) {
  if (this->parent_ == nullptr) {
    ESP_LOGE(TAG, "ADDRSPI2 device 0x%02X has no parent", this->address_);
    return;
  }
  this->parent_->transfer_transaction(this->address_, tx_payload, rx_payload, length);
}

}  // namespace addrspi2
}  // namespace esphome
