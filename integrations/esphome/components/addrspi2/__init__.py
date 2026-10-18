import esphome.codegen as cg
import esphome.final_validate as fv
from esphome.components import spi
import esphome.config_validation as cv
from esphome.const import CONF_ADDRESS, CONF_DEVICES, CONF_ID

CONF_BUS_ID = "bus_id"

DEPENDENCIES = ["spi"]
CODEOWNERS = ["@wizath"]
MULTI_CONF = True

addrspi2_ns = cg.esphome_ns.namespace("addrspi2")
ADDRSPI2Component = addrspi2_ns.class_("ADDRSPI2Component", cg.Component, spi.SPIDevice)
ADDRSPI2Channel = addrspi2_ns.class_("ADDRSPI2Channel", spi.SPIComponent)

DEVICE_SCHEMA = cv.Schema(
    {
        cv.Required(CONF_BUS_ID): cv.declare_id(ADDRSPI2Channel),
        cv.Required(CONF_ADDRESS): cv.hex_uint8_t,
    }
).extend(cv.COMPONENT_SCHEMA)

CONFIG_SCHEMA = (
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(ADDRSPI2Component),
            cv.Optional("shared_device", default=False): cv.boolean,
            cv.Optional("max_data_rate"): cv.All(cv.frequency, cv.Range(min=1000, max=40000000)),
            cv.Optional(CONF_DEVICES, default=[]): cv.ensure_list(DEVICE_SCHEMA),
        }
    )
    .extend(cv.COMPONENT_SCHEMA)
    .extend(spi.spi_device_schema(cs_pin_required=True, default_mode="MODE0"))
)

def validate_upstream_chain(config):
    """Follow virtual parallel channels to the physical hardware bus."""
    full = fv.full_config.get()
    bus = config["spi_id"]
    seen = set()
    while True:
        key = str(bus)
        if key in seen:
            raise cv.Invalid("Addressed SPI bus cycle")
        seen.add(key)
        path = full.get_path_for_id(bus)
        declaration = full.get_config_for_path(path[:-1])
        if path[0] == "spi":
            if "mosi_pin" not in declaration:
                raise cv.Invalid("Serial header requires physical MOSI")
            if declaration.get("interface") == "software":
                raise cv.Invalid("Serial addressed SPI requires hardware SPI")
            break
        if path[0] != "addrspi":
            raise cv.Invalid("addrspi2 upstream must be physical SPI or an addrspi parallel channel")
        owner = full.get_config_for_path(path[:2])
        bus = owner["spi_id"]
    if str(config.get("spi_mode", "MODE0")) != "MODE0":
        raise cv.Invalid("Serial header router requires MODE0")
    if config["shared_device"] and config.get("write_only", False):
        raise cv.Invalid("Shared serial head handle must permit RX")
    serial_buses = {str(d[CONF_BUS_ID]) for d in config["devices"]}
    def check_children(fragment):
        if isinstance(fragment, dict):
            if str(fragment.get("spi_id", "")) in serial_buses:
                if str(fragment.get("spi_mode", "MODE0")) != "MODE0":
                    raise cv.Invalid("Serial header child requires MODE0; set DAC spi_mode explicitly")
                if config["shared_device"] and fragment.get("data_rate", 0) != config["data_rate"]:
                    raise cv.Invalid("Shared head handle requires identical hub and child data_rate")
                if "max_data_rate" in config and fragment.get("data_rate", 0) > config["max_data_rate"]:
                    raise cv.Invalid("Serial child data_rate exceeds hub max_data_rate")
            for value in fragment.values():
                check_children(value)
        elif isinstance(fragment, list):
            for value in fragment:
                check_children(value)
    check_children(full.get_config_for_path([]))
    addresses = [d["address"] for d in config["devices"]]
    if len(set(addresses)) != len(addresses):
        raise cv.Invalid("Duplicate serial device addresses")
    return config

FINAL_VALIDATE_SCHEMA = validate_upstream_chain

async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    await spi.register_spi_device(var, config)
    cg.add(var.set_shared_device(config["shared_device"]))
    if "max_data_rate" in config:
        cg.add(var.set_max_data_rate(config["max_data_rate"]))

    for device_config in config[CONF_DEVICES]:
        channel = cg.new_Pvariable(device_config[CONF_BUS_ID])
        await cg.register_component(channel, device_config)
        cg.add(channel.set_parent(var))
        cg.add(channel.set_address(device_config[CONF_ADDRESS]))
        cg.add(var.register_channel(channel))
