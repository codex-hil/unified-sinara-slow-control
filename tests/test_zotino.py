import pathlib
import subprocess
import tempfile
import unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class ZotinoTests(unittest.TestCase):
    def test_portable_driver(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary=str(pathlib.Path(tmp)/'zotino')
            subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror','-I',str(ROOT/'integrations/esphome/components/sinara_gpio_endpoint'),str(ROOT/'tests/zotino_core_test.cpp'),'-o',binary],check=True,timeout=30)
            subprocess.run([binary],check=True,timeout=30)
