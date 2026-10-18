#![no_std]
//! Bounded raw-GPIO gateway for integration in STM RTIC firmware.
//! Not a standalone flashed image. Board must implement bounded QSPI access
//! and attest to the corrected gateware ABI before enabling the service.
pub const ABI_MAGIC: u32 = 0x53434731;
pub const FRAME_LEN: usize = 16;

#[derive(Debug, PartialEq)]
pub enum BusError { Hardware, Timeout }

pub trait RegisterBus {
    /// Must check build-specific identity. Never infer this from 0xaaaa/0x5555.
    fn compatible(&mut self) -> bool;
    /// Implementations MUST enforce this deadline (milliseconds).
    fn read(&mut self, address: u16, deadline_ms: u32) -> Result<u16, BusError>;
    fn write(&mut self, address: u16, value: u16, deadline_ms: u32) -> Result<(), BusError>;
}

fn word(frame: &[u8; FRAME_LEN], offset: usize) -> u32 {
    u32::from_be_bytes(frame[offset..offset+4].try_into().unwrap())
}

/// Exactly one request/reply. No retry, allocation, YAML or RTIO.
/// Framing/UART ownership and invocation from RTIC remain board integration work.
pub fn handle<B: RegisterBus>(bus: &mut B, request: &[u8; FRAME_LEN], deadline_ms: u32) -> [u8; FRAME_LEN] {
    let mut reply = *request;
    reply[0..2].copy_from_slice(b"SC"); reply[2] = 1;
    reply[3] = 0;
    reply[12..16].fill(0);
    if &request[0..2] != b"SC" || request[2] != 1 {
        reply[3] = 1; return reply;
    }
    if !bus.compatible() { reply[3] = 3; return reply; }
    let address = word(request, 8);
    let offset = address % 20;
    let result = match request[3] {
        0 => { reply[12..16].copy_from_slice(&ABI_MAGIC.to_be_bytes()); return reply; },
        1 if address < 160 && offset <= 2 => bus.read(address as u16, deadline_ms).map(u32::from),
        2 if address < 160 && (offset == 0 || offset == 2) && word(request, 12) <= 65535 =>
            bus.write(address as u16, word(request, 12) as u16, deadline_ms).map(|_| 0),
        1 | 2 => { reply[3] = 2; return reply; },
        _ => { reply[3] = 1; return reply; },
    };
    match result {
        Ok(value) => reply[12..16].copy_from_slice(&value.to_be_bytes()),
        Err(BusError::Hardware) => reply[3] = 3,
        Err(BusError::Timeout) => reply[3] = 4,
    }
    reply
}

#[cfg(test)]
mod tests {
    use super::*;
    struct Bus { address: u16, value: u16, compatible: bool, fail: bool }
    impl RegisterBus for Bus {
        fn compatible(&mut self) -> bool { self.compatible }
        fn read(&mut self, a:u16, d:u32) -> Result<u16,BusError> {
            assert_eq!(d,100); self.address=a;
            if self.fail { Err(BusError::Timeout) } else { Ok(self.value) }
        }
        fn write(&mut self,a:u16,v:u16,d:u32) -> Result<(),BusError> {
            assert_eq!(d,100); self.address=a; self.value=v; Ok(())
        }
    }
    fn request(op:u8,a:u32,v:u32) -> [u8;16] {
        let mut f=[0;16]; f[..4].copy_from_slice(&[b'S',b'C',1,op]);
        f[4..8].copy_from_slice(&7u32.to_be_bytes());
        f[8..12].copy_from_slice(&a.to_be_bytes()); f[12..].copy_from_slice(&v.to_be_bytes());f
    }
    fn bus() -> Bus { Bus {address:0,value:0,compatible:true,fail:false} }
    #[test] fn identify_and_preserve_sequence() {
        let f=handle(&mut bus(),&request(0,0,0),100);
        assert_eq!(word(&f,12),ABI_MAGIC);assert_eq!(word(&f,4),7);
    }
    #[test] fn roundtrip_last_slot() {
        let mut b=bus();assert_eq!(handle(&mut b,&request(2,142,65535),100)[3],0);
        assert_eq!(word(&handle(&mut b,&request(1,142,0),100),12),65535);
        assert_eq!(b.address,142);
    }
    #[test] fn reject_legacy_and_forbidden_registers() {
        let mut b=bus();b.compatible=false;
        assert_eq!(handle(&mut b,&request(0,0,0),100)[3],3);
        b.compatible=true;
        for a in [1,3,159,160,65536] {assert_eq!(handle(&mut b,&request(2,a,0),100)[3],2);}
        assert_eq!(handle(&mut b,&request(2,0,65536),100)[3],2);
    }
    #[test] fn timeout_is_explicit() {
        let mut b=bus();b.fail=true;
        assert_eq!(handle(&mut b,&request(1,0,0),100)[3],4);
    }
    #[test] fn unknown_opcode_and_version() {
        assert_eq!(handle(&mut bus(),&request(4,0,0),100)[3],1);
        let mut f=request(0,0,0);f[2]=2;
        assert_eq!(handle(&mut bus(),&f,100)[3],1);
    }
}
