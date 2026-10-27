"""Run the requested unchanged model commands with durable UTF-8 evidence."""
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
import json
import os
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "logs"
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, encoding="utf-8").strip()

def main():
    environment = {
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "packages": {name: version(name) for name in ("numpy", "pandas", "scipy", "matplotlib", "pip", "setuptools", "pillow")},
        "git_head": git("rev-parse", "HEAD"),
        "branch": git("branch", "--show-current"),
        "remote_branch_head": git("ls-remote", "origin", "refs/heads/feat/reservoir-inventory-prototype"),
        "tracked_diff": git("diff", "HEAD", "--stat"),
        "git_status": git("status", "--short"),
        "sparse_checkout": git("sparse-checkout", "list"),
    }
    assert environment["git_head"] == "82d7cddb27729062f6a393b703b56d9f56008331"
    save(LOGS / "environment.json", environment)
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    # pip 22.2.1 freeze misdecodes Git's UTF-8 repository path on this host.
    # Listing distributions does not invoke Git or change the environment.
    freeze = subprocess.check_output([sys.executable, "-m", "pip", "list", "--format=freeze", "--disable-pip-version-check"], cwd=ROOT, env=env, encoding="utf-8")
    (LOGS / "pip_list_freeze.txt").write_text(freeze, encoding="utf-8")
    pins = [line for line in freeze.splitlines() if not line.lower().startswith("reservoir-inventory-prototype==")]
    (LOGS / "requirements_run01.txt").write_text("\n".join(pins) + "\n-e .\n", encoding="utf-8")
    commands = [
        ("00_pip_check", ["-m", "pip", "check"]),
        ("01_unittest", ["-m", "unittest", "discover", "-s", "tests", "-v"]),
        ("02_verify_toy", ["-m", "reservoir_inventory", "verify-toy", "--out", "outputs/toy"]),
        ("03_demo", ["-m", "reservoir_inventory", "demo", "--config", "configs/xiaowan_demo.json", "--out", "outputs/demo"]),
        ("04_sweep", ["-m", "reservoir_inventory", "sweep", "--inputs", "outputs/demo/inputs/normal", "--out", "outputs/sweep"]),
    ]
    records = []
    for name, args in commands:
        start = datetime.now(timezone.utc).isoformat()
        clock = time.perf_counter()
        argv = [sys.executable, *args]
        print(f"START {name}: {subprocess.list2cmdline(argv)}", flush=True)
        with (LOGS / f"{name}.log").open("wb") as stream:
            process = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
            status = process.wait()
        record = {"name": name, "argv": argv, "cwd": str(ROOT), "pid": process.pid,
                  "start_utc": start, "end_utc": datetime.now(timezone.utc).isoformat(),
                  "elapsed_seconds": time.perf_counter() - clock, "exit_code": status,
                  "log": f"logs/{name}.log"}
        save(LOGS / f"{name}.status.json", record)
        records.append(record)
        save(LOGS / "command_statuses.json", records)
        print((LOGS / f"{name}.log").read_text(encoding="utf-8", errors="replace"), flush=True)
        print(f"END {name}: exit={status}; elapsed={record['elapsed_seconds']:.3f}s", flush=True)
        if status:
            return status
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
