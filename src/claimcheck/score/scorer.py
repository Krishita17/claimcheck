"""Exposure scorer + verdict engine — the heart of ClaimCheck.

This fuses classification, the read-only registry probe, and the fallback
analysis into a single deterministic, explainable verdict per name:

* **CLAIMABLE**       — internal name, unregistered publicly, and the install
  config permits public fallback → an attacker could register it and your build
  would pull it. (If config prevents fallback, it is PROTECTED instead.)
* **TAKEN-NOT-YOURS** — internal name that already exists publicly and is not
  yours → a possible existing squat; investigate. A recent publish date and an
  exploitable config raise the priority.
* **PROTECTED**       — internal name that is unclaimed but whose scope is
  reserved / index pinned, so public fallback cannot occur.
* **SAFE**            — legitimately public and yours, or a well-known package.

Every verdict carries cited evidence (where the name was found + registry state
+ fallback reasoning) so it is auditable rather than a black box.
"""

from __future__ import annotations

from typing import Optional

from ..classify.classifier import Classifier, ClassifierConfig
from ..schema import (
    Classification,
    DependencyName,
    FallbackConfig,
    NameFinding,
    RegistryStatus,
    Verdict,
    PRIORITY_CRITICAL,
    PRIORITY_HIGH,
    PRIORITY_MEDIUM,
    PRIORITY_INFO,
)

ACTIONS: dict[Verdict, str] = {
    Verdict.CLAIMABLE: (
        "Defensively register this name on the public registry now (a stub you "
        "control), and reserve the npm scope / pin the pip index so builds cannot "
        "fall back to public."
    ),
    Verdict.TAKEN_NOT_YOURS: (
        "Investigate: a public package with this name exists and is not yours "
        "(possible squat). Verify the owner and publish date; if malicious, report "
        "it to the registry and pin/replace the dependency."
    ),
    Verdict.PROTECTED: (
        "Exposure is mitigated by configuration (scope reserved / index pinned). "
        "Keep the config under review and re-scan in CI — a config change re-opens "
        "the exposure."
    ),
    Verdict.SAFE: (
        "No action needed: the name is legitimately public (well-known or "
        "org-owned)."
    ),
}


class Scorer:
    def __init__(
        self,
        classifier: Optional[Classifier] = None,
        classifier_config: Optional[ClassifierConfig] = None,
    ):
        self.classifier = classifier or Classifier(classifier_config)
        self.config = self.classifier.config

    def score(
        self,
        name: DependencyName,
        status: RegistryStatus,
        fallback: FallbackConfig,
    ) -> NameFinding:
        classification, reason = self.classifier.classify_with_registry(name, status)

        finding = NameFinding(
            name=name,
            classification=classification,
            registry=status,
            fallback=fallback,
        )
        evidence: list[str] = [f"classification: {classification.value} ({reason})"]
        # Cite where the name was found.
        src_desc = ", ".join(
            f"{s.path}:{s.line} [{s.source_type.value}]" for s in name.sources[:5]
        )
        if src_desc:
            evidence.append(f"found in: {src_desc}")
        if status:
            if status.exists:
                evidence.append(
                    f"public registry: EXISTS (owner={status.owner or 'unknown'}, "
                    f"first_published={status.first_published or 'unknown'}, "
                    f"recent={status.recently_published}, src={status.source})"
                )
            else:
                evidence.append(f"public registry: NOT FOUND (src={status.source})")
        evidence.extend(f"fallback: {e}" for e in (fallback.evidence or []))

        verdict, priority = self._decide(name, classification, status, fallback)
        finding.verdict = verdict
        finding.priority = priority
        finding.action = ACTIONS[verdict]
        finding.evidence = evidence
        return finding

    # ------------------------------------------------------------------ #
    def _decide(
        self,
        name: DependencyName,
        classification: Classification,
        status: RegistryStatus,
        fallback: FallbackConfig,
    ) -> tuple[Verdict, int]:
        owned_public = name.normalized in self.config.owned_public_names

        # External / well-known / org-owned public -> SAFE.
        if classification is Classification.EXTERNAL:
            return Verdict.SAFE, PRIORITY_INFO

        # From here we are dealing with INTERNAL or UNKNOWN (treated as a
        # candidate worth checking).
        exists = bool(status and status.exists)

        if not exists:
            # Unclaimed internal name. Exploitable iff config permits fallback.
            if fallback and not fallback.exploitable:
                return Verdict.PROTECTED, PRIORITY_MEDIUM
            # Critical: unclaimed AND an attacker's public publish would be pulled.
            return Verdict.CLAIMABLE, PRIORITY_CRITICAL

        # Exists publicly.
        if owned_public or (status.owner and status.owner in self.config.owned_public_names):
            return Verdict.SAFE, PRIORITY_INFO

        # Public and not yours -> possible squat.
        if status.recently_published and fallback and fallback.exploitable:
            # Freshly published + your build would pull it: highest concern.
            return Verdict.TAKEN_NOT_YOURS, PRIORITY_CRITICAL
        if status.recently_published or (fallback and fallback.exploitable):
            return Verdict.TAKEN_NOT_YOURS, PRIORITY_HIGH
        return Verdict.TAKEN_NOT_YOURS, PRIORITY_MEDIUM
