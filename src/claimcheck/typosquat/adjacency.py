"""Typosquat-adjacency detection.

Dependency confusion claims your *exact* internal name. A typosquat claims a
*near-miss*: ``acmecorp_config_loader`` for ``acmecorp-config-loader``,
``acme-internal-biling`` for ``acme-internal-billing``. A single typo, a bad
copy-paste, or an auto-corrected separator then pulls the attacker's package in.

For each internal name, this module generates a **bounded** set of confusable
variants and probes each against the public registry (read-only, via the same
oracle as the main scan). A variant that *exists publicly and is not yours* is
reported as a potential typosquat.

Design notes:

* The candidate set is deliberately bounded (separator swaps, single deletions,
  adjacent transpositions, character doubling, and a scope-drop for npm) rather
  than the full edit-distance-1 neighborhood, so live mode stays practical.
* PyPI name canonicalization (PEP 503) already collapses ``-``/``_``/``.``, so a
  pure separator swap is *not* a distinct PyPI name — the generator drops
  candidates that canonicalize back to the original.
"""

from __future__ import annotations

from typing import Iterable, Optional

from ..extract import canonicalize_npm, canonicalize_pypi, split_npm_scope
from ..schema import (
    DependencyName,
    Ecosystem,
    NameFinding,
    RegistryStatus,
    TyposquatFinding,
    Verdict,
    PRIORITY_CRITICAL,
    PRIORITY_HIGH,
)

_SEPARATORS = ["-", "_", "."]


def edit_distance(a: str, b: str) -> int:
    """Levenshtein edit distance (iterative, O(len(a)*len(b)))."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost))
        prev = cur
    return prev[-1]


def _canon(name: str, ecosystem: Ecosystem) -> str:
    return canonicalize_npm(name) if ecosystem is Ecosystem.NPM else canonicalize_pypi(name)


def generate_candidates(
    name: DependencyName, max_candidates: int = 128
) -> list[tuple[str, str]]:
    """Return a bounded list of ``(variant, kind)`` confusable with ``name``.

    Variants are canonicalized for their ecosystem and exclude any that collapse
    back to the original name. ``kind`` labels the transformation.
    """
    original = name.normalized
    eco = name.ecosystem
    seen: set[str] = {original}
    out: list[tuple[str, str]] = []

    def add(variant: str, kind: str) -> None:
        if not variant:
            return
        c = _canon(variant, eco)
        if c in seen:
            return
        seen.add(c)
        out.append((c, kind))

    # For npm scoped names, also consider the "scope dropped" collapse, a very
    # common confusion (e.g. @acme/billing -> acme-billing).
    if eco is Ecosystem.NPM:
        scope, bare = split_npm_scope(original)
        if scope:
            flat = scope.lstrip("@")
            add(f"{flat}-{bare}", "scope-drop")
            add(f"{flat}{bare}", "scope-drop")
            # Work the rest of the transforms on the bare part.
            work = bare
            prefix = f"{scope}/"
        else:
            work = original
            prefix = ""
    else:
        work = original
        prefix = ""

    # 1. Separator swaps (meaningful for npm; dropped for PyPI by canonicalization).
    for i, ch in enumerate(work):
        if ch in _SEPARATORS:
            for sep in _SEPARATORS:
                if sep != ch:
                    add(prefix + work[:i] + sep + work[i + 1:], "separator-swap")
            add(prefix + work[:i] + work[i + 1:], "separator-removed")

    # 2. Single-character deletions (a dropped letter).
    for i in range(len(work)):
        if work[i] in _SEPARATORS:
            continue
        add(prefix + work[:i] + work[i + 1:], "char-deletion")

    # 3. Adjacent transpositions (swapped neighbors).
    for i in range(len(work) - 1):
        swapped = work[:i] + work[i + 1] + work[i] + work[i + 2:]
        add(prefix + swapped, "transposition")

    # 4. Character doubling (a repeated keystroke).
    for i, ch in enumerate(work):
        if ch in _SEPARATORS:
            continue
        add(prefix + work[:i + 1] + ch + work[i + 1:], "char-doubling")

    return out[:max_candidates]


class TyposquatDetector:
    """Probe confusable variants of internal names against the public registry."""

    def __init__(self, oracle, owned_public_names: Optional[set[str]] = None,
                 max_candidates: int = 128):
        self.oracle = oracle
        self.owned = {n.lower() for n in (owned_public_names or set())}
        self.max_candidates = max_candidates

    def detect(self, findings: Iterable[NameFinding]) -> list[TyposquatFinding]:
        """Find typosquats of every internal name among ``findings``.

        Only names the scan considers at risk (verdict CLAIMABLE, PROTECTED, or
        TAKEN-NOT-YOURS — i.e. internal) are expanded; SAFE/external names are
        skipped to keep the probe focused and cheap.
        """
        results: list[TyposquatFinding] = []
        seen_variants: set[tuple[str, str]] = set()
        at_risk = {Verdict.CLAIMABLE, Verdict.PROTECTED, Verdict.TAKEN_NOT_YOURS}

        for f in findings:
            if f.verdict not in at_risk:
                continue
            name = f.name
            for variant, kind in generate_candidates(name, self.max_candidates):
                key = (name.ecosystem.value, variant)
                if key in seen_variants:
                    continue
                seen_variants.add(key)
                status: RegistryStatus = self.oracle.lookup(variant, name.ecosystem)
                if not status.exists:
                    continue
                if variant in self.owned or (status.owner and status.owner.lower() in self.owned):
                    continue  # a near-name you legitimately own is not a squat
                dist = edit_distance(name.normalized, variant)
                priority = (PRIORITY_CRITICAL
                            if status.recently_published else PRIORITY_HIGH)
                results.append(TyposquatFinding(
                    internal_name=name.normalized,
                    ecosystem=name.ecosystem.value,
                    variant=variant,
                    kind=kind,
                    distance=dist,
                    registry=status,
                    priority=priority,
                ))
        results.sort(key=lambda t: (t.priority, t.ecosystem, t.internal_name, t.variant))
        return results
