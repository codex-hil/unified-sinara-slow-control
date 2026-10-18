#include <cassert>
#include <cstdint>
#include <cstring>
struct QSPI_HandleTypeDef {struct {uint32_t ClockPrescaler=15;} Init;};
struct QSPI_CommandTypeDef {uint32_t InstructionMode,Instruction,AddressMode,AddressSize,Address,AlternateByteMode,DataMode,DummyCycles,NbData,DdrMode,DdrHoldHalfCycle,SIOOMode;};
enum {QSPI_INSTRUCTION_4_LINES=4,QSPI_ADDRESS_4_LINES=4,QSPI_ADDRESS_24_BITS=24,QSPI_ALTERNATE_BYTES_NONE=0,QSPI_DATA_4_LINES=4,QSPI_DDR_MODE_DISABLE=0,QSPI_DDR_HHC_ANALOG_DELAY=0,QSPI_SIOO_INST_EVERY_CMD=0,HAL_OK=0};
static QSPI_CommandTypeDef last;static uint32_t tick=0;static unsigned calls=0;static bool fail=false;
uint32_t HAL_GetTick(){return tick;}
int HAL_QSPI_Command(QSPI_HandleTypeDef *,QSPI_CommandTypeDef *c,uint32_t timeout){assert(timeout==1000);last=*c;calls++;return fail?1:0;}
int HAL_QSPI_Receive(QSPI_HandleTypeDef *,uint8_t *data,uint32_t timeout){assert(timeout==1000);assert(last.Instruction==0x0b&&last.DummyCycles==8);assert(last.InstructionMode==4&&last.AddressMode==4&&last.DataMode==4&&last.AddressSize==24);uint32_t value=last.Address==0?0x53434635:0;data[0]=value>>24;data[1]=value>>16;data[2]=value>>8;data[3]=value;return 0;}
int HAL_QSPI_Transmit(QSPI_HandleTypeDef *,uint8_t *data,uint32_t timeout){assert(timeout==1000);assert(last.Instruction==0x32&&last.DummyCycles==0);assert(last.NbData==4);assert(data[0]==0xab&&data[1]==0xcd&&data[2]==0xef&&data[3]==0x12);return 0;}
#include "stm32_qspi_hal.h"
using namespace sinara::fabric;
int main(){
 QSPI_HandleTypeDef h;
 STM32QuadHAL hal(h,100000000,100000000);QSPIBus bus(hal,100000000,6250000);
 uint32_t value=0;assert(bus.read(0,value)&&value==MAGIC);assert(bus.write(0x108,0xabcdef12));
 uint8_t words[]={0xab,0xcd,0xef,0x12};assert(bus.stream(words,4));
 unsigned before=calls;assert(!bus.read(1,value)&&!bus.write(0x900,0));assert(calls==before);
 QSPIBus too_fast(hal,100000000,100000000);assert(!too_fast.read(0,value));assert(calls==before);
 h.Init.ClockPrescaler=1;STM32QuadHAL invalid(h,100000000,100000000);assert(!invalid.transfer(0x0b,0,8,nullptr,words,4,1000));assert(calls==before);
 fail=true;assert(!bus.write(0x108,0xabcdef12));assert(calls==before+1);
 alignas(4) uint32_t registers[0x900/4]{};MMIOBus mmio(reinterpret_cast<uintptr_t>(registers),HAL_GetTick,[](){});
 assert(mmio.write(0x108,0xfedcba98));assert(mmio.read(0x108,value)&&value==0xfedcba98);assert(!mmio.write(1,0));
 return 0;
}
