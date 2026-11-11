# Bayesmith

Bayesmith turns an engineer's tuning brief into a reviewable Bayesian optimization harness bundle: a profile, cited recommendation plan, safe run configuration, evaluator boundary, resumable study, verification report, and input provenance. Version 1 generates the harness; the engineer runs it. Its core planner is offline and rule-only.

## Quickstart

```sh
python -m pip install -e '.[optuna]'
bayesmith validate-brief --brief examples/openblas_gemm_pqr/brief.md
bayesmith generate --brief examples/openblas_gemm_pqr/brief.md \
  --code examples/openblas_gemm_pqr/fixtures --backend optuna --out ./gemm-harness
cd gemm-harness
python run_study.py --mode synthetic
python verify.py --mode synthetic
```

The OpenBLAS brief records the merged PR's reported result table exactly as published. Those numbers are historical context, not an expected outcome. Its search bounds and cache expression are explicitly illustrative; check the exact source revision, precision, core type, kernel limits, buffer/stack invariants, compiler and machine before any real evaluation. The fixture source is a small scanner demonstration, not upstream OpenBLAS source.

## Brief format

Provide a Markdown problem statement with optional sections for `Problem`, `Black-box nature`, `Hardware / environment`, `Constraints`, `Validity`, and `Notes from engineers`. A fenced YAML block is the authoritative structured profile. It can define parameters, objective direction, pre-evaluation expressions, hardware cache topology, workloads, failure modes, budgets, assumptions and questions. Natural language extraction is deliberately conservative; missing information becomes a visible assumption/question.

```yaml
problem: compiler flag tuning
parameters:
  - {name: unroll, type: stepped_integer, bounds: [1, 32], step: 1, baseline: 4}
pre_eval_constraints:
  - {name: safe, expression: "unroll <= 16", rationale: "known compiler limit"}
objectives: [{name: runtime_ms, direction: minimize}]
budget_trials: 40
failure_modes: [{mode: timeout, behavior: rare}]
validity_oracle: "Compare output with reference data at a declared tolerance."
```

Input code is read-only. Numeric constants are scanned from files up to 1 MB, with common generated/vendor directories skipped. Only YAML-defined profile fields are currently used by the planner; code-scan results are not yet automatically substituted into symbolic parameter definitions. Notes are retained as scope context; environment YAML can fill hardware facts.

## What the planner chooses

Bayesmith prefers its cited Tier-1 catalog. The v1 runnable harness uses a seeded Optuna TPE sampler for mixed/discrete spaces, includes the exact baseline as trial 0, checks known analytical constraints before evaluator launch, and records labeled black-box failures. If needed to continue optimization, failures get direction-aware conservative imputation, marked heuristic and excluded from best-result reporting. No custom optimization mathematics is generated. There is no runnable BoTorch or SMAC adapter yet; these packages are inspection targets only. Tier-2 outside-catalog selection is not enabled until live introspection, docs provenance, and a tested fallback adapter are available.

The method catalog distinguishes `established`, `heuristic`, and `hypothesis`; `bayesmith rules lint` checks reference and rationale integrity. Read [docs/DESIGN.md](docs/DESIGN.md) and [ADR 0001](docs/adr/0001-backend-selection-and-tier-policy.md) for implementation boundaries.

## Generated bundle and safety

`PLAN.md`, `provenance.json`, and `config.yaml` make recommendations and assumptions reviewable. Generated defaults cap trial count at 10,000, wall time and per-trial time are finite, build parallelism is at most four, and `nice` defaults to 10. The evaluator runs in a separate process and records UPPER_SNAKE statuses. The generic real runner requires a user-supplied command and does not build or edit a host tree. The engineer must configure an isolated source copy/worktree, correctness checks, build cache, workload suite, and clean final verification before using real mode.

Synthetic mode is for wiring checks. `verify.py` labels its synthetic interval illustrative; it is not a valid performance significance test. Real ABBA/BAAB paired verification is an open implementation item. Runtime harness code has no LLM dependency. `--planner llm` is currently rejected; no network research provider is enabled, so API secrets are neither read nor sent. `--local-only` is accepted as a safety switch.

## Examples

- `examples/openblas_gemm_pqr/`: OpenBLAS P/Q/R brief, source fixtures and two evaluator-mode sketches.
- `examples/synthetic_noisy_cliff/`: stepped noisy cliff profile.
- `examples/gpu_tile_search/`: many-invalid-config GPU tile profile.
- `examples/db_config/`: expensive mixed database configuration profile.

Use `bayesmith example list` and `bayesmith example copy NAME --out DIR` to copy one.

## Related work

Bayesmith is not the first BO harness generator or autotuner. Optuna provides general-purpose samplers and study storage; BoTorch/Ax provide GP-based optimization tools; SMAC targets algorithm configuration; Kernel Tuner, OpenTuner and ytopt support empirical program/kernel tuning. BaCO focuses on Bayesian compiler optimization. LLAMBO studies LLM-assisted BO, while Honegumi RAG Assistant is a 2025 working paper describing natural-language generation of Ax-based BO code, and 2026 work such as LMABO studies LLM selection of acquisition strategies. These systems have different goals and evidence levels; links below are for context, not a comparative performance claim.

Bayesmith's intended emphasis is systems/HPC tuning inputs with build-parameterized evaluation, explicit noise/failure/validity concerns, safe resource defaults, and an auditable cited rule plan. That focus is a design choice, not a novelty or superiority claim.

- [Optuna samplers](https://optuna.readthedocs.io/en/stable/reference/samplers/index.html)
- [BoTorch documentation](https://botorch.org/docs/introduction)
- [SMAC3 repository](https://github.com/automl/SMAC3)
- [Kernel Tuner paper](https://doi.org/10.1016/j.future.2018.08.004)
- [OpenTuner paper](https://doi.org/10.1145/2628071.2628092)
- [ytopt project](https://github.com/ytopt-team/ytopt)
- [BaCO paper](https://doi.org/10.1145/3623278.3624770)
- [LLAMBO (ICLR 2024)](https://proceedings.iclr.cc/paper_files/paper/2024/file/84b8d9fcb4e262fcd429544697e1e720-Paper-Conference.pdf)
- [Honegumi RAG Assistant (working paper)](https://doi.org/10.26434/chemrxiv-2025-f1wcr)
- [LMABO (ICLR 2026)](https://proceedings.iclr.cc/paper_files/paper/2026/hash/f1b7a29fe9759d4c9d23f78738e40b42-Abstract-Conference.html)
- [scikit-optimize upstream archive](https://github.com/scikit-optimize/scikit-optimize) (not selected as a default)

## Future features

See [ROADMAP.md](ROADMAP.md) for planned or under-consideration work: code scope discovery, clarification dialogue, safe run mode and noise probing, evidence-backed patch generation, additional backends and optimization regimes, domain packs, meta-benchmarks, reviewed community rule packs, and IDE/MCP integration.

## Contributing, testing and sponsorship

Contributions, testing proposals, new benchmarks, hardware/OS coverage and failure reports are very welcome. Start with [CONTRIBUTING.md](CONTRIBUTING.md) and the [issue templates](.github/ISSUE_TEMPLATE/). Sponsorship in any form is welcome.
