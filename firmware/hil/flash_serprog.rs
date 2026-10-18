//! Maintenance firmware: UART3 serprog -> dedicated SPI1 -> configuration NOR.
//! Holds FPGA reset until explicit BOOT; never calls upstream module setup.
#![no_std]
#![no_main]
use cortex_m_rt::entry;
use stm_sys_board::hardware::hal;
use hal::prelude::*;
use hal::gpio::{Output,PushPull};
use embedded_hal::{digital::v2::{OutputPin,InputPin}, serial::{Read as SerialRead,Write as SerialWrite},
                    blocking::spi::{Write as SpiWrite,Transfer as SpiTransfer}};
use sinara_flash_serprog::{Error,Server,Stream,SpiFlashPort};
type Out = Output<PushPull>;
struct Link { tx:hal::serial::Tx<hal::device::USART3>, rx:hal::serial::Rx<hal::device::USART3> }
fn wait<T,E>(mut op:impl FnMut()->nb::Result<T,E>)->Result<T,Error>{
 let start=cortex_m::peripheral::DWT::cycle_count();
 loop {match op(){Ok(x)=>return Ok(x),Err(nb::Error::Other(_))=>return Err(Error::Io),Err(nb::Error::WouldBlock)=>{}}
  if cortex_m::peripheral::DWT::cycle_count().wrapping_sub(start)>200_000_000{return Err(Error::Io)}
 }
}
impl Stream for Link {
 fn read(&mut self,b:&mut[u8])->Result<(),Error>{for v in b{*v=wait(||self.rx.read())?;}Ok(())}
 fn write(&mut self,b:&[u8])->Result<(),Error>{for v in b{wait(||self.tx.write(*v))?;}wait(||self.tx.flush())}
}
struct Port {
 spi:hal::spi::Spi<hal::device::SPI1,hal::spi::Enabled,u8>,
 cs:hal::gpio::gpiog::PG10<Out>,
 mux:hal::gpio::gpioe::PE15<Out>,
 reset:hal::gpio::gpiog::PG0<Out>,
 done:hal::gpio::gpioe::PE1<hal::gpio::Input<hal::gpio::Floating>>,
}
impl SpiFlashPort for Port {
 fn acquire(&mut self)->Result<(),Error>{
  self.mux.set_low().map_err(|_|Error::Hardware)?;
  self.reset.set_low().map_err(|_|Error::Hardware)?;
  self.cs.set_high().map_err(|_|Error::Hardware)?;
  cortex_m::asm::delay(40_000); // 200us at 200MHz, then connect analog switch
  if self.done.is_high().map_err(|_|Error::Hardware)? { return Err(Error::Hardware); }
  self.mux.set_high().map_err(|_|Error::Hardware)?;Ok(())
 }
 fn release(&mut self){let _=self.cs.set_high();let _=self.mux.set_low();}
 fn exchange(&mut self,tx:&[u8],rx:&mut[u8])->Result<(),Error>{
  self.cs.set_low().map_err(|_|Error::Hardware)?;
  rx.fill(255);
  let result=SpiWrite::write(&mut self.spi,tx).and_then(|_|SpiTransfer::transfer(&mut self.spi,rx).map(|_|()));
  let _=self.cs.set_high(); result.map_err(|_|Error::Hardware)
 }
 fn boot(&mut self)->Result<(),Error>{
  self.acquire()?;let mut status=[0];
  let result=self.exchange(&[5],&mut status); self.release();result?;
  if status[0]&1!=0{return Err(Error::Hardware)}
  cortex_m::asm::delay(40_000);
  self.reset.set_high().map_err(|_|Error::Hardware)?;
  let start=cortex_m::peripheral::DWT::cycle_count();
  while !self.done.is_high().map_err(|_|Error::Hardware)? {
   if cortex_m::peripheral::DWT::cycle_count().wrapping_sub(start)>1_000_000_000 {
    let _=self.reset.set_low();return Err(Error::Hardware)
   }
  }Ok(())
 }
}
#[entry]
fn main()->! {
 let mut core=hal::device::CorePeripherals::take().unwrap();
 core.DCB.enable_trace();core.DWT.enable_cycle_counter();
 let p=hal::device::Peripherals::take().unwrap();
 let power=p.PWR.constrain().freeze();
 p.RCC.d2ccip1r.modify(|_,w|w.spi123sel().per());
 let ccdr=p.RCC.constrain().use_hse(8.mhz()).sysclk(200.mhz()).hclk(100.mhz()).per_ck(64.mhz()).freeze(power,&p.SYSCFG);
 let d=p.GPIOD.split(ccdr.peripheral.GPIOD);
 let e=p.GPIOE.split(ccdr.peripheral.GPIOE);
 let g=p.GPIOG.split(ccdr.peripheral.GPIOG);
 // Output defaults are low: mux disconnected, FPGA deliberately held reset.
 let reset=g.pg0.into_push_pull_output();
 let mut mux=e.pe15.into_push_pull_output();let _=mux.set_low();
 let mut cs=g.pg10.into_push_pull_output();let _=cs.set_high();
 let done=e.pe1.into_floating_input();
 let spi=p.SPI1.spi((g.pg11.into_alternate_af5(),g.pg9.into_alternate_af5(),d.pd7.into_alternate_af5()),
                   hal::spi::MODE_0,1.mhz(),ccdr.peripheral.SPI1,&ccdr.clocks);
 let serial=p.USART3.serial((d.pd8.into_alternate_af7(),d.pd9.into_alternate_af7()),
                           1_000_000.bps(),ccdr.peripheral.USART3,&ccdr.clocks).unwrap();
 let(tx,rx)=serial.split();let mut link=Link{tx,rx};let mut port=Port{spi,cs,mux,reset,done};
 let mut server=Server::default();
 loop{if server.step(&mut link,&mut port).is_err(){
   // Lost framing: discard bytes until a 20ms quiet interval, then allow SYNCNOP.
   let mut quiet=cortex_m::peripheral::DWT::cycle_count();
   loop{if link.rx.read().is_ok(){quiet=cortex_m::peripheral::DWT::cycle_count();}
     if cortex_m::peripheral::DWT::cycle_count().wrapping_sub(quiet)>4_000_000{break}}
 }}
}
