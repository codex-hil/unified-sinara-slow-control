// SPDX-License-Identifier: MIT
#pragma once
#include "fabric_client.h"
#include <stdint.h>
#include <stddef.h>
namespace sinara::fabric {
// Board implementation must bound every operation and use SDR QPI4-4-4 mode0.
// STM HAL: instruction/address/data four lines, address24 bits, MSB-first bytes.
class QuadHAL {
 public:
  virtual ~QuadHAL()=default;
  virtual bool transfer(uint8_t opcode,uint32_t byte_address,uint8_t dummy_cycles,
                        const uint8_t *tx,uint8_t *rx,size_t bytes,uint32_t deadline_ms)=0;
  virtual uint32_t now_ms()=0;
  virtual void idle()=0;
};
class QSPIBus : public Bus {
 public:
  QSPIBus(QuadHAL &hal,uint32_t sys_hz,uint32_t sck_hz,uint32_t timeout_ms=1000)
      :hal_(hal),timeout_(timeout_ms),valid_(sck_hz>0&&sck_hz<=sys_hz/16) {}
  bool read(uint32_t address,uint32_t &value) override {
    if(!valid_||(address&3)||address>=0x900)return false;
    uint8_t bytes[4];if(!hal_.transfer(0x0b,address,8,nullptr,bytes,4,timeout_))return false;
    value=uint32_t(bytes[0])<<24|uint32_t(bytes[1])<<16|uint32_t(bytes[2])<<8|bytes[3];
    if(address==44)return true;
    uint32_t status=0;return read(44,status)&&status==0;
  }
  bool write(uint32_t address,uint32_t value) override {
    if(!valid_||(address&3)||address>=0x900)return false;
    uint8_t bytes[4]={uint8_t(value>>24),uint8_t(value>>16),uint8_t(value>>8),uint8_t(value)};
    if(!hal_.transfer(0x32,address,0,bytes,nullptr,4,timeout_))return false;
    uint32_t status=0;return read(44,status)&&status==0;
  }
  // Stream ingress: packed envelopes/commands for multiple slots under one CS.
  // Caller preflights per-slot TX credits. No automatic retry after failure.
  bool stream(const uint8_t *big_endian_words,size_t bytes) {
    if(!valid_||!bytes||(bytes&3))return false;
    if(!hal_.transfer(0x32,0x40,0,big_endian_words,nullptr,bytes,timeout_))return false;
    uint32_t status=0;return read(44,status)&&status==0;
  }
  uint32_t now_ms() override {return hal_.now_ms();}
  void idle() override {hal_.idle();}
 private:QuadHAL &hal_;uint32_t timeout_;bool valid_;
};
class MMIOBus : public Bus {
 public:
  MMIOBus(uintptr_t base,uint32_t(*clock)(),void(*idle_hook)()) :base_(base),clock_(clock),idle_(idle_hook) {}
  bool read(uint32_t address,uint32_t &value) override {
    if((address&3)||address>=0x900)return false;
    fence();value=*reinterpret_cast<volatile uint32_t *>(base_+address);fence();return true;
  }
  bool write(uint32_t address,uint32_t value) override {
    if((address&3)||address>=0x900)return false;
    fence();*reinterpret_cast<volatile uint32_t *>(base_+address)=value;fence();return true;
  }
  uint32_t now_ms() override {return clock_();}
  void idle() override {idle_();}
 private:
  static void fence() {
#ifdef __riscv
    __asm__ volatile("fence iorw,iorw":::"memory");
#elif defined(__arm__) || defined(__thumb__)
    __asm__ volatile("dmb sy":::"memory");
#else
    __asm__ volatile("":::"memory");
#endif
  }
  uintptr_t base_;uint32_t(*clock_)();void(*idle_)();
};
} // namespace sinara::fabric
