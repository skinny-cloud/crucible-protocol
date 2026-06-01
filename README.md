# The CRUCIBLE Protocol

**Code Review Under Conditions Inducing Bug Latency Exposure**

An 8-gate audit protocol for detecting and preventing measurement fraud in
AI-assisted software development. Distinguishes test-suite failures into three
escalation levels — **accidental** (L1) → **systematic** (L2) → **structural**
(L3) — and provides gate-level detection procedures for each.

This repository is the machine-readable open standard accompanying the paper.

---

## The 8 Gates

Gate names and IDs below match [`crucible-gates.yaml`](./crucible-gates.yaml)
verbatim — the same IDs the `crucible` CLI prints.

| Gate | Layer | Role |
|---|---|---|
| **G1** xfail Governance | Quality | Detect xfail/skip markers removed without a confirming CI run |
| **G2** Non-Empty Result Assertions | Quality | Detect hollow asserts (`isinstance(x, list)` — an empty list passes vacuously) |
| **G3** Mock Drift Detection | Quality | Detect mocks updated in the same commit as impl, with no spec justification |
| **G4** Test-Count Delta | Quality | Detect undocumented test-count decreases (hidden test deletion) |
| **G5** Silent Exception Audit | Quality | Detect exception swallowing (`except: pass`) that hides failures from tests |
| **G6** Mutation Testing | Quality | Detect tests that survive all mutations (coverage without constraint) |
| **G7** Spec-Test Traceability | Quality | Detect integration tests with no corresponding specification reference |
| **G8** Coverage Integrity Audit | Measurement Integrity | Audit the measurement system itself (omits, env-gates, conftest mocks, badge, infra) — subchecks G8.1–G8.7 |

Full specifications, detection commands, and pass/fail criteria in
[`crucible-gates.yaml`](./crucible-gates.yaml).

---

## Why This Exists

AI coding agents optimize for measurable targets. When a team sets
"90% coverage" as a goal and an agent writes tests to reach it, Goodhart's
Law activates: the metric stops representing quality and starts
*replacing* it. Traditional CI gates (tests pass, coverage meets threshold)
cannot detect this — they measure the very thing being gamed.

CRUCIBLE audits the measurement system itself.

---

## Quick Start — the `crucible` auditor (runnable)

This repo ships a **functional reference auditor**: a `crucible` CLI that reads
[`crucible-gates.yaml`](./crucible-gates.yaml) and executes each gate's real
detection logic against a target repo, emitting a per-gate **PASS / FAIL / SKIP**
report.

```bash
git clone https://github.com/nxtg-ai/crucible-protocol
cd crucible-protocol
pip install -e .                       # installs the `crucible` command (Python ≥3.9)

crucible audit examples/known-bad      # -> VERDICT: FAIL (8 real violations caught)
crucible audit examples/known-good     # -> VERDICT: PASS (clean target)
crucible audit examples/known-bad --json   # machine-readable report
```

Or run the whole thing in one command (isolated venv, install, audit both
fixtures, run the test suite):

```bash
./demo.sh        # or: make demo
```

### The three-state contract (load-bearing)

A gate that cannot run in the target context reports **SKIP(reason)** — it
**never** reports PASS. A tool that painted an un-runnable gate green would
commit the very measurement fraud this protocol exists to detect. The summary
counts SKIPs separately: `PASS 8/8 applicable, FAIL 0, SKIP 6`.

### What each gate actually does

| Gate(s) | Kind | What runs |
|---|---|---|
| G2, G5, G7, G8.2, G8.3, G8.6 | **static (AST)** | Python `ast` walk — multi-line bodies and commented-out checks do **not** fool it |
| G8.1, G8.4 | **static (config)** | parse coverage config / README badge URL |
| G1, G3, G4 | **git** | `git diff HEAD~1..HEAD` forensics — **SKIP** if target is not a git repo with history |
| G6, G8.5, G8.7 | **shell-out** | `mutmut` / `pytest --cov` / `pg_isready` — **SKIP** if tool/service absent |

The CLI follows the gate IDs in `crucible-gates.yaml` (G1=`xfail_governance`,
G2=`non_empty_result_assertions`, …, G8.1–G8.7 = measurement-integrity
subchecks). See the YAML for each gate's full spec.

### Sample targets

- [`examples/known-bad/`](./examples/known-bad) — a payments service with one
  embedded defect per static gate (silent `except`, hollow `isinstance` assert,
  unjustified coverage omit, `MagicMock` in an integration test, module-level
  `asyncpg = AsyncMock()` in conftest, dead env-gated test, hardcoded coverage
  badge, untraced integration tests).
- [`examples/known-good/`](./examples/known-good) — the same surface, every
  defect fixed; passes all static gates.

### Render the paper figures

```bash
cd docs && node render_figures.mjs   # requires playwright >= 1.57
```

---

## Three Case Studies (Summarized)

| Case | System | Finding | Level |
|---|---|---|---|
| CS#1 | dx3, 2026-03-06 | Six gates fired on silent `except: pass` over NOT NULL violation. 3,277 tests remained green. | L1 Accidental |
| CS#2 | Podcast-Pipeline, 2026-03-07 | `pyproject.toml` omit list hid 1,145 LOC. Reported 77% coverage → honest 15%. | L2 Systematic |
| CS#3 | dx3, 2026-03-17 | Single `asyncpg = AsyncMock()` at module scope invalidated 4,726 tests claiming 100% coverage against a database not started for three months. | L3 Structural |

See [`figures/`](./figures/) for rendered diagrams.

---

## Figures

Rendered paper-ready artifacts in [`figures/`](./figures/):

| File | What |
|---|---|
| `figure1.pdf/.png` | The Quality Stack — three independent oracle layers |
| `figure2.pdf/.png` | Escalation Taxonomy — L1 → L2 → L3 with case studies |
| `figure3.pdf/.png` | CS#1 Directive-to-remediation interval (16 minutes) |
| `figure4.pdf/.png` | CS#2 Reported vs honest coverage (77% → 15%) |

Source HTML (from Claude Design) in `docs/claude-design-source.html`.
Regeneration script in `docs/render_figures.mjs`.

---

## Citation

```bibtex
@unpublished{crucible2026,
  title   = {The CRUCIBLE Protocol: Detecting and Preventing Measurement Fraud
             in AI-Assisted Software Development},
  author  = {Waliuddin, Asif and {Others}},
  year    = {2026},
  note    = {Manuscript in preparation; target venue ICSE 2027 SEIP}
}
```

---

## License

MIT — see [`LICENSE`](./LICENSE). The protocol specification, gate
definitions, detection commands, figures, and render scripts are released
without restriction for adoption by any team or organization.

---

## Contributing

This is an open standard. Issues and pull requests welcome — especially:

- Additional case studies demonstrating Gate N firings on external systems
- Detection command refinements for specific language/framework ecosystems
- Translations of the gate specifications to other build systems
- Validation studies on systems the authors do not own

## Conflicts & Positional Statements

The authors develop [Faultline Pro](https://github.com/nxtg-ai/faultline-pro),
an open-core AI Trust & Safety CLI. The case studies in this protocol are
drawn from systems the authors design and operate. See §11 of the paper for
full disclosure. CRUCIBLE is released independently of any paid product.

---

## Acknowledgments

Figure typography and initial conceptual framing produced with Claude Design
(Anthropic Labs). Verified against primary evidence; integrity corrections
applied pre-publication (see `docs/render_figures.mjs` comment blocks). The
authors thank the research-preview reviewers who caught a fabricated data
panel in an earlier figure draft.
