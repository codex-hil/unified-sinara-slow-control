"""Repeatable source-level regression evidence. Does not claim hardware tests."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
main=(ROOT/'references/stm-gateware/stm_sys_board_hdl.py').read_text()
tpr=(ROOT/'evidence/tpr-stm_sys_board_hdl.py').read_text()
firm=(ROOT/'references/stm-firmware/src/hardware/ecp5.rs').read_text()
assert 'self.address_reg_len = 7' in main
assert 'for i in range(8)' in main
assert 'pub const OFFSET_TO_SLOT: u16 = SLOT::_END + SPI::_END' in firm
assert 'self.address_reg_len = 15' in tpr
assert 'align_bits=0' in tpr
result={'type':'source_analysis','main_address_capacity':128,'required_slot_registers':160,
        'main_capacity_sufficient':False,'tpr_wire_header_bits':16,
        'firmware_wire_header_bits':16,'hardware_tested':False}
print(json.dumps(result,indent=2))
