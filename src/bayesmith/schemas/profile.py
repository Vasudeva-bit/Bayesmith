"""Versioned problem profile and safe constraint evaluation."""

from __future__ import annotations

import ast
import operator
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Parameter(StrictModel):
    name: str
    type: Literal[
        "continuous", "integer", "stepped_integer", "categorical", "ordinal", "boolean"
    ] = "integer"
    bounds: list[float | int] | None = None
    choices: list[Any] = Field(default_factory=list)
    step: float | int | None = None
    multiple_of: float | int | None = None
    scale: Literal["linear", "log"] = "linear"
    baseline: Any | None = None
    condition: str | None = None
    source_ref: str | None = None
    provenance: Literal["user-stated", "read-from-code", "LLM-assumed"] = "user-stated"

    @model_validator(mode="after")
    def valid_range(self) -> Parameter:
        if self.bounds is not None and (len(self.bounds) != 2 or self.bounds[0] > self.bounds[1]):
            raise ValueError("bounds must be [low, high]")
        if self.type in {"integer", "stepped_integer", "continuous"} and self.bounds is None:
            raise ValueError(f"{self.type} parameter requires bounds")
        if self.type == "stepped_integer" and not (self.step or self.multiple_of):
            raise ValueError("stepped_integer requires step or multiple_of")
        if self.type in {"categorical", "ordinal"} and not self.choices:
            raise ValueError(f"{self.type} parameter requires choices")
        return self


class Constraint(StrictModel):
    name: str
    expression: str
    rationale: str = "Analytical validity constraint"


class Objective(StrictModel):
    name: str = "performance"
    direction: Literal["maximize", "minimize"] = "maximize"
    weight: float = 1.0
    threshold: float | None = None


class FailureMode(StrictModel):
    mode: str
    behavior: Literal["none", "rare", "region-correlated near bounds"] = "rare"


class HardwareContext(StrictModel):
    cpu_model: str | None = None
    l1d_per_core_bytes: int | None = None
    l2_per_core_bytes: int | None = None
    l3_bytes_per_sharing_domain: int | None = None
    num_l3_domains: int | None = None
    l3_aggregate_bytes: int | None = None
    cores_per_domain: int | None = None
    smt: bool | None = None
    compiler: str | None = None
    os: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class ProblemProfile(StrictModel):
    schema_version: str = "1.0"
    problem: str
    parameters: list[Parameter] = Field(default_factory=list)
    pre_eval_constraints: list[Constraint] = Field(default_factory=list)
    objectives: list[Objective] = Field(default_factory=lambda: [Objective()])
    aggregation: str = "weighted_geometric_mean"
    landscape: Literal["smooth", "cliff_like_discrete", "high_noise", "mixed_combinatorial"] = (
        "cliff_like_discrete"
    )
    noise_level_pct: float | None = None
    drift_notes: str | None = None
    trial_cost_seconds: float | None = None
    budget_trials: int = 30
    batch_size: int = 1
    parallelism: int = 1
    failure_modes: list[FailureMode] = Field(default_factory=list)
    validity_oracle: str | None = None
    workloads: list[dict[str, Any]] = Field(default_factory=list)
    hardware_context: HardwareContext = Field(default_factory=HardwareContext)
    fidelity_ladder: list[Any] = Field(default_factory=list)
    environment_scope: list[str] = Field(default_factory=list)
    engineer_notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_constraints(self) -> ProblemProfile:
        names = {parameter.name for parameter in self.parameters}
        names.update(
            key.upper()
            for key, value in self.hardware_context.model_dump(exclude_none=True).items()
            if isinstance(value, (int, float, bool))
        )
        names.update(
            key
            for key, value in self.hardware_context.extra.items()
            if isinstance(value, (int, float, bool))
        )
        placeholders = {name: 1 for name in names}
        for constraint in self.pre_eval_constraints:
            try:
                safe_expression(constraint.expression, placeholders)
            except (SyntaxError, TypeError, ValueError) as exc:
                raise ValueError(f"unsafe/invalid constraint {constraint.name!r}: {exc}") from exc
        return self

    assumptions_made: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


_BIN = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_CMP = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}


def safe_expression(expression: str, values: dict[str, Any]) -> bool:
    """Evaluate a deliberately small arithmetic/boolean expression; Python eval is never used."""
    tree = ast.parse(expression, mode="eval")

    def visit(node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float, bool)):
            return node.value
        if isinstance(node, ast.Name) and node.id in values:
            return values[node.id]
        if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
            return _BIN[type(node.op)](visit(node.left), visit(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub, ast.Not)):
            val = visit(node.operand)
            return (
                not val
                if isinstance(node.op, ast.Not)
                else (+val if isinstance(node.op, ast.UAdd) else -val)
            )
        if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
            vals = [bool(visit(v)) for v in node.values]
            return all(vals) if isinstance(node.op, ast.And) else any(vals)
        if isinstance(node, ast.Compare):
            left = visit(node.left)
            for op, right_node in zip(node.ops, node.comparators):
                if type(op) not in _CMP:
                    raise ValueError("comparison operator not allowed")
                right = visit(right_node)
                if not _CMP[type(op)](left, right):
                    return False
                left = right
            return True
        raise ValueError(f"unsafe or unsupported expression node: {type(node).__name__}")

    return bool(visit(tree))


def constraints_pass(
    profile: ProblemProfile, params: dict[str, Any], environment: dict[str, Any] | None = None
) -> bool:
    values = {**(environment or {}), **params}
    return all(safe_expression(c.expression, values) for c in profile.pre_eval_constraints)
