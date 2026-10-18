//! SPI-only serprog v1. NOR algorithms remain in flashrom, not this bridge.
#![no_std]
pub const ACK: u8 = 6;
pub const NAK: u8 = 0x15;
pub const WRITE_MAX: usize = 1024;
pub const READ_MAX: usize = 1024;
#[derive(Debug, PartialEq)]
pub enum Error { Io, Frame, Hardware }
pub trait Stream {
    fn read(&mut self, bytes: &mut [u8]) -> Result<(), Error>;
    fn write(&mut self, bytes: &[u8]) -> Result<(), Error>;
}
pub trait SpiFlashPort {
    // Assert FPGA reset before connecting the STM via the analog switch.
    fn acquire(&mut self) -> Result<(), Error>;
    // Disconnect SPI; intentionally KEEP FPGA reset asserted after a session.
    fn release(&mut self);
    fn boot(&mut self) -> Result<(), Error> { Err(Error::Hardware) }
    fn exchange(&mut self, tx: &[u8], rx: &mut [u8]) -> Result<(), Error>;
}
#[derive(Default)]
pub struct Server { enabled: bool }
impl Server {
    pub fn disconnect(&mut self, port: &mut impl SpiFlashPort) {
        port.release(); self.enabled = false;
    }
    pub fn step(&mut self, stream: &mut impl Stream, port: &mut impl SpiFlashPort) -> Result<(), Error> {
        let result = self.command(stream, port);
        if result.is_err() { self.disconnect(port); }
        result
    }
    fn command(&mut self, io: &mut impl Stream, port: &mut impl SpiFlashPort) -> Result<(), Error> {
        let mut op = [0u8]; io.read(&mut op)?;
        match op[0] {
            0 => io.write(&[ACK]),
            1 => io.write(&[ACK, 1, 0]),
            2 => {
                let mut map = [0u8; 33]; map[0] = ACK;
                for c in [0u8,1,2,3,4,5,8,0x10,0x11,0x12,0x13,0x14,0x15] {
                    map[1+c as usize/8] |= 1 << (c%8);
                }
                io.write(&map)
            },
            3 => io.write(b"\x06Sinara-SPI1\0\0\0\0\0"),
            4 => io.write(&[ACK, 1, 0]), // no pipelining: one-byte UART receive register
            5 => io.write(&[ACK, 8]), // only BUS_SPI
            8 => io.write(&[ACK, 0, 2, 0]), // flashrom data write 512 + opcode/address
            0x10 => io.write(&[NAK, ACK]),
            0x11 => io.write(&[ACK, 0, 4, 0]),
            0x12 => { let mut x=[0]; io.read(&mut x)?; io.write(&[if x[0]==8 {ACK} else {NAK}]) },
            0x14 => { // Fixed conservative SPI1 clock; never faster than requested.
                let mut x=[0;4]; io.read(&mut x)?;
                if u32::from_le_bytes(x) < 1_000_000 { return io.write(&[NAK]); }
                io.write(&[ACK])?; io.write(&1_000_000u32.to_le_bytes())
            },
            0x15 => {
                let mut x=[0]; io.read(&mut x)?;
                if x[0] == 0 { self.disconnect(port); }
                else { port.acquire()?; self.enabled=true; }
                io.write(&[ACK])
            },
            0x13 => {
                let mut header=[0;6]; io.read(&mut header)?;
                let n = u32::from_le_bytes([header[0],header[1],header[2],0]) as usize;
                let r = u32::from_le_bytes([header[3],header[4],header[5],0]) as usize;
                if n > WRITE_MAX || r > READ_MAX { io.write(&[NAK])?; return Err(Error::Frame); }
                let mut tx=[0;WRITE_MAX]; let mut rx=[0;READ_MAX];
                io.read(&mut tx[..n])?;
                if !self.enabled { return io.write(&[NAK]); }
                port.exchange(&tx[..n], &mut rx[..r])?;
                io.write(&[ACK])?; io.write(&rx[..r])
            },
            0x80 => { // Explicit Sinara extension, never used by flashrom itself.
                let mut magic=[0;4]; io.read(&mut magic)?;
                if &magic != b"BOOT" || self.enabled { return io.write(&[NAK]); }
                port.boot()?; io.write(&[ACK])
            },
            _ => io.write(&[NAK]),
        }
    }
}

#[cfg(test)]
extern crate std;
#[cfg(test)]
mod tests {
    use super::*;
    use std::vec::Vec;
    struct Io { input: Vec<u8>, output: Vec<u8> }
    impl Stream for Io {
        fn read(&mut self, b:&mut[u8])->Result<(),Error> {
            if self.input.len()<b.len(){return Err(Error::Io)}
            b.copy_from_slice(&self.input[..b.len()]);self.input.drain(..b.len());Ok(())
        }
        fn write(&mut self,b:&[u8])->Result<(),Error>{self.output.extend_from_slice(b);Ok(())}
    }
    #[derive(Default)] struct Port { acquisitions:u32, releases:u32, transfers:u32, boots:u32 }
    impl SpiFlashPort for Port {
        fn boot(&mut self)->Result<(),Error>{self.boots+=1;Ok(())}
        fn acquire(&mut self)->Result<(),Error>{self.acquisitions+=1;Ok(())}
        fn release(&mut self){self.releases+=1;}
        fn exchange(&mut self,tx:&[u8],rx:&mut[u8])->Result<(),Error>{assert_eq!(tx,[0x9f]);rx.copy_from_slice(&[0xef,0x40,0x18]);self.transfers+=1;Ok(())}
    }
    #[test] fn handshake_and_name(){
        for (input,expected) in [(std::vec![0x10],std::vec![NAK,ACK]),(std::vec![1],std::vec![ACK,1,0])]{
            let mut io=Io{input,output:Vec::new()};Server::default().step(&mut io,&mut Port::default()).unwrap();assert_eq!(io.output,expected);
        }
        let mut io=Io{input:std::vec![3],output:Vec::new()};Server::default().step(&mut io,&mut Port::default()).unwrap();assert_eq!(io.output.len(),17);
    }
    #[test] fn ownership_and_jedec(){
        let mut server=Server::default();let mut p=Port::default();
        for input in [std::vec![0x13,1,0,0,3,0,0,0x9f],std::vec![0x15,1],std::vec![0x13,1,0,0,3,0,0,0x9f],std::vec![0x15,0]]{
            let mut io=Io{input,output:Vec::new()};server.step(&mut io,&mut p).unwrap();
        }
        assert_eq!((p.acquisitions,p.transfers,p.releases),(1,1,1));
    }
    #[test] fn truncated_and_oversized_release(){
        for input in [std::vec![0x13,1],std::vec![0x13,0xff,0xff,0xff,0,0,0]]{
            let mut io=Io{input,output:Vec::new()};let mut p=Port::default();
            assert!(Server::default().step(&mut io,&mut p).is_err());assert_eq!(p.releases,1);assert_eq!(p.transfers,0);
        }
    }
}

#[cfg(test)]
mod boot_tests {
    use super::*;
    struct Io { bytes: std::vec::Vec<u8>, out: std::vec::Vec<u8> }
    impl Stream for Io {
        fn read(&mut self, b:&mut[u8])->Result<(),Error>{if self.bytes.len()<b.len(){return Err(Error::Io)}b.copy_from_slice(&self.bytes[..b.len()]);self.bytes.drain(..b.len());Ok(())}
        fn write(&mut self,b:&[u8])->Result<(),Error>{self.out.extend_from_slice(b);Ok(())}
    }
    #[derive(Default)] struct P { boots:u32 }
    impl SpiFlashPort for P {
        fn acquire(&mut self)->Result<(),Error>{Ok(())}
        fn release(&mut self){}
        fn boot(&mut self)->Result<(),Error>{self.boots+=1;Ok(())}
        fn exchange(&mut self,_:&[u8],_:&mut[u8])->Result<(),Error>{Ok(())}
    }
    #[test] fn boot_requires_disconnected_bus_and_magic(){
        let mut server=Server::default();let mut p=P::default();
        for (bytes,answer) in [(std::vec![0x15,1],ACK),(b"\x80BOOT".to_vec(),NAK),
                              (std::vec![0x15,0],ACK),(b"\x80NOPE".to_vec(),NAK),(b"\x80BOOT".to_vec(),ACK)] {
            let mut io=Io{bytes,out:std::vec::Vec::new()};server.step(&mut io,&mut p).unwrap();assert_eq!(io.out,[answer]);
        }assert_eq!(p.boots,1);
    }
}
