"""Internal / external classifier.

The classifier decides which names are *meant to be private* — the only ones
worth checking for dependency confusion. A public, well-known package
(``requests``, ``lodash``) is correctly ignored; ``acme-internal-auth`` is
flagged for checking.

Signals, in priority order:

1. **Explicit org allowlist** — names/prefixes/scopes the operator declares
   as theirs (highest confidence; config-driven).
2. **Private npm scope** — a scope mapped to a non-public registry in ``.npmrc``
   is, by definition, private.
3. **Well-known public package** — classified EXTERNAL without a lookup.
4. **Naming conventions** — configurable internal prefixes (e.g. ``acme-``).
5. **"Not on the public registry" heuristic** — a name used in builds that does
   not exist publicly is a strong internal signal (requires registry info, so
   it is applied as a fallback by :meth:`classify_with_registry`).

The classifier never mutates registry state; it only reads configuration and,
optionally, a registry status object produced by the read-only probe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..data.wellknown import is_wellknown
from ..schema import Classification, DependencyName, RegistryStatus


@dataclass
class ClassifierConfig:
    """Operator-provided hints about which names are theirs."""

    # Exact canonical names the operator owns / declares internal.
    internal_names: set[str] = field(default_factory=set)
    # Name prefixes that indicate internal packages (applied per-ecosystem-agnostic).
    internal_prefixes: list[str] = field(default_factory=list)
    # npm scopes that are private (e.g. "@acme"). Usually derived from .npmrc too.
    private_scopes: set[str] = field(default_factory=set)
    # Public names the org legitimately owns/publishes (treated as SAFE later).
    owned_public_names: set[str] = field(default_factory=set)

    @classmethod
    def from_dict(cls, d: dict) -> "ClassifierConfig":
        d = d or {}
        return cls(
            internal_names={n.lower() for n in d.get("internal_names", [])},
            internal_prefixes=[p.lower() for p in d.get("internal_prefixes", [])],
            private_scopes={s.lower() for s in d.get("private_scopes", [])},
            owned_public_names={n.lower() for n in d.get("owned_public_names", [])},
        )


class Classifier:
    def __init__(self, config: Optional[ClassifierConfig] = None,
                 discovered_private_scopes: Optional[set[str]] = None):
        self.config = config or ClassifierConfig()
        # Scopes discovered from .npmrc are merged with configured ones.
        self.private_scopes = set(self.config.private_scopes)
        if discovered_private_scopes:
            self.private_scopes |= {s.lower() for s in discovered_private_scopes}

    # -- config-only signals (no registry needed) ------------------------- #
    def classify(self, name: DependencyName) -> tuple[Classification, str]:
        """Classify using configuration and conventions only.

        Returns (classification, reason). May return UNKNOWN when no config
        signal fires and the name is not well-known; the registry heuristic in
        :meth:`classify_with_registry` can then refine it.
        """
        norm = name.normalized

        # 1. Explicit internal allowlist wins over everything.
        if norm in self.config.internal_names:
            return Classification.INTERNAL, "declared in org internal allowlist"

        # 2. Explicitly org-owned public names are EXTERNAL even if they happen to
        #    match an internal prefix (the scorer marks them SAFE).
        if norm in self.config.owned_public_names:
            return Classification.EXTERNAL, "org-owned public package"

        # 3. Well-known public packages are EXTERNAL without a lookup.
        if is_wellknown(norm, name.ecosystem.value):
            return Classification.EXTERNAL, "well-known public package"

        # 4. A private npm scope is internal by definition.
        if name.scope and name.scope.lower() in self.private_scopes:
            return Classification.INTERNAL, f"npm scope {name.scope} is private"

        # 5. Naming conventions.
        for prefix in self.config.internal_prefixes:
            # For scoped npm names, match against the bare name too.
            candidate = norm.split("/", 1)[-1]
            if norm.startswith(prefix) or candidate.startswith(prefix):
                return Classification.INTERNAL, f"matches internal prefix '{prefix}'"

        return Classification.UNKNOWN, "no config/convention signal"

    # -- registry-aware refinement --------------------------------------- #
    def classify_with_registry(
        self, name: DependencyName, status: Optional[RegistryStatus]
    ) -> tuple[Classification, str]:
        """Refine an UNKNOWN classification using the registry heuristic."""
        base, reason = self.classify(name)
        if base is not Classification.UNKNOWN:
            return base, reason
        if status is None:
            return Classification.UNKNOWN, reason
        if not status.exists:
            return (
                Classification.INTERNAL,
                "used in builds but absent from the public registry",
            )
        # Exists publicly and no internal signal -> treat as external.
        return Classification.EXTERNAL, "present on public registry, no internal signal"
