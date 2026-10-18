// SPDX-License-Identifier: GPL-3.0-or-later
#include "sinara_fpga.h"
#include "esphome/core/log.h"
#include <cstring>
#include <algorithm>
#ifdef USE_HOST
#include <fcntl.h>
#include <poll.h>
#include <sys/file.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <arpa/inet.h>
#include <netinet/tcp.h>
#include <termios.h>
#include <unistd.h>
#include <cerrno>
#endif
namespace esphome::sinara_fpga {
using namespace sinara::fabric;
static void put(uint8_t *p,uint32_t v) {p[0]=v>>24;p[1]=v>>16;p[2]=v>>8;p[3]=v;}
static uint32_t get(const uint8_t *p) {return uint32_t(p[0])<<24|uint32_t(p[1])<<16|uint32_t(p[2])<<8|p[3];}
bool FPGAComponent::error() {if(!is_failed()){ESP_LOGE("sinara_fpga","SCF5 client error=%u",unsigned(client_.error()));status_set_error(LOG_STR("SCF5 operation failed; no automatic retry"));mark_failed();}return false;}
FPGAComponent::~FPGAComponent() {on_shutdown();}
void FPGAComponent::on_shutdown() {
#ifdef USE_HOST
 if(fd_>=0){close(fd_);fd_=-1;}if(lock_fd_>=0){close(lock_fd_);lock_fd_=-1;}
#endif
}
bool FPGAComponent::io(bool sending,uint8_t *data,size_t size) {
#ifdef USE_HOST
 const uint32_t started=millis();size_t done=0;
 while(done<size) {
  uint32_t elapsed=uint32_t(millis()-started);if(elapsed>=timeout_)return error();
  pollfd p{fd_,short(sending?POLLOUT:POLLIN),0};
  int n=poll(&p,1,timeout_-elapsed);if(n<0&&errno==EINTR)continue;
  if(n<=0||(p.revents&(POLLERR|POLLNVAL)))return error();
  ssize_t count;
  if(sending)count=stm_?::write(fd_,data+done,size-done):send(fd_,data+done,size-done,MSG_NOSIGNAL);
  else count=::read(fd_,data+done,size-done);
  if(count<0&&(errno==EINTR||errno==EAGAIN))continue;
  if(count<=0)return error();done+=count;
 }
 return true;
#else
 return error();
#endif
}
void FPGAComponent::setup() {
#ifdef USE_HOST
 lock_fd_=open(lock_path_.c_str(),O_CREAT|O_RDWR,0600);
 if(lock_fd_<0||flock(lock_fd_,LOCK_EX|LOCK_NB)<0){error();return;}
 if(stm_) {
  fd_=open(serial_path_.c_str(),O_RDWR|O_NOCTTY|O_NONBLOCK);termios t{};
  if(fd_<0||ioctl(fd_,TIOCEXCL)<0||tcgetattr(fd_,&t)<0){error();return;}
  cfmakeraw(&t);cfsetispeed(&t,B115200);cfsetospeed(&t,B115200);t.c_cflag|=CLOCAL|CREAD;t.c_cflag&=~CRTSCTS;
  if(tcsetattr(fd_,TCSANOW,&t)<0){error();return;}
 } else {
  fd_=socket(AF_INET,SOCK_STREAM|SOCK_NONBLOCK,0);sockaddr_in a{};
  a.sin_family=AF_INET;a.sin_port=htons(port_);
  if(fd_<0||inet_pton(AF_INET,host_.c_str(),&a.sin_addr)!=1){error();return;}
  if(connect(fd_,reinterpret_cast<sockaddr *>(&a),sizeof(a))<0&&errno!=EINPROGRESS){error();return;}
  pollfd p{fd_,POLLOUT,0};int e=0;socklen_t len=sizeof(e);
  if(poll(&p,1,timeout_)<=0||getsockopt(fd_,SOL_SOCKET,SO_ERROR,&e,&len)<0||e){error();return;}
  int one=1;setsockopt(fd_,IPPROTO_TCP,TCP_NODELAY,&one,sizeof(one));
  // Drain the initial LiteX banner before the first framed request.
  size_t total=0;uint8_t banner[128];const uint32_t start=millis();
  while(uint32_t(millis()-start)<timeout_) {
   pollfd q{fd_,POLLIN,0};int n=poll(&q,1,total?20:int(timeout_));if(n==0&&total)break;
   if(n<=0||total==sizeof(banner)){error();return;}
   ssize_t got=::read(fd_,banner+total,sizeof(banner)-total);if(got<=0){error();return;}total+=got;
  }
  if(!total){error();return;}
 }
 if(!client_.identify(build_id_)){error();return;}
 if(initialize_) {
  uint32_t enabled=0;if(!client_.read(12,enabled)||enabled){error();return;}
  if(!client_.write(16,interlocks_)||!client_.write(20,active_low_)||!client_.write(24,triggers_)||!client_.write(28,width_)||!client_.write(68,ready_mask_)||!client_.write(72,ready_low_)||!client_.write(36,stm_trigger_)){error();return;}
  // Wait for boot direction transaction, then commit all configured directions.
  const uint32_t start=millis();uint32_t status=0;
  do {if(!client_.read(8,status)){error();return;}if(uint32_t(millis()-start)>=timeout_){error();return;}idle();}while(status&16);
  if(!client_.write(32,4)){error();return;}
  do {if(!client_.read(8,status)){error();return;}if(uint32_t(millis()-start)>=timeout_){error();return;}idle();}while(status&16);
 }
#else
 error();
#endif
}
bool FPGAComponent::exchange(uint8_t op,uint32_t address,uint32_t value,uint32_t &reply) {
 if(is_failed()||(address&3))return false;
 if(stm_) {
  uint8_t tx[16]={'S','C',2,op},rx[16]{};put(tx+4,++sequence_);put(tx+8,address+base_);put(tx+12,value);
  if(!io(true,tx,16)||!io(false,rx,16))return false;
  if(rx[0]!='S'||rx[1]!='C'||rx[2]!=2||rx[3]!=0||get(rx+4)!=sequence_||get(rx+8)!=address+base_)return error();
  reply=get(rx+12);return true;
 }
 uint8_t tx[20]={0x4e,0x6f,0x10,0x44,0,0,0,0,0,0x0f,0,0},rx[20]{};
 if(op==1) {tx[11]=1;put(tx+12,0);put(tx+16,address+base_);}
 else {tx[10]=1;put(tx+12,address+base_);put(tx+16,value);}
 if(!io(true,tx,20))return false;
 if(op==1) {
  if(!io(false,rx,20)||std::memcmp(tx,rx,4)||rx[9]!=15||rx[10]!=1||rx[11]!=0||get(rx+12)!=0)return error();
  reply=get(rx+16);return true;
 }
 // Fence at the side-effect-free global transport-status register, never RX/FIFO.
 return exchange(1,44,0,reply)&&reply==0;
}
bool FPGAComponent::read(uint32_t address,uint32_t &value) {return exchange(1,address,0,value);}
bool FPGAComponent::write(uint32_t address,uint32_t value) {uint32_t ignored;return exchange(2,address,value,ignored);}
bool FPGAComponent::begin(uint8_t slot,uint8_t selector,uint32_t rate,spi::SPIMode mode) {
 if(locked_||!healthy()||rate==0)return error();locked_=true;selector_=selector;
 uint32_t divisor=(hz_+rate-1)/rate;
 if(divisor<4)divisor=4;if(divisor>257){locked_=false;return error();}
 if(!client_.configure(slot,divisor-2,mode)||!client_.execute(slot,CS_ASSERT,selector,0,nullptr,nullptr))return error();
 return true;
}
void FPGAComponent::end(uint8_t slot) {
 if(locked_&&healthy()&&!client_.execute(slot,CS_RELEASE,0,0,nullptr,nullptr))error();
 locked_=false;
}
bool FPGAComponent::transfer(uint8_t slot,uint8_t selector,const uint8_t *tx,uint8_t *rx,size_t length) {
 if(!locked_||!healthy()||length>65535)return error();
 if(!length)return true;
 if(!client_.execute(slot,rx?(tx?XFER:READ):WRITE,selector,length,tx,rx))return error();return true;
}
bool FPGAComponent::gpio(uint8_t slot,uint8_t line,bool output,bool value) {
 if(locked_||!healthy()||slot>=8||line>=16)return error();
 uint32_t b=Client::slot_base(slot),old=0,oe=0,control=0,status=0;
 if(!client_.read(b+24,old)||!client_.read(b+28,oe)||!client_.read(b,control)||!client_.read(b+4,status))return error();
 uint32_t desired=output?oe|(1u<<line):oe&~(1u<<line);
 if(output&&!client_.write(b+24,value?old|(1u<<line):old&~(1u<<line)))return error();
 if(desired!=oe) {
  if(status&0x104||!client_.write(b,0)||!client_.write(b+28,desired))return error();
  if(slot<6&&line>=8) {
   if(!client_.write(32,4))return error();uint32_t start=millis();
   do {if(!client_.read(8,status))return error();if(uint32_t(millis()-start)>=timeout_)return error();idle();}while(status&16);
  }
  if(!client_.write(b,control))return error();
 }
 return true;
}
bool FPGAComponent::gpio_read(uint8_t slot,uint8_t line) {uint32_t value=0;if(!healthy()||!client_.read(Client::slot_base(slot)+56,value)){error();return false;}return (value>>line)&1;}
static uint8_t reverse(uint8_t v) {uint8_t r=0;for(int i=0;i<8;i++){r=(r<<1)|(v&1);v>>=1;}return r;}
class Delegate : public spi::SPIDelegate {
 public:
  Delegate(FPGAComponent &root,uint8_t slot,uint8_t selector,uint32_t rate,spi::SPIBitOrder order,spi::SPIMode mode):root_(root),slot_(slot),selector_(selector) {data_rate_=rate;bit_order_=order;mode_=mode;}
  void begin_transaction() override {active_=root_.begin(slot_,selector_,data_rate_,mode_);}
  void end_transaction() override {if(active_)root_.end(slot_);active_=false;}
  uint8_t transfer(uint8_t value) override {uint8_t rx;transfer(&value,&rx,1);return rx;}
  void transfer(const uint8_t *tx,uint8_t *rx,size_t n) override {
   // Finite chunks fit the RX FIFO; hardware CS remains held across chunks.
   for(size_t i=0;i<n;i+=root_.chunk_limit()) {
    size_t count=std::min(root_.chunk_limit(),n-i);uint8_t bytes[64];const uint8_t *source=tx?tx+i:nullptr;
    if(tx&&bit_order_==spi::BIT_ORDER_LSB_FIRST){for(size_t j=0;j<count;j++)bytes[j]=reverse(tx[i+j]);source=bytes;}
    bool ok=active_&&root_.transfer(slot_,selector_,source,rx?rx+i:nullptr,count);
    if(!ok){if(rx)std::memset(rx,0xff,n);return;}
    if(rx&&bit_order_==spi::BIT_ORDER_LSB_FIRST)for(size_t j=0;j<count;j++)rx[i+j]=reverse(rx[i+j]);
   }
  }
  void transfer(uint8_t *data,size_t n) override {transfer(data,data,n);}
  void write(uint16_t value,size_t bits) override {
    if(bits==8){uint8_t byte=value;write_array(&byte,1);}
    else if(bits==16)spi::SPIDelegate::write16(value);
    else {ESP_LOGE("sinara_fpga","Only byte-aligned SPI writes supported");root_.unsupported(slot_);active_=false;}
  }
  void read_array(uint8_t *data,size_t n) override {transfer(nullptr,data,n);}
  void write_array(const uint8_t *data,size_t n) override {transfer(data,nullptr,n);}
  bool is_ready() override {return root_.healthy();}
 private:
  FPGAComponent &root_;uint8_t slot_,selector_;bool active_=false;
};
class HardwareSPIBus : public spi::SPIBus {
 public:
  HardwareSPIBus(FPGAComponent &root,uint8_t slot,uint8_t selector):root_(root),slot_(slot),selector_(selector) {}
  bool is_hw() override {return true;}
  spi::SPIDelegate *get_delegate(uint32_t rate,spi::SPIBitOrder order,spi::SPIMode mode,GPIOPin *cs,bool release,bool write_only) override {return new Delegate(root_,slot_,selector_,rate,order,mode);}
 private:FPGAComponent &root_;uint8_t slot_,selector_;
};
spi::SPIBus *FPGAComponent::make_spi_bus(uint8_t slot,uint8_t selector) {return new HardwareSPIBus(*this,slot,selector);}
}
