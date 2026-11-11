"""Subprocess evaluation contract for generated harnesses."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time
from pathlib import Path

import yaml


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trial-json", required=True)
    args = parser.parse_args()
    trial = json.loads(Path(args.trial_json).read_text())
    cfg = yaml.safe_load(Path("config.yaml").read_text())
    result = {
        "trial_id": trial["trial_id"],
        "params": trial["params"],
        "status": "OK",
        "objective": None,
        "objective_std": None,
        "metrics": {},
        "build_seconds": 0.0,
        "benchmark_seconds": 0.0,
        "cache_hit": False,
        "error_message": "",
    }
    if trial.get("synthetic"):
        from synthetic_objective import evaluate

        result["status"], result["objective"], result["error_message"] = evaluate(
            trial["params"], trial.get("seed", 0), cfg["profile"]
        )
    else:
        ev = cfg["evaluator"]
        command = ev.get("command") or []
        if not command:
            result.update(
                status="BUILD_FAIL",
                error_message="Set evaluator.command in config.yaml for real mode",
            )
        else:
            env = os.environ.copy()
            env.update({str(k): str(v) for k, v in ev.get("runtime_env", {}).items()})
            env.update({str(k): str(v) for k, v in trial["params"].items()})
            start = time.monotonic()
            try:
                os.nice(cfg.get("nice", 10))
                process = subprocess.Popen(
                    command,
                    cwd=ev.get("cwd", "."),
                    env=env,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    start_new_session=True,
                )
                try:
                    stdout, stderr = process.communicate(timeout=cfg["per_trial_timeout_seconds"])
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.communicate()
                    result.update(status="TIMEOUT", error_message="per-trial timeout exceeded")
                    stdout, stderr = "", ""
                result["benchmark_seconds"] = time.monotonic() - start
                if result["status"] == "TIMEOUT":
                    pass
                elif process.returncode == 0:
                    try:
                        result.update(json.loads(stdout.strip().splitlines()[-1]))
                    except (json.JSONDecodeError, IndexError):
                        try:
                            result["objective"] = float(stdout.strip().splitlines()[-1])
                        except (ValueError, IndexError):
                            result.update(
                                status="CORRECTNESS_FAIL",
                                error_message="Command must emit JSON or one numeric objective",
                            )
                else:
                    result.update(
                        status="SEGFAULT" if process.returncode < 0 else "BUILD_FAIL",
                        error_message=stderr[-2000:],
                    )
            except OSError as exc:
                result.update(status="BUILD_FAIL", error_message=str(exc))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
