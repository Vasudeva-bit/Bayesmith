"""Bayesmith command line interface."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.pretty import Pretty

from bayesmith.backends.introspection import inspect_backend
from bayesmith.codegen.generator import generate
from bayesmith.ingest.brief_parser import parse_brief
from bayesmith.ingest.code_scanner import scan_code

app = typer.Typer(help="Generate auditable Bayesian optimization harnesses.", no_args_is_help=True)
rules_app = typer.Typer(help="Inspect and lint the method catalog.")
example_app = typer.Typer(help="List or copy bundled examples.")
app.add_typer(rules_app, name="rules")
app.add_typer(example_app, name="example")
console = Console()


@app.command("generate")
def generate_command(
    brief: Path = typer.Option(..., "--brief", exists=True, readable=True),
    out: Path = typer.Option(..., "--out"),
    code: list[Path] = typer.Option([], "--code"),
    notes: Path | None = typer.Option(None, "--notes", exists=True, readable=True),
    env: Path | None = typer.Option(None, "--env", exists=True, readable=True),
    backend: str = typer.Option("auto", "--backend"),
    planner: str = typer.Option("rule-only", "--planner"),
    research: bool = typer.Option(False, "--research"),
    local_only: bool = typer.Option(False, "--local-only"),
) -> None:
    """Generate PLAN.md, provenance, config, and a standalone harness."""
    if backend not in {"auto", "optuna", "botorch", "smac3"}:
        raise typer.BadParameter("choose auto, optuna, botorch, or smac3")
    if planner != "rule-only":
        console.print(
            "LLM mode is not configured in this v1 build; use --planner rule-only.", style="yellow"
        )
        raise typer.Exit(2)
    if research:
        console.print(
            "No research provider configured; generated plan records no retrieved sources.",
            style="yellow",
        )
    profile, _ = parse_brief(
        brief,
        [str(p) for p in code],
        notes.read_text() if notes else None,
        str(env) if env else None,
    )
    inputs = (
        [str(brief), *map(str, code)]
        + ([str(notes)] if notes else [])
        + ([str(env)] if env else [])
    )
    path = generate(profile, str(brief), str(out), backend, inputs, planner)
    console.print(f"Generated harness at {path}", style="green")
    console.print(
        f"Profile: {len(profile.parameters)} parameters; assumptions/open questions: {len(profile.assumptions_made) + len(profile.open_questions)}"
    )
    if not local_only and planner == "llm":
        console.print("Hosted providers require explicit payload review and are disabled.")


@app.command("validate-brief")
def validate_brief(
    brief: Path = typer.Option(..., "--brief", exists=True, readable=True),
    code: list[Path] = typer.Option([], "--code"),
) -> None:
    profile, _ = parse_brief(brief, [str(p) for p in code])
    constants = scan_code([str(p) for p in code]) if code else {}
    console.print(
        Pretty({"profile": profile.model_dump(mode="json"), "resolved_constants": constants})
    )


@app.command("inspect-backends")
def inspect_backends() -> None:
    console.print(
        json.dumps({k: inspect_backend(k) for k in ("optuna", "botorch", "smac3")}, indent=2)
    )


@app.command("check-harness")
def check_harness(directory: Path) -> None:
    if not (directory / "run_study.py").is_file():
        raise typer.BadParameter("not a generated harness directory")
    with tempfile.TemporaryDirectory(prefix="bayesmith-smoke-") as temporary:
        smoke_dir = Path(temporary) / "harness"
        shutil.copytree(
            directory,
            smoke_dir,
            ignore=shutil.ignore_patterns(
                "study.db", "trials.jsonl", "VERIFICATION_REPORT.md", "__pycache__"
            ),
        )
        config_path = smoke_dir / "config.yaml"
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        config["budget_trials"] = 5
        config["wall_time_seconds"] = min(config.get("wall_time_seconds", 60), 60)
        config["per_trial_timeout_seconds"] = min(config.get("per_trial_timeout_seconds", 10), 10)
        config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
        run = subprocess.run(
            [sys.executable, "run_study.py", "--mode", "synthetic"],
            cwd=smoke_dir,
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        if run.returncode:
            console.print(run.stderr[-2000:], style="red")
            raise typer.Exit(run.returncode)
        verify = subprocess.run(
            [sys.executable, "verify.py", "--mode", "synthetic"],
            cwd=smoke_dir,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if verify.returncode:
            console.print(verify.stderr[-2000:], style="red")
            raise typer.Exit(verify.returncode)
        console.print(run.stdout.strip())
        console.print(verify.stdout.strip())
        console.print("Synthetic harness smoke check passed.", style="green")


@rules_app.command("lint")
def rules_lint() -> None:
    root = Path(__file__).parent / "catalog"
    methods = yaml.safe_load((root / "methods.yaml").read_text())["methods"]
    refs = yaml.safe_load((root / "bibliography.yaml").read_text())["references"]
    rules = yaml.safe_load((root / "rules.yaml").read_text())["rules"]
    errors = []
    rule_ids = {rule.get("rule_id") for rule in rules}
    for method_id, method in methods.items():
        if (
            not method.get("category")
            or not method.get("status")
            or not method.get("citation_keys")
            or not method.get("rule_ids")
        ):
            errors.append(f"{method_id}: missing category/status/citation/rule ID")
        for key in method.get("citation_keys", []):
            if key not in refs:
                errors.append(f"{method_id}: unknown citation {key}")
        for rule_id in method.get("rule_ids", []):
            if rule_id not in rule_ids:
                errors.append(f"{method_id}: unknown rule ID {rule_id}")
    seen_rules: set[str] = set()
    for rule in rules:
        if rule["rule_id"] in seen_rules:
            errors.append(f"duplicate rule ID: {rule['rule_id']}")
        seen_rules.add(rule["rule_id"])
        if rule["recommend_method_id"] not in methods:
            errors.append(f"{rule['rule_id']}: dangling method")
        for key in rule.get("citation_keys", []):
            if key not in refs:
                errors.append(f"{rule['rule_id']}: unknown citation {key}")
        if not rule.get("rationale") or not rule.get("status"):
            errors.append(f"{rule['rule_id']}: missing rationale/status")
        if rule.get("status") not in {"established", "heuristic", "hypothesis"}:
            errors.append(f"{rule['rule_id']}: invalid evidence status")
    if errors:
        console.print("\n".join(errors), style="red")
        raise typer.Exit(1)
    console.print(
        f"Catalog valid: {len(methods)} methods, {len(rules)} rules, {len(refs)} references.",
        style="green",
    )


@example_app.command("list")
def example_list() -> None:
    root = _examples_root()
    console.print("\n".join(sorted(p.name for p in root.iterdir() if p.is_dir())))


@example_app.command("copy")
def example_copy(name: str, out: Path = typer.Option(Path("."), "--out")) -> None:
    root = _examples_root() / name
    if not root.is_dir():
        raise typer.BadParameter(f"unknown example {name}")
    dest = out / name
    if dest.exists():
        raise typer.BadParameter(f"destination already exists: {dest}")
    shutil.copytree(root, dest)
    console.print(dest)


def _examples_root() -> Path:
    repository_examples = Path(__file__).resolve().parents[2] / "examples"
    return (
        repository_examples if repository_examples.is_dir() else Path(__file__).parent / "examples"
    )


@app.callback()
def main() -> None:
    """Bayesmith v1; generation only."""


if __name__ == "__main__":
    app()
