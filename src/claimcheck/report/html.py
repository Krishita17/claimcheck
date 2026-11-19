"""Self-contained HTML exposure report.

Produces a single standalone HTML document (inline CSS, no external assets, no
JavaScript required) so it can be opened directly, attached to a ticket, or
published. Verdicts are colour-coded and ordered by priority; every finding
keeps its cited evidence in a collapsible block.
"""

from __future__ import annotations

import html as _html
from collections import Counter

from ..schema import NameFinding, ScanResult, Verdict

_PRIORITY_LABEL = {1: "CRITICAL", 2: "HIGH", 3: "MEDIUM", 4: "INFO"}

_VERDICT_STYLE = {
    "CLAIMABLE": "#d1495b",
    "TAKEN-NOT-YOURS": "#edae49",
    "PROTECTED": "#00798c",
    "SAFE": "#66a182",
}

_CSS = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
       margin: 0; padding: 2rem; line-height: 1.5; color: #1a1a1a; background: #fafafa; }
@media (prefers-color-scheme: dark) { body { color: #e8e8e8; background: #16181d; } }
h1 { font-size: 1.6rem; margin: 0 0 .25rem; }
.sub { color: #777; font-size: .9rem; margin-bottom: 1.5rem; }
.cards { display: flex; flex-wrap: wrap; gap: .75rem; margin-bottom: 1.75rem; }
.card { flex: 1 1 140px; border-radius: 10px; padding: .9rem 1rem; color: #fff; }
.card .n { font-size: 1.9rem; font-weight: 700; display: block; }
.card .l { font-size: .78rem; text-transform: uppercase; letter-spacing: .04em; opacity: .95; }
table { border-collapse: collapse; width: 100%; margin-bottom: 2rem; font-size: .88rem;
        background: #fff; border-radius: 8px; overflow: hidden; }
@media (prefers-color-scheme: dark) { table { background: #1f232b; } }
th, td { text-align: left; padding: .55rem .7rem; border-bottom: 1px solid #e3e3e3; vertical-align: top; }
@media (prefers-color-scheme: dark) { th, td { border-bottom: 1px solid #2c313b; } }
th { background: #f0f0f0; font-size: .74rem; text-transform: uppercase; letter-spacing: .03em; color: #555; }
@media (prefers-color-scheme: dark) { th { background: #262b34; color: #aaa; } }
code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .85em; }
.badge { display: inline-block; padding: .12rem .5rem; border-radius: 999px; color: #fff;
         font-size: .72rem; font-weight: 700; white-space: nowrap; }
.prio { font-weight: 700; font-size: .72rem; }
details { margin: 0; } summary { cursor: pointer; color: #00798c; font-size: .8rem; }
.ev { margin: .4rem 0 0; padding-left: 1rem; font-size: .8rem; color: #666; }
@media (prefers-color-scheme: dark) { .ev { color: #9aa; } }
footer { color: #999; font-size: .78rem; margin-top: 1rem; border-top: 1px solid #ddd; padding-top: 1rem; }
"""


def _esc(s) -> str:
    return _html.escape(str(s if s is not None else ""))


def _badge(verdict: str) -> str:
    color = _VERDICT_STYLE.get(verdict, "#777")
    return f'<span class="badge" style="background:{color}">{_esc(verdict)}</span>'


def _row(f: NameFinding) -> str:
    src = ", ".join(f"{_esc(s.source_type.value)}:{s.line}" for s in f.name.sources[:4])
    reg = "unknown"
    if f.registry:
        reg = ("unclaimed" if not f.registry.exists
               else f"taken ({_esc(f.registry.owner or 'unknown')})")
    evidence = "".join(f"<div class='ev'>• {_esc(e)}</div>" for e in f.evidence)
    verdict = f.verdict.value if f.verdict else "-"
    return (
        "<tr>"
        f"<td class='prio'>{_PRIORITY_LABEL.get(f.priority, '?')}</td>"
        f"<td>{_esc(f.name.ecosystem.value)}</td>"
        f"<td><code>{_esc(f.name.normalized)}</code></td>"
        f"<td>{src or '-'}</td>"
        f"<td>{reg}</td>"
        f"<td>{_badge(verdict)}</td>"
        f"<td>{_esc(f.action)}"
        f"<details><summary>evidence</summary>{evidence}</details></td>"
        "</tr>"
    )


def _typosquat_rows(result: ScanResult) -> str:
    if not result.typosquats:
        return ""
    rows = []
    for t in result.typosquats:
        owner = t.registry.owner if t.registry else "unknown"
        recent = " <b>(recent)</b>" if (t.registry and t.registry.recently_published) else ""
        rows.append(
            "<tr>"
            f"<td>{_esc(t.ecosystem)}</td>"
            f"<td><code>{_esc(t.variant)}</code></td>"
            f"<td><code>{_esc(t.internal_name)}</code></td>"
            f"<td>{t.distance}</td>"
            f"<td>{_esc(t.kind)}</td>"
            f"<td>{_esc(owner)}{recent}</td>"
            "</tr>"
        )
    return (
        "<h2>Potential typosquats</h2>"
        "<p>Public packages that are confusable near-misses of your internal names.</p>"
        "<table><thead><tr><th>Ecosystem</th><th>Public variant</th>"
        "<th>Confusable with</th><th>Distance</th><th>Kind</th><th>Owner</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def render_html(result: ScanResult) -> str:
    counts = Counter(f.verdict.value for f in result.findings if f.verdict)
    cards = "".join(
        f'<div class="card" style="background:{_VERDICT_STYLE[v]}">'
        f'<span class="n">{counts.get(v, 0)}</span>'
        f'<span class="l">{v}</span></div>'
        for v in ("CLAIMABLE", "TAKEN-NOT-YOURS", "PROTECTED", "SAFE")
    )
    rows = "".join(_row(f) for f in result.sorted_findings())
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ClaimCheck Exposure Report</title>
<style>{_CSS}</style></head>
<body>
<h1>ClaimCheck Exposure Report</h1>
<div class="sub">Target: <code>{_esc(result.target)}</code> &middot; mode: {_esc(result.mode)}
&middot; {len(result.findings)} names analyzed</div>
<div class="cards">{cards}</div>
<table><thead><tr>
<th>Priority</th><th>Eco</th><th>Name</th><th>Found in</th>
<th>Public status</th><th>Verdict</th><th>Action &amp; evidence</th>
</tr></thead><tbody>{rows}</tbody></table>
{_typosquat_rows(result)}
<footer>Generated by ClaimCheck — a read-only dependency-confusion exposure checker.
Verdicts reflect registry &amp; config state at scan time; re-scan in CI.</footer>
</body></html>"""
