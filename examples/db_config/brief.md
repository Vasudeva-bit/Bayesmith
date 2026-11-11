# Problem

Tune a mocked database configuration under expensive evaluations; use a finite run budget, keep failure records, and evaluate the final choice on held-out query mixes.

```yaml
problem: mock database config
parameters:
  - {name: cache_mb, type: integer, bounds: [64, 4096], baseline: 512}
  - {name: workers, type: integer, bounds: [1, 32], baseline: 4}
  - {name: scheduler, type: categorical, choices: [fifo, fair, adaptive], baseline: fifo}
objectives: [{name: queries_per_second, direction: maximize}]
landscape: mixed_combinatorial
budget_trials: 20
trial_cost_seconds: 120
failure_modes: [{mode: timeout, behavior: rare}]
```
