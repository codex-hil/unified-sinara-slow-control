"""Portable extraction of STM SlotController's offline SPI/GPIO mux.

No pad primitives or CSR dependency: usable with ECP5 and Artix-7 wrappers.
Mapping is elaboration-time; spi_mask/offline are runtime controls. Physical
buffer directions, MLVDS shift-register control and IRQ remain platform code.
"""
from migen import Module, Signal, TSTriple, Mux, Cat


class SlotPinMux(Module):
    def __init__(self, spi, width=16, mapping=None):
        if isinstance(mapping, str):
            from sinara_slow.pinmaps import spi_mapping
            mapping = spi_mapping(mapping)
        mapping = {"clk": 0, "mosi": 1, "miso": 2, "cs": [3]} if mapping is None else mapping
        if set(mapping) != {"clk", "mosi", "miso", "cs"}:
            raise ValueError("mapping requires clk, mosi, miso and cs")
        cs = mapping["cs"]
        if not isinstance(cs, (list, tuple)) or not 1 <= len(cs) <= len(spi.cs_spi.o):
            raise ValueError("invalid number of CS lines")
        lines = [mapping[k] for k in ("clk", "mosi", "miso")] + list(cs)
        if any(type(n) is not int or not 0 <= n < width for n in lines):
            raise ValueError("line outside logical port")
        if len(set(lines)) != len(lines):
            raise ValueError("SPI functions must use distinct lines")
        self.slot = [TSTriple(name=f"line_{i}") for i in range(width)]
        self.output = Signal(width)
        self.input = Signal(width)
        self.oe = Signal(width)
        self.offline = Signal(reset=1)
        mask = sum(1 << i for i in lines)
        self.spi_mask = Signal(width, reset=mask)
        routes = {mapping[k]: (getattr(spi, k), 0) for k in ("clk", "mosi", "miso")}
        routes.update({line: (spi.cs_spi, bit) for bit, line in enumerate(cs)})
        for i, pad in enumerate(self.slot):
            if i in routes:
                source, bit = routes[i]
                active = ~self.offline & self.spi_mask[i]
                self.comb += [pad.o.eq(Mux(active, source.o[bit], self.output[i])),
                              pad.oe.eq(Mux(active, source.oe, self.oe[i]))]
            else:
                self.comb += [pad.o.eq(self.output[i]), pad.oe.eq(self.oe[i])]
        self.comb += self.input.eq(Cat(*(p.i for p in self.slot)))
        for name in ("clk", "mosi", "miso"):
            self.comb += getattr(spi, name).i.eq(self.slot[mapping[name]].i)
        self.comb += spi.cs_spi.i.eq(Cat(*(self.slot[line].i for line in cs)))
