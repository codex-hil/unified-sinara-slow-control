#pragma once
#include <cstddef>
#include <cstdint>
#include <cstring>

namespace sinara {
// UART HAL or TCP socket implements bounded exact byte transfers. A protocol
// error poisons this instance; caller must reopen instead of replaying writes.
class RegisterStream {
 public:
  virtual ~RegisterStream() = default;
  virtual bool send(const uint8_t *,size_t)=0;
  virtual bool receive(uint8_t *,size_t)=0;
};
inline uint32_t be32(const uint8_t *p) {
  return uint32_t(p[0])<<24 | uint32_t(p[1])<<16 | uint32_t(p[2])<<8 | p[3];
}
inline void put32(uint8_t *p,uint32_t v) {
  p[0]=v>>24;p[1]=v>>16;p[2]=v>>8;p[3]=v;
}
constexpr uint32_t GPIO_ABI=0x53434731;
class STMRegisterProtocol {
 public:
  explicit STMRegisterProtocol(RegisterStream &stream):stream_(stream) {}
  bool identify() { uint32_t v=0;return exchange(0,0,0,v)&&v==GPIO_ABI; }
  bool read(uint32_t a,uint32_t &v) { return exchange(1,a,0,v); }
  bool write(uint32_t a,uint16_t v) { uint32_t result;return exchange(2,a,v,result); }
 private:
  bool exchange(uint8_t op,uint32_t a,uint32_t value,uint32_t &result) {
    if (failed_) return false;
    uint8_t tx[16]={'S','C',1,op},rx[16]{};
    put32(tx+4,++sequence_);put32(tx+8,a);put32(tx+12,value);
    bool ok=stream_.send(tx,16)&&stream_.receive(rx,16);
    ok=ok && rx[0]=='S' && rx[1]=='C' && rx[2]==1 && rx[3]==0 &&
       be32(rx+4)==sequence_ && be32(rx+8)==a;
    if (!ok) {failed_=true;return false;}
    result=be32(rx+12);return true;
  }
  RegisterStream &stream_;uint32_t sequence_=0;bool failed_=false;
};
class KasliRegisterProtocol {
 public:
  explicit KasliRegisterProtocol(RegisterStream &stream):stream_(stream) {}
  bool identify(uint32_t abi_address) {uint32_t v=0;return read(abi_address,v)&&v==GPIO_ABI;}
  bool read(uint32_t address,uint32_t &value) {
    if (failed_ || (address&3)) return false;
    uint8_t tx[20]={0x4e,0x6f,0x10,0x44,0,0,0,0,0,0x0f,0,1},rx[20]{};
    // LiteX RemoteServer replies at base_addr=0 (ignores return address).
    const uint32_t token=0;
    put32(tx+12,token);put32(tx+16,address);
    bool ok=stream_.send(tx,20)&&stream_.receive(rx,20);
    ok=ok && rx[0]==0x4e && rx[1]==0x6f && rx[2]==0x10 && rx[3]==0x44 &&
       rx[8]==0 && rx[9]==0x0f && rx[10]==1 && rx[11]==0 && be32(rx+12)==token;
    if (!ok) {failed_=true;return false;}
    value=be32(rx+16);return true;
  }
  bool write(uint32_t address,uint16_t value) {
    if (failed_ || (address&3)) return false;
    uint8_t tx[20]={0x4e,0x6f,0x10,0x44,0,0,0,0,0,0x0f,1,0};
    put32(tx+12,address);put32(tx+16,value);
    if (!stream_.send(tx,20)) {failed_=true;return false;}
    // LiteX writes have no reply. GPIO output/OE are safe to read: confirm the
    // ordered write before continuing, including the final PGIA latch edge.
    uint32_t actual=0;
    if (!read(address,actual) || actual!=value) {failed_=true;return false;}
    return true;
  }
 private:
  RegisterStream &stream_;bool failed_=false;
};
}  // namespace sinara
