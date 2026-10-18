#define STM32H743xx
#include "stm32h7xx_hal_dma.h"
#include "stm32h7xx_hal_mdma.h"
#include "stm32h7xx_hal_qspi.h"
extern "C" uint32_t HAL_GetTick(void);
#include "stm32_qspi_hal.h"
static_assert(sizeof(uint32_t)==4&&sizeof(uintptr_t)==4,"native ARM32 types required");
extern "C" bool scf5_stm_read(QSPI_HandleTypeDef *handle) {
 sinara::fabric::STM32QuadHAL hal(*handle,100000000,100000000);
 sinara::fabric::QSPIBus bus(hal,100000000,6250000);
 uint32_t value=0;return bus.read(0,value)&&value==sinara::fabric::MAGIC;
}
