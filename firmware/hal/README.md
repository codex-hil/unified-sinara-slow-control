# Shared native SCF5 bus adapters

`fabric_client.h` (in the ESPHome component directory) is standalone MIT C++
using only stdint/stddef. `fabric_buses.h` provides bounded QSPI HAL callbacks
and uncached/fenced MMIO. `stm32_qspi_hal.h` binds QPI4-4-4 transactions to the
actual STM32H7 HAL. Board GPIO/RCC/QUADSPI bank2 setup is owned by the BSP;
it is not guessed by this library. Existing upstream Rust firmware is retained.

Native ARM Cortex-M7/H743 and RISC-V RV32IMA objects were compiled; neither is
a linked board application. ARM uses pinned ST HAL/CMSIS headers, compiler
builtin C types and existing Picolibc include/config for otherwise unused HAL
math declarations. This does not validate a full ARM libc/runtime or STM BSP.
The host fixture checks opcode, lane modes, dummy count, packing, clock limits,
failed HAL calls, range checks and MMIO. No firmware was loaded or flash written.

The QSPI bridge currently requires FPGA sys>=16*SCK. Validate real RCC kernel
clock against ClockPrescaler before starting; the HAL adapter rejects too-fast
configuration. Poll the bridge transport status; do not retry ambiguous writes.
A stream batch needs per-slot FIFO credit preflight. MMIO uses RISC-V fences or
ARM DMB. Access to unsupported Wishbone registers can trap and requires BSP
bus-fault handling; this interface does not install a trap handler.

Native ESPHome still needs its platform/runtime, standard C++ library,
startup/timers/network and board integration. Initially run its scheduler on one
owner core; the reused SMP4 CPU does not imply a multithread-safe SPI client.
Other producers must serialize shared ingress and per-slot transactions.

Reproduce compile-only checks with `python3 tools/check_native_fabric.py`.
Paths to existing SDK/toolchain/libc headers are overrideable arguments.
The SDK files are not redistributed; obtain the exact source files listed in
`evidence/scf5-stm32-sdk.json` from their upstream repository/revision,
flatten their basenames into `work/scf5-stm32-sdk`, and place
`stm32_hal_legacy.h` also under its `Legacy/` directory. The script checks
all pinned hashes before compilation. Results: `evidence/scf5-native-compile.json`.
