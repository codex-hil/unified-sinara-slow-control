// SPDX-License-Identifier: MIT
#pragma once
// Include the board's stm32h7xx_hal.h (and enable HAL_QSPI_MODULE_ENABLED)
// before this header. GPIO/clock/mux setup is owned by the reviewed board BSP.
#include "fabric_buses.h"
namespace sinara::fabric {
class STM32QuadHAL : public QuadHAL {
 public:
  STM32QuadHAL(QSPI_HandleTypeDef &handle,uint32_t kernel_hz,uint32_t fpga_sys_hz)
      :handle_(handle),valid_(kernel_hz && fpga_sys_hz &&
        uint64_t(kernel_hz)*16<=uint64_t(fpga_sys_hz)*(handle.Init.ClockPrescaler+1)) {}
  bool transfer(uint8_t opcode,uint32_t address,uint8_t dummy,const uint8_t *tx,
                uint8_t *rx,size_t bytes,uint32_t timeout) override {
    if(!valid_||!bytes||bytes>0xffffffffu||(bool(tx)==bool(rx)))return false;
    QSPI_CommandTypeDef c{};
    c.InstructionMode=QSPI_INSTRUCTION_4_LINES;c.Instruction=opcode;
    c.AddressMode=QSPI_ADDRESS_4_LINES;c.AddressSize=QSPI_ADDRESS_24_BITS;c.Address=address;
    c.AlternateByteMode=QSPI_ALTERNATE_BYTES_NONE;c.DataMode=QSPI_DATA_4_LINES;
    c.DummyCycles=dummy;c.NbData=bytes;c.DdrMode=QSPI_DDR_MODE_DISABLE;
    c.DdrHoldHalfCycle=QSPI_DDR_HHC_ANALOG_DELAY;c.SIOOMode=QSPI_SIOO_INST_EVERY_CMD;
    const uint32_t start=HAL_GetTick();
    if(HAL_QSPI_Command(&handle_,&c,timeout)!=HAL_OK)return false;
    const uint32_t elapsed=uint32_t(HAL_GetTick()-start);if(elapsed>=timeout)return false;
    return (rx?HAL_QSPI_Receive(&handle_,rx,timeout-elapsed):
               HAL_QSPI_Transmit(&handle_,const_cast<uint8_t *>(tx),timeout-elapsed))==HAL_OK;
  }
  uint32_t now_ms() override {return HAL_GetTick();}
  void idle() override {}
 private:QSPI_HandleTypeDef &handle_;bool valid_;
};
}
