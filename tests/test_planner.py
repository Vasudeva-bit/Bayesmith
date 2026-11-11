from bayesmith.planner.failures import impute_failure
from bayesmith.planner.rule_engine import plan
from bayesmith.schemas.profile import (
    Constraint,
    FailureMode,
    HardwareContext,
    Parameter,
    ProblemProfile,
    constraints_pass,
)


def test_rule_selection_is_deterministic():
    profile = ProblemProfile(
        problem="cliff",
        parameters=[
            Parameter(name=n, type="stepped_integer", bounds=[16, 256], step=16) for n in "PQR"
        ],
        pre_eval_constraints=[Constraint(name="cache", expression="P * Q * 8 <= l2")],
        failure_modes=[FailureMode(mode="crash", behavior="region-correlated near bounds")],
        hardware_context=HardwareContext(extra={"l2": 65536}),
    )
    assert plan(profile, "optuna") == plan(profile, "optuna")
    assert [r["rule_id"] for r in plan(profile, "optuna")] == [
        "R_INIT_BASELINE_SOBOL",
        "R_PRE_EVAL_REPARAM",
        "R_TPE_FALLBACK",
        "R_CRASH_IMPUTE",
    ]


def test_invalid_constraint_detectable_before_evaluation():
    profile = ProblemProfile(
        problem="x",
        parameters=[Parameter(name="x", type="integer", bounds=[1, 5])],
        pre_eval_constraints=[Constraint(name="cap", expression="x <= 3")],
    )
    assert constraints_pass(profile, {"x": 2})
    assert not constraints_pass(profile, {"x": 4})


def test_failure_imputation_is_direction_aware_and_cold_start_bounded():
    assert impute_failure([10.0, 20.0], "maximize", 0.15) == (8.5, False)
    assert impute_failure([], "minimize", 0.15) == (0.15, True)
