"""Scope / config fallback analyzer.

An unclaimed internal name is only *exploitable* if your install configuration
would actually let a package manager resolve it from the public registry. This
analyzer turns the registry config discovered by the collectors into a per-name
:class:`~claimcheck.schema.FallbackConfig`, which is what separates a theoretical
exposure from an actionable one.

Rules modeled (grounded in documented package-manager behavior):

* **npm** — a scoped name (``@acme/x``) whose scope is pinned to a private
  registry in ``.npmrc`` (``@acme:registry=https://npm.internal``) will *not*
  fall back to the public registry: PROTECTED. An unscoped name, or a scope with
  no private mapping, resolves against the default registry and can fall back.
* **pip** — ``index-url`` pointing only at a private index with **no**
  public ``extra-index-url`` pins resolution to that index (no fallback). But
  ``extra-index-url`` pointing at public PyPI (a very common misconfiguration)
  means pip may pick the *highest version across all indexes* — the classic
  dependency-confusion fallback.
"""

from __future__ import annotations

from ..collect.collectors import (
    RegistryConfig,
    _is_public_npm_registry,
    _is_public_pypi_index,
)
from ..schema import DependencyName, Ecosystem, FallbackConfig


class FallbackAnalyzer:
    def __init__(self, config: RegistryConfig):
        self.config = config

    def analyze(self, name: DependencyName) -> FallbackConfig:
        if name.ecosystem is Ecosystem.NPM:
            return self._analyze_npm(name)
        return self._analyze_pypi(name)

    # -- npm -------------------------------------------------------------- #
    def _analyze_npm(self, name: DependencyName) -> FallbackConfig:
        fb = FallbackConfig(ecosystem=Ecosystem.NPM)
        scope = name.scope.lower() if name.scope else None
        if scope and scope in self.config.npm_scope_registries:
            reg = self.config.npm_scope_registries[scope]
            if not _is_public_npm_registry(reg):
                fb.scope_reserved = True
                fb.public_fallback_enabled = False
                fb.evidence.append(
                    f"scope {scope} pinned to private registry {reg} (.npmrc)"
                )
                return fb
            fb.evidence.append(f"scope {scope} points at public registry {reg}")
        elif scope:
            fb.evidence.append(
                f"scope {scope} has no private registry mapping; "
                "resolves against the default registry"
            )
        else:
            fb.evidence.append(
                "unscoped name resolves against the default registry "
                "(public fallback possible)"
            )

        default = self.config.npm_default_registry
        if default and not _is_public_npm_registry(default):
            # A private default registry still typically proxies/falls back to
            # public for unknown names unless explicitly locked down.
            fb.evidence.append(
                f"default registry is private ({default}) but may proxy to public"
            )
        fb.public_fallback_enabled = True
        return fb

    # -- pip -------------------------------------------------------------- #
    def _analyze_pypi(self, name: DependencyName) -> FallbackConfig:
        fb = FallbackConfig(ecosystem=Ecosystem.PYPI)
        index = self.config.pip_index_url
        extras = self.config.pip_extra_index_urls

        public_extra = [u for u in extras if _is_public_pypi_index(u)]
        private_index = bool(index) and not _is_public_pypi_index(index)

        if public_extra:
            fb.public_fallback_enabled = True
            fb.evidence.append(
                "pip extra-index-url includes public PyPI "
                f"({', '.join(public_extra)}); highest version wins across indexes"
            )
            return fb

        if private_index and not public_extra:
            fb.pinned_index_only = True
            fb.public_fallback_enabled = False
            fb.evidence.append(
                f"pip index-url pinned to private index {index} with no public "
                "extra-index-url (no fallback)"
            )
            return fb

        # No pip config discovered, or index-url is public -> default behavior
        # resolves from public PyPI.
        if index and _is_public_pypi_index(index):
            fb.evidence.append(f"pip index-url is public PyPI ({index})")
        else:
            fb.evidence.append(
                "no pip index configuration found; default resolution uses public PyPI"
            )
        fb.public_fallback_enabled = True
        return fb
