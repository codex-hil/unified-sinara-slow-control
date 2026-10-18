"""Bounded ESPHome host proof of concept. No hardware, API server or MQTT."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "integrations/esphome/examples/max31865-simulation.yaml"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--esphome", default="/home/codex-hil/.local/bin/esphome")
    parser.add_argument("--compile", action="store_true")
    args = parser.parse_args()
    env = os.environ.copy()
    env["PLATFORMIO_CORE_DIR"] = str(ROOT / "work/platformio")
    version = subprocess.check_output([args.esphome, "version"], text=True).strip()
    if version != "Version: 2026.9.0":
        raise RuntimeError(f"Adapter pinned to ESPHome 2026.9.0, got {version}")
    if args.compile:
        with (ROOT / "evidence/esphome-build.log").open("w") as log:
            subprocess.run([args.esphome, "compile", str(CONFIG)], cwd=ROOT, env=env, stdout=log,
                           stderr=subprocess.STDOUT, check=True, timeout=180)
    temp = ROOT / "work/esphome-tests"
    temp.mkdir(parents=True, exist_ok=True)
    base = CONFIG.read_text().replace("path: ../components", "path: " + str(ROOT / "integrations/esphome/components"))
    negative = {}
    for name, old, new, expected in [("hardware_rejected", "mode: simulation", "mode: hardware", "simulation"),
                                      ("slot_range", "slot: 0", "slot: 8", "at most 7")]:
        path = temp / (name + ".yaml")
        path.write_text(base.replace(old, new))
        result = subprocess.run([args.esphome, "config", str(path)], cwd=ROOT, env=env,
                                capture_output=True, text=True, timeout=30)
        output = result.stdout + result.stderr
        (ROOT / "evidence" / ("esphome-" + name + ".log")).write_text(output)
        assert result.returncode != 0 and expected in output, output
        negative[name] = "PASS"
    binary = ROOT / "work/builds/esphome-host/.pioenvs/sinara-esphome-simulation/program"
    with (ROOT / "evidence/esphome-host-run.log").open("w") as log:
        child = subprocess.Popen([str(binary)], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        try:
            child.wait(timeout=5)
            raise RuntimeError("ESPHome exited unexpectedly")
        except subprocess.TimeoutExpired:
            child.terminate()
            child.wait(timeout=3)
    output = (ROOT / "evidence/esphome-host-run.log").read_text()
    values = re.findall(r"SIMULATED_([A-Z0-9]+)=(-?\d+\.\d+)", output)
    assert values and {name for name, _ in values} == {"PT100", "LM75B"}, output
    for name, value in values:
        assert abs(float(value) - (25 if name == "LM75B" else 0)) < 0.1
    assert "SIM GPIO" in output and "mode=1 hz=4000000" in output
    report = {"esphome": version, "result": "PASS", "hardware_tested": False,
              "existing_drivers_modified": False, "spi_bus_injection": "local patched external component",
              "values_simulated": dict(values), "validation": negative,
              "limits": ["x86_64 Linux host only; no Kasli cross-build",
                         "STM platform/service not integrated", "I2C logical model; SPI tunnel not implemented",
                         "Addressed SPI hardware protocol from other thread not integrated",
                         "Simulation does not verify atomicity/timing/fault recovery of real buses"]}
    (ROOT / "evidence/esphome-test-result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
