"""Baseline / suppression support.

A baseline records the exposures an organization has already triaged and
accepted, so a CI scan fails only on *new* findings. A finding is identified by
``ecosystem:name:verdict`` — if the verdict later worsens (say SAFE -> CLAIMABLE),
the key changes and the finding resurfaces rather than staying suppressed.
"""

from __future__ import annotations

import json
from pathlib import Path

from .schema import NameFinding, ScanResult, Verdict


def finding_key(finding: NameFinding) -> str:
    verdict = finding.verdict.value if finding.verdict else "-"
    return f"{finding.name.ecosystem.value}:{finding.name.normalized}:{verdict}"


def load_baseline(path: str | Path) -> set[str]:
    """Load a baseline file into a set of finding keys."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return set(data.get("accepted", []))
    return set(data)  # a bare list of keys


def write_baseline(result: ScanResult, path: str | Path) -> int:
    """Write all current non-SAFE findings as the accepted baseline."""
    accepted = sorted(
        finding_key(f) for f in result.findings
        if f.verdict and f.verdict is not Verdict.SAFE
    )
    payload = {
        "version": 1,
        "target": result.target,
        "accepted": accepted,
    }
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return len(accepted)


def is_suppressed(finding: NameFinding, baseline: set[str]) -> bool:
    return finding_key(finding) in baseline


def apply_baseline(result: ScanResult, baseline: set[str]) -> list[NameFinding]:
    """Return the findings NOT suppressed by the baseline (new/changed ones)."""
    return [f for f in result.findings if not is_suppressed(f, baseline)]
