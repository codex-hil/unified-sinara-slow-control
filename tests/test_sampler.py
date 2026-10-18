"""Portable C++ driver tests; simulated GPIO and protocol fixtures only."""
import pathlib
import subprocess
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]

class SamplerTests(unittest.TestCase):
    def test_portable_driver_and_both_register_protocols(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary=str(pathlib.Path(tmp)/'sampler')
            subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror','-pedantic',
                '-I'+str(ROOT/'integrations/esphome/components/sinara_gpio_endpoint'),
                str(ROOT/'tests/sampler_core_test.cpp'),'-o',binary],check=True,timeout=30)
            subprocess.run([binary],check=True,timeout=10)
