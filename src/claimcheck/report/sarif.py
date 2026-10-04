"""SARIF 2.1.0 export so ClaimCheck can run as a CI code-scanning gate.

Each non-SAFE finding becomes a SARIF ``result`` anchored to the file and line
where the name was discovered, so it surfaces inline in code-scanning UIs.
Verdicts map to SARIF levels: CLAIMABLE -> error, TAKEN-NOT-YOURS -> warning,
PROTECTED -> note. SAFE findings are omitted to keep the gate signal clean.
"""

from __future__ import annotations

import json

from .. import __version__
from ..schema import NameFinding, ScanResult, Verdict

_LEVEL = {
    Verdict.CLAIMABLE: "error",
    Verdict.TAKEN_NOT_YOURS: "warning",
    Verdict.PROTECTED: "note",
    Verdict.SAFE: "none",
}

_RULES = {
    Verdict.CLAIMABLE: {
        "id": "claimcheck/claimable-internal-name",
        "name": "ClaimableInternalName",
        "shortDescription": {"text": "Internal package name is claimable on the public registry"},
        "fullDescription": {
            "text": "An internal dependency name is unregistered on the public "
                    "registry and the install configuration permits public fallback. "
                    "An attacker could publish this name publicly and have it pulled "
                    "into builds (dependency confusion)."
        },
        "helpUri": "https://github.com/Krishita17/claimcheck#remediation",
        "defaultConfiguration": {"level": "error"},
    },
    Verdict.TAKEN_NOT_YOURS: {
        "id": "claimcheck/taken-not-yours",
        "name": "TakenNotYours",
        "shortDescription": {"text": "Internal name already public and not owned by you"},
        "fullDescription": {
            "text": "An internal dependency name already exists on the public "
                    "registry and is not owned by your organization — a possible "
                    "existing squat. Investigate the owner and publish date."
        },
        "helpUri": "https://github.com/Krishita17/claimcheck#remediation",
        "defaultConfiguration": {"level": "warning"},
    },
    Verdict.PROTECTED: {
        "id": "claimcheck/protected-internal-name",
        "name": "ProtectedInternalName",
        "shortDescription": {"text": "Internal name is unclaimed but protected by config"},
        "fullDescription": {
            "text": "An internal dependency name is unregistered publicly but the "
                    "scope is reserved / index pinned, preventing public fallback. "
                    "Re-scan in CI because a config change re-opens the exposure."
        },
        "helpUri": "https://github.com/Krishita17/claimcheck#remediation",
        "defaultConfiguration": {"level": "note"},
    },
}


def _result_for(f: NameFinding) -> dict:
    src = f.name.sources[0] if f.name.sources else None
    location = {}
    if src:
        location = {
            "physicalLocation": {
                "artifactLocation": {"uri": src.path},
                "region": {"startLine": max(src.line, 1)},
            }
        }
    message = (
        f"{f.verdict.value}: internal {f.name.ecosystem.value} name "
        f"'{f.name.normalized}'. {f.action}"
    )
    return {
        "ruleId": _RULES[f.verdict]["id"],
        "level": _LEVEL[f.verdict],
        "message": {"text": message},
        "locations": [location] if location else [],
        "properties": {
            "priority": f.priority,
            "classification": f.classification.value,
            "evidence": f.evidence,
        },
    }


def render_sarif(result: ScanResult) -> str:
    reported = [
        f for f in result.sorted_findings()
        if f.verdict and f.verdict is not Verdict.SAFE
    ]
    used_rules = []
    seen = set()
    for f in reported:
        rid = _RULES[f.verdict]["id"]
        if rid not in seen:
            used_rules.append(_RULES[f.verdict])
            seen.add(rid)

    sarif = {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "ClaimCheck",
                        "informationUri": "https://github.com/Krishita17/claimcheck",
                        "version": __version__,
                        "rules": used_rules,
                    }
                },
                "results": [_result_for(f) for f in reported],
            }
        ],
    }
    return json.dumps(sarif, indent=2)
