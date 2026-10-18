#pragma once
#include "i2c_bus.h"
#include "esphome/core/component.h"
#include "esphome/core/log.h"
namespace esphome::i2c {
// Logical I2C model only: a physical SPI bridge and its protocol are pending.
class SimI2CBus : public Component, public I2CBus {
 public:
  void set_route(uint8_t s,uint8_t p) {slot_=s;port_=p;}
  ErrorCode write_readv(uint8_t addr,const uint8_t *w,size_t nw,uint8_t *r,size_t nr) override {
    if(addr!=0x48) return ERROR_NOT_ACKNOWLEDGED;
    if(nw!=1 || nr!=2 || !w || !r || w[0]!=0) return ERROR_INVALID_ARGUMENT;
    ESP_LOGD("sinara_bus","SIM virtual I2C slot=%u port=%u address=0x48 write1/read2 repeated START; SPI bridge pending",slot_,port_);
    r[0]=0x19;r[1]=0; return ERROR_OK; // Synthetic LM75B temperature25C
  }
 protected:
  uint8_t slot_{0},port_{0};
};
}
