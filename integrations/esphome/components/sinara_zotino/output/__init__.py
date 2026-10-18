import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import output
from esphome.const import CONF_ID
from .. import ns,ZotinoComponent
DEPENDENCIES=['sinara_zotino']
ZotinoOutput=ns.class_('ZotinoOutput',output.FloatOutput)
CONFIG_SCHEMA=output.FLOAT_OUTPUT_SCHEMA.extend({
    cv.GenerateID():cv.declare_id(ZotinoOutput),
    cv.Required('zotino_id'):cv.use_id(ZotinoComponent),
    cv.Required('channel'):cv.int_range(min=0,max=31),
})
async def to_code(c):
    v=cg.new_Pvariable(c[CONF_ID]);await output.register_output(v,c)
    cg.add(v.set_parent(await cg.get_variable(c['zotino_id'])))
    cg.add(v.set_channel(c['channel']))

import esphome.final_validate as fv

def final_validate(c):
    outputs=fv.full_config.get().get('output',[])
    if sum(o.get('platform')=='sinara_zotino' and o.get('zotino_id')==c['zotino_id'] and o.get('channel')==c['channel'] for o in outputs)!=1:
        raise cv.Invalid('Zotino channel already has an output')
    return c
FINAL_VALIDATE_SCHEMA=final_validate
