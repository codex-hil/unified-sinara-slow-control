from esphome import pins
import esphome.codegen as cg
from esphome.components import spi
import esphome.config_validation as cv
from esphome.const import CONF_CHANNEL, CONF_CHANNELS, CONF_ID

try:
    from esphome.const import CONF_BUS_ID
except ImportError:
    CONF_BUS_ID = "bus_id"

CODEOWNERS = ["@wizath"]
DEPENDENCIES = ["spi"]

addrspi_ns = cg.esphome_ns.namespace("addrspi")
ADDRSPIComponent = addrspi_ns.class_("ADDRSPIComponent", cg.Component, spi.SPIDevice)
ADDRSPIChannel = addrspi_ns.class_("ADDRSPIChannel", spi.SPIComponent)

MULTI_CONF = True

CONF_ADDRESS_PINS = "address_pins"


def validate_channels(config):
    """Validate channel numbers based on address pin count."""
    num_pins = len(config[CONF_ADDRESS_PINS])
    max_channel = (2**num_pins) - 1

    for channel_conf in config.get(CONF_CHANNELS, []):
        channel_num = channel_conf[CONF_CHANNEL]
        if channel_num > max_channel:
            raise cv.Invalid(
                f"Channel {channel_num} exceeds maximum {max_channel} "
                f"for {num_pins} address pins (valid range: 0-{max_channel})"
            )
    return config


CONFIG_SCHEMA = cv.All(
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(ADDRSPIComponent),
            cv.Required(CONF_ADDRESS_PINS): cv.All(
                cv.ensure_list(pins.gpio_output_pin_schema),
                cv.Length(min=1, max=8),
            ),
            cv.Optional(CONF_CHANNELS, default=[]): cv.ensure_list(
                {
                    cv.Required(CONF_BUS_ID): cv.declare_id(ADDRSPIChannel),
                    cv.Required(CONF_CHANNEL): cv.positive_int,
                }
            ),
        }
    )
    .extend(spi.spi_device_schema(cs_pin_required=False))
    .extend(cv.COMPONENT_SCHEMA),
    validate_channels,
)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    await spi.register_spi_device(var, config)

    # Setup address pins (variable length)
    address_pins = []
    for pin_config in config[CONF_ADDRESS_PINS]:
        pin = await cg.gpio_pin_expression(pin_config)
        address_pins.append(pin)
    cg.add(var.set_address_pins(address_pins))

    # Setup channels
    for conf in config[CONF_CHANNELS]:
        chan = cg.new_Pvariable(conf[CONF_BUS_ID])
        await cg.register_component(chan, config)
        cg.add(chan.set_parent(var))
        cg.add(chan.set_channel(conf[CONF_CHANNEL]))
