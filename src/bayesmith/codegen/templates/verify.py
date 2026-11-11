"""Paired confirmation/reporting from recorded synthetic evaluations."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import yaml


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["synthetic", "real"], default="synthetic")
    ap.parse_args()
    rows = [
        json.loads(line) for line in Path("trials.jsonl").read_text().splitlines() if line.strip()
    ]
    valid = [
        r
        for r in rows
        if r.get("status") == "OK"
        and isinstance(r.get("objective"), (int, float))
        and not r.get("imputed")
    ]
    cfg = yaml.safe_load(Path("config.yaml").read_text())
    if len(valid) < 2:
        outcome, body = (
            "INSUFFICIENT_VALID_TRIALS",
            "At least two valid trials are required for confirmation.",
        )
    else:
        baseline = next((r for r in valid if r.get("trial_id") == 0), valid[0])
        maximize = cfg["profile"]["objectives"][0]["direction"] == "maximize"
        best = (max if maximize else min)(valid, key=lambda r: r["objective"])
        delta = best["objective"] - baseline["objective"]
        pct = (delta if maximize else -delta) / max(abs(baseline["objective"]), 1e-12) * 100
        random.seed(cfg["seed"])
        diffs = [
            best["objective"] - baseline["objective"] + random.gauss(0, abs(pct) / 4 + 0.01)
            for _ in range(1000)
        ]
        diffs.sort()
        lo, hi = diffs[24], diffs[974]
        outcome = (
            "NO_SIGNIFICANT_GAIN"
            if lo <= 0 <= hi or pct <= 0
            else "PROMISING_GAIN_REQUIRES_REAL_PAIRED_RUNS"
        )
        body = f"Baseline objective: {baseline['objective']:.6g}\nBest observed objective: {best['objective']:.6g}\nObserved synthetic change: {pct:.3f}%\nBootstrap-like interval (illustrative synthetic check only): [{lo:.3f}, {hi:.3f}] percentage points\nPaired significance: not computed; run real interleaved ABBA/BAAB confirmations."
    report = f"# Verification report\n\nOutcome: **{outcome}**\n\n{body}\n\nTrials: {len(rows)} total, {len(valid)} valid. Imputed failures and invalid trials are excluded. This script's synthetic mode is a wiring check, not evidence of performance. Real confirmation requires repeated interleaved baseline/candidate evaluations on held-out workloads and hardware.\n"
    Path("VERIFICATION_REPORT.md").write_text(report)
    print(outcome)


if __name__ == "__main__":
    main()
