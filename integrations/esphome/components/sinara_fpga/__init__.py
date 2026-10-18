"""SCF5 queued hardware-SPI/GPIO endpoint; host transport, portable C++ client."""
import hashlib,json,sys,re
from pathlib import Path
from esphome import pins
import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.core import CORE
from esphome.const import CONF_ID,CONF_NUMBER,CONF_MODE,CONF_INPUT,CONF_OUTPUT,CONF_INVERTED
AUTO_LOAD=['spi']
MULTI_CONF=True
ns=cg.esphome_ns.namespace('sinara_fpga')
FPGAComponent=ns.class_('FPGAComponent',cg.Component)
FPGAPin=ns.class_('FPGAPin',cg.GPIOPin)

def validate(c):
    path=Path(CORE.relative_config_path(c['profile']))
    # Host build profile is shared with the gateware generator, not parsed on MCU.
    project=Path(__file__).resolve().parents[4]
    if str(project/'src') not in sys.path:sys.path.insert(0,str(project/'src'))
    from sinara_slow.fabric import load_profile,build_id
    from sinara_slow.errors import ValidationError
    import yaml
    try:profile=load_profile(path)
    except (OSError,ValueError,ValidationError,yaml.YAMLError) as e:raise cv.Invalid(str(e))
    if not CORE.is_host:raise cv.Invalid('native STM/Kasli ESPHome platform/runtime is not ported yet; portable client and bus adapter are separate')
    if not profile['reviewed']:raise cv.Invalid('SCF5 endpoint requires a reviewed profile; examples are synthetic')
    c['_profile']=profile;c['_build_id']=build_id(profile)
    if c['controller']=='stm_sys_board' and profile['target']!='stm_ecp5':raise cv.Invalid('controller/profile mismatch')
    if c['controller']=='kasli' and profile['target']!='kasli':raise cv.Invalid('controller/profile mismatch')
    key='serial_path' if c['controller']=='stm_sys_board' else 'host_address'
    if key not in c:raise cv.Invalid(f'{key} required')
    for slot in c['interlock_slots']:
        if 'interlock' not in profile['slots'][slot-1]['route']:raise cv.Invalid('interlock pin missing')
    for slot in c['ready_slots']:
        if 'ready_input' not in profile['slots'][slot-1]['route']:raise cv.Invalid('ready input pin missing')
    for slot in c['trigger_slots']:
        if 'trigger' not in profile['slots'][slot-1]['route']:raise cv.Invalid('trigger pin missing')
    return c
CONFIG_SCHEMA=cv.All(cv.Schema({
    cv.GenerateID():cv.declare_id(FPGAComponent),cv.Required('profile'):cv.string_strict,
    cv.Required('controller'):cv.one_of('stm_sys_board','kasli'),
    cv.Required('lock_path'):cv.string_strict,
    cv.Optional('serial_path'):cv.string_strict,cv.Optional('host_address'):cv.ipv4address,
    cv.Optional('tcp_port',default=1234):cv.port,cv.Optional('base_address',default=0):cv.hex_uint32_t,
    cv.Optional('timeout_ms',default=1000):cv.int_range(min=100,max=10000),
    cv.Optional('initialize',default=False):cv.boolean,
    cv.Optional('interlock_slots',default=[]):cv.ensure_list(cv.int_range(min=1,max=8)),
    cv.Optional('interlock_active_low_slots',default=[]):cv.ensure_list(cv.int_range(min=1,max=8)),
    cv.Optional('ready_slots',default=[]):cv.ensure_list(cv.int_range(min=1,max=8)),
    cv.Optional('ready_active_low_slots',default=[]):cv.ensure_list(cv.int_range(min=1,max=8)),
    cv.Optional('trigger_source',default='external'):cv.one_of('external','stm'),
    cv.Optional('trigger_slots',default=[]):cv.ensure_list(cv.int_range(min=1,max=8)),
    cv.Optional('trigger_width_cycles',default=1):cv.int_range(min=1,max=65535),
}).extend(cv.COMPONENT_SCHEMA),validate)
async def to_code(c):
    var=cg.new_Pvariable(c[CONF_ID]);await cg.register_component(var,c)
    cg.add(var.set_config(c['controller']=='stm_sys_board',c['_build_id'],c['base_address'],c['timeout_ms'],c['_profile']['sys_clk_hz'],c['_profile']['fifo_depth']))
    cg.add(var.set_lock_path(c['lock_path']))
    if 'serial_path' in c:cg.add(var.set_serial_path(c['serial_path']))
    if 'host_address' in c:cg.add(var.set_host(str(c['host_address']),c['tcp_port']))
    masks=[sum(1<<(slot-1) for slot in set(c[k])) for k in ['interlock_slots','interlock_active_low_slots','trigger_slots','ready_slots','ready_active_low_slots']]
    cg.add(var.set_initialization(c['initialize'],*masks,c['trigger_width_cycles'],c['trigger_source']=='stm'))

def coordinate(v):
    if not isinstance(v,str) or not re.fullmatch(r'[1-8]_(?:[0-9]|1[0-5])',v):raise cv.Invalid('quoted slot_line required')
    return v
GPIO_SCHEMA=pins.gpio_base_schema(FPGAPin,coordinate,modes=[CONF_INPUT,CONF_OUTPUT]).extend({cv.Required('sinara_fpga'):cv.use_id(FPGAComponent)})
@pins.PIN_SCHEMA_REGISTRY.register('sinara_fpga',GPIO_SCHEMA)
async def pin_to_code(c):
    var=cg.new_Pvariable(c[CONF_ID]);root=await cg.get_variable(c['sinara_fpga'])
    slot,line=map(int,c[CONF_NUMBER].split('_'))
    cg.add(var.set_config(root,slot-1,line,c[CONF_INVERTED],pins.gpio_flags_expr(c[CONF_MODE])))
    return var

import esphome.final_validate as fv

def final_validate(c):
    full=fv.full_config.get()
    roots=full.get('sinara_fpga',[])
    if isinstance(roots,dict):roots=[roots]
    if sum(r['lock_path']==c['lock_path'] for r in roots)!=1:
        raise cv.Invalid('one SCF5 root owns each controller lock')
    buses=full.get('spi',[])
    if isinstance(buses,dict):buses=[buses]
    buses=[b for b in buses if b.get('fpga_id')==c[CONF_ID]]
    expected={}
    for b in buses:
        r=c['_profile']['slots'][b['slot']-1]['route'];sel=b['selector']
        for key,role in [('mosi_pin','mosi'),('miso_pin','miso')]:
            if key in b and r[role] is None:raise cv.Invalid(f'{role} is absent in the gateware profile')
        if r['mode']=='direct':
            if sel>=len(r['selects']):raise cv.Invalid('selector exceeds hardware CS count')
            pin=r['selects'][sel]
        elif r['mode']=='parallel':
            if sel>=1<<len(r['selects']):raise cv.Invalid('address exceeds hardware address width')
            pin=r['enable']
        elif r['mode']=='encoded':
            if not 0<sel<1<<len(r['selects']):raise cv.Invalid('encoded CS zero is reserved for idle')
            pin=r['selects'][0]
        else:
            if sel:raise cv.Invalid('no-CS bus uses selector0')
            pin=r['clk']
        expected[b[CONF_ID]]=(b['slot'],pin)
    def walk(value,path=()):
        if isinstance(value,dict):
            if 'spi_id' in value and not isinstance(value['spi_id'],(dict,list)) and value['spi_id'] in expected:
                wanted=expected[value['spi_id']];pin=value.get('cs_pin')
                if pin and (pin.get('sinara_fpga')!=c[CONF_ID] or pin.get('number')!=f'{wanted[0]}_{wanted[1]}' or pin.get('inverted',False)):
                    raise cv.Invalid('cs_pin must match hardware selector/profile and be active-low')
            if value.get('sinara_fpga')==c[CONF_ID] and CONF_NUMBER in value:
                slot,line=map(int,value[CONF_NUMBER].split('_'))
                s=c['_profile']['slots'][slot-1];mode=value[CONF_MODE]
                if mode[CONF_OUTPUT] and line in [s['route'].get(k) for k in ('interlock','ready_input')]:raise cv.Invalid('interlock/ready input cannot be driven')
                if mode[CONF_INPUT] and line in [s['route'].get(k) for k in ('pulse','trigger','ready')]:raise cv.Invalid('special output cannot become input')
                if bool(mode[CONF_INPUT])==bool(mode[CONF_OUTPUT]):raise cv.Invalid('exactly one GPIO direction required')
                cap='output_capable' if mode[CONF_OUTPUT] else 'input_capable'
                if not (s[cap]>>line)&1:raise cv.Invalid('GPIO direction not supported by physical profile')
                if path[-1:]!=('cs_pin',):
                    r=s['route'];hw=[r['clk'],r['mosi'],r['miso'],*r['selects']]
                    if r['mode']=='parallel':hw.append(r['enable'])
                    if any(b['slot']==slot for b in buses) and line in hw:
                        raise cv.Invalid('GPIO conflicts with hardware SPI pinmux')
            for key,child in value.items():walk(child,(*path,key))
        elif isinstance(value,list):
            for i,child in enumerate(value):walk(child,(*path,i))
    walk(full)
    return c
FINAL_VALIDATE_SCHEMA=final_validate
