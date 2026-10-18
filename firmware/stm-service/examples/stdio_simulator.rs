//! Host-only protocol integration fixture. NOT STM32 firmware.
use std::io::{Read, Write};
use sinara_stm_gateway::{RegisterBus, BusError, handle};
struct Memory([u16;160]);
impl RegisterBus for Memory {
    fn compatible(&mut self)->bool {true}
    fn read(&mut self,a:u16,_:u32)->Result<u16,BusError>{Ok(self.0[a as usize])}
    fn write(&mut self,a:u16,v:u16,_:u32)->Result<(),BusError>{self.0[a as usize]=v;Ok(())}
}
fn main() {
    let mut b=Memory([0;160]);let mut stdin=std::io::stdin().lock();let mut stdout=std::io::stdout().lock();
    loop {
        let mut frame=[0;16];if stdin.read_exact(&mut frame).is_err(){break;}
        let reply=handle(&mut b,&frame,100);
        stdout.write_all(&reply).unwrap();stdout.flush().unwrap();
    }
}
