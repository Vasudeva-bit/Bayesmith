"""Bounded read-only extraction of C/C++ and Python constants."""

from __future__ import annotations

import re
from pathlib import Path

MAX_FILE_BYTES = 1_000_000
DENIED_PARTS = {".git", "node_modules", "vendor", "build", "dist"}


def scan_code(paths: list[str], allowlist: list[str] | None = None) -> dict[str, dict[str, object]]:
    found: dict[str, dict[str, object]] = {}
    for raw in paths:
        path = Path(raw)
        files = [path] if path.is_file() else [p for p in path.rglob("*") if p.is_file()]
        for file in files:
            if any(part in DENIED_PARTS for part in file.parts):
                continue
            if allowlist and not any(file.match(pattern) for pattern in allowlist):
                continue
            try:
                if file.stat().st_size > MAX_FILE_BYTES:
                    continue
                lines = file.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for number, line in enumerate(lines, 1):
                match = re.match(r"\s*#\s*define\s+([A-Za-z_]\w*)\s+([-+]?\d+)\b", line)
                py = re.match(r"\s*([A-Z][A-Z0-9_]*)\s*=\s*([-+]?\d+)\s*(?:#.*)?$", line)
                assignment = re.match(
                    r"\s*[A-Za-z_]\w*\s*\.\s*([A-Za-z_]\w*)\s*=\s*([-+]?\d+)\s*;",
                    line,
                )
                m = match or py or assignment
                if m:
                    symbol = m.group(1).upper() if m is assignment else m.group(1)
                    found[symbol] = {"value": int(m.group(2)), "source_ref": f"{file}:{number}"}
    return found
