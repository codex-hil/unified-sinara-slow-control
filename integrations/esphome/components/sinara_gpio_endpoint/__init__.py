"""GPIO register endpoint for Sampler; existing STM/LiteX wire protocols."""
import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.core import CORE
from esphome.const import CONF_ID
ns = cg.esphome_ns.namespace('sinara_gpio_endpoint')
GPIOEndpoint = ns.class_('GPIOEndpoint', cg.Component)
MULTI_CONF = True

def validate(c):
    if c['controller'] == 'stm_sys_board':
        if c['slot'] > 8:
            raise cv.Invalid('STM has eight slots')
        if [c[k] for k in ('output_address','input_address','oe_address')] != [20*(c['slot']-1)+i for i in range(3)]:
            raise cv.Invalid('STM requires the reviewed 20-word GPIO register map')
    elif any(c[k] % 4 for k in ('output_address','input_address','oe_address','abi_address')):
        raise cv.Invalid('Kasli requires 32-bit-aligned byte addresses')
    addresses=[c[k] for k in ('output_address','input_address','oe_address')]
    if len(set(addresses)) != 3 or (c['controller']=='kasli' and c['abi_address'] in addresses):
        raise cv.Invalid('CSR addresses overlap')
    if c['mode']=='hardware':
        if not CORE.is_host:
            raise cv.Invalid('hardware transport currently supports ESPHome host only; native STM HAL/runtime not ported')
        if not c['electrical_profile_reviewed']:
            raise cv.Invalid('hardware requires reviewed pad/translator directions, not just logical GPIO OE')
        if 'lock_path' not in c:
            raise cv.Invalid('hardware endpoint requires exclusive board lock_path')
        key='serial_path' if c['controller']=='stm_sys_board' else 'host_address'
        if key not in c:
            raise cv.Invalid(f'hardware endpoint requires {key}')
    return c

CONFIG_SCHEMA=cv.All(cv.Schema({
    cv.GenerateID():cv.declare_id(GPIOEndpoint),
    cv.Required('controller'):cv.one_of('stm_sys_board','kasli'),
    cv.Required('mode'):cv.one_of('simulation','hardware'),
    cv.Required('slot'):cv.int_range(min=1,max=8),
    cv.Required('output_address'):cv.hex_uint32_t,
    cv.Required('input_address'):cv.hex_uint32_t,
    cv.Required('oe_address'):cv.hex_uint32_t,
    cv.Optional('abi_address',default=0):cv.hex_uint32_t,
    cv.Optional('electrical_profile_reviewed',default=False):cv.boolean,
    cv.Required('output_capable'):cv.ensure_list(cv.int_range(min=0,max=15)),
    cv.Required('input_capable'):cv.ensure_list(cv.int_range(min=0,max=15)),
    cv.Optional('serial_path'):cv.string_strict,
    cv.Optional('host_address'):cv.ipv4address,  # Numeric IP: no unbounded DNS lookup.
    cv.Optional('tcp_port',default=1234):cv.port,
    cv.Optional('lock_path'):cv.string_strict,
    cv.Optional('timeout_ms',default=5000):cv.int_range(min=100,max=30000),
}).extend(cv.COMPONENT_SCHEMA),validate)

async def to_code(c):
    var=cg.new_Pvariable(c[CONF_ID]);await cg.register_component(var,c)
    cg.add(var.set_config(c['controller']=='stm_sys_board',c['mode']=='simulation',
                         c['output_address'],c['input_address'],c['oe_address'],c['abi_address']))
    cg.add(var.set_capabilities(sum(1<<i for i in set(c['output_capable'])),sum(1<<i for i in set(c['input_capable']))))
    cg.add(var.set_timeout(c['timeout_ms']))
    if 'serial_path' in c:cg.add(var.set_serial_path(c['serial_path']))
    if 'host_address' in c:cg.add(var.set_host(str(c['host_address']),c['tcp_port']))
    if 'lock_path' in c:cg.add(var.set_lock_path(c['lock_path']))

# Logical connector coordinates, never FPGA package pins or CSR bit addresses.
GPIO_REFERENCE_SCHEMA = cv.Schema({
    cv.Required('slot'): cv.int_range(min=1, max=8),
    cv.Required('line'): cv.int_range(min=0, max=15),
})

def validate_pin_slots(config, endpoint):
    for name, pin in config['pinmux'].items():
        if pin['slot'] != endpoint['slot']:
            raise cv.Invalid(f"{name}: GPIO slot must match endpoint slot; cross-slot routing is not implemented")
