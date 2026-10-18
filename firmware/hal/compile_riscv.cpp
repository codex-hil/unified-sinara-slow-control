#include "fabric_buses.h"
using namespace sinara::fabric;
extern "C" bool scf5_native_read(uintptr_t base,uint32_t(*clock)(),void(*idle)(),uint64_t expected) {
 MMIOBus bus(base,clock,idle);Client client(bus);
 return client.identify(expected);
}
