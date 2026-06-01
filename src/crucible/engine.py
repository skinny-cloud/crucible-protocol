"""CRUCIBLE engine — loads crucible-gates.yaml (the gate registry) and dispatches
each gate ID to its registered Python detector.

The YAML is used as a *registry + metadata + thresholds* source, NOT as an eval
target: several `detection_command` fields in the spec are prose/pseudo-shell,
not literal commands. Loading the YAML satisfies "reads crucible-gates.yaml" and
drives which gates exist, their names, layers, priorities, and pass thresholds;
the actual detection is real Python in detectors.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import yaml

from . import detectors as D
from .result import GateResult, Status

# gate_id -> detector. Sub-gates of G8 dispatch by their own id ("8.1", ...).
DISPATCH: dict[str, Callable[[Path, dict[str, Any]], GateResult]] = {
    "G1": D.gate_g1_xfail,
    "G2": D.gate_g2_nonempty,
    "G3": D.gate_g3_mock_drift,
    "G4": D.gate_g4_test_delta,
    "G5": D.gate_g5_silent_except,
    "G6": D.gate_g6_mutation,
    "G7": D.gate_g7_spec_trace,
    "8.1": D.gate_g8_1_omit,
    "8.2": D.gate_g8_2_env_gated,
    "8.3": D.gate_g8_3_integration_mocks,
    "8.4": D.gate_g8_4_badge,
    "8.5": D.gate_g8_5_real_coverage,
    "8.6": D.gate_g8_6_conftest_mock,
    "8.7": D.gate_g8_7_infra_reach,
}

# Classification for the honest "what runs deep vs shallow" report, keyed by the
# gate_id as it appears in GateResult (G1..G7, G8.1..G8.7).
KIND = {
    "G1": "git", "G3": "git", "G4": "git",
    "G2": "static-ast", "G5": "static-ast", "G7": "static-ast",
    "G8.2": "static-ast", "G8.3": "static-ast", "G8.6": "static-ast",
    "G8.1": "static-config", "G8.4": "static-config",
    "G6": "shell-out", "G8.5": "shell-out", "G8.7": "shell-out",
}


def find_gates_yaml(target: Path, override: Path | None = None) -> Path:
    """Locate crucible-gates.yaml: explicit override, then the target, then the
    repo root that ships the canonical spec."""
    if override:
        return override
    # search order: the target dir, the cwd (demo runs from repo root), then the
    # source tree that ships the canonical spec (editable installs keep src/ in place).
    for cand in (target / "crucible-gates.yaml",
                 Path.cwd() / "crucible-gates.yaml",
                 Path(__file__).resolve().parents[2] / "crucible-gates.yaml"):
        if cand.exists():
            return cand
    raise FileNotFoundError(
        "crucible-gates.yaml not found (looked in target and repo root); "
        "pass --gates <path>")


def load_spec(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def audit(target: Path, gates_yaml: Path) -> dict[str, Any]:
    spec = load_spec(gates_yaml)
    results: list[GateResult] = []

    for gate in spec.get("gates", []):
        gid = gate["id"]
        if gid == "G8":
            # expand the integrity gate into its registered subchecks
            for sub in gate.get("subchecks", []):
                sid = sub["id"]
                detector = DISPATCH.get(sid)
                sub_spec = {
                    "id": sid if sid.startswith("G") else f"G{sid}",
                    "name": sub.get("name", sid),
                    "layer": gate.get("layer", "measurement_integrity"),
                    "priority": sub.get("priority", gate.get("priority", "?")),
                    "pass_criterion": sub.get("pass_criterion"),
                }
                results.append(detector(target, sub_spec) if detector
                               else GateResult.skipped(sub_spec, "no detector registered"))
        else:
            detector = DISPATCH.get(gid)
            results.append(detector(target, gate) if detector
                           else GateResult.skipped(gate, "no detector registered"))

    counts = {s.value: 0 for s in Status}
    for r in results:
        counts[r.status.value] += 1
    applicable = counts["PASS"] + counts["FAIL"]

    return {
        "protocol": spec.get("protocol", {}).get("name", "CRUCIBLE"),
        "protocol_version": spec.get("protocol", {}).get("version"),
        "target": str(target),
        "gates_spec": str(gates_yaml),
        "summary": {
            "total_gates": len(results),
            "applicable": applicable,
            "passed": counts["PASS"],
            "failed": counts["FAIL"],
            "skipped": counts["SKIP"],
            "verdict": "FAIL" if counts["FAIL"] else ("PASS" if counts["PASS"] else "INCONCLUSIVE"),
        },
        "results": [r.to_dict() | {"kind": KIND.get(r.gate_id, "?")} for r in results],
        "_results": results,
    }


def to_json(report: dict[str, Any]) -> str:
    out = {k: v for k, v in report.items() if k != "_results"}
    return json.dumps(out, indent=2)
