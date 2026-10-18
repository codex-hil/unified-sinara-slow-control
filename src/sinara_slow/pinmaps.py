"""Module-side logical EEM routes, independent of controller package pins.

Urukul.io in pinned ARTIQ gateware/eem.py: EEM0 pairs 0..5.
CS is a three-bit active-high decoded address, not three device enables.
The DIOT-to-EEM adapter must preserve these indices or supply an explicit map.
"""


def spi_mapping(profile):
    if profile != 'urukul_eem0':
        raise ValueError(f'unknown SPI pinmux profile: {profile}')
    # Return fresh lists: one build must not mutate another slot's routes.
    return {'clk': 0, 'mosi': 1, 'miso': 2, 'cs': [3, 4, 5]}


def sampler_mapping():
    """Sampler primary EEM pairs, ARTIQ Sampler.io, no auxiliary port."""
    return dict(zip(('adc_clk','adc_miso','sdr','cnv','pgia_clk','pgia_mosi',
                     'pgia_miso','pgia_latch'),range(8)))


def zotino_mapping():
    """Zotino EEM pairs from pinned ARTIQ Zotino.io; active-low selects."""
    return dict(zip(('clk','mosi','miso','sync_n','led_cs_n','ldac_n','busy','clr_n'),range(8)))
