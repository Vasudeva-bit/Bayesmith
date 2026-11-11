"""Resumable Optuna ask/tell study; evaluator always runs out of process."""

from __future__ import annotations

import argparse
import json
import math
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import optuna
import yaml


def valid(
    params: dict[str, object], constraints: list[dict[str, str]], environment: dict[str, object]
) -> bool:
    # A tiny safe expression evaluator. Only parameter names and arithmetic/comparisons are accepted.
    import ast
    import operator

    ops = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Mod: operator.mod,
        ast.Eq: operator.eq,
        ast.NotEq: operator.ne,
        ast.Lt: operator.lt,
        ast.LtE: operator.le,
        ast.Gt: operator.gt,
        ast.GtE: operator.ge,
        ast.And: operator.and_,
        ast.Or: operator.or_,
    }

    values = {**environment, **params}

    def ev(n: ast.AST):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float, bool)):
            return n.value
        if isinstance(n, ast.Name) and n.id in values:
            return values[n.id]
        if isinstance(n, ast.BinOp) and type(n.op) in ops:
            return ops[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.Compare):
            left = ev(n.left)
            for op, right in zip(n.ops, n.comparators):
                if type(op) not in ops or not ops[type(op)](left, ev(right)):
                    return False
                left = ev(right)
            return True
        if isinstance(n, ast.BoolOp) and type(n.op) in ops:
            return (
                all(ev(x) for x in n.values)
                if isinstance(n.op, ast.And)
                else any(ev(x) for x in n.values)
            )
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            return -ev(n.operand) if isinstance(n.op, ast.USub) else ev(n.operand)
        raise ValueError("unsupported or unsafe constraint")

    return all(bool(ev(ast.parse(c["expression"], mode="eval"))) for c in constraints)


def suggest(trial, profile, baseline):
    params = {}
    for p in profile["parameters"]:
        name, kind = p["name"], p["type"]
        if kind in ("integer", "stepped_integer"):
            lo, hi = p["bounds"]
            step = int(p.get("step") or p.get("multiple_of") or 1)
            nsteps = math.floor((hi - lo) / step)
            params[name] = lo + trial.suggest_int(f"{name}__index", 0, nsteps) * step
        elif kind == "continuous":
            params[name] = trial.suggest_float(name, *p["bounds"], log=p.get("scale") == "log")
        elif kind == "boolean":
            params[name] = trial.suggest_categorical(name, [False, True])
        else:
            params[name] = trial.suggest_categorical(name, p["choices"])
    return params


def invoke(params, trial_id, seed, synthetic, timeout_s):
    data = {
        "trial_id": trial_id,
        "params": params,
        "seed": seed,
        "synthetic": synthetic,
        "is_baseline": trial_id == 0,
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        filename = f.name
    try:
        proc = subprocess.Popen(
            [sys.executable, "evaluator.py", "--trial-json", filename],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        try:
            out, err = proc.communicate(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
            return {"status": "TIMEOUT", "error_message": "runner timeout"}
        if proc.returncode != 0:
            return {"status": "BUILD_FAIL", "error_message": err[-2000:]}
        return json.loads(out.strip().splitlines()[-1])
    finally:
        Path(filename).unlink(missing_ok=True)


def valid_objectives(log: Path) -> list[float]:
    if not log.exists():
        return []
    rows = (json.loads(line) for line in log.read_text().splitlines() if line.strip())
    return [
        float(row["objective"])
        for row in rows
        if row.get("status") == "OK"
        and isinstance(row.get("objective"), (int, float))
        and not row.get("imputed")
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["synthetic", "real"], default="synthetic")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--use-catalog-fallback", action="store_true")
    args = ap.parse_args()
    cfg = yaml.safe_load(Path("config.yaml").read_text())
    profile = cfg["profile"]
    if (
        not cfg.get("budget_trials")
        or not cfg.get("wall_time_seconds")
        or not cfg.get("per_trial_timeout_seconds")
    ):
        raise SystemExit("finite trial, wall-time, and per-trial caps are required")
    caps = cfg["hard_caps"]
    for key in ("budget_trials", "wall_time_seconds", "per_trial_timeout_seconds"):
        if cfg[key] > caps[key]:
            raise SystemExit(f"{key} exceeds the generated hard cap ({caps[key]})")
    cfg["use_catalog_fallback"] = args.use_catalog_fallback or cfg.get(
        "use_catalog_fallback", False
    )
    db = "sqlite:///study.db"
    sampler = optuna.samplers.TPESampler(seed=cfg["seed"], multivariate=True)
    study = optuna.create_study(
        direction="maximize" if profile["objectives"][0]["direction"] == "maximize" else "minimize",
        sampler=sampler,
        storage=db,
        study_name="bayesmith",
        load_if_exists=args.resume,
    )
    baseline = cfg.get("baseline", {})
    existing = len(study.trials)
    if len(study.trials) == 0:
        study.enqueue_trial(baseline)
    started = time.monotonic()
    log = Path("trials.jsonl")
    while (
        len(study.trials) < cfg["budget_trials"]
        and time.monotonic() - started < cfg["wall_time_seconds"]
    ):
        trial = study.ask()
        params = baseline if trial.number == 0 else suggest(trial, profile, baseline)
        if (
            trial.number != 0
            and profile["pre_eval_constraints"]
            and not valid(
                params, profile["pre_eval_constraints"], cfg.get("constraint_environment", {})
            )
        ):
            # Reject before evaluation; a bounded penalty only keeps scalar TPE usable.
            good = valid_objectives(log)
            maximize = study.direction.name == "MAXIMIZE"
            worst = (min(good) if maximize else max(good)) if good else 0.0
            scale = max(max(good) - min(good), abs(worst) * 0.01, 1e-12) if good else 1.0
            margin = cfg["imputation_margin_fraction"] * scale
            penalty = worst - margin if maximize else worst + margin
            study.tell(trial, penalty)
            record = {
                "trial_id": trial.number,
                "params": params,
                "status": "CONSTRAINT_VIOLATION",
                "objective": None,
                "imputed_objective": penalty,
                "imputed": True,
                "cold_start_imputation": not bool(good),
            }
        else:
            record = invoke(
                params,
                trial.number,
                cfg["seed"] + trial.number,
                args.mode == "synthetic",
                min(
                    cfg["per_trial_timeout_seconds"],
                    max(0.1, cfg["wall_time_seconds"] - (time.monotonic() - started)),
                ),
            )
            record["params"] = params
            record["trial_id"] = trial.number
            if (
                trial.number == 0
                and profile["pre_eval_constraints"]
                and not valid(
                    params, profile["pre_eval_constraints"], cfg.get("constraint_environment", {})
                )
            ):
                record["baseline_constraint_warning"] = (
                    "baseline was evaluated despite a pre-evaluation constraint violation"
                )
            if record.get("status") == "OK" and isinstance(record.get("objective"), (int, float)):
                study.tell(trial, float(record["objective"]))
            else:
                good = valid_objectives(log)
                worst = (
                    (min(good) if study.direction.name == "MAXIMIZE" else max(good))
                    if good
                    else 0.0
                )
                scale = max(max(good) - min(good), abs(worst) * 0.01, 1e-12) if good else 1.0
                margin = cfg["imputation_margin_fraction"] * scale
                imputed = worst - margin if study.direction.name == "MAXIMIZE" else worst + margin
                study.tell(trial, imputed)
                record.update(
                    objective=None,
                    imputed_objective=imputed,
                    imputed=True,
                    cold_start_imputation=not bool(good),
                )
        with log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, sort_keys=True) + "\n")
    print(f"Completed {len(study.trials) - existing} trials; records: {log}")


if __name__ == "__main__":
    main()
