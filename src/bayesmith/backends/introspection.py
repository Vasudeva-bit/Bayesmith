"""Isolated subprocess checks for optional backend availability."""

from __future__ import annotations

import importlib.metadata
import subprocess
import sys
from typing import Any


def inspect_backend(name: str, timeout: float = 5.0) -> dict[str, Any]:
    packages = {"optuna": "optuna", "botorch": "botorch", "smac3": "smac"}
    package = packages[name]
    try:
        version = importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return {"installed": False, "package": package}
    script = (
        "import importlib,inspect,json; m=importlib.import_module('optuna.samplers'); c=getattr(m,'TPESampler'); s=c(seed=2026,multivariate=True); print(json.dumps({'callable': callable(c), 'instantiated': s is not None, 'signature': str(inspect.signature(c))}))"
        if name == "optuna"
        else "import importlib; importlib.import_module('botorch')"
        if name == "botorch"
        else "import importlib; importlib.import_module('smac')"
    )
    try:
        run = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "installed": run.returncode == 0,
            "package": package,
            "version": version,
            "returncode": run.returncode,
            "stdout": run.stdout.strip(),
            "stderr": run.stderr.strip()[:1000],
        }
    except subprocess.TimeoutExpired:
        return {
            "installed": True,
            "package": package,
            "version": version,
            "introspection": "timeout",
        }


def choose_backend(requested: str) -> tuple[str, dict[str, Any]]:
    # Only Optuna has a runnable adapter in v1. Importing another framework is
    # not enough to claim Bayesmith can generate its harness correctly.
    results: dict[str, Any] = {"optuna": inspect_backend("optuna")}
    if requested in {"botorch", "smac3"}:
        results[requested] = inspect_backend(requested)
        results["requested_backend_note"] = {
            "requested": requested,
            "selected": "optuna",
            "reason": f"{requested} is inspection-only in this v1; its harness adapter is not implemented.",
        }
    elif requested == "auto":
        results["botorch"] = inspect_backend("botorch")
        results["smac3"] = inspect_backend("smac3")
    return "optuna", results
