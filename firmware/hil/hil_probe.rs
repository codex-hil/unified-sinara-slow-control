//! Read-only ECP5 CSR probe using the reproduced upstream STM setup/QSPI HAL.
//! No module init, MQTT service, SPI4 transfer or ECP5 CSR writes.
//! Board setup still configures clocks/GPIO/I2C/Ethernet PHY; not a passive image.
#![no_std]
#![no_main]

use stm_sys_board::hardware::{self, SystemTimer, Systick};

#[rtic::app(device = hardware::hal::stm32, peripherals = true)]
mod app {
    use super::*;
    #[monotonic(binds = SysTick, default = true, priority = 2)]
    type Monotonic = Systick;
    #[shared]
    struct Shared {}
    #[local]
    struct Local {}

    #[init]
    fn init(c: init::Context) -> (Shared, Local, init::Monotonics) {
        let clock = SystemTimer::new(|| monotonics::now().ticks() as u32);
        let (board, _, _) = hardware::setup::setup(c.core, c.device, clock);
        let mut ecp5 = board.slots_bus.ecp5;
        log::info!("HIL_PROBE: read-only ECP5, no module initialization");
        let mut ids = [0u16; 3];
        let mut ok = true;
        for round in 0..8 {
            for (index, address) in [160u16, 161, 162].iter().enumerate() {
                let mut ready = false;
                for _ in 0..100_000 {
                    if ecp5.qspi.is_busy().is_ok() { ready = true; break; }
                }
                if !ready {
                    log::error!("HIL_PROBE: QSPI busy timeout round {} adr {}", round, address);
                    ok = false; break;
                }
                let mut data = [0u8; 2];
                // Same framing as upstream: x1, U16 read header, five dummy cycles.
                let result = ecp5.qspi.read_extended(
                    hardware::hal::xspi::QspiWord::None,
                    hardware::hal::xspi::QspiWord::U16(0x8000 | address),
                    hardware::hal::xspi::QspiWord::None, 5, &mut data);
                if result.is_err() {
                    log::error!("HIL_PROBE: QSPI read error round {} adr {}", round, address);
                    ok = false; break;
                }
                let value = u16::from_be_bytes(data);
                log::info!("HIL_PROBE: round {} adr {} value {:04x}", round, address, value);
                if round == 0 { ids[index] = value; }
                else if ids[index] != value { ok = false; }
            }
            if !ok { break; }
        }
        ok &= ids[0] == 0xaaaa && ids[1] == 0x5555 && (ids[2] == 3 || ids[2] == 4);
        if ok { log::info!("HIL_PROBE: ID_STABILITY PASS ABI {}", ids[2]); }
        else { log::error!("HIL_PROBE: ID_STABILITY FAIL"); }
        log::info!("HIL_PROBE: complete; idling, no CSR writes");
        (Shared {}, Local {}, init::Monotonics(board.systick))
    }
}
