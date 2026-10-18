import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.const import CONF_ID
DOMAIN = "sinara_bus"
AUTO_LOAD = ["spi"]
MULTI_CONF = True
ns = cg.esphome_ns.namespace("sinara_bus")
AddressedBus = ns.class_("AddressedBus", cg.Component)
CONFIG_SCHEMA = cv.Schema({
    cv.GenerateID(): cv.declare_id(AddressedBus),
    cv.Required("mode"): cv.one_of("simulation"),
    cv.Required("slot"): cv.int_range(min=0, max=7),
    cv.Required("port"): cv.int_range(min=0, max=7),
}).extend(cv.COMPONENT_SCHEMA)
async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    cg.add(var.set_route(config["slot"], config["port"]))

from esphome import pins
from esphome.const import CONF_NUMBER, CONF_INPUT, CONF_OUTPUT, CONF_INVERTED, CONF_MODE
SimGPIO = ns.class_("SimGPIO", cg.GPIOPin)
GPIO_SCHEMA = pins.gpio_base_schema(SimGPIO, cv.int_range(min=0,max=15), modes=[CONF_INPUT,CONF_OUTPUT]).extend({cv.Required("sinara_bus"): cv.use_id(AddressedBus)})
@pins.PIN_SCHEMA_REGISTRY.register("sinara_bus", GPIO_SCHEMA)
async def pin_to_code(config):
    var=cg.new_Pvariable(config[CONF_ID])
    bus=await cg.get_variable(config["sinara_bus"])
    cg.add(var.set_bus(bus))
    cg.add(var.set_number(config[CONF_NUMBER]))
    cg.add(var.set_inverted(config[CONF_INVERTED]))
    cg.add(var.set_flags(pins.gpio_flags_expr(config[CONF_MODE])))
    return var
