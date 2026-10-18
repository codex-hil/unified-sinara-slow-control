// SPDX-License-Identifier: MIT
#pragma once
#include <stdint.h>
#include <stddef.h>
namespace sinara::fabric {
constexpr uint32_t MAGIC=0x53434635;
enum class Error { OK, IO, ABI, PROFILE, BUSY, TIMEOUT, FIFO, QUEUE, RX };
enum Opcode : uint8_t { WRITE=1, READ=2, XFER=3, DELAY=4, WAIT_TRIGGER=5, PULSE=6, CS_ASSERT=7, CS_RELEASE=8 };
class Bus {
 public:
  virtual ~Bus()=default;
  virtual bool read(uint32_t byte_address,uint32_t &value)=0;
  virtual bool write(uint32_t byte_address,uint32_t value)=0;
  virtual uint32_t now_ms()=0;
  virtual void idle()=0;
};
class Client {
 public:
  explicit Client(Bus &bus):bus_(bus) {}
  static uint32_t slot_base(uint8_t slot) {return 0x100+uint32_t(slot)*0x100;}
  Error error() const {return error_;}
  bool healthy() const {return error_==Error::OK;}
  void set_timeout(uint32_t timeout) {timeout_=timeout;}
  bool identify(uint64_t expected) {
    uint32_t magic=0,abi=0,lo=0,hi=0;
    if (!read(0,magic)||!read(4,abi)||!read(56,lo)||!read(60,hi))return false;
    if(magic!=MAGIC||abi!=5)return fail(Error::ABI);
    if((uint64_t(hi)<<32|lo)!=expected)return fail(Error::PROFILE);
    return true;
  }
  bool configure(uint8_t slot,uint8_t divider,uint8_t mode) {
    if(slot>=8||mode>3)return fail(Error::PROFILE);
    uint32_t status=0,levels=0;
    const auto b=slot_base(slot);
    if(!read(b+4,status)||!read(b+16,levels))return false;
    if((status&0x1fc)||(levels&0xffff))return fail(Error::BUSY);
    return write(b,0)&&write(b+20,divider|uint32_t(mode>>1)<<8|uint32_t(mode&1)<<9)&&write(b,1);
  }
  bool execute(uint8_t slot,Opcode opcode,uint8_t selector,uint16_t length,
               const uint8_t *tx,uint8_t *rx) {
    if(!healthy()||slot>=8||selector>15)return fail(Error::PROFILE);
    const auto b=slot_base(slot);uint32_t before=0,levels=0,depth=0,status_before=0;
    const uint32_t words=1+((opcode==WRITE||opcode==XFER)?(uint32_t(length)+3)/4:0);
    if(!read(b+4,status_before)||!read(b+40,before)||!read(b+16,levels)||!read(b+60,depth))return false;
    if(status_before&0xf0)return fail(Error::QUEUE);
    if((levels&0xffff)||((status_before&4)&&!(status_before&512)))return fail(Error::BUSY);
    if(words>depth-(levels&0xffff))return fail(Error::FIFO);
    if((opcode==READ||opcode==XFER)&&((levels>>16)!=0||length>depth))return fail(Error::RX);
    uint8_t tag=++tag_;
    if(!write(b+8,uint32_t(opcode)<<28|uint32_t(selector)<<24|uint32_t(tag)<<16|length))return false;
    if(opcode==WRITE||opcode==XFER) {
      for(uint32_t i=0;i<length;i+=4) {
        uint32_t word=0;
        for(uint32_t j=0;j<4&&i+j<length;j++)word|=uint32_t(tx?tx[i+j]:0)<<(8*j);
        if(!write(b+8,word))return false;
      }
    }
    const uint32_t started=bus_.now_ms();
    while(true) {
      uint32_t status=0,done=0,transport=0;
      if(!read(b+4,status)||!read(b+40,done)||!read(44,transport))return false;
      if((status&0xf0)||transport)return fail(Error::QUEUE);
      if(uint16_t(done)==uint16_t(before+1)) {
        if(uint8_t(done>>16)!=tag)return fail(Error::QUEUE);
        break;
      }
      if(uint32_t(bus_.now_ms()-started)>=timeout_)return fail(Error::TIMEOUT);
      bus_.idle();
    }
    if(opcode==READ||opcode==XFER) {
      for(uint16_t i=0;i<length;i++) {
        uint32_t value=0;
        if(!read(b+12,value))return false;
        if(uint8_t(value>>8)!=tag||bool(value&0x10000)!=(i==length-1))return fail(Error::RX);
        if(rx)rx[i]=value;
      }
    }
    return true;
  }
  bool read(uint32_t address,uint32_t &value) {return healthy()&&bus_.read(address,value)?true:fail(Error::IO);}
  bool write(uint32_t address,uint32_t value) {return healthy()&&bus_.write(address,value)?true:fail(Error::IO);}
 private:
  bool fail(Error error) {if(error_==Error::OK)error_=error;return false;}
  Bus &bus_;uint32_t timeout_=1000;uint8_t tag_=0;Error error_=Error::OK;
};
}  // namespace sinara::fabric
