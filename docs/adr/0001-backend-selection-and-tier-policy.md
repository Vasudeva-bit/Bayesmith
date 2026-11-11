# ADR 0001: Optuna-first backend and catalog-first policy

**Status:** Accepted for v1

## Decision

Implement Optuna as the only runnable backend adapter. Keep BoTorch and SMAC3 as optional capability/introspection targets, and do not choose them as runnable adapters yet. Recommend only methods in the checked-in Tier-1 catalog. Do not promote a framework method from memory or silently mutate the catalog.

## Context

The flagship OpenBLAS search is low-dimensional but stepped/discrete, expensive to build, and has invalid/failure regions. Optuna TPE is a direct fit to mixed/discrete suggestions and supports persistent studies. BoTorch offers richer GP and acquisition control but requires a separately tested tensor path and discrete candidate filtering. Shipping a partial BoTorch integration would overstate support. SMAC's categorical/mixed support is attractive but also needs a maintained, tested adapter.

## Consequences

`auto` selects Optuna if installed and otherwise explains the missing extra; the generated runner itself requires Optuna. BoTorch and SMAC3 are not advertised as selectable runnable v1 backends. This is a narrower implementation than the brief's desirable backend matrix and avoids unverified API assumptions. Revisit when adapters pass generated-harness smoke tests on supported dependency versions.

## Evidence reviewed

- Optuna's sampler API and stable documentation: https://optuna.readthedocs.io/en/stable/reference/samplers/index.html
- OpenBLAS PR #5868 and its documented results: https://github.com/OpenMathLib/OpenBLAS/pull/5868
- The archived scikit-optimize upstream repository: https://github.com/scikit-optimize/scikit-optimize
