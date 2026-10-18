"""Platform-free pinmux: SPI on lines0..7 only; GPIO/trigger on0..15."""
from migen import Module, Signal, Mux, Cat


def validate_routes(route):
    mode=route.get('mode','direct')
    if mode not in ('direct','parallel','encoded','none'):raise ValueError('unknown selector mode')
    selects=route.get('selects',[3,4,5,6])
    if mode in ('direct','parallel','encoded') and not selects:raise ValueError('select/address line required')
    if mode=='none' and selects:raise ValueError('no-CS bus has no selects')
    if not isinstance(selects,list) or len(selects)>4:raise ValueError('at most four select/address lines')
    functions=[route.get('clk',0),route.get('mosi',1),route.get('miso',2),*selects]
    if mode=='parallel':functions.append(route.get('enable',7))
    if any(type(p) is not int or not 0<=p<8 for p in functions if p is not None):
        raise ValueError('SPI pinmux is restricted to lines0..7')
    used=[p for p in functions if p is not None]
    if len(set(used))!=len(used):raise ValueError('SPI pin conflict')
    extras=[route.get('pulse'),route.get('trigger'),route.get('ready'),route.get('ready_input'),route.get('interlock')]
    if any(type(p) is not int or not 0<=p<16 for p in extras if p is not None):raise ValueError('GPIO line outside0..15')
    all_used=used+[p for p in extras if p is not None]
    if len(set(all_used))!=len(all_used):raise ValueError('special output pin conflict')
    return mode,selects


class FabricPinMux(Module):
    def __init__(self, engine, route):
        mode,selects=validate_routes(route)
        self.input=Signal(16);self.output=Signal(16);self.oe=Signal(16)
        self.gpio_output=Signal(16);self.gpio_oe=Signal(16)
        self.safe_output=Signal(16);self.safe_oe=Signal(16)
        self.spi_enable=Signal();self.permit=Signal(reset=1)
        self.common_trigger=Signal();self.common_ready=Signal()
        sources={route.get('clk',0):engine.clk,route.get('mosi',1):engine.mosi}
        sources.pop(None,None)
        for i,p in enumerate(selects):sources[p]=engine.select_out[i]
        if mode=='parallel':sources[route.get('enable',7)]=engine.enable_n
        miso=route.get('miso',2)
        self.comb += engine.miso.eq(self.input[miso] if miso is not None else 0)
        special={route[k]:s ^ int(route.get(k+'_active_low',False)) for k,s in [('pulse',engine.pulse),('trigger',self.common_trigger),('ready',self.common_ready)] if route.get(k) is not None}
        for line in range(16):
            value=self.gpio_output[line];oe=self.gpio_oe[line]
            if line in sources:
                value=Mux(self.spi_enable,sources[line],value);oe=Mux(self.spi_enable,1,oe)
            if line==miso:oe=Mux(self.spi_enable,0,oe)
            if line in special:value=special[line];oe=1
            self.comb += [self.output[line].eq(Mux(self.permit,value,self.safe_output[line])),
                          self.oe[line].eq(Mux(self.permit,oe,self.safe_oe[line]))]
