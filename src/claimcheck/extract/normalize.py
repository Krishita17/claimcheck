"""Name extractor + normalizer.

Normalization matters: PyPI treats ``Acme_Internal.Auth`` and
``acme-internal-auth`` as the *same* project (PEP 503), so a naive string
compare against the registry would miss a match on a technicality and
under-report exposure. npm is case-insensitive and keeps an optional ``@scope``.

This module turns a raw string from any source into a canonical
:class:`~claimcheck.schema.DependencyName`, and merges duplicate findings while
preserving every source location (needed for explainable verdicts).
"""

from __future__ import annotations

import re
from typing import Iterable, Optional

from ..schema import DependencyName, Ecosystem, SourceRef

# PEP 503: runs of -, _, . collapse to a single - and the name is lowercased.
_PEP503_SEP = re.compile(r"[-_.]+")


def canonicalize_pypi(name: str) -> str:
    """Canonicalize a PyPI project name per PEP 503.

    >>> canonicalize_pypi("Acme_Internal.Auth")
    'acme-internal-auth'
    """
    return _PEP503_SEP.sub("-", name.strip()).lower()


def split_npm_scope(name: str) -> tuple[Optional[str], str]:
    """Split an npm name into (scope, bare_name).

    >>> split_npm_scope("@acme/billing")
    ('@acme', 'billing')
    >>> split_npm_scope("lodash")
    (None, 'lodash')
    """
    name = name.strip()
    if name.startswith("@") and "/" in name:
        scope, _, rest = name.partition("/")
        return scope.lower(), rest.lower()
    return None, name.lower()


def canonicalize_npm(name: str) -> str:
    """Canonicalize an npm package name (lowercase, scope preserved).

    >>> canonicalize_npm("@Acme/Billing")
    '@acme/billing'
    """
    scope, bare = split_npm_scope(name)
    return f"{scope}/{bare}" if scope else bare


def make_name(
    raw: str,
    ecosystem: Ecosystem,
    source: Optional[SourceRef] = None,
) -> Optional[DependencyName]:
    """Build a normalized :class:`DependencyName` from a raw token.

    Returns ``None`` for tokens that are not package names (empty, URLs, local
    paths, option flags). Keeping this strict avoids polluting the name set.
    """
    raw = raw.strip()
    if not raw:
        return None
    # Reject obvious non-names: flags, URLs, VCS/local installs, environment refs.
    if raw.startswith(("-", "#", ".", "/", "http://", "https://", "git+", "file:")):
        return None
    if raw.startswith("${") or "://" in raw:
        return None

    if ecosystem is Ecosystem.NPM:
        scope, _ = split_npm_scope(raw)
        normalized = canonicalize_npm(raw)
    else:
        scope = None
        normalized = canonicalize_pypi(raw)

    # A canonical name must contain at least one alphanumeric character.
    if not re.search(r"[a-z0-9]", normalized):
        return None

    sources = [source] if source else []
    return DependencyName(
        raw=raw,
        normalized=normalized,
        ecosystem=ecosystem,
        scope=scope,
        sources=sources,
    )


def merge_names(names: Iterable[DependencyName]) -> list[DependencyName]:
    """Deduplicate names by (ecosystem, normalized), unioning their source refs.

    The first-seen ``raw`` spelling and ``scope`` are kept; all source
    locations are preserved and de-duplicated so a verdict can cite every place
    the name leaked.
    """
    merged: dict[tuple[str, str], DependencyName] = {}
    for dn in names:
        if dn is None:
            continue
        key = dn.key()
        if key not in merged:
            merged[key] = DependencyName(
                raw=dn.raw,
                normalized=dn.normalized,
                ecosystem=dn.ecosystem,
                scope=dn.scope,
                sources=list(dn.sources),
            )
        else:
            existing = merged[key]
            seen = {(s.path, s.line, s.source_type) for s in existing.sources}
            for s in dn.sources:
                if (s.path, s.line, s.source_type) not in seen:
                    existing.sources.append(s)
                    seen.add((s.path, s.line, s.source_type))
    return list(merged.values())
