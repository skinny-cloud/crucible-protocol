"""crucible CLI — `crucible audit <path>`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .engine import audit, find_gates_yaml, to_json
from .result import Status

_GLYPH = {Status.PASS: "PASS", Status.FAIL: "FAIL", Status.SKIP: "SKIP"}


def _render_human(report: dict) -> str:
    lines: list[str] = []
    s = report["summary"]
    lines.append("=" * 70)
    lines.append(f" CRUCIBLE Audit — {report['protocol']} v{report['protocol_version']}")
    lines.append(f" Target: {report['target']}")
    lines.append(f" Gate spec: {report['gates_spec']}")
    lines.append("=" * 70)
    for r in report["_results"]:
        lines.append(f"  [{_GLYPH[r.status]}] {r.gate_id:<6} {r.name:<34} {r.summary}")
        for f in r.findings:
            lines.append(f.human())
    lines.append("-" * 70)
    lines.append(
        f" VERDICT: {s['verdict']}  "
        f"(PASS {s['passed']}/{s['applicable']} applicable, "
        f"FAIL {s['failed']}, SKIP {s['skipped']})")
    lines.append(
        " NOTE: SKIP means the gate could not run in this target context "
        "(no git history / no live service / tool absent).")
    lines.append(" A SKIP is never counted as a PASS.")
    lines.append("=" * 70)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="crucible",
        description="CRUCIBLE Protocol auditor — runs the mechanized gates (G1–G8) against a target repo.")
    sub = parser.add_subparsers(dest="command", required=True)

    pa = sub.add_parser("audit", help="audit a target directory")
    pa.add_argument("path", help="path to the repo/test-suite to audit")
    pa.add_argument("--gates", help="path to crucible-gates.yaml (default: auto-locate)")
    pa.add_argument("--json", action="store_true", help="emit JSON instead of human-readable")
    pa.add_argument("--fail-on-skip", action="store_true",
                    help="exit non-zero if any gate SKIPs (strict CI mode)")

    args = parser.parse_args(argv)

    if args.command == "audit":
        target = Path(args.path).resolve()
        if not target.exists():
            print(f"error: target does not exist: {target}", file=sys.stderr)
            return 2
        gates_yaml = find_gates_yaml(target, Path(args.gates).resolve() if args.gates else None)
        report = audit(target, gates_yaml)

        if args.json:
            print(to_json(report))
        else:
            print(_render_human(report))

        if report["summary"]["failed"] > 0:
            return 1
        if args.fail_on_skip and report["summary"]["skipped"] > 0:
            return 1
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
