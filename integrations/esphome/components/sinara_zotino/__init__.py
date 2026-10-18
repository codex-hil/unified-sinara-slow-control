"""Zotino AD5372 slow control over the shared STM/Kasli GPIO endpoint."""
import esphome.codegen as cg
import esphome.config_validation as cv
import esphome.final_validate as fv
from esphome.const import CONF_ID
from esphome.components.sinara_gpio_endpoint import GPIOEndpoint, GPIO_REFERENCE_SCHEMA, validate_pin_slots
AUTO_LOAD=['sinara_gpio_endpoint','output']
MULTI_CONF=True
ns=cg.esphome_ns.namespace('sinara_zotino')
ZotinoComponent=ns.class_('ZotinoComponent',cg.Component)
PINS=['clk','mosi','miso','sync_n','led_cs_n','ldac_n','busy','clr_n']
def validate(c):
    if len(set((p['slot'],p['line']) for p in c['pinmux'].values()))!=8: raise cv.Invalid('Zotino requires eight distinct lines')
    return c
CONFIG_SCHEMA=cv.All(cv.Schema({
    cv.GenerateID():cv.declare_id(ZotinoComponent),
    cv.Required('endpoint_id'):cv.use_id(GPIOEndpoint),
    cv.Required('pinmux'):cv.Schema({cv.Required(k):GPIO_REFERENCE_SCHEMA for k in PINS}),
}).extend(cv.COMPONENT_SCHEMA),validate)
def final_validate(c):
    full=fv.full_config.get()
    def items(k):
        v=full.get(k,[])
        return [v] if isinstance(v,dict) else v
    e=next(e for e in items('sinara_gpio_endpoint') if e[CONF_ID]==c['endpoint_id'])
    validate_pin_slots(c,e)
    for k in PINS:
        cap='input_capable' if k in ('miso','busy') else 'output_capable'
        if c['pinmux'][k]['line'] not in e[cap]:raise cv.Invalid('Zotino pinmux violates endpoint electrical capabilities')
    if sum(h['endpoint_id']==c['endpoint_id'] for h in items('sinara_sampler')+items('sinara_zotino'))!=1:
        raise cv.Invalid('Zotino requires exclusive endpoint ownership')
    return c
FINAL_VALIDATE_SCHEMA=final_validate
async def to_code(c):
    v=cg.new_Pvariable(c[CONF_ID]);await cg.register_component(v,c)
    cg.add(v.set_endpoint(await cg.get_variable(c['endpoint_id'])))
    cg.add(v.set_pinmux(*[c['pinmux'][k]['line'] for k in PINS]))
