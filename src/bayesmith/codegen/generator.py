"""Render an auditable plan and standalone evaluator bundle."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from bayesmith import __version__
from bayesmith.backends.introspection import choose_backend
from bayesmith.planner.rule_engine import plan
from bayesmith.schemas.profile import ProblemProfile


def _hash(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _input_files(inputs: list[str]) -> list[Path]:
    denied = {".git", "node_modules", "vendor", "build", "dist", ".venv"}
    files: set[Path] = set()
    for raw in inputs:
        path = Path(raw)
        candidates = path.rglob("*") if path.is_dir() else [path]
        for candidate in candidates:
            if not candidate.is_file() or any(part in denied for part in candidate.parts):
                continue
            try:
                if candidate.stat().st_size <= 1_000_000:
                    files.add(candidate.resolve())
            except OSError:
                continue
    return sorted(files)


def generate(
    profile: ProblemProfile,
    brief_path: str,
    out: str,
    backend: str = "auto",
    inputs: list[str] | None = None,
    planner: str = "rule-only",
) -> Path:
    dest = Path(out).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    selected, introspection = choose_backend(backend)
    fired = plan(profile, selected)
    bibliography = yaml.safe_load(
        (Path(__file__).parents[1] / "catalog" / "bibliography.yaml").read_text(encoding="utf-8")
    )["references"]
    defaults = {
        p.name: (
            p.baseline if p.baseline is not None else (p.bounds[0] if p.bounds else p.choices[0])
        )
        for p in profile.parameters
    }
    constraint_environment = {
        key.upper(): value
        for key, value in profile.hardware_context.model_dump(exclude_none=True).items()
        if isinstance(value, (int, float, bool))
    }
    constraint_environment.update(profile.hardware_context.extra)
    config: dict[str, Any] = {
        "profile": profile.model_dump(mode="json"),
        "backend": selected,
        "backend_version": introspection.get(selected, {}).get("version"),
        "use_catalog_fallback": False,
        "seed": 2026,
        "budget_trials": min(max(profile.budget_trials, 2), 10000),
        "wall_time_seconds": 86400,
        "per_trial_timeout_seconds": 3600,
        "hard_caps": {
            "budget_trials": 10000,
            "wall_time_seconds": 604800,
            "per_trial_timeout_seconds": 86400,
        },
        "max_build_jobs": 4,
        "nice": 10,
        "cpu_affinity": None,
        "repeats": 3,
        "warmup": 1,
        "imputation_margin_fraction": 0.15,
        "regression_tolerance_pct": 2.0,
        "verification_rounds": 10,
        "evaluator": {
            "mode": "command_only",
            "command": [],
            "cwd": ".",
            "build_command": [],
            "max_build_jobs": 4,
            "runtime_env": {},
            "parameter_env": {},
        },
        "baseline": defaults,
        "constraint_environment": constraint_environment,
    }
    (dest / "config.yaml").write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    template_dir = Path(__file__).parent / "templates"
    for name in ("evaluator.py", "run_study.py", "verify.py", "synthetic_objective.py"):
        shutil.copyfile(template_dir / name, dest / name)
    table = "\n".join(
        f"| {r['method']} | Tier 1 | {r['rule_id']}: {r['rationale']} | {'; '.join(r['citation_keys'])} | {r['status']} | catalog fallback |"
        for r in fired
    )
    citation_keys = sorted({key for rule in fired for key in rule["citation_keys"]})
    citation_section = "\n".join(
        f"- `{key}`: [{bibliography[key]['title']}]({bibliography[key]['url']}) — {bibliography[key].get('kind', 'unverified')}"
        for key in citation_keys
    )
    params = (
        "\n".join(
            f"| {p.name} | {p.type} | {p.bounds or p.choices} | {p.step or p.multiple_of or '—'} | {p.baseline} | {p.source_ref or 'brief/profile'} | {p.provenance} |"
            for p in profile.parameters
        )
        or "| _none parsed_ | — | — | — | — | brief | user-stated |"
    )
    assumptions = (
        "\n".join(f"- [ ] {x}" for x in profile.assumptions_made + profile.open_questions)
        or "- [ ] Confirm parameter ranges, baseline, and target validity oracle."
    )
    notes = "\n".join(f"- {line}" for line in profile.engineer_notes) or "- None supplied."
    warning = (
        "\n> **Backend warning:** Optuna was not installed during generation. The bundle is configured for Optuna; install its pinned backend extra before running.\n"
        if not introspection.get(selected, {}).get("installed")
        else ""
    )
    backend_note = introspection.get("requested_backend_note", {})
    backend_warning = (
        f"\n> **Backend fallback:** {backend_note['reason']} Requested `{backend_note['requested']}`, generated `{backend_note['selected']}`.\n"
        if backend_note
        else ""
    )
    plan_md = f"""# Tuning plan: {profile.problem}

## Recommendation

Backend: **{selected}** (generator version {__version__}; installed version {introspection.get(selected, {}).get("version", "not installed")}). The default profile is discrete and expense-conscious, so Optuna TPE is the Tier-1 sampler. The harness does not execute the target in the optimizer process.
{warning}
{backend_warning}
## Profile

| Parameter | Type | Bounds/choices | Step | Baseline | Source | Provenance |
|---|---|---|---:|---:|---|---|
{params}

Landscape: `{profile.landscape}`. Objectives: {", ".join(f"{o.name} ({o.direction})" for o in profile.objectives)}. Aggregation: `{profile.aggregation}`. Budget: {config["budget_trials"]} trials; per-trial timeout: {config["per_trial_timeout_seconds"]} s; wall-time cap: {config["wall_time_seconds"]} s.

## Constraints and failures

Pre-evaluation constraints are evaluated before the evaluator subprocess. Stepped integers should be sampled on their declared lattice. Baseline trial 0 is retained as the reference even when it violates a constraint (a warning is written to the trial record). Black-box failures are labeled and excluded from best-result reporting. To keep a scalar optimizer usable, failures receive direction-aware worst-valid-observation imputation minus/plus {config["imputation_margin_fraction"]:.0%} of observed valid range; this is a **heuristic**, with a conservative cold-start penalty until valid data exist. Imputed values never become reported results or noise estimates. A feasibility classifier is documented as an alternative but is not selected by this backend adapter.

## Component audit

| Slot | Method | Tier | Rule / justification | Citation | Status | Fallback |
|---|---|---|---|---|---|---|
{table}

## Sources for selected rules

{citation_section}

No outside-catalog method is selected. The catalog remains unchanged at generation time. `--use-catalog-fallback` switches the generated harness to its conservative catalog configuration.

## Hardware and validity scope

Hardware context: `{profile.hardware_context.model_dump_json(exclude_none=True)}`. L3 constraints, if any, must name the sharing domain. Aggregate multi-domain L3 is not used as a per-domain cache budget. Confirm cache topology on the target with `lscpu`/CPUID. Validity oracle: {profile.validity_oracle or "not specified; correctness comparison must be supplied before real runs"}. Environment scope: {", ".join(profile.environment_scope) or "not specified"}.

## Assumptions and open questions

{assumptions}

## Engineer notes

{notes}

## Safe execution settings

The generated config caps the study at {config["hard_caps"]["budget_trials"]} trials, {config["hard_caps"]["wall_time_seconds"]} seconds, and {config["hard_caps"]["per_trial_timeout_seconds"]} seconds per trial. Builds default to at most {config["max_build_jobs"]} jobs and commands use `nice` {config["nice"]}. CPU pinning is optional and unset. Review `config.yaml` and the evaluator command before using `--mode real`. Builds should use an isolated source copy/worktree and a parameter-keyed cache; the generic command-only runner will not edit or build a host tree for you.
"""
    (dest / "PLAN.md").write_text(plan_md, encoding="utf-8")
    input_paths = inputs or [brief_path]
    hashes = {str(path): _hash(path) for path in _input_files(input_paths)}
    libraries = {}
    for distribution in ("pydantic", "PyYAML", "Jinja2", "typer", "rich", "numpy", "scipy"):
        try:
            libraries[distribution] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            libraries[distribution] = "not installed"
    provenance = {
        "bayesmith_version": __version__,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "python": sys.version,
        "core_library_versions": libraries,
        "hardware_context": profile.hardware_context.model_dump(exclude_none=True),
        "input_sha256": hashes,
        "backend_introspection": introspection,
        "selected_backend": selected,
        "fired_rules": fired,
        "dropped_suggestions": [],
        "retrieved_sources": [],
        "llm_call_metadata": None,
        "planner": planner,
        "seed": config["seed"],
    }
    (dest / "provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (dest / "README.md").write_text(
        """# Generated Bayesmith harness

Review `PLAN.md` and edit `config.yaml` before running. Synthetic validation:

```sh
python -m pip install 'optuna==5.0.0'
python run_study.py --mode synthetic
python verify.py --mode synthetic
```

Real evaluation requires a configured evaluator command and an isolated build/copy strategy. The runner uses subprocess timeouts, records `trials.jsonl`, enforces configured caps, and does not import the target library. It never modifies the source tree.
""",
        encoding="utf-8",
    )
    return dest
