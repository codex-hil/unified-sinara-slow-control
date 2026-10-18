#include "sinara_gpio_endpoint.h"
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

namespace esphome::sinara_gpio_endpoint {
GPIOEndpoint::~GPIOEndpoint() {close_fds();}
void GPIOEndpoint::close_fds() {
#ifdef USE_HOST
  if (fd_>=0) {::close(fd_);fd_=-1;}
  if (lock_fd_>=0) {::close(lock_fd_);lock_fd_=-1;}
#endif
}
void GPIOEndpoint::on_shutdown() {close_fds();}
void GPIOEndpoint::setup() {
  if (simulated_) return;
  started_=millis();
#ifdef USE_HOST
  lock_fd_=::open(lock_path_.c_str(),O_CREAT|O_RDWR,0600);
  if (lock_fd_<0 || flock(lock_fd_,LOCK_EX|LOCK_NB)<0) {fail();close_fds();return;}
  if (stm_) {
    fd_=::open(serial_path_.c_str(),O_RDWR|O_NOCTTY|O_NONBLOCK);
    termios t{};
    if (fd_<0 || ioctl(fd_,TIOCEXCL)<0 || tcgetattr(fd_,&t)<0) {fail();close_fds();return;}
    cfmakeraw(&t);cfsetispeed(&t,B115200);cfsetospeed(&t,B115200);
    t.c_cflag|=CLOCAL|CREAD;t.c_cflag&=~CRTSCTS;
    if (tcsetattr(fd_,TCSANOW,&t)<0 || !stm_protocol_.identify()) {fail();close_fds();return;}
  } else {
    fd_=::socket(AF_INET,SOCK_STREAM|SOCK_NONBLOCK,0);
    sockaddr_in addr{};addr.sin_family=AF_INET;addr.sin_port=htons(port_);
    if (fd_<0 || inet_pton(AF_INET,host_.c_str(),&addr.sin_addr)!=1) {fail();close_fds();return;}
    if (::connect(fd_,reinterpret_cast<sockaddr *>(&addr),sizeof(addr))<0 && errno!=EINPROGRESS) {
      fail();close_fds();return;
    }
    int one=1;setsockopt(fd_,IPPROTO_TCP,TCP_NODELAY,&one,sizeof(one));
    pollfd p{fd_,POLLOUT,0};int err=0;socklen_t len=sizeof(err);
    if (::poll(&p,1,remaining_ms())<=0 || getsockopt(fd_,SOL_SOCKET,SO_ERROR,&err,&len)<0 || err) {
      fail();close_fds();return;
    }
    // LiteX RemoteServer sends an unframed banner before the first request.
    // Require a quiet 20ms gap after it; no requests have yet been sent.
    char banner[128];size_t total=0;
    while (!expired()) {
      pollfd q{fd_,POLLIN,0};int n=::poll(&q,1,total ? std::min(20,remaining_ms()) : remaining_ms());
      if (n==0 && total) break;
      if (n<=0 || total==sizeof(banner)) {fail();close_fds();return;}
      ssize_t got=::read(fd_,banner+total,sizeof(banner)-total);
      if (got<=0) {fail();close_fds();return;} total+=got;
    }
    if (total==0 || expired() || !kasli_protocol_.identify(abi_)) {fail();close_fds();return;}
  }
#else
  fail();
#endif
}
void GPIOEndpoint::dump_config() {
  ESP_LOGCONFIG("sinara_endpoint","Sinara %s GPIO endpoint: %s; native STM/Kasli runtime port not implied",
                stm_ ? "STM" : "Kasli",simulated_ ? "SIMULATION" : "host transport");
}
bool GPIOEndpoint::io(bool writing,uint8_t *data,size_t size) {
#ifdef USE_HOST
  size_t done=0;
  while (done<size) {
    const int remain=remaining_ms();
    if (remain<=0) return fail();
    pollfd p{fd_,short(writing ? POLLOUT : POLLIN),0};
    int r=::poll(&p,1,remain);
    if (r<0 && errno==EINTR) continue;
    if (r<=0 || (p.revents&(POLLERR|POLLNVAL))) return fail();
    ssize_t n;
    if (writing && !stm_) n=::send(fd_,data+done,size-done,MSG_NOSIGNAL);
    else n=writing ? ::write(fd_,data+done,size-done) : ::read(fd_,data+done,size-done);
    if (n<0 && (errno==EINTR || errno==EAGAIN)) continue;
    if (n<=0) return fail();
    done+=size_t(n);
  }
  return done==size ? true : fail();
#else
  return fail();
#endif
}
bool GPIOEndpoint::send(const uint8_t *data,size_t size) {return io(true,const_cast<uint8_t *>(data),size);}
bool GPIOEndpoint::receive(uint8_t *data,size_t size) {return io(false,data,size);}
bool GPIOEndpoint::read(uint32_t address,uint16_t &value) {
  if (is_failed() || !locked_ || expired()) return false;
  if (address!=route_.output && address!=route_.input && address!=route_.oe) return false;
  if (!simulated_) {
    uint32_t v=0;
    bool ok=stm_ ? stm_protocol_.read(address,v) : kasli_protocol_.read(address,v);
    if (!ok || v>65535) return fail();
    value=v;return true;
  }
  if (address==route_.output) value=output_;
  else if (address==route_.oe) value=oe_;
  else {
    value=0;
    if (zotino_) value=((zreply_>>(24-std::min(std::max(zbits_,1u),24u)))&1)<<zroute_.miso;
    else if (sample_bit_<128) {
      const uint16_t word=uint16_t(MODEL_RAW[7-sample_bit_/16]);
      value=((word>>(15-sample_bit_%16))&1)<<route_.adc_miso;
    }
  }
  return true;
}
void GPIOEndpoint::model_write(uint16_t value) {
  if (generic_) { output_=value;return; }
  if (zotino_) {
    const auto &r=zroute_;
    const bool was=output_&(1u<<r.sync_n), now=value&(1u<<r.sync_n);
    if(was && !now) {zbits_=0;zshift_=0;}
    // AD5372 captures MOSI on falling edges (mode 1).
    if(!now && (output_&(1u<<r.clk)) && !(value&(1u<<r.clk))) {
      zshift_=(zshift_<<1)|((value>>r.mosi)&1);++zbits_;
    }
    if(!was && now && zbits_==24) {
      unsigned addr=(zshift_>>16)&63;
      if((zshift_>>22)==3 && addr>=8 && addr<40) zdata_[addr-8]=zshift_;
      if((zshift_>>16)==1) zcontrol_=zshift_;
      if((zshift_>>16)==5) {
        uint16_t op=zshift_&0xffff;
        zreply_=op==0x8080 ? zcontrol_ : op>=0x400 && op<0x1400 ? zdata_[(op>>7)-8] : 0;
      } else zreply_=0;
    }
    output_=value;return;
  }
  auto rise=[&](uint8_t p){return !(output_&(1u<<p)) && (value&(1u<<p));};
  if (rise(route_.cnv)) sample_bit_=0;
  if ((output_&(1u<<route_.adc_clk)) && !(value&(1u<<route_.adc_clk)) && sample_bit_<128) ++sample_bit_;
  if (rise(route_.pgia_clk)) pgia_shift_=uint16_t((pgia_shift_<<1)|((value>>route_.pgia_mosi)&1));
  if (rise(route_.pgia_latch)) pgia_latched_=pgia_shift_;
  output_=value;
}
bool GPIOEndpoint::write(uint32_t address,uint16_t value) {
  if (is_failed() || !locked_ || expired()) return false;
  if (address!=route_.output && address!=route_.oe) return false;
  if (!simulated_) {
    bool ok=stm_ ? stm_protocol_.write(address,value) : kasli_protocol_.write(address,value);
    return ok ? true : fail();
  }
  if (address==route_.output) model_write(value); else oe_=value;
  return true;
}
}  // namespace esphome::sinara_gpio_endpoint
