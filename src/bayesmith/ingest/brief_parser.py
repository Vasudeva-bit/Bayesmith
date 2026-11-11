"""Parse Markdown briefs with optional YAML profile blocks."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from bayesmith.schemas.profile import ProblemProfile


def parse_brief(
    path: str | Path,
    code_paths: list[str] | None = None,
    notes: str | None = None,
    env_path: str | None = None,
) -> tuple[ProblemProfile, str]:
    text = Path(path).read_text(encoding="utf-8")
    blocks = re.findall(r"```(?:yaml|yml)\s*\n(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
    data: dict[str, Any] = {}
    for block in blocks:
        loaded = yaml.safe_load(block) or {}
        if isinstance(loaded, dict):
            data.update(loaded)
    sections: dict[str, str] = {}
    heading = None
    for line in text.splitlines():
        if line.startswith("# "):
            heading = line[2:].strip().lower().replace(" / ", "_").replace(" ", "_")
            sections[heading] = ""
        elif heading:
            sections[heading] += line + "\n"
    if not data:
        problem_text = sections.get("problem", "") or text
        params = []
        # Parse simple prose declarations such as "P: integer 64..512 step 16 baseline 256".
        for name, lo, hi, step in re.findall(
            r"\b([A-Za-z_]\w*)\s*:\s*(?:stepped[_ -]?integer|integer)\s+(\d+)\s*\.\.\s*(\d+)(?:\s+step\s+(\d+))?",
            problem_text,
            re.IGNORECASE,
        ):
            p: dict[str, Any] = {
                "name": name,
                "type": "stepped_integer" if step else "integer",
                "bounds": [int(lo), int(hi)],
            }
            if step:
                p["step"] = int(step)
            params.append(p)
        data = {
            "problem": problem_text.strip().splitlines()[0][:200] or Path(path).stem,
            "parameters": params,
        }
    data.setdefault("problem", Path(path).stem)
    assumptions = list(data.get("assumptions_made", []))
    questions = list(data.get("open_questions", []))
    if not data.get("parameters"):
        assumptions.append(
            "No tunable parameters were parsed; define them in a YAML profile block."
        )
        questions.append(
            "What parameter names, types, bounds, steps, and baseline values should be tuned?"
        )
    data["assumptions_made"] = assumptions
    data["open_questions"] = questions
    if notes:
        data["engineer_notes"] = [line.strip() for line in notes.splitlines() if line.strip()]
    if env_path:
        env = yaml.safe_load(Path(env_path).read_text(encoding="utf-8")) or {}
        data["hardware_context"] = {
            **data.get("hardware_context", {}),
            **env.get("hardware_context", env),
        }
    if code_paths:
        from bayesmith.ingest.code_scanner import scan_code

        symbols = scan_code(code_paths)
        data.setdefault("environment_scope", []).append(
            f"Read-only code scan found {len(symbols)} constants."
        )
    profile = ProblemProfile.model_validate(data)
    return profile, text
