"""Gate result model — the three-state contract (PASS / FAIL / SKIP).

SKIP is not a soft PASS. It means the gate could not run in this target context
(no git history, no live DB, no coverage tool). The overall summary counts SKIPs
separately and never folds them into PASS.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class Status(str, enum.Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass
class Finding:
    """One concrete violation: where it is and why it trips the gate."""

    path: str
    line: int | None
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "line": self.line, "message": self.message}

    def human(self) -> str:
        loc = f"{self.path}:{self.line}" if self.line else self.path
        return f"      - {loc}: {self.message}"


@dataclass
class GateResult:
    gate_id: str
    name: str
    layer: str
    priority: str
    status: Status
    summary: str
    findings: list[Finding] = field(default_factory=list)
    skip_reason: str | None = None

    @classmethod
    def passed(cls, spec: dict[str, Any], summary: str) -> "GateResult":
        return cls(spec["id"], spec["name"], spec["layer"], spec.get("priority", "?"),
                   Status.PASS, summary)

    @classmethod
    def failed(cls, spec: dict[str, Any], summary: str,
               findings: list[Finding]) -> "GateResult":
        return cls(spec["id"], spec["name"], spec["layer"], spec.get("priority", "?"),
                   Status.FAIL, summary, findings)

    @classmethod
    def skipped(cls, spec: dict[str, Any], reason: str) -> "GateResult":
        return cls(spec["id"], spec["name"], spec["layer"], spec.get("priority", "?"),
                   Status.SKIP, f"SKIPPED: {reason}", skip_reason=reason)

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "name": self.name,
            "layer": self.layer,
            "priority": self.priority,
            "status": self.status.value,
            "summary": self.summary,
            "skip_reason": self.skip_reason,
            "findings": [f.to_dict() for f in self.findings],
        }
