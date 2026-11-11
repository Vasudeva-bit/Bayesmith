from pathlib import Path

import pytest
from pydantic import ValidationError

from bayesmith.ingest.brief_parser import parse_brief
from bayesmith.ingest.code_scanner import scan_code
from bayesmith.schemas.profile import Parameter, ProblemProfile, constraints_pass, safe_expression


def test_profile_rejects_extra_and_bad_steps():
    with pytest.raises(ValidationError):
        Parameter(name="x", type="stepped_integer", bounds=[1, 5])
    with pytest.raises(ValidationError):
        ProblemProfile(problem="x", invented=True)


def test_expression_whitelist():
    assert safe_expression("x % 16 == 0 and x * 2 <= limit", {"x": 32, "limit": 64})
    with pytest.raises(ValueError):
        safe_expression("__import__('os').system('true')", {})
    with pytest.raises(ValueError):
        safe_expression("x[0]", {"x": [1]})


def test_scanner_line_provenance():
    fixture = Path(__file__).parents[1] / "examples/openblas_gemm_pqr/fixtures/param.h"
    symbols = scan_code([str(fixture)])
    assert symbols["GEMM_DEFAULT_P"] == {"value": 384, "source_ref": f"{fixture}:1"}
    dynamic = Path(__file__).parents[1] / "examples/openblas_gemm_pqr/fixtures/setparam-ref.c"
    assert scan_code([str(dynamic)])["GEMM_P"] == {"value": 384, "source_ref": f"{dynamic}:3"}


def test_parse_example_profile():
    brief = Path(__file__).parents[1] / "examples/openblas_gemm_pqr/brief.md"
    profile, _ = parse_brief(brief)
    assert [p.name for p in profile.parameters] == ["P", "Q", "R"]
    assert profile.hardware_context.l3_bytes_per_sharing_domain == 33554432
    assert profile.hardware_context.l3_aggregate_bytes == 134217728
    assert not constraints_pass(
        profile, {"P": 384, "Q": 512, "R": 5936}, {"L2_PER_CORE_BYTES": 1048576}
    )
