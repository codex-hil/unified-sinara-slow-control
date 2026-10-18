"""One-cycle CSR bank with registered one-hot read select.

Same word ordering/write strobe as MiSoC CSRBank. It registers selection,
not values, to keep the 163-word read mux off the address decode path.
Writes are still standard synchronous CSR writes; read values have no side
 effects. Platform transport must provide at least the normal CSR read cycle.
"""
from migen import Signal, Cat, Mux
from functools import reduce
from operator import or_
from misoc.interconnect import csr


class RegisteredSelectCSRBank(csr.GenericBank):
    def __init__(self, description, address, bus, align_bits=0):
        self.bus = bus
        csr.GenericBank.__init__(self, description, len(bus.dat_w))
        selected = bus.adr[11-align_bits:] == address
        enables = Signal(len(self.simple_csrs))
        tests = [selected & (bus.adr[:self.decode_bits] == i)
                 for i in range(len(self.simple_csrs))]
        self.sync += enables.eq(Cat(*tests))
        for i, c in enumerate(self.simple_csrs):
            self.comb += [c.r.eq(bus.dat_w[:c.size]), c.re.eq(bus.we & tests[i])]
        self.comb += bus.dat_r.eq(reduce(or_, [Mux(enables[i], c.w, 0)
                                               for i, c in enumerate(self.simple_csrs)]))
