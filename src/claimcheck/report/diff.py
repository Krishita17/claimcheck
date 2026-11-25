"""Scan diff: compare two ClaimCheck JSON reports to catch regressions.

Used as a CI regression gate: run a scan on the base branch and on the PR, then
``claimcheck diff base.json pr.json`` fails if the PR introduces a new claimable
or squatted exposure (a name newly at risk, or one whose verdict worsened).
"""

from __future__ import annotations

import json
from pathlib import Path

# Lower index = more dangerous. Used to decide whether a verdict "worsened".
_SEVERITY = {"CLAIMABLE": 0, "TAKEN-NOT-YOURS": 1, "PROTECTED": 2, "SAFE": 3, "-": 4}
_EXPOSED = {"CLAIMABLE", "TAKEN-NOT-YOURS"}


def _load(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _verdict_map(report: dict) -> dict[str, str]:
    out = {}
    for f in report.get("findings", []):
        name = f.get("name", {})
        key = f"{name.get('ecosystem')}:{name.get('normalized')}"
        out[key] = f.get("verdict") or "-"
    return out


def _typosquat_set(report: dict) -> set[str]:
    return {
        f"{t.get('ecosystem')}:{t.get('variant')}"
        for t in report.get("typosquats", [])
    }


def diff_reports(old: dict, new: dict) -> dict:
    old_v, new_v = _verdict_map(old), _verdict_map(new)
    old_ts, new_ts = _typosquat_set(old), _typosquat_set(new)

    new_exposures, worsened, resolved, new_names = [], [], [], []
    for key, nv in new_v.items():
        ov = old_v.get(key)
        if ov is None:
            new_names.append((key, nv))
            if nv in _EXPOSED:
                new_exposures.append((key, None, nv))
        elif _SEVERITY[nv] < _SEVERITY[ov]:
            worsened.append((key, ov, nv))
            if nv in _EXPOSED and ov not in _EXPOSED:
                new_exposures.append((key, ov, nv))
    for key, ov in old_v.items():
        nv = new_v.get(key)
        if ov in _EXPOSED and (nv is None or nv not in _EXPOSED):
            resolved.append((key, ov, nv or "removed"))

    new_typosquats = sorted(new_ts - old_ts)
    is_regression = bool(new_exposures or new_typosquats)
    return {
        "new_exposures": new_exposures,
        "worsened": worsened,
        "resolved": resolved,
        "new_names": new_names,
        "new_typosquats": new_typosquats,
        "is_regression": is_regression,
    }


def diff_scan_files(old_path: str | Path, new_path: str | Path) -> dict:
    return diff_reports(_load(old_path), _load(new_path))


def render_diff_text(d: dict) -> str:
    lines = ["=" * 70, "ClaimCheck scan diff", "=" * 70]
    if d["new_exposures"]:
        lines.append(f"\nNEW EXPOSURES ({len(d['new_exposures'])}):")
        for key, ov, nv in d["new_exposures"]:
            was = f" (was {ov})" if ov else " (new name)"
            lines.append(f"  + {key} -> {nv}{was}")
    if d["worsened"]:
        lines.append(f"\nWORSENED ({len(d['worsened'])}):")
        for key, ov, nv in d["worsened"]:
            lines.append(f"  ~ {key}: {ov} -> {nv}")
    if d["new_typosquats"]:
        lines.append(f"\nNEW TYPOSQUATS ({len(d['new_typosquats'])}):")
        for t in d["new_typosquats"]:
            lines.append(f"  + {t}")
    if d["resolved"]:
        lines.append(f"\nRESOLVED ({len(d['resolved'])}):")
        for key, ov, nv in d["resolved"]:
            lines.append(f"  - {key}: {ov} -> {nv}")
    if not any((d["new_exposures"], d["worsened"], d["new_typosquats"], d["resolved"])):
        lines.append("\nNo changes in exposure between the two scans.")
    lines.append("\n" + ("REGRESSION DETECTED" if d["is_regression"]
                         else "No new exposure introduced."))
    return "\n".join(lines)
