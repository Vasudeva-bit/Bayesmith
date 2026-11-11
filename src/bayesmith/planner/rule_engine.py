"""Small deterministic Tier-1 planner backed by the checked-in rule catalog."""

from __future__ import annotations

from typing import Any

from bayesmith.schemas.profile import ProblemProfile


def plan(profile: ProblemProfile, backend: str) -> list[dict[str, Any]]:
    fired = [
        {
            "rule_id": "R_INIT_BASELINE_SOBOL",
            "method": "baseline_first",
            "status": "heuristic",
            "citation_keys": ["optuna"],
            "rationale": "Evaluate the exact baseline first; subsequent startup sampling uses the selected framework sampler.",
        }
    ]
    if any(p.type == "stepped_integer" for p in profile.parameters) or profile.pre_eval_constraints:
        fired.append(
            {
                "rule_id": "R_PRE_EVAL_REPARAM",
                "method": "pre_eval_filter",
                "status": "heuristic",
                "citation_keys": ["optuna"],
                "rationale": "Map stepped integers to integer indices and filter analytical constraints before evaluation.",
            }
        )
    if backend == "optuna":
        fired.append(
            {
                "rule_id": "R_TPE_FALLBACK",
                "method": "tpe",
                "status": "established",
                "citation_keys": ["bergstra2011", "optuna"],
                "rationale": "Optuna TPE handles discrete and mixed search spaces.",
            }
        )
    if profile.failure_modes:
        fired.append(
            {
                "rule_id": "R_CRASH_IMPUTE",
                "method": "conservative_imputation",
                "status": "heuristic",
                "citation_keys": ["bayesmith_imputation_heuristic"],
                "rationale": "Use direction-aware conservative imputation; preserve failure labels and exclude failures from reported best.",
            }
        )
    return fired
