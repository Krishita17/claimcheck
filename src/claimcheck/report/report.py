"""Exposure report renderers: console text, Markdown, and JSON.

The signature artifact is the name -> source -> registry status -> verdict table,
ordered by priority so the most urgent exposures sit at the top.
"""

from __future__ import annotations

import json
from collections import Counter

from ..schema import NameFinding, ScanResult, Verdict

_PRIORITY_LABEL = {1: "CRITICAL", 2: "HIGH", 3: "MEDIUM", 4: "INFO"}


def verdict_counts(result: ScanResult) -> dict[str, int]:
    c = Counter(f.verdict.value for f in result.findings if f.verdict)
    # Ensure all verdicts are present (zeros included) for stable charts/tables.
    for v in Verdict:
        c.setdefault(v.value, 0)
    return dict(c)


def _first_source(f: NameFinding) -> str:
    if f.name.sources:
        s = f.name.sources[0]
        return f"{s.source_type.value}"
    return "-"


def _registry_cell(f: NameFinding) -> str:
    if not f.registry:
        return "unknown"
    if not f.registry.exists:
        return "unclaimed"
    owner = f.registry.owner or "unknown"
    return f"taken ({owner})"


# --------------------------------------------------------------------------- #
# Console text
# --------------------------------------------------------------------------- #
def render_text(result: ScanResult) -> str:
    findings = result.sorted_findings()
    counts = verdict_counts(result)
    lines: list[str] = []
    lines.append("=" * 78)
    lines.append(f"ClaimCheck exposure report  —  target: {result.target}  (mode: {result.mode})")
    lines.append("=" * 78)
    lines.append(
        "Summary:  "
        + "  ".join(f"{v}={counts.get(v, 0)}" for v in
                    (Verdict.CLAIMABLE.value, Verdict.TAKEN_NOT_YOURS.value,
                     Verdict.PROTECTED.value, Verdict.SAFE.value))
    )
    lines.append("")

    header = f"{'PRIO':<9}{'ECO':<6}{'NAME':<34}{'SOURCE':<18}{'REGISTRY':<22}VERDICT"
    lines.append(header)
    lines.append("-" * len(header))
    for f in findings:
        if f.verdict in (Verdict.SAFE,) and f.priority >= 4:
            # keep SAFE rows but compactly; still listed for completeness
            pass
        lines.append(
            f"{_PRIORITY_LABEL.get(f.priority, '?'):<9}"
            f"{f.name.ecosystem.value:<6}"
            f"{f.name.normalized[:33]:<34}"
            f"{_first_source(f):<18}"
            f"{_registry_cell(f):<22}"
            f"{f.verdict.value if f.verdict else '-'}"
        )
    lines.append("")

    # Detailed actions for everything that is not SAFE.
    actionable = [f for f in findings if f.verdict and f.verdict is not Verdict.SAFE]
    if actionable:
        lines.append("Recommended actions (most urgent first):")
        lines.append("-" * 78)
        for f in actionable:
            lines.append(f"[{_PRIORITY_LABEL.get(f.priority)}] {f.name.normalized} "
                         f"({f.name.ecosystem.value}) -> {f.verdict.value}")
            lines.append(f"    action: {f.action}")
            for ev in f.evidence:
                lines.append(f"      - {ev}")
            lines.append("")
    else:
        lines.append("No actionable exposures found. All names are SAFE.")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Markdown
# --------------------------------------------------------------------------- #
def render_markdown(result: ScanResult) -> str:
    findings = result.sorted_findings()
    counts = verdict_counts(result)
    out: list[str] = []
    out.append(f"# ClaimCheck Exposure Report")
    out.append("")
    out.append(f"- **Target:** `{result.target}`")
    out.append(f"- **Mode:** {result.mode}")
    out.append(f"- **Names analyzed:** {len(findings)}")
    out.append("")
    out.append("## Summary")
    out.append("")
    out.append("| Verdict | Count |")
    out.append("|---|---|")
    for v in (Verdict.CLAIMABLE, Verdict.TAKEN_NOT_YOURS, Verdict.PROTECTED, Verdict.SAFE):
        out.append(f"| {v.value} | {counts.get(v.value, 0)} |")
    out.append("")
    out.append("## Findings")
    out.append("")
    out.append("| Priority | Ecosystem | Name | Found in | Public status | Verdict | Action |")
    out.append("|---|---|---|---|---|---|---|")
    for f in findings:
        out.append(
            f"| {_PRIORITY_LABEL.get(f.priority, '?')} "
            f"| {f.name.ecosystem.value} "
            f"| `{f.name.normalized}` "
            f"| {_first_source(f)} "
            f"| {_registry_cell(f)} "
            f"| **{f.verdict.value if f.verdict else '-'}** "
            f"| {f.action} |"
        )
    out.append("")
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# JSON
# --------------------------------------------------------------------------- #
def render_json(result: ScanResult, indent: int = 2) -> str:
    payload = result.to_dict()
    payload["summary"] = verdict_counts(result)
    return json.dumps(payload, indent=indent)
