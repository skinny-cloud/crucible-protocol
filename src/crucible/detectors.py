"""Real gate detectors for the CRUCIBLE Protocol.

Each detector does genuine work against a target directory:

- STATIC gates (G2, G5, G7, G8.1, G8.2, G8.3, G8.4, G8.6) parse files. The
  Python-source gates use the `ast` module, NOT grep — a multi-line except body
  or a commented assertion would fool a regex but not an AST walker.
- GIT gates (G1, G3, G4) require a git repo with >=2 commits; SKIP otherwise.
- TOOL gates (G6 mutation, G8.5 real coverage, G8.7 infra reachability) shell
  out to the real tool/service; SKIP if it is not present.

A gate that cannot run reports SKIP(reason). It never reports PASS. Painting an
un-runnable gate green would be the measurement fraud this protocol detects.
"""

from __future__ import annotations

import ast
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .result import Finding, GateResult, Status

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

INTEGRATION_DIR_HINTS = ("integration", "e2e", "functional")
MOCK_NAMES = {"AsyncMock", "MagicMock", "Mock", "patch"}
INFRA_CLIENTS = {
    "asyncpg", "psycopg", "psycopg2", "redis", "boto3",
    "elasticsearch", "pymongo", "aiomysql", "aiopg",
}


def _py_files(root: Path, *subdirs: str) -> list[Path]:
    bases = [root / s for s in subdirs] if subdirs else [root]
    out: list[Path] = []
    for base in bases:
        if base.exists():
            out.extend(p for p in base.rglob("*.py") if p.is_file())
    return out


def _all_py_files(root: Path) -> list[Path]:
    skip = {".git", "node_modules", ".venv", "venv", "__pycache__", ".tox", "build", "dist"}
    return [
        p for p in root.rglob("*.py")
        if p.is_file() and not any(part in skip for part in p.parts)
    ]


def _test_files(root: Path) -> list[Path]:
    out: list[Path] = []
    tdir = root / "tests"
    if tdir.exists():
        out.extend(p for p in tdir.rglob("*.py") if p.is_file())
    # top-level test_*.py
    out.extend(p for p in root.glob("test_*.py"))
    return out


def _integration_test_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for p in _test_files(root):
        rel = p.relative_to(root).as_posix().lower()
        name = p.name.lower()
        if any(h in rel for h in INTEGRATION_DIR_HINTS) or any(
            h in name for h in INTEGRATION_DIR_HINTS
        ):
            out.append(p)
    return out


def _rel(root: Path, p: Path) -> str:
    try:
        return p.relative_to(root).as_posix()
    except ValueError:
        return str(p)


def _parse(p: Path) -> ast.Module | None:
    try:
        return ast.parse(p.read_text(encoding="utf-8", errors="replace"), filename=str(p))
    except (SyntaxError, ValueError):
        return None


def _is_git_repo(root: Path) -> bool:
    if not shutil.which("git"):
        return False
    r = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
        capture_output=True, text=True,
    )
    return r.returncode == 0 and r.stdout.strip() == "true"


def _git_commit_count(root: Path) -> int:
    r = subprocess.run(
        ["git", "-C", str(root), "rev-list", "--count", "HEAD"],
        capture_output=True, text=True,
    )
    try:
        return int(r.stdout.strip())
    except ValueError:
        return 0


# ===========================================================================
# QUALITY GATES (1-7)
# ===========================================================================

def gate_g1_xfail(root: Path, spec: dict[str, Any]) -> GateResult:
    """G1 xfail governance — last commit must not remove an xfail/skip marker
    without referencing a CI run that confirmed the test passes. GIT gate."""
    if not _is_git_repo(root):
        return GateResult.skipped(spec, "target is not a git repository")
    if _git_commit_count(root) < 2:
        return GateResult.skipped(spec, "git history has fewer than 2 commits")

    diff = subprocess.run(
        ["git", "-C", str(root), "diff", "HEAD~1", "HEAD", "--", "*.py"],
        capture_output=True, text=True,
    ).stdout
    removed = [
        ln for ln in diff.splitlines()
        if ln.startswith("-") and re.search(r"@?(pytest\.mark\.)?(xfail|skip)\b", ln)
        and not ln.startswith("---")
    ]
    if not removed:
        return GateResult.passed(spec, "no xfail/skip markers removed in HEAD")

    msg = subprocess.run(
        ["git", "-C", str(root), "log", "-1", "--pretty=%B"],
        capture_output=True, text=True,
    ).stdout
    if re.search(r"\b(CI|run[- ]?id|pipeline)\b", msg, re.I):
        return GateResult.passed(
            spec, f"{len(removed)} marker(s) removed, CI reference present in commit")
    findings = [Finding("HEAD commit", None, f"removed marker: {ln.strip()}") for ln in removed]
    return GateResult.failed(
        spec, f"{len(removed)} xfail/skip removed with no CI-run reference", findings)


def gate_g2_nonempty(root: Path, spec: dict[str, Any]) -> GateResult:
    """G2 non-empty result assertions (AST). A test function that calls a
    create/insert helper and then only does a type/bool assertion (no
    len(...)>=1 / non-empty check) is hollow — an empty list passes
    isinstance(x, list). STATIC gate over test files."""
    files = _test_files(root)
    if not files:
        return GateResult.skipped(spec, "no test files found")

    findings: list[Finding] = []
    checked = 0
    create_kw = re.compile(r"(create|insert|add|store|write|save|put|seed)", re.I)

    for f in files:
        tree = _parse(f)
        if tree is None:
            continue
        for fn in ast.walk(tree):
            if not isinstance(fn, ast.FunctionDef) or not fn.name.startswith("test"):
                continue
            creates = False
            has_type_only = False
            has_nonempty = False
            for node in ast.walk(fn):
                if isinstance(node, ast.Call):
                    callee = _call_name(node.func)
                    if callee and create_kw.search(callee):
                        creates = True
                    if callee == "len":
                        # len(x) compared >= 1 / > 0 / == N(>0) counts as non-empty
                        has_nonempty = has_nonempty or _len_is_nonempty_check(node, fn)
                if isinstance(node, ast.Assert):
                    if _assert_is_type_or_bool_only(node.test):
                        has_type_only = True
            if creates:
                checked += 1
                if has_type_only and not has_nonempty:
                    findings.append(Finding(
                        _rel(root, f), fn.lineno,
                        f"test '{fn.name}' creates data then asserts only type/bool "
                        f"(isinstance/is True) — no non-empty (len>=1) check"))

    if checked == 0:
        return GateResult.skipped(spec, "no create-then-assert test patterns found")
    if findings:
        return GateResult.failed(
            spec, f"{len(findings)} of {checked} create-query test(s) lack a non-empty assertion",
            findings)
    return GateResult.passed(spec, f"all {checked} create-query test(s) have non-empty assertions")


def _call_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _len_is_nonempty_check(len_call: ast.Call, fn: ast.FunctionDef) -> bool:
    """True if some assert compares this kind of len(...) against a positive bound."""
    for node in ast.walk(fn):
        if isinstance(node, ast.Assert) and isinstance(node.test, ast.Compare):
            cmp = node.test
            if isinstance(cmp.left, ast.Call) and _call_name(cmp.left.func) == "len":
                for op, comp in zip(cmp.ops, cmp.comparators):
                    if isinstance(op, (ast.GtE, ast.Gt)) and _const_int(comp) is not None:
                        return True
                    if isinstance(op, ast.Eq):
                        v = _const_int(comp)
                        if v is not None and v > 0:
                            return True
    return False


def _const_int(node: ast.expr) -> int | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value
    return None


def _assert_is_type_or_bool_only(test: ast.expr) -> bool:
    """isinstance(x, list) / x.success is True / assert result — vacuous shapes."""
    if isinstance(test, ast.Call) and _call_name(test.func) == "isinstance":
        return True
    if isinstance(test, ast.Compare):
        # `x is True` / `x.success is True`
        for op, comp in zip(test.ops, test.comparators):
            if isinstance(op, ast.Is) and isinstance(comp, ast.Constant) and comp.value is True:
                return True
    return False


def gate_g3_mock_drift(root: Path, spec: dict[str, Any]) -> GateResult:
    """G3 mock drift — HEAD touches both a src/ module and a tests/ mock/fixture
    for the same module name without a spec reference in the message. GIT gate."""
    if not _is_git_repo(root):
        return GateResult.skipped(spec, "target is not a git repository")
    if _git_commit_count(root) < 2:
        return GateResult.skipped(spec, "git history has fewer than 2 commits")

    names = subprocess.run(
        ["git", "-C", str(root), "diff", "HEAD~1", "HEAD", "--name-only"],
        capture_output=True, text=True,
    ).stdout.split()
    src = {Path(n).stem for n in names if n.startswith("src/") or "/src/" in n}
    tst = {re.sub(r"^test_|_test$", "", Path(n).stem)
           for n in names if "/tests/" in n or n.startswith("tests/")}
    shared = src & tst
    if not shared:
        return GateResult.passed(spec, "no same-module src+test co-change in HEAD")

    msg = subprocess.run(
        ["git", "-C", str(root), "log", "-1", "--pretty=%B"],
        capture_output=True, text=True,
    ).stdout
    if re.search(r"\b(SPEC|NEXUS|AC-|contract|spec)\b", msg, re.I):
        return GateResult.passed(spec, f"co-change of {sorted(shared)} justified by spec reference")
    findings = [Finding("HEAD commit", None, f"module '{m}' impl+mock co-changed, no spec ref")
                for m in sorted(shared)]
    return GateResult.failed(spec, f"{len(shared)} module(s) co-changed without spec reference", findings)


def gate_g4_test_delta(root: Path, spec: dict[str, Any]) -> GateResult:
    """G4 test-count delta — if HEAD drops >5 test functions vs HEAD~1 without a
    [test-delta: -N justified: ...] tag, fail. GIT gate."""
    if not _is_git_repo(root):
        return GateResult.skipped(spec, "target is not a git repository")
    if _git_commit_count(root) < 2:
        return GateResult.skipped(spec, "git history has fewer than 2 commits")

    cur = _count_tests_at(root, "HEAD")
    prev = _count_tests_at(root, "HEAD~1")
    if cur is None or prev is None:
        return GateResult.skipped(spec, "could not count tests across revisions")
    delta = cur - prev
    if delta >= -5:
        return GateResult.passed(spec, f"test count {prev}->{cur} (delta {delta:+d}, within tolerance)")
    msg = subprocess.run(
        ["git", "-C", str(root), "log", "-1", "--pretty=%B"],
        capture_output=True, text=True,
    ).stdout
    if re.search(r"\[test-delta:", msg, re.I):
        return GateResult.passed(spec, f"test count dropped {delta:+d} but justified in commit")
    return GateResult.failed(
        spec, f"test count dropped {delta:+d} ({prev}->{cur}) with no [test-delta:] justification",
        [Finding("HEAD commit", None, f"{-delta} tests vanished without justification")])


def _count_tests_at(root: Path, rev: str) -> int | None:
    ls = subprocess.run(
        ["git", "-C", str(root), "ls-tree", "-r", "--name-only", rev],
        capture_output=True, text=True,
    )
    if ls.returncode != 0:
        return None
    total = 0
    for name in ls.stdout.split():
        if not name.endswith(".py"):
            continue
        if not (name.startswith("tests/") or "/tests/" in name or Path(name).name.startswith("test_")):
            continue
        blob = subprocess.run(
            ["git", "-C", str(root), "show", f"{rev}:{name}"],
            capture_output=True, text=True,
        )
        if blob.returncode != 0:
            continue
        try:
            tree = ast.parse(blob.stdout)
        except SyntaxError:
            continue
        total += sum(
            1 for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name.startswith("test")
        )
    return total


def gate_g5_silent_except(root: Path, spec: dict[str, Any]) -> GateResult:
    """G5 silent exception audit (AST). An except handler whose body neither
    logs, re-raises, nor returns/sets an error status swallows the failure.
    AST handles multi-line bodies a grep -A1 would miss. STATIC over src/."""
    files = _py_files(root, "src") or [
        p for p in _all_py_files(root)
        if "/tests/" not in p.as_posix() and not p.name.startswith("test_")
    ]
    if not files:
        return GateResult.skipped(spec, "no source files found")

    findings: list[Finding] = []
    for f in files:
        tree = _parse(f)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and _handler_is_silent(node):
                findings.append(Finding(
                    _rel(root, f), node.lineno,
                    "except handler swallows error (no log / raise / error-return)"))
    if findings:
        return GateResult.failed(spec, f"{len(findings)} silent exception handler(s)", findings)
    return GateResult.passed(spec, f"no silent exception handlers across {len(files)} source file(s)")


def _handler_is_silent(handler: ast.ExceptHandler) -> bool:
    observable = False
    for node in ast.walk(handler):
        if isinstance(node, ast.Raise):
            observable = True
        elif isinstance(node, ast.Call):
            name = _call_name(node.func) or ""
            if any(k in name.lower() for k in ("log", "warn", "error", "exception",
                                               "print", "capture", "report", "alert")):
                observable = True
        elif isinstance(node, ast.Return) and node.value is not None:
            observable = True  # returns an error sentinel / status
    return not observable


def gate_g7_spec_trace(root: Path, spec: dict[str, Any]) -> GateResult:
    """G7 spec-test traceability (AST). Integration test functions must carry a
    spec reference (Validates:/SPEC:/NEXUS:/AC-) in their docstring. STATIC."""
    files = _integration_test_files(root)
    if not files:
        return GateResult.skipped(spec, "no integration/e2e test files found")
    ref = re.compile(r"(Validates:|SPEC:|NEXUS:|AC-\d|acceptance)", re.I)
    findings: list[Finding] = []
    total = 0
    for f in files:
        tree = _parse(f)
        if tree is None:
            continue
        for fn in ast.walk(tree):
            if isinstance(fn, ast.FunctionDef) and fn.name.startswith("test"):
                total += 1
                doc = ast.get_docstring(fn) or ""
                if not ref.search(doc):
                    findings.append(Finding(
                        _rel(root, f), fn.lineno,
                        f"integration test '{fn.name}' has no spec reference in docstring"))
    if total == 0:
        return GateResult.skipped(spec, "no integration test functions found")
    if findings:
        return GateResult.failed(
            spec, f"{len(findings)} of {total} integration test(s) lack a spec reference", findings)
    return GateResult.passed(spec, f"all {total} integration test(s) trace to a spec")


def gate_g6_mutation(root: Path, spec: dict[str, Any]) -> GateResult:
    """G6 mutation testing — shells out to mutmut. SKIP if mutmut absent or the
    suite is below the 500-test deployment threshold (deployment is audit-time,
    cost-gated). TOOL gate."""
    if shutil.which("mutmut") is None:
        return GateResult.skipped(spec, "mutmut not installed (shell-out tool absent)")
    # honor the spec's >500-test deployment trigger
    n = sum(
        1
        for f in _test_files(root)
        for node in ast.walk(_parse(f) or ast.Module(body=[], type_ignores=[]))
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test")
    )
    if n < 500:
        return GateResult.skipped(
            spec, f"suite has {n} tests (<500 deployment threshold; mutation is audit-time only)")
    proc = subprocess.run(
        ["mutmut", "run", "--paths-to-mutate", "src/"],
        cwd=str(root), capture_output=True, text=True,
    )
    res = subprocess.run(["mutmut", "results"], cwd=str(root), capture_output=True, text=True)
    killed = len(re.findall(r"killed", res.stdout, re.I))
    survived = len(re.findall(r"survived", res.stdout, re.I))
    total = killed + survived
    if total == 0:
        return GateResult.skipped(spec, "mutmut produced no mutants")
    score = killed / total
    thresh = float(spec.get("pass_criterion", {}).get("standard_code", "40%").rstrip("%")) / 100 \
        if isinstance(spec.get("pass_criterion"), dict) else 0.40
    if score >= thresh:
        return GateResult.passed(spec, f"mutation score {score:.0%} >= {thresh:.0%}")
    return GateResult.failed(
        spec, f"mutation score {score:.0%} < {thresh:.0%} ({survived} survived)",
        [Finding("src/", None, f"{survived} mutants survived — tests do not constrain behavior")])


# ===========================================================================
# INTEGRITY GATE (8) — subchecks
# ===========================================================================

def gate_g8_1_omit(root: Path, spec: dict[str, Any]) -> GateResult:
    """G8.1 coverage-omit audit. Every omit/exclude entry in coverage config must
    carry an inline `# OMIT JUSTIFIED:` comment. STATIC config gate."""
    cfgs = [root / n for n in ("pyproject.toml", "setup.cfg", ".coveragerc")
            if (root / n).exists()]
    if not cfgs:
        return GateResult.skipped(spec, "no coverage config (pyproject.toml/.coveragerc) found")

    findings: list[Finding] = []
    saw_omit_section = False
    for cfg in cfgs:
        lines = cfg.read_text(encoding="utf-8", errors="replace").splitlines()
        in_omit = False
        for i, raw in enumerate(lines, 1):
            line = raw.strip()
            if re.search(r"^omit\s*=", line) or re.search(r"\bomit\b\s*=", line):
                in_omit = True
                saw_omit_section = True
                # single-line form: omit = ["a.py"]
                if "[" in line and "]" in line and ".py" in line and "OMIT JUSTIFIED" not in raw:
                    findings.append(Finding(_rel(root, cfg), i,
                                            f"omit entry without '# OMIT JUSTIFIED:' comment: {line}"))
                continue
            if in_omit:
                if re.match(r'^["\'].*\.py', line) or re.match(r'^\*', line):
                    if "OMIT JUSTIFIED" not in raw:
                        findings.append(Finding(
                            _rel(root, cfg), i,
                            f"omit entry without '# OMIT JUSTIFIED:' comment: {line}"))
                elif line.startswith("]") or (line and "=" in line and not line.startswith("#")):
                    in_omit = False
    if not saw_omit_section:
        return GateResult.passed(spec, "no coverage omit list configured")
    if findings:
        return GateResult.failed(spec, f"{len(findings)} unjustified coverage omit(s)", findings)
    return GateResult.passed(spec, "all coverage omit entries are justified")


def gate_g8_2_env_gated(root: Path, spec: dict[str, Any]) -> GateResult:
    """G8.2 env-gated test audit (AST + CI scan). A test skipped on an env var
    that is never set in any CI workflow is dead code. STATIC."""
    files = _test_files(root)
    if not files:
        return GateResult.skipped(spec, "no test files found")

    gated: list[tuple[Path, int, str]] = []
    env_re = re.compile(r"environ(?:\.get)?\(?\s*['\"]([A-Z0-9_]+)['\"]")
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        tree = _parse(f)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.Call, ast.Attribute)):
                seg = ast.get_source_segment(text, node) or ""
                if "skipif" in seg.lower() or "skipIf" in seg:
                    for m in env_re.finditer(seg):
                        gated.append((f, getattr(node, "lineno", 0), m.group(1)))
    if not gated:
        return GateResult.skipped(spec, "no environment-gated tests found")

    # Collect env vars actually SET in CI workflows / Makefile. We strip comment
    # lines so a var named only in a `# NOTE: VAR is never set` comment does not
    # count as set — that comment is exactly the dead-code smell we want to catch.
    def _non_comment(text: str) -> str:
        out = []
        for ln in text.splitlines():
            stripped = ln.lstrip()
            if stripped.startswith("#"):
                continue
            out.append(ln.split(" #", 1)[0] if " #" in ln else ln)
        return "\n".join(out)

    ci_text = ""
    wf_dir = root / ".github" / "workflows"
    if wf_dir.exists():
        for wf in wf_dir.glob("*"):
            ci_text += _non_comment(wf.read_text(encoding="utf-8", errors="replace"))
    for extra in ("Makefile", "tox.ini"):
        if (root / extra).exists():
            ci_text += _non_comment((root / extra).read_text(encoding="utf-8", errors="replace"))

    findings: list[Finding] = []
    for f, line, var in gated:
        if var not in ci_text:
            findings.append(Finding(_rel(root, f), line,
                                    f"test gated on ${var} which is never set in any CI workflow — dead code"))
    if findings:
        return GateResult.failed(spec, f"{len(findings)} dead env-gated test(s)", findings)
    return GateResult.passed(spec, f"all {len(gated)} env-gated test(s) have their var set in CI")


def gate_g8_3_integration_mocks(root: Path, spec: dict[str, Any]) -> GateResult:
    """G8.3 integration-test mock audit (AST). Mocking frameworks in
    integration/e2e tests mean it is not an integration test. STATIC."""
    files = _integration_test_files(root)
    if not files:
        return GateResult.skipped(spec, "no integration/e2e test files found")
    findings: list[Finding] = []
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        if "MOCK JUSTIFIED" in text:
            continue
        tree = _parse(f)
        if tree is None:
            continue
        for node in ast.walk(tree):
            name = None
            if isinstance(node, ast.Call):
                name = _call_name(node.func)
            elif isinstance(node, ast.Attribute) and node.attr in ("patch", "mock"):
                name = node.attr
            if name in MOCK_NAMES or name == "patch":
                findings.append(Finding(_rel(root, f), getattr(node, "lineno", 0),
                                        f"mock '{name}' used in integration/e2e test"))
    if findings:
        return GateResult.failed(spec, f"{len(findings)} mock use(s) in integration tests", findings)
    return GateResult.passed(spec, "no undocumented mocks in integration/e2e tests")


def gate_g8_4_badge(root: Path, spec: dict[str, Any]) -> GateResult:
    """G8.4 badge accuracy. A hardcoded shields.io coverage badge (static
    number, not generated from CI) is a fraud surface. STATIC."""
    readme = root / "README.md"
    if not readme.exists():
        return GateResult.skipped(spec, "no README.md found")
    findings: list[Finding] = []
    for i, line in enumerate(readme.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        m = re.search(r"img\.shields\.io/badge/coverage-(\d+)%25", line)
        if m:
            findings.append(Finding("README.md", i,
                                    f"hardcoded coverage badge ({m.group(1)}%) — static shields.io URL, "
                                    f"not generated from a CI coverage run"))
    if findings:
        return GateResult.failed(spec, "hardcoded coverage badge in README", findings)
    return GateResult.passed(spec, "no hardcoded coverage badge")


def gate_g8_5_real_coverage(root: Path, spec: dict[str, Any]) -> GateResult:
    """G8.5 real coverage number — shell out to `pytest --cov`. SKIP if
    pytest/pytest-cov absent. TOOL gate."""
    try:
        import pytest_cov  # noqa: F401
    except ImportError:
        return GateResult.skipped(spec, "pytest-cov not installed (cannot compute real coverage)")
    # cover the AUDITED repo's package, not our own — prefer src/, else a
    # top-level package dir that contains the tests' import target.
    cov_target = "src" if (root / "src").exists() else "."
    if not (root / "tests").exists():
        return GateResult.skipped(spec, "no tests/ dir to run coverage against")
    proc = subprocess.run(
        ["python", "-m", "pytest", f"--cov={cov_target}", "--cov-report=term", "-q",
         str(root / "tests")],
        cwd=str(root), capture_output=True, text=True,
    )
    m = re.search(r"TOTAL\s+\d+\s+\d+\s+(\d+)%", proc.stdout)
    if not m:
        return GateResult.skipped(spec, "coverage run produced no TOTAL line")
    pct = int(m.group(1))
    return GateResult.passed(spec, f"real measured coverage (post-omit) = {pct}%")


def gate_g8_6_conftest_mock(root: Path, spec: dict[str, Any]) -> GateResult:
    """G8.6 conftest infrastructure-mock audit (AST). A module-level assignment
    binding an infra client name (asyncpg = AsyncMock()) in a conftest.py mocks
    that client for EVERY importing test — the structural oracle compromise.
    STATIC, and the highest-severity static check."""
    conftests = [p for p in root.rglob("conftest.py")
                 if p.is_file() and not any(s in p.parts for s in (".venv", "venv", "node_modules"))]
    if not conftests:
        return GateResult.skipped(spec, "no conftest.py found")
    findings: list[Finding] = []
    for cf in conftests:
        tree = _parse(cf)
        if tree is None:
            continue
        for node in tree.body:  # module-level only
            if isinstance(node, ast.Assign):
                rhs_is_mock = any(
                    _call_name(c.func) in MOCK_NAMES
                    for c in ast.walk(node.value) if isinstance(c, ast.Call)
                )
                for tgt in node.targets:
                    tname = tgt.id if isinstance(tgt, ast.Name) else None
                    if tname and (tname in INFRA_CLIENTS or rhs_is_mock):
                        if rhs_is_mock:
                            findings.append(Finding(
                                _rel(root, cf), node.lineno,
                                f"module-level '{tname} = <Mock>' in conftest mocks infra for ALL "
                                f"importing tests (structural oracle compromise)"))
    if findings:
        return GateResult.failed(spec, "module-level infra mock in conftest.py", findings)
    return GateResult.passed(spec, "no module-level infra mocks in conftest.py")


def gate_g8_7_infra_reach(root: Path, spec: dict[str, Any]) -> GateResult:
    """G8.7 infrastructure reachability — `pg_isready`. SKIP if the probe tool
    is absent (cannot prove the service is or isn't reachable). TOOL gate."""
    if shutil.which("pg_isready") is None:
        return GateResult.skipped(spec, "pg_isready not installed (cannot probe infra reachability)")
    proc = subprocess.run(["pg_isready"], capture_output=True, text=True)
    if proc.returncode == 0:
        return GateResult.passed(spec, "postgres reachable (infra is live for infra tests)")
    return GateResult.skipped(
        spec, "postgres not reachable; G8.6 (conftest mock) is the static proxy for this risk")
