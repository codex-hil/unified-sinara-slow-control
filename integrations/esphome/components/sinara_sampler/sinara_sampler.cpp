#include "sinara_sampler.h"
#include "esphome/core/log.h"
#include <cmath>
namespace esphome::sinara_sampler {
void SamplerComponent::setup() {
  if (endpoint_==nullptr || endpoint_->is_failed()) {mark_failed();return;}
  auto route=endpoint_->route();
  route.adc_clk=pins_[0];route.adc_miso=pins_[1];route.sdr=pins_[2];route.cnv=pins_[3];
  route.pgia_clk=pins_[4];route.pgia_mosi=pins_[5];route.pgia_miso=pins_[6];route.pgia_latch=pins_[7];
  if (!endpoint_->bind_sampler(route)) {ESP_LOGE("sinara_sampler","Endpoint already owned by another Sampler");mark_failed();return;}
  driver_=std::make_unique<sinara::Sampler>(*endpoint_,route);
  driver_->set_revision(corrected_);
  if (driver_->initialize(gains_)!=sinara::SamplerResult::OK) {
    ESP_LOGE("sinara_sampler","Initialization failed; no samples will be published");mark_failed();
  }
}
void SamplerComponent::update() {
  if (is_failed() || !driver_) return;
  std::array<int16_t,8> raw{};std::array<float,8> volts{};
  auto result=driver_->sample(raw,volts);
  if (result==sinara::SamplerResult::BUSY) {status_set_warning(LOG_STR("Endpoint busy"));return;}
  if (result!=sinara::SamplerResult::OK) {
    for (auto *s:sensors_) if (s) s->publish_state(NAN);
    ESP_LOGE("sinara_sampler","Acquisition failed; endpoint must be reopened, no automatic replay");
    mark_failed();return;
  }
  status_clear_warning();
  for (unsigned i=0;i<8;++i) if (sensors_[i]) sensors_[i]->publish_state(volts[i]);
}
void SamplerComponent::dump_config() {
  ESP_LOGCONFIG("sinara_sampler","Sampler 8-channel slow SPI/GPIO, %s reference, all channels captured together",corrected_ ? "v2.2" : "v2.1");
}
}  // namespace esphome::sinara_sampler
