# Problem

Choose GPU tile settings using a mock evaluator. The fixture includes a large infeasible region; all known analytical constraints should be filtered before launch.

```yaml
problem: mock GPU tile search
parameters:
  - {name: tile_m, type: stepped_integer, bounds: [8, 128], step: 8, baseline: 32}
  - {name: tile_n, type: stepped_integer, bounds: [8, 128], step: 8, baseline: 32}
  - {name: warps, type: categorical, choices: [2, 4, 8], baseline: 4}
pre_eval_constraints: [{name: shared_memory, expression: "tile_m * tile_n * 4 <= 49152", rationale: "mock shared-memory cap"}]
objectives: [{name: throughput, direction: maximize}]
landscape: mixed_combinatorial
budget_trials: 30
```
