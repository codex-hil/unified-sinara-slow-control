//! Synthetic NOR behind the SAME protocol core. No physical IO.
use sinara_flash_serprog::{Error, Server, SpiFlashPort, Stream};
use std::{io::{Read,Write},net::{TcpListener,TcpStream},path::PathBuf};
struct Link(TcpStream);
impl Stream for Link {
 fn read(&mut self,b:&mut[u8])->Result<(),Error>{self.0.read_exact(b).map_err(|_|Error::Io)}
 fn write(&mut self,b:&[u8])->Result<(),Error>{self.0.write_all(b).map_err(|_|Error::Io)}
}
struct Nor { bytes: Vec<u8>, wel: bool }
impl SpiFlashPort for Nor {
 fn acquire(&mut self)->Result<(),Error>{Ok(())}
 fn release(&mut self){}
 fn boot(&mut self)->Result<(),Error>{Ok(())}
 fn exchange(&mut self,tx:&[u8],rx:&mut[u8])->Result<(),Error>{
   rx.fill(0xff);
   let cmd=*tx.first().ok_or(Error::Frame)?;
   let addr=if tx.len()>=4 {((tx[1] as usize)<<16)|((tx[2] as usize)<<8)|tx[3] as usize} else {0};
   match cmd {
    0x9f=>{for (d,s) in rx.iter_mut().zip([0xef,0x40,0x18]){*d=s;}},
    0x90=>{for(d,s)in rx.iter_mut().zip([0xef,0x17]){*d=s;}},
    0x05=>rx.fill(if self.wel {2}else{0}),
    0x35|0x15=>rx.fill(0),
    0x06=>self.wel=true,
    0x04=>self.wel=false,
    0x03|0x0b=>{let data=self.bytes.get(addr..addr+rx.len()).ok_or(Error::Frame)?;rx.copy_from_slice(data);},
    0x02 if self.wel && tx.len()>=4=>{for(i,v)in tx[4..].iter().enumerate(){let a=(addr&!255)|((addr+i)&255);*self.bytes.get_mut(a).ok_or(Error::Frame)? &= *v;}self.wel=false;},
    0x20|0x52|0xd8 if self.wel=>{let size=match cmd{0x20=>4096,0x52=>32768,_=>65536};let start=addr&!(size-1);self.bytes.get_mut(start..start+size).ok_or(Error::Frame)?.fill(255);self.wel=false;},
    0x60|0xc7 if self.wel=>{self.bytes.fill(255);self.wel=false;},
    _=>{}, // unsupported SFDP returns FF; flashrom uses its explicit chip table.
   } Ok(())
 }
}
fn main(){
 let args:Vec<_>=std::env::args().collect();let port_file=PathBuf::from(&args[1]);
 let listener=TcpListener::bind("127.0.0.1:0").unwrap();
 std::fs::write(port_file,listener.local_addr().unwrap().port().to_string()).unwrap();
 let mut port=Nor{bytes:vec![255;16*1024*1024],wel:false};
 // A sentinel outside the tested image must survive updates.
 port.bytes[0x800..0x810].copy_from_slice(b"0123456789ABCDEF");
 port.bytes[0x200000..0x200010].copy_from_slice(b"SINARA_SENTINEL!");
 for stream in listener.incoming(){
  let mut io=Link(stream.unwrap());io.0.set_nodelay(true).unwrap();io.0.set_read_timeout(Some(std::time::Duration::from_secs(30))).unwrap();
  let mut server=Server::default();while server.step(&mut io,&mut port).is_ok(){} server.disconnect(&mut port);
 }
}
