"""Eight-channel Sinara Sampler over a GPIO endpoint (slow SPI mode 0)."""
import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.const import CONF_ID
from esphome.components.sinara_gpio_endpoint import GPIOEndpoint, GPIO_REFERENCE_SCHEMA, validate_pin_slots
AUTO_LOAD=['sinara_gpio_endpoint','sensor']
MULTI_CONF=True
ns=cg.esphome_ns.namespace('sinara_sampler')
SamplerComponent=ns.class_('SamplerComponent',cg.PollingComponent)
PINS=['adc_clk','adc_miso','sdr','cnv','pgia_clk','pgia_mosi','pgia_miso','pgia_latch']

def validate(c):
    if len(set((p['slot'],p['line']) for p in c['pinmux'].values()))!=8:
        raise cv.Invalid('Sampler requires eight distinct logical EEM lines')
    return c

CONFIG_SCHEMA=cv.All(cv.Schema({
    cv.GenerateID():cv.declare_id(SamplerComponent),
    cv.Required('endpoint_id'):cv.use_id(GPIOEndpoint),
    cv.Optional('hardware_revision',default='v2.2'):cv.one_of('v2.1','v2.2'),
    cv.Optional('gains',default=[1]*8):cv.All(cv.ensure_list(cv.one_of(1,10,100,1000,int=True)),cv.Length(min=8,max=8)),
    cv.Required('pinmux'):cv.Schema({cv.Required(k):GPIO_REFERENCE_SCHEMA for k in PINS}),
}).extend(cv.polling_component_schema('1s')),validate)

async def to_code(c):
    var=cg.new_Pvariable(c[CONF_ID]);await cg.register_component(var,c)
    cg.add(var.set_endpoint(await cg.get_variable(c['endpoint_id'])))
    cg.add(var.set_revision(c['hardware_revision']=='v2.2'))
    cg.add(var.set_gains(*c['gains']))
    cg.add(var.set_pinmux(*[c['pinmux'][k]['line'] for k in PINS]))

# Validate electrical capability and ownership before any connection is opened.
import esphome.final_validate as fv

def final_validate(c):
    full=fv.full_config.get()
    endpoints=full.get('sinara_gpio_endpoint',[])
    if isinstance(endpoints,dict): endpoints=[endpoints]
    endpoint=next(e for e in endpoints if e[CONF_ID]==c['endpoint_id'])
    validate_pin_slots(c,endpoint)
    outputs=[c['pinmux'][k]['line'] for k in PINS if k not in ('adc_miso','pgia_miso')]
    inputs=[c['pinmux'][k]['line'] for k in ('adc_miso','pgia_miso')]
    if not set(outputs)<=set(endpoint['output_capable']) or not set(inputs)<=set(endpoint['input_capable']):
        raise cv.Invalid('Sampler pinmux violates endpoint electrical capabilities')
    hubs=full.get('sinara_sampler',[])
    if isinstance(hubs,dict): hubs=[hubs]
    others=full.get('sinara_zotino',[])
    if isinstance(others,dict): others=[others]
    if sum(h['endpoint_id']==c['endpoint_id'] for h in hubs+others)!=1:
        raise cv.Invalid('Sampler requires exclusive endpoint ownership')
    return c

FINAL_VALIDATE_SCHEMA=final_validate
