"""CRUCIBLE Protocol — functional reference implementation.

A runnable auditor for the 8 CRUCIBLE gates defined in crucible-gates.yaml.
Reads the gate spec, dispatches each gate to a real Python detector, and emits
a per-gate PASS / FAIL / SKIP report.

The three-state model is load-bearing: a gate that cannot run in the target
context reports SKIP(reason) — it NEVER reports PASS. A tool that painted an
un-runnable gate green would commit the very measurement fraud this protocol
exists to detect.
"""

__version__ = "0.1.0"
