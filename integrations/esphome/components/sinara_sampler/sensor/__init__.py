import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import sensor
from esphome.const import CONF_ID,CONF_CHANNEL,UNIT_VOLT,DEVICE_CLASS_VOLTAGE,STATE_CLASS_MEASUREMENT
from .. import SamplerComponent
DEPENDENCIES=['sinara_sampler']
CONFIG_SCHEMA=sensor.sensor_schema(unit_of_measurement=UNIT_VOLT,accuracy_decimals=5,
    device_class=DEVICE_CLASS_VOLTAGE,state_class=STATE_CLASS_MEASUREMENT).extend({
    cv.Required('sampler_id'):cv.use_id(SamplerComponent),
    cv.Required(CONF_CHANNEL):cv.int_range(min=0,max=7),
})
async def to_code(c):
    var=await sensor.new_sensor(c)
    parent=await cg.get_variable(c['sampler_id'])
    cg.add(parent.set_sensor(c[CONF_CHANNEL],var))

import esphome.final_validate as fv

def final_validate(c):
    sensors=fv.full_config.get().get('sensor',[])
    if sum(s.get('platform')=='sinara_sampler' and s.get('sampler_id')==c['sampler_id'] and
           s.get(CONF_CHANNEL)==c[CONF_CHANNEL] for s in sensors)!=1:
        raise cv.Invalid('Sampler channel already has a sensor')
    return c

FINAL_VALIDATE_SCHEMA=final_validate
