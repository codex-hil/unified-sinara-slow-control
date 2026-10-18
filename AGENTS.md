# Unified Sinara Slow Control

Project root is on the second disk. Read STATUS.md and HARDWARE_SUPPORT.md first.
Do not equate simulated GPIO/SPI or Vivado synthesis with hardware validation.
No physical board action is currently authorized. Example connection profiles
are synthetic and hardware connect must reject use=simulation.

Keep RTIO out of slow control. Current platform direction is ESPHome/C++; retain upstream Rust for baseline/HIL diagnostics. Host tools stay Python.
Do not modify source repositories outside this isolated project. references/
contains local audit clones, pinned by evidence/source-commits.json.

STM main gateware/debug firmware differ in address width. tpr_devel fixes the
wire width, but gateware pins differ from downloaded v1.0/v1.1 schematics.
Do not program a guessed pinout. Urukul CPLD8 only; status reads also write CFG;
attenuator readback is intrusive. No RF enable, DDS timing or frequency support.

Run python3 tools/test_all.py after relevant changes. The Rust library is a core
requiring RTIC/HAL integration, not a deployable STM firmware image. The Kasli
UARTbone target is CPU-free bring-up, not final bare-metal autonomous control.
