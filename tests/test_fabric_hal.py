"""Compile real portable C++/STM HAL adapter against a call-checking HAL fixture."""
import subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class HALTests(unittest.TestCase):
    def test_qspi_packets_and_clock_bound(self):
        with tempfile.TemporaryDirectory() as d:
            binary=Path(d)/'hal-test'
            subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror','-I'+str(ROOT/'firmware/hal'),
                '-I'+str(ROOT/'integrations/esphome/components/sinara_fpga'),str(ROOT/'tests/fabric_hal_test.cpp'),'-o',str(binary)],check=True,capture_output=True)
            subprocess.run([str(binary)],check=True,timeout=5)
