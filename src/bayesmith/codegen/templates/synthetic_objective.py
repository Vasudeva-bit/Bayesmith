"""Synthetic cliff objective with parameter-scaled noise and failure regions."""

from __future__ import annotations

import random
from typing import Any


def evaluate(
    params: dict[str, Any], seed: int = 0, profile: dict[str, Any] | None = None
) -> tuple[str, float | None, str]:
    rng = random.Random(seed)
    definitions = {p["name"]: p for p in (profile or {}).get("parameters", [])}
    values: list[float] = []
    for name, value in params.items():
        definition = definitions.get(name, {})
        if isinstance(value, (int, float)):
            bounds = definition.get("bounds")
            if bounds and bounds[1] > bounds[0]:
                values.append((float(value) - bounds[0]) / (bounds[1] - bounds[0]) * 100)
            else:
                values.append(float(value))
        elif value in definition.get("choices", []):
            choices = definition["choices"]
            values.append(100.0 * choices.index(value) / max(len(choices) - 1, 1))
    if not values:
        values = [0.0]
    if any(value > 92 for value in values):
        return "SEGFAULT", None, "synthetic boundary crash region"
    target = [23.0, 47.0, 68.0]
    score = 100.0 - sum(
        (value - target[i % len(target)]) ** 2 for i, value in enumerate(values)
    ) / max(1, len(values))
    if any(45 < value < 55 for value in values):
        score -= 18.0
    return "OK", score + rng.gauss(0, 0.6), ""
