# Contributing

Contributions are welcome, especially rule/citation reviews, new workload fixtures, generated-harness safety reports, and operating system/hardware coverage. Keep the generator deterministic and offline by default. Never add an uncited method as established or let a generated evaluator edit a host checkout.

## Development

```sh
python -m pip install -e '.[dev,optuna]'
ruff check src tests
mypy src/bayesmith
pytest
bayesmith rules lint
```

## Evidence and proposals

Use the issue templates for bugs, rule/citation proposals, and benchmarks. Include exact dependency versions, input brief, platform/toolchain fingerprint, and a minimal reproduction. Report negative or inconclusive outcomes too. Rule status should distinguish established evidence, heuristic engineering judgment, and hypothesis.

Sponsorship and other support are welcome; no particular form is expected.
