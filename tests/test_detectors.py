"""Tests for the CRUCIBLE detectors.

Integrity proof: each static gate must FAIL on examples/known-bad and PASS (or
SKIP, never FAIL) on examples/known-good. If a detector painted known-bad green,
the artifact would commit the very fraud the protocol detects — so these tests
ARE the no-theater guarantee.
"""

from pathlib import Path

import pytest

from crucible.engine import DISPATCH, audit, find_gates_yaml
from crucible.result import Status

REPO = Path(__file__).resolve().parents[1]
BAD = REPO / "examples" / "known-bad"
GOOD = REPO / "examples" / "known-good"
GATES = REPO / "crucible-gates.yaml"


# --- per-detector, against the fixtures -----------------------------------

STATIC_GATES = ["G2", "G5", "G7"]
STATIC_SUB = ["G8.1", "G8.2", "G8.3", "G8.4", "G8.6"]


@pytest.fixture
def spec():
    import yaml
    return yaml.safe_load(GATES.read_text())


def _sub_spec(gid, spec):
    g8 = next(g for g in spec["gates"] if g["id"] == "G8")
    sub = next(s for s in g8["subchecks"] if f"G{s['id']}" == gid or s["id"] == gid.lstrip("G"))
    return {"id": gid, "name": sub["name"], "layer": "measurement_integrity",
            "priority": sub.get("priority", "?"), "pass_criterion": sub.get("pass_criterion")}


def _gate_spec(gid, spec):
    return next(g for g in spec["gates"] if g["id"] == gid)


@pytest.mark.parametrize("gid", STATIC_GATES)
def test_static_gate_fails_on_known_bad(gid, spec):
    r = DISPATCH[gid](BAD, _gate_spec(gid, spec))
    assert r.status is Status.FAIL, f"{gid} should FAIL on known-bad, got {r.status}: {r.summary}"
    assert r.findings, f"{gid} FAIL must carry findings"


@pytest.mark.parametrize("gid", STATIC_GATES)
def test_static_gate_not_fail_on_known_good(gid, spec):
    r = DISPATCH[gid](GOOD, _gate_spec(gid, spec))
    assert r.status is not Status.FAIL, f"{gid} must not FAIL on known-good, got {r.summary}"


@pytest.mark.parametrize("gid", STATIC_SUB)
def test_static_subgate_fails_on_known_bad(gid, spec):
    r = DISPATCH[gid.replace("G8.", "8.")](BAD, _sub_spec(gid, spec))
    assert r.status is Status.FAIL, f"{gid} should FAIL on known-bad, got {r.status}: {r.summary}"
    assert r.findings


@pytest.mark.parametrize("gid", STATIC_SUB)
def test_static_subgate_not_fail_on_known_good(gid, spec):
    r = DISPATCH[gid.replace("G8.", "8.")](GOOD, _sub_spec(gid, spec))
    assert r.status is not Status.FAIL, f"{gid} must not FAIL on known-good, got {r.summary}"


# --- specific behavioral assertions (not just status) ---------------------

def test_g5_finds_the_silent_handler(spec):
    r = DISPATCH["G5"](BAD, _gate_spec("G5", spec))
    assert any("engine.py" in f.path for f in r.findings)


def test_g8_6_finds_module_level_asyncpg(spec):
    r = DISPATCH["8.6"](BAD, _sub_spec("G8.6", spec))
    assert any("conftest" in f.path and "asyncpg" in f.message.lower() for f in r.findings)


def test_g2_empty_list_assertion_is_caught(spec):
    r = DISPATCH["G2"](BAD, _gate_spec("G2", spec))
    assert any("non-empty" in f.message for f in r.findings)


def test_g2_ast_not_fooled_by_commented_len_check(tmp_path, spec):
    """A commented-out len() check must NOT satisfy G2 (AST sees no real assert)."""
    t = tmp_path / "tests"
    t.mkdir()
    (t / "test_x.py").write_text(
        "def test_create_and_read():\n"
        "    rows = create_rows()\n"
        "    # assert len(rows) >= 1   <- commented out, must not count\n"
        "    assert isinstance(rows, list)\n"
    )
    r = DISPATCH["G2"](tmp_path, _gate_spec("G2", spec))
    assert r.status is Status.FAIL


def test_g5_ast_not_fooled_by_multiline_body(tmp_path, spec):
    """grep -A1 would miss a pass after a multi-line body; AST catches it."""
    s = tmp_path / "src"
    s.mkdir()
    (s / "m.py").write_text(
        "def f():\n"
        "    try:\n"
        "        risky()\n"
        "    except Exception:\n"
        "        x = 1\n"
        "        y = 2\n"
        "        pass\n"   # silent, three lines down from except
    )
    r = DISPATCH["G5"](tmp_path, _gate_spec("G5", spec))
    assert r.status is Status.FAIL


# --- three-state contract: tool/git gates SKIP, never PASS, on a plain dir -

def test_git_gates_skip_on_non_repo(spec, tmp_path):
    for gid in ("G1", "G3", "G4"):
        r = DISPATCH[gid](tmp_path, _gate_spec(gid, spec))
        assert r.status is Status.SKIP, f"{gid} must SKIP on a non-git dir, got {r.status}"


def test_tool_gate_g6_skips_without_threshold_or_tool(spec):
    r = DISPATCH["G6"](GOOD, _gate_spec("G6", spec))
    assert r.status is Status.SKIP  # mutmut absent or <500 tests


# --- end-to-end engine report --------------------------------------------

def test_audit_known_bad_verdict_is_fail():
    report = audit(BAD, GATES)
    assert report["summary"]["verdict"] == "FAIL"
    assert report["summary"]["failed"] >= 5  # the 8 static gates, minus any that legitimately skip

def test_audit_known_good_verdict_is_not_fail():
    report = audit(GOOD, GATES)
    assert report["summary"]["verdict"] != "FAIL", report["summary"]
    assert report["summary"]["failed"] == 0

def test_skip_is_never_counted_as_pass():
    report = audit(GOOD, GATES)
    s = report["summary"]
    assert s["passed"] + s["failed"] + s["skipped"] == s["total_gates"]
    assert s["passed"] == s["applicable"] - s["failed"]
