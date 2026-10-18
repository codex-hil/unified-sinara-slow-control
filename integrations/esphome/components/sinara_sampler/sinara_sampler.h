#pragma once
#include "esphome/core/component.h"
#include "esphome/components/sensor/sensor.h"
#include "esphome/components/sinara_gpio_endpoint/sinara_gpio_endpoint.h"
#include <memory>

namespace esphome::sinara_sampler {
class SamplerComponent : public PollingComponent {
 public:
  void set_endpoint(sinara_gpio_endpoint::GPIOEndpoint *endpoint) {endpoint_=endpoint;}
  void set_revision(bool corrected) {corrected_=corrected;}
  void set_gains(uint16_t a,uint16_t b,uint16_t c,uint16_t d,uint16_t e,uint16_t f,uint16_t g,uint16_t h) {gains_={a,b,c,d,e,f,g,h};}
  void set_pinmux(uint8_t a,uint8_t b,uint8_t c,uint8_t d,uint8_t e,uint8_t f,uint8_t g,uint8_t h) {pins_={a,b,c,d,e,f,g,h};}
  void set_sensor(uint8_t channel,sensor::Sensor *sensor) {sensors_[channel]=sensor;}
  float get_setup_priority() const override {return setup_priority::DATA;}
  void setup() override;
  void update() override;
  void dump_config() override;
 protected:
  sinara_gpio_endpoint::GPIOEndpoint *endpoint_=nullptr;
  std::unique_ptr<sinara::Sampler> driver_;
  std::array<uint16_t,8> gains_{};
  std::array<uint8_t,8> pins_{};
  std::array<sensor::Sensor *,8> sensors_{};
  bool corrected_=true;
};
}  // namespace esphome::sinara_sampler
