# Problem

Optimize a synthetic three-dimensional stepped integer objective with noise, a cliff, and a crash region.

```yaml
problem: synthetic noisy cliff
parameters:
  - {name: x, type: stepped_integer, bounds: [0, 100], step: 5, baseline: 20}
  - {name: y, type: integer, bounds: [0, 100], baseline: 40}
  - {name: z, type: categorical, choices: [a, b, c], baseline: a}
pre_eval_constraints: [{name: budget, expression: "x + y <= 150", rationale: synthetic resource constraint}]
objectives: [{name: score, direction: maximize}]
landscape: cliff_like_discrete
budget_trials: 25
failure_modes: [{mode: crash, behavior: region-correlated near bounds}]
```
