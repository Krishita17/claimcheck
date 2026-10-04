"""Core data schema for ClaimCheck.

Every stage of the pipeline exchanges these dataclasses. Keeping the schema in
one place makes the pipeline explainable: a final verdict can always be traced
back to the sources a name was found in and the registry evidence behind it.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field, asdict
from typing import Optional


# --------------------------------------------------------------------------- #
# Enumerations
# --------------------------------------------------------------------------- #
class Ecosystem(str, enum.Enum):
    """Package ecosystem a name belongs to."""

    PYPI = "pypi"
    NPM = "npm"


class SourceType(str, enum.Enum):
    """Where a dependency name was discovered."""

    REQUIREMENTS_TXT = "requirements.txt"
    PYPROJECT_TOML = "pyproject.toml"
    SETUP_PY = "setup.py"
    SETUP_CFG = "setup.cfg"
    PIPFILE = "Pipfile"
    POETRY_LOCK = "poetry.lock"
    PACKAGE_JSON = "package.json"
    PACKAGE_LOCK_JSON = "package-lock.json"
    YARN_LOCK = "yarn.lock"
    NPMRC = ".npmrc"
    PIP_CONF = "pip.conf"
    DOCKERFILE = "Dockerfile"
    CI_FILE = "ci"


class Classification(str, enum.Enum):
    """Whether a name is meant to be private/internal."""

    INTERNAL = "internal"      # an org-private name that must be checked
    EXTERNAL = "external"      # a well-known public dependency; ignore
    UNKNOWN = "unknown"        # undetermined; treated as a candidate to check


class Verdict(str, enum.Enum):
    """Final per-name exposure verdict (the deliverable)."""

    CLAIMABLE = "CLAIMABLE"                 # unregistered publicly + exploitable
    TAKEN_NOT_YOURS = "TAKEN-NOT-YOURS"     # public and not yours (possible squat)
    PROTECTED = "PROTECTED"                 # scope reserved / index pinned
    SAFE = "SAFE"                           # legitimately public / well-known


# Priority: 1 = critical, 4 = informational.
PRIORITY_CRITICAL = 1
PRIORITY_HIGH = 2
PRIORITY_MEDIUM = 3
PRIORITY_INFO = 4


# --------------------------------------------------------------------------- #
# Records
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SourceRef:
    """A single place a name was found."""

    path: str
    line: int
    source_type: SourceType

    def to_dict(self) -> dict:
        d = asdict(self)
        d["source_type"] = self.source_type.value
        return d


@dataclass
class DependencyName:
    """A dependency name extracted from one or more sources."""

    raw: str
    normalized: str
    ecosystem: Ecosystem
    scope: Optional[str] = None            # e.g. "@acme" for npm scoped names
    sources: list[SourceRef] = field(default_factory=list)

    def key(self) -> tuple[str, str]:
        """Stable identity: (ecosystem, normalized name)."""
        return (self.ecosystem.value, self.normalized)

    def to_dict(self) -> dict:
        return {
            "raw": self.raw,
            "normalized": self.normalized,
            "ecosystem": self.ecosystem.value,
            "scope": self.scope,
            "sources": [s.to_dict() for s in self.sources],
        }


@dataclass
class RegistryStatus:
    """Result of a read-only public-registry lookup."""

    exists: bool
    owner: Optional[str] = None
    first_published: Optional[str] = None   # ISO date string
    recently_published: bool = False        # published within the recent window
    source: str = "mock"                    # "mock" | "live" | "cache"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FallbackConfig:
    """Per-ecosystem assessment of whether install config permits public fallback.

    This is what separates a *theoretical* exposure (name is unclaimed) from an
    *exploitable* one (install would actually resolve the name from the public
    registry if a higher version appeared there).
    """

    ecosystem: Ecosystem
    public_fallback_enabled: bool = True    # default pm behaviour is to fall back
    scope_reserved: bool = False            # npm scope pinned to a private registry
    pinned_index_only: bool = False         # pip index pinned, no extra-index public
    evidence: list[str] = field(default_factory=list)

    @property
    def exploitable(self) -> bool:
        """True if public fallback could actually occur for this ecosystem."""
        if self.scope_reserved or self.pinned_index_only:
            return False
        return self.public_fallback_enabled

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ecosystem"] = self.ecosystem.value
        d["exploitable"] = self.exploitable
        return d


@dataclass
class NameFinding:
    """Everything known about one name after the full pipeline runs."""

    name: DependencyName
    classification: Classification = Classification.UNKNOWN
    registry: Optional[RegistryStatus] = None
    fallback: Optional[FallbackConfig] = None
    verdict: Optional[Verdict] = None
    priority: int = PRIORITY_INFO
    action: str = ""
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name.to_dict(),
            "classification": self.classification.value,
            "registry": self.registry.to_dict() if self.registry else None,
            "fallback": self.fallback.to_dict() if self.fallback else None,
            "verdict": self.verdict.value if self.verdict else None,
            "priority": self.priority,
            "action": self.action,
            "evidence": list(self.evidence),
        }


@dataclass
class ScanResult:
    """The full output of a scan: all findings plus the target that was scanned."""

    target: str
    findings: list[NameFinding] = field(default_factory=list)
    mode: str = "mock"                      # "mock" | "live"

    def to_dict(self) -> dict:
        return {
            "target": self.target,
            "mode": self.mode,
            "findings": [f.to_dict() for f in self.findings],
        }

    def by_verdict(self, verdict: Verdict) -> list[NameFinding]:
        return [f for f in self.findings if f.verdict == verdict]

    def sorted_findings(self) -> list[NameFinding]:
        """Findings ordered by priority (critical first), then name."""
        return sorted(
            self.findings,
            key=lambda f: (f.priority, f.name.ecosystem.value, f.name.normalized),
        )
