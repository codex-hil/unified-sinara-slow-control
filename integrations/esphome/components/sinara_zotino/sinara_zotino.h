#pragma once
#include "esphome/components/sinara_gpio_endpoint/sinara_gpio_endpoint.h"
#include "esphome/components/output/float_output.h"
#include <memory>
namespace esphome::sinara_zotino {
class ZotinoComponent : public Component {
 public:
  void set_endpoint(sinara_gpio_endpoint::GPIOEndpoint *p){endpoint_=p;}
  void set_pinmux(uint8_t a,uint8_t b,uint8_t c,uint8_t d,uint8_t e,uint8_t f,uint8_t g,uint8_t h){pins_={a,b,c,d,e,f,g,h};}
  float get_setup_priority() const override {return setup_priority::DATA;}
  void setup() override {
    if(!endpoint_ || endpoint_->is_failed()){mark_failed();return;}
    auto e=endpoint_->route();sinara::ZotinoRoute r{e.output,e.input,e.oe};
    r.clk=pins_[0];r.mosi=pins_[1];r.miso=pins_[2];r.sync_n=pins_[3];r.led_cs_n=pins_[4];r.ldac_n=pins_[5];r.busy=pins_[6];r.clr_n=pins_[7];
    r.output_capable=e.output_capable;r.input_capable=e.input_capable;
    if(!endpoint_->bind_zotino(r)){mark_failed();return;}
    driver_=std::make_unique<sinara::Zotino>(*endpoint_,r);
    if(driver_->initialize()!=sinara::ZotinoResult::OK)mark_failed();
  }
  bool set_voltage(uint8_t channel,double voltage){return check(driver_ && !is_failed() && driver_->set_voltage(channel,voltage)==sinara::ZotinoResult::OK);}
  bool set_leds(uint8_t value){return check(driver_ && !is_failed() && driver_->set_leds(value)==sinara::ZotinoResult::OK);}
 protected:
  bool check(bool ok){if(!ok){status_set_error(LOG_STR("Zotino operation failed; state uncertain"));mark_failed();}return ok;}
  sinara_gpio_endpoint::GPIOEndpoint *endpoint_=nullptr;
  std::unique_ptr<sinara::Zotino> driver_;
  std::array<uint8_t,8> pins_{};
};
class ZotinoOutput : public output::FloatOutput {
 public:
  void set_parent(ZotinoComponent *p){parent_=p;}
  void set_channel(uint8_t c){channel_=c;}
 protected:
  // ESPHome level 0..1 maps to the representable bipolar DAC range.
  void write_state(float state) override {parent_->set_voltage(channel_,-10.0+double(state)*(20.0-20.0/65536));}
  ZotinoComponent *parent_=nullptr;uint8_t channel_=0;
};
}
