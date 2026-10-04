"""Tests for the scope/config fallback analyzer."""

from claimcheck.collect.collectors import RegistryConfig
from claimcheck.fallback.analyzer import FallbackAnalyzer
from claimcheck.extract import make_name
from claimcheck.schema import Ecosystem


def test_npm_reserved_scope_is_protected():
    cfg = RegistryConfig(npm_scope_registries={"@acme": "https://npm.acme.internal/"})
    fb = FallbackAnalyzer(cfg).analyze(make_name("@acme/secrets", Ecosystem.NPM))
    assert fb.scope_reserved is True
    assert fb.exploitable is False


def test_npm_unscoped_falls_back():
    cfg = RegistryConfig()
    fb = FallbackAnalyzer(cfg).analyze(make_name("acmecorp-ui", Ecosystem.NPM))
    assert fb.exploitable is True


def test_npm_scope_pointing_public_is_exploitable():
    cfg = RegistryConfig(npm_scope_registries={"@acme": "https://registry.npmjs.org/"})
    fb = FallbackAnalyzer(cfg).analyze(make_name("@acme/x", Ecosystem.NPM))
    assert fb.scope_reserved is False
    assert fb.exploitable is True


def test_pip_public_extra_index_is_exploitable():
    cfg = RegistryConfig(pip_index_url="https://pypi.acme.internal/simple/",
                         pip_extra_index_urls=["https://pypi.org/simple/"])
    fb = FallbackAnalyzer(cfg).analyze(make_name("acme-auth", Ecosystem.PYPI))
    assert fb.exploitable is True


def test_pip_pinned_private_index_is_protected():
    cfg = RegistryConfig(pip_index_url="https://pypi.acme.internal/simple/",
                         pip_extra_index_urls=[])
    fb = FallbackAnalyzer(cfg).analyze(make_name("acme-auth", Ecosystem.PYPI))
    assert fb.pinned_index_only is True
    assert fb.exploitable is False


def test_pip_no_config_defaults_to_public():
    cfg = RegistryConfig()
    fb = FallbackAnalyzer(cfg).analyze(make_name("acme-auth", Ecosystem.PYPI))
    assert fb.exploitable is True
