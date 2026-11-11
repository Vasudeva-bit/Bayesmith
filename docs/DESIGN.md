# Bayesmith v1 design

Bayesmith is a generator. Its runtime output is a standalone directory containing the machine-readable profile, safe configuration, recommendation audit, provenance, and an evaluator / study / verification harness. The core path is offline and uses deterministic rules; optional frameworks are only introspected in short-lived subprocesses.

## Data and ingestion

`ProblemProfile` is a Pydantic v2 model (`schema_version: 1.0`, extra keys forbidden). It models parameter bounds and provenance, analytical constraints, objective direction and aggregation, landscape/noise/budget, failure behavior, workload and validity scope, cache topology, assumptions, and open questions. Markdown accepts a fenced YAML profile. Missing parameters are retained as an explicit assumption and question. `--code` scans read-only files up to 1 MB each, skips common generated/vendor trees, and extracts numeric C preprocessor and Python uppercase constants with file/line provenance.

Constraints are parsed using Python's AST and evaluated only for a small whitelist of arithmetic, comparisons, boolean operators, names, and numeric literals. There is no `eval`. Inputs that are syntactically valid Python but outside this whitelist fail closed.

## Planning and catalog

Catalog YAML separates method metadata, rules, citations, and capability bindings. `bayesmith rules lint` rejects unresolved references, missing rationale, and missing status. The current rules prefer baseline-first and Optuna TPE for discrete spaces, pre-evaluation filtering for known constraints, and labeled direction-aware imputation when failures exist. Optuna's adapter currently uses its default TPE startup sampler, not the catalogued Sobol option. The exact status of each rule appears in the plan. The catalog is read-only during generation.

Rule-only is implemented. LLM providers and live research providers are intentionally not wired in this first implementation: there is no secret-bearing or hosted-egress path to surprise the user. CLI options are accepted only where a safe behavior exists; `--planner llm` exits with a clear message. Future provider work must show the outbound payload and support redaction / allowlists.

## Backend policy

Optuna is the v1 implemented backend. BoTorch and SMAC3 can be inspected if installed, but the generated study adapter currently uses Optuna. Automatic selection never claims a backend is operational merely because import succeeds. See ADR 0001. The generated Optuna TPE sampler is seeded and configured explicitly; no assumed GP kernel is used. Optional extras pin or bound dependencies independently.

## Generated evaluation contract

The study process writes one JSON trial request and invokes `evaluator.py` in a new process session. It records one JSON result per line in `trials.jsonl`, includes UPPER_SNAKE statuses, isolates target execution, and applies a finite timeout. The command-only mode accepts an explicit evaluator command and JSON/numeric output. Generated config documents build-per-trial and runtime-hook fields; source copying, builds, compile cache population, correctness oracles, per-workload aggregation, full process-tree timeout killing, and statistically valid real paired verification remain engineer-configured work. Synthetic mode is self-contained and is the default smoke path.

Analytical constraints are checked before evaluator invocation. The exact baseline remains trial zero even if invalid. Failed black-box evaluations are labeled and imputed only for optimizer continuity; imputed points are excluded from best valid reporting. The imputation is a heuristic. Generated `verify.py` explicitly labels its synthetic interval as illustrative, not inferential.

## Safety and provenance

Generated budgets are finite and capped, build parallelism defaults to four, and nice defaults to ten. The harness does not edit or build a host source tree. It records input hashes, platform/Python, selected backend introspection, rule firings, and generation timestamp. Credentials are not read or emitted. The `--local-only` switch is a no-op guard in the rule-only build because no network-capable provider exists.

## Open implementation questions

- Implement mature source-copy/build-cache strategies and process-group termination on all supported platforms.
- Add fully tested BoTorch ask/tell, discrete acquisition optimization, explicit kernel construction, and supported feasibility modeling before advertising it as a runnable backend.
- Improve natural-language parameter extraction and resolve symbolic code references into parameter metadata; YAML remains the authoritative profile today.
- Add real ABBA/BAAB verification, paired tests, held-out workload support, and per-shape regression reporting.
- Validate method references against versioned live docs during release review and broaden citation coverage before claiming a complete research survey.
