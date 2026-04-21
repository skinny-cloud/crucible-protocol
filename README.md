# The CRUCIBLE Protocol

**Code Review Under Conditions Inducing Bug Latency Exposure**

An 8-gate audit protocol for detecting and preventing measurement fraud in
AI-assisted software development. Distinguishes test-suite failures into three
escalation levels — **accidental** (L1) → **systematic** (L2) → **structural**
(L3) — and provides gate-level detection procedures for each.

This repository is the machine-readable open standard accompanying the paper.

---

## The 8 Gates

| Gate | Layer | Role |
|---|---|---|
| **G1** Coverage Configuration | Controls | Detect coverage gaming via excluded files / directories |
| **G2** Mock Proliferation | Controls | Detect excessive mocking (test-against-mocks rather than behavior) |
| **G3** Skip Rate | Controls | Detect tests silently skipped via env vars / markers |
| **G4** Hollow Assertion | Controls | Detect assertions satisfied by correct **and** incorrect behavior |
| **G5** Silent Failure | Controls | Detect exception swallowing (`except: pass`) patterns |
| **G6** Mutation Sampling | Substantive | Detect systematic metric manipulation via mutation survival |
| **G7** Spec-Test Traceability | Substantive | Detect tests with no corresponding specification claim |
| **G8** Measurement Integrity | Forensic | Detect Goodhart's Law activation across the prior seven gates |

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

## Quick Start

```bash
# Read the machine-readable spec
cat crucible-gates.yaml

# Render the figures from the paper
cd docs
node render_figures.mjs   # requires playwright >= 1.57
```

Gates 1–5 can typically be run as shell one-liners against a target
repository. Gates 6–8 require more setup — see `examples/` for sample
implementations and `docs/` for the full paper.

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
