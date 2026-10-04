"""Synthetic organization generator.

Produces a plausible, fully-labeled dependency surface for a *fictional* org so
ClaimCheck can be evaluated reproducibly without probing or exposing any real
company. Every generated name carries ground-truth labels (its intended
classification and verdict) assigned *by construction* — independent of the
scorer — so the benchmark measures whether the scorer reproduces the intended
semantics rather than grading itself.

SAFETY / ETHICS: all names here are fictional and operator-controlled
(``acme-*``, ``@acme/*``, ``acmecorp-*``). The "already-squatted" cases use the
fictional owner ``mallory`` and never reference a real organization's real
internal package names.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field, asdict
from typing import Optional

from ..schema import Classification, Verdict

# Category -> (ground-truth classification, ground-truth verdict).
CATEGORIES: dict[str, tuple[Classification, Verdict]] = {
    "wellknown_public": (Classification.EXTERNAL, Verdict.SAFE),
    "owned_public": (Classification.EXTERNAL, Verdict.SAFE),
    "internal_claimable": (Classification.INTERNAL, Verdict.CLAIMABLE),
    "internal_protected": (Classification.INTERNAL, Verdict.PROTECTED),
    "internal_taken_squat": (Classification.INTERNAL, Verdict.TAKEN_NOT_YOURS),
    "looks_internal_public": (Classification.INTERNAL, Verdict.TAKEN_NOT_YOURS),
    # --- adversarial / hard cases that probe the heuristics' limits ------- #
    # Internal, no naming signal, unclaimed: caught only by the
    # "absent from public registry" heuristic (a strength case).
    "hard_internal_no_signal_unclaimed": (Classification.INTERNAL, Verdict.CLAIMABLE),
    # Internal, no naming signal, already squatted: indistinguishable from a
    # normal public dependency without an allowlist (expected FALSE NEGATIVE).
    "hard_internal_no_signal_squatted": (Classification.INTERNAL, Verdict.TAKEN_NOT_YOURS),
    # Public package that merely collides with the internal prefix: a human
    # analyst triages it as not-an-exposure (expected FALSE POSITIVE from the
    # prefix heuristic over-triggering).
    "hard_external_prefix_collision": (Classification.EXTERNAL, Verdict.SAFE),
}

# Categories that represent legitimately-public packages (used to measure the
# false-positive rate — flagging any of these non-SAFE is a false positive).
PUBLIC_CATEGORIES = {"wellknown_public", "owned_public", "hard_external_prefix_collision"}


@dataclass
class SyntheticName:
    raw: str
    ecosystem: str                 # "pypi" | "npm"
    category: str
    place: str                     # which source file it is emitted into
    scope: Optional[str] = None
    exists_public: bool = False
    owner: Optional[str] = None
    first_published: Optional[str] = None
    recently_published: bool = False

    @property
    def true_classification(self) -> Classification:
        return CATEGORIES[self.category][0]

    @property
    def true_verdict(self) -> Verdict:
        return CATEGORIES[self.category][1]

    def to_label(self) -> dict:
        return {
            "raw": self.raw,
            "ecosystem": self.ecosystem,
            "scope": self.scope,
            "category": self.category,
            "true_classification": self.true_classification.value,
            "true_verdict": self.true_verdict.value,
        }


@dataclass
class SyntheticOrg:
    slug: str
    names: list[SyntheticName]
    private_scope: str                        # npm scope reserved in .npmrc
    internal_pip_prefix: str                  # pip internal prefix
    internal_npm_prefix: str                  # npm unscoped internal prefix
    private_npm_registry: str
    private_pip_index: str
    public_fallback: bool = True              # does this org's config allow fallback?
    owned_public_names: list[str] = field(default_factory=list)

    def classifier_config_dict(self) -> dict:
        return {
            "internal_prefixes": [self.internal_pip_prefix, self.internal_npm_prefix],
            "private_scopes": [self.private_scope],
            "owned_public_names": list(self.owned_public_names),
            "internal_names": [],
        }

    def registry_fixture(self) -> dict:
        """Build the mock-oracle fixture (which names 'exist' publicly)."""
        fixture = {"pypi": {}, "npm": {}}
        for n in self.names:
            if not n.exists_public:
                continue
            from ..extract import canonicalize_pypi, canonicalize_npm
            key = canonicalize_pypi(n.raw) if n.ecosystem == "pypi" else canonicalize_npm(n.raw)
            fixture[n.ecosystem][key] = {
                "owner": n.owner,
                "first_published": n.first_published,
                "recently_published": n.recently_published,
            }
        return fixture

    def labels(self) -> list[dict]:
        return [n.to_label() for n in self.names]


# Well-known seeds drawn from the curated lists so they classify as EXTERNAL.
_WELLKNOWN_PYPI = ["requests", "flask", "numpy", "pydantic", "pyyaml"]
_WELLKNOWN_NPM = ["lodash", "express", "react", "chalk", "axios"]


def generate_org(seed: int = 0, slug: str = "acme") -> SyntheticOrg:
    """Generate one labeled synthetic organization deterministically from ``seed``."""
    rng = random.Random(seed)
    suffix = rng.choice(["svc", "core", "lib", "kit", "api"]) + str(seed % 97)

    pip_prefix = f"{slug}-"
    npm_prefix = f"{slug}corp-"
    scope = f"@{slug}"
    priv_npm = f"https://npm.{slug}.internal/"
    priv_pip = f"https://pypi.{slug}.internal/simple/"

    names: list[SyntheticName] = []

    # -- well-known public (noise that must be ignored) -------------------- #
    for w in rng.sample(_WELLKNOWN_PYPI, 3):
        names.append(SyntheticName(w, "pypi", "wellknown_public", "requirements.txt",
                                   exists_public=True, owner="community",
                                   first_published="2013-01-01"))
    for w in rng.sample(_WELLKNOWN_NPM, 3):
        names.append(SyntheticName(w, "npm", "wellknown_public", "package.json",
                                   exists_public=True, owner="community",
                                   first_published="2013-01-01"))

    # -- org-owned legitimately-public packages ---------------------------- #
    owned_pypi = f"{pip_prefix}sdk"
    owned_npm = f"{npm_prefix}widgets"
    names.append(SyntheticName(owned_pypi, "pypi", "owned_public", "pyproject.toml",
                               exists_public=True, owner=slug,
                               first_published="2021-03-01"))
    names.append(SyntheticName(owned_npm, "npm", "owned_public", "package.json",
                               exists_public=True, owner=slug,
                               first_published="2021-03-01"))

    # -- internal, CLAIMABLE (unclaimed publicly, fallback-enabled) -------- #
    for base in ("auth", "billing", f"telemetry-{suffix}"):
        names.append(SyntheticName(f"{pip_prefix}internal-{base}", "pypi",
                                   "internal_claimable", "requirements.txt"))
    names.append(SyntheticName(f"{npm_prefix}internal-ui", "npm",
                               "internal_claimable", "package.json"))
    names.append(SyntheticName(f"{npm_prefix}config-loader", "npm",
                               "internal_claimable", "Dockerfile"))

    # -- internal, PROTECTED (reserved @scope, unclaimed) ------------------ #
    for base in ("secrets", "payments"):
        names.append(SyntheticName(f"{scope}/{base}", "npm", "internal_protected",
                                   "package.json", scope=scope))

    # -- internal, already squatted by someone else (fictional 'mallory') -- #
    names.append(SyntheticName(f"{pip_prefix}internal-utils", "pypi",
                               "internal_taken_squat", "requirements.txt",
                               exists_public=True, owner="mallory",
                               first_published="2026-09-25", recently_published=True))
    names.append(SyntheticName(f"{npm_prefix}internal-logger", "npm",
                               "internal_taken_squat", "ci",
                               exists_public=True, owner="mallory",
                               first_published="2026-09-20", recently_published=True))

    # -- looks internal but is an unrelated public package (not recent) ---- #
    names.append(SyntheticName(f"{pip_prefix}tools", "pypi", "looks_internal_public",
                               "requirements.txt", exists_public=True,
                               owner="thirdparty-dev", first_published="2018-06-01"))

    # -- adversarial / hard cases ----------------------------------------- #
    # Strength: internal name with NO prefix/scope signal, unclaimed -> caught
    # only by the "absent from public registry" heuristic.
    names.append(SyntheticName(f"paymentsvc-core-{suffix}", "pypi",
                               "hard_internal_no_signal_unclaimed", "requirements.txt"))
    # Honest limitation (false negative): internal name with no signal that was
    # already squatted -> looks like a normal public dependency.
    names.append(SyntheticName("datastore-sync-layer", "npm",
                               "hard_internal_no_signal_squatted", "package.json",
                               exists_public=True, owner="mallory",
                               first_published="2026-09-18", recently_published=True))
    # Honest limitation (false positive): a long-established public package that
    # merely collides with the internal prefix.
    names.append(SyntheticName(f"{pip_prefix}logging-legacy", "pypi",
                               "hard_external_prefix_collision", "requirements.txt",
                               exists_public=True, owner="oss-maintainer",
                               first_published="2016-02-01"))

    org = SyntheticOrg(
        slug=slug,
        names=names,
        private_scope=scope,
        internal_pip_prefix=pip_prefix,
        internal_npm_prefix=npm_prefix,
        private_npm_registry=priv_npm,
        private_pip_index=priv_pip,
        public_fallback=True,
        owned_public_names=[owned_pypi.lower(), owned_npm.lower()],
    )
    return org
