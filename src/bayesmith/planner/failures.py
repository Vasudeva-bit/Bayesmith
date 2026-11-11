"""Direction-aware, bounded failure imputation helpers."""

from __future__ import annotations

from typing import Literal


def impute_failure(
    valid_objectives: list[float],
    direction: Literal["maximize", "minimize"],
    margin_fraction: float = 0.15,
) -> tuple[float, bool]:
    """Return an optimizer-only penalty and whether it used the cold-start prior.

    This is a heuristic. Failed values must retain their original failure status
    and must not enter valid-result or noise summaries.
    """
    if not 0 <= margin_fraction <= 1:
        raise ValueError("margin_fraction must be between zero and one")
    if not valid_objectives:
        return (-margin_fraction if direction == "maximize" else margin_fraction), True
    low, high = min(valid_objectives), max(valid_objectives)
    worst = low if direction == "maximize" else high
    margin = margin_fraction * max(high - low, abs(worst) * 0.01, 1e-12)
    return (low - margin if direction == "maximize" else high + margin), False
