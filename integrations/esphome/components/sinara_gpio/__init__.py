"""ESPHome GPIO provider backed by logical FPGA slot/line coordinates."""
import re
from esphome import pins
import esphome.codegen as cg
import esphome.config_validation as cv
import esphome.final_validate as fv
from esphome.const import CONF_ID, CONF_NUMBER, CONF_MODE, CONF_INPUT, CONF_OUTPUT, CONF_INVERTED
from esphome.components.sinara_gpio_endpoint import GPIOEndpoint
AUTO_LOAD = ['sinara_gpio_endpoint']
MULTI_CONF = True
ns = cg.esphome_ns.namespace('sinara_gpio')
GPIOProvider = ns.class_('GPIOProvider', cg.Component)
FPGAPin = ns.class_('FPGAPin', cg.GPIOPin)
CONFIG_SCHEMA = cv.Schema({
    cv.GenerateID(): cv.declare_id(GPIOProvider),
    cv.Required('endpoint_id'): cv.use_id(GPIOEndpoint),
}).extend(cv.COMPONENT_SCHEMA)

def coordinate(value):
    if not isinstance(value, str) or not re.fullmatch(r'[1-8]_(?:[0-9]|1[0-5])', value):
        raise cv.Invalid('Use a quoted GPIO coordinate "slot_line": slots1..8, lines0..15')
    return value

def one_direction(mode):
    if bool(mode[CONF_INPUT]) == bool(mode[CONF_OUTPUT]):
        raise cv.Invalid('Select exactly one of INPUT or OUTPUT; no pulls/open drain supported')
    return mode

def items(config, key):
    value = config.get(key, [])
    return [value] if isinstance(value, dict) else value


GPIO_SCHEMA = pins.gpio_base_schema(FPGAPin, coordinate,
    modes=[CONF_INPUT, CONF_OUTPUT], mode_validator=one_direction).extend({
        cv.Required('sinara_gpio'): cv.use_id(GPIOProvider),
    })

@pins.PIN_SCHEMA_REGISTRY.register('sinara_gpio', GPIO_SCHEMA)
async def pin_to_code(config):
    pin = cg.new_Pvariable(config[CONF_ID])
    cg.add(pin.set_provider(await cg.get_variable(config['sinara_gpio'])))
    cg.add(pin.set_line(int(config[CONF_NUMBER].split('_')[1])))
    cg.add(pin.set_inverted(config[CONF_INVERTED]))
    cg.add(pin.set_flags(pins.gpio_flags_expr(config[CONF_MODE])))
    return pin

async def to_code(config):
    provider = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(provider, config)
    cg.add(provider.set_endpoint(await cg.get_variable(config['endpoint_id'])))

def final_validate(config):
    full = fv.full_config.get()
    owners = items(full,'sinara_gpio') + items(full,'sinara_sampler') + items(full,'sinara_zotino')
    if sum(c['endpoint_id'] == config['endpoint_id'] for c in owners) != 1:
        raise cv.Invalid('GPIO provider requires exclusive endpoint ownership')
    endpoint = next(e for e in items(full,'sinara_gpio_endpoint') if e[CONF_ID] == config['endpoint_id'])
    def walk(value):
        if isinstance(value, dict):
            if value.get('sinara_gpio') == config[CONF_ID] and CONF_NUMBER in value:
                slot, line = map(int, value[CONF_NUMBER].split('_'))
                if slot != endpoint['slot']:
                    raise cv.Invalid('GPIO slot must match the provider endpoint slot')
                cap = 'output_capable' if value[CONF_MODE][CONF_OUTPUT] else 'input_capable'
                if line not in endpoint[cap]:
                    raise cv.Invalid('GPIO mode violates endpoint electrical capabilities')
                if (endpoint['mode']=='hardware' and endpoint['controller']=='stm_sys_board'
                        and endpoint['slot']<=6 and line>=8):
                    raise cv.Invalid('STM upper GPIO needs an ABI4 translator-direction adapter; SCG1 is insufficient')
            for child in value.values(): walk(child)
        elif isinstance(value,list):
            for child in value: walk(child)
    walk(full)
    return config
FINAL_VALIDATE_SCHEMA = final_validate
