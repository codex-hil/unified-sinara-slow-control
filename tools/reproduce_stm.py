#!/usr/bin/env python3
"""Offline build of archived upstream sources; never programs hardware."""
import argparse
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=["elaborate", "gateware", "firmware", "slot-sim", "bridge-sim", "fabric-sim", "integrated-bridge-sim"])
    parser.add_argument("--python", default="/home/codex-hil/vector-analyser/.venv/bin/python")
    parser.add_argument("--fpga-tools", default="/srv/codex-hil-data/toolchains/gatemate/oss-cad-suite/bin")
    parser.add_argument("--seed", type=int, default=3, help="Placement seed; timing failure returns nonzero")
    parser.add_argument("--firmware-source", type=Path, default=ROOT / "work/upstream-stm/firmware")
    args = parser.parse_args()
    env = os.environ.copy()
    if args.step in ("elaborate", "slot-sim", "bridge-sim", "fabric-sim", "integrated-bridge-sim"):
        deps = ROOT / "work/upstream-stm/deps"
        env["PYTHONPATH"] = os.pathsep.join(str(deps / n) for n in ("migen", "misoc", "litex")) + ":/usr/lib/python3/dist-packages"
        code = "import sys;sys.path.insert(0,'work/upstream-stm/gateware');from stm_sys_board import Platform;from stm_sys_board_hdl import STMSysBoard;p=Platform();p.build(STMSysBoard(p),build_name='stm_sys_board',build_dir='work/builds/stm-gateware',run=False)"
        command, cwd = [args.python, "-c", code], ROOT
        if args.step != "elaborate":
            env["PATH"] = args.fpga_tools + os.pathsep + env["PATH"]
            script = {"bridge-sim": "test_stm_bridge.py", "slot-sim": "test_stm_upstream.py",
                      "fabric-sim": "test_integrated_fabric.py",
                      "integrated-bridge-sim": "test_integrated_bridge.py"}[args.step]
            command = [args.python, str(ROOT / "tools" / script)]
    elif args.step == "gateware":
        env["PATH"] = args.fpga_tools + os.pathsep + env["PATH"]
        # The upstream script permits failed timing. Follow it with a strict run.
        command, cwd = ["bash", "build_stm_sys_board.sh"], ROOT / "work/builds/stm-gateware"
    else:
        toolchain = ROOT / "work/toolchains/rust/toolchains/1.88.0-x86_64-unknown-linux-gnu/bin"
        env.update(CARGO_HOME=str(ROOT / "work/cargo"), CARGO_TARGET_DIR=str(ROOT / "work/builds/stm-1.88"), TMPDIR=str(ROOT / "work/tmp"), RUSTC=str(toolchain / "rustc"))
        command, cwd = [str(toolchain / "cargo"), "build", "--locked", "--release"], args.firmware_source.resolve()
    log = ROOT / "evidence" / ("stm-reproduce-" + args.step + ".log")
    with log.open("w") as output:
        result = subprocess.run(command, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT)
        if args.step == "gateware" and result.returncode == 0:
            result = subprocess.run(["nextpnr-ecp5", "--json", "stm_sys_board.json", "--lpf", "stm_sys_board.lpf", "--textcfg", "stm_sys_board-strict.config", "--85k", "--package", "CABGA554", "--speed", "6", "--seed", str(args.seed)], cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT)
            if result.returncode == 0:
                result = subprocess.run(["ecppack", "stm_sys_board-strict.config", "--svf", "stm_sys_board-strict.svf", "--bit", "stm_sys_board-strict.bit", "--bootaddr", "0"], cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT)
    print(f"exit={result.returncode}; log={log}")
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
