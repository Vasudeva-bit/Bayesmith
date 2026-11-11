# Problem

Tune OpenBLAS GEMM macro-blocking P, Q, R per precision on AMD Zen 4/5. Compile-time macros require a rebuild per trial in static builds; DYNAMIC_ARCH assigns parameters during initialization. Objective is GFLOPs across explicitly selected shapes. The landscape is expected to be discrete and cliff-like around cache boundaries. Bad values may crash or corrupt output. The published PR #5868 reports the following results for its test setup; they are context only, not a prediction or target for a new run:

| Variant | Baseline GFLOPs | Parameters (P,Q,R) | Tuned GFLOPs | Net improvement |
|---|---:|---|---:|---:|
| SGEMM | 2880.00 | 384, 512, 5936 | 3080.71 | +6.9% |
| DGEMM | 1293.73 | 512, 512, 2288 | 1511.87 | +16.8% |
| CGEMM | 2981.33 | 160, 480, 528 | 3143.95 | +5.4% |
| ZGEMM | 1288.60 | 176, 256, 1520 | 1459.45 | +13.2% |

The PR also lists SBGEMM, CGEMM_3M, and ZGEMM_3M among discarded candidates; no performance benefit is inferred here. Source: [OpenBLAS PR #5868](https://github.com/OpenMathLib/OpenBLAS/pull/5868).

```yaml
schema_version: "1.0"
problem: "OpenBLAS GEMM macro-blocking P/Q/R tuning on Zen 4/5"
parameters:
  - {name: P, type: stepped_integer, bounds: [64, 768], step: 16, baseline: 384, source_ref: "fixtures/param.h:1", provenance: read-from-code}
  - {name: Q, type: stepped_integer, bounds: [64, 768], step: 16, baseline: 512, source_ref: "fixtures/param.h:2", provenance: read-from-code}
  - {name: R, type: stepped_integer, bounds: [128, 8192], step: 16, baseline: 5936, source_ref: "fixtures/param.h:3", provenance: read-from-code}
pre_eval_constraints:
  - {name: p_q_panel_l2, expression: "P * Q * 8 <= 0.75 * L2_PER_CORE_BYTES", rationale: "Illustrative double-precision working-set budget; confirm panel accounting and target cache."}
objectives: [{name: GFLOPs, direction: maximize}]
aggregation: weighted_geometric_mean
landscape: cliff_like_discrete
noise_level_pct: 2.0
trial_cost_seconds: 600
budget_trials: 80
batch_size: 1
failure_modes:
  - {mode: crash, behavior: region-correlated near bounds}
  - {mode: wrong result, behavior: region-correlated near bounds}
validity_oracle: "Compare each output with a trusted reference within a precision-specific tolerance; define tolerance before real run."
workloads: [{name: "engineer-selected shapes", weight: 1.0}]
hardware_context:
  cpu_model: "AMD Zen 4/5 (exact SKU required)"
  l2_per_core_bytes: 1048576
  l3_bytes_per_sharing_domain: 33554432
  num_l3_domains: 4
  l3_aggregate_bytes: 134217728
  cores_per_domain: null
  extra: {note: "Illustrative Zen 4 values from issue discussion; SKU topology varies. Never substitute aggregate L3 for per-domain L3."}
environment_scope:
  - "Record exact OpenBLAS revision, core type, compiler, ABI, thread count, and build flags."
  - "Document fixed stack/buffer limits and identify every kernel consuming P, Q, and R."
  - "Test forced core types and non-AVX512 fallback kernels; upstream follow-up issues document a buffer-safety failure path for some core overrides."
assumptions_made:
  - "The ranges and step are fixture examples, not authoritative OpenBLAS limits. Derive production ranges from the exact source revision and kernels."
  - "Cache footprint expression is illustrative and must be replaced with the true panel bytes and cache sharing topology."
open_questions:
  - "Which exact precision and kernel/core types will be tuned in each separate study?"
  - "Which shape suite, correctness tolerance, build command, and clean-build verification procedure apply?"
  - "Are P/Q/R macros or runtime init values for this build configuration?"
```

## Evaluator modes

`build_per_trial`: set compile-time values in a temporary source copy/worktree, build with at most `max_build_jobs`, and cache by parameter/build hash. Never build in the developer working tree.

`runtime_env_hook`: local tuning-only hook sketch: at startup read engineer-defined `BAYESMITH_GEMM_P`, `BAYESMITH_GEMM_Q`, `BAYESMITH_GEMM_R`, then assign the selected per-precision table values after validating them. This is an illustrative local change only, not an upstream patch. DYNAMIC_ARCH values are initialized in `kernel/setparam-ref.c`; static builds use compile-time defaults. Check the exact OpenBLAS revision and affected core's buffers before adapting. Final confirmation must use clean builds without this hook.

Source notes: [PR #5868](https://github.com/OpenMathLib/OpenBLAS/pull/5868), [issue #5837](https://github.com/OpenMathLib/OpenBLAS/issues/5837). A later issue records a safety path where host-derived blocking interacted with forced core types and kernel buffer assumptions; review [issue #6021](https://github.com/OpenMathLib/OpenBLAS/issues/6021) before using this example.
