from typer.testing import CliRunner

from bayesmith.cli import app


def test_catalog_lint():
    result = CliRunner().invoke(app, ["rules", "lint"])
    assert result.exit_code == 0, result.stdout


def test_generate_minimal(tmp_path):
    brief = tmp_path / "brief.md"
    brief.write_text(
        "# Problem\nA small test.\n```yaml\nproblem: small test\nparameters:\n  - {name: x, type: integer, bounds: [1, 10], baseline: 2}\nbudget_trials: 5\n```\n"
    )
    out = tmp_path / "bundle"
    result = CliRunner().invoke(
        app, ["generate", "--brief", str(brief), "--out", str(out), "--backend", "optuna"]
    )
    assert result.exit_code == 0, result.stdout
    for name in (
        "PLAN.md",
        "provenance.json",
        "config.yaml",
        "evaluator.py",
        "run_study.py",
        "verify.py",
        "synthetic_objective.py",
    ):
        assert (out / name).is_file()
    smoke = CliRunner().invoke(app, ["check-harness", str(out)])
    assert smoke.exit_code == 0, smoke.stdout
