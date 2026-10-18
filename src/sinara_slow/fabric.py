"""Strict build profile and command encoding for the shared SCF5 fabric."""
import hashlib,json
from pathlib import Path
import yaml
from .yaml_loader import StrictLoader


def load_profile(path):
    p=yaml.load(Path(path).read_text(),Loader=StrictLoader)
    keys={'schema_version','target','sys_clk_hz','fifo_depth','reviewed','slots'}
    if not isinstance(p,dict) or set(p)!=keys:raise ValueError('fabric profile fields mismatch')
    if type(p['schema_version']) is not int or p['schema_version']!=1 or p['target'] not in ('stm_ecp5','kasli'):raise ValueError('unsupported fabric profile')
    if type(p['reviewed']) is not bool:raise ValueError('reviewed must be boolean')
    if type(p['sys_clk_hz']) is not int or not 1000000<=p['sys_clk_hz']<=200000000:raise ValueError('invalid clock')
    if type(p['fifo_depth']) is not int or not 4<=p['fifo_depth']<=4096:raise ValueError('invalid depth')
    if not isinstance(p['slots'],list) or len(p['slots'])!=8:raise ValueError('exactly eight slot definitions required')
    for i,s in enumerate(p['slots'],1):
        if not isinstance(s,dict) or set(s)!={'slot','route','output_capable','input_capable'} or type(s['slot']) is not int or s['slot']!=i:raise ValueError('ordered slots1..8 required')
        for cap in ('output_capable','input_capable'):
            if type(s[cap]) is not int or not 0<=s[cap]<=65535:raise ValueError('invalid capability mask')
        r=s['route'];allowed={'clk','mosi','miso','selects','mode','enable','pulse','trigger','ready','ready_input','interlock','pulse_active_low','trigger_active_low','ready_active_low'}
        if not isinstance(r,dict) or set(r)-allowed or not {'clk','mosi','miso','selects','mode'}<=set(r):raise ValueError('invalid route fields')
        if r['mode'] not in ('direct','parallel','encoded','none'):raise ValueError('invalid selection mode')
        if not isinstance(r['selects'],list) or len(r['selects'])>4:raise ValueError('too many select lines')
        if any(type(r[k]) is not bool for k in ['pulse_active_low','trigger_active_low','ready_active_low'] if k in r):raise ValueError('polarity flags must be boolean')
        if 'enable' in r and r['mode']!='parallel':raise ValueError('enable is only valid for parallel addressing')
        if r['mode']=='direct' and not r['selects']:raise ValueError('direct bus needs CS')
        if r['mode']=='none' and r['selects']:raise ValueError('no-CS profile has no select lines')
        if r['mode'] in ('parallel','encoded') and not r['selects']:raise ValueError('address pins required')
        funcs=[r['clk'],r['mosi'],r['miso'],*r['selects']]
        if r['mode']=='parallel':
            if 'enable' not in r:raise ValueError('parallel address needs separate enable')
            funcs.append(r['enable'])
        if r['clk'] is None:raise ValueError('SCK required')
        used=[v for v in funcs if v is not None]
        if any(type(v) is not int or not 0<=v<8 for v in used):raise ValueError('SPI is restricted to lines0..7')
        extras=[r[k] for k in ('pulse','trigger','ready','ready_input','interlock') if k in r]
        if any(type(v) is not int or not 0<=v<16 for v in extras):raise ValueError('invalid GPIO function')
        if len(set(used+extras))!=len(used+extras):raise ValueError('pin conflict')
        outputs=[r['clk'],r['mosi'],*r['selects']]+[r[k] for k in ('enable','pulse','trigger','ready') if k in r]
        if any(v is not None and not (s['output_capable']>>v)&1 for v in outputs):raise ValueError('output capability mismatch')
        inputs=[r['miso']]+([r['interlock']] if 'interlock' in r else [])+([r['ready_input']] if 'ready_input' in r else [])
        if any(v is not None and not (s['input_capable']>>v)&1 for v in inputs):raise ValueError('input capability mismatch')
    return p


def build_id(profile):
    p={k:v for k,v in profile.items() if k!='reviewed'}
    return int.from_bytes(hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).digest()[:8],'little')


def transfer_words(opcode,selector,length,data=b'',tag=0):
    if opcode not in range(1,9) or not 0<=selector<16 or not 0<=tag<256 or not 0<=length<65536:raise ValueError('invalid command')
    if len(data)!=(length if opcode in (1,3) else 0):raise ValueError('payload length mismatch')
    result=[opcode<<28|selector<<24|tag<<16|length]
    result += [int.from_bytes(data[i:i+4].ljust(4,b'\0'),'little') for i in range(0,len(data),4)]
    return result


def stream_commands(commands):
    out=[]
    for slot,words in commands:
        if type(slot) is not int or not 1<=slot<=8 or not 1<=len(words)<=4096:raise ValueError('invalid routed command')
        out += [(len(words)<<16)|(slot-1),*words]
    return out
