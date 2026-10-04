"""Tests for the exposure scorer + verdict engine."""

from claimcheck.classify.classifier import Classifier, ClassifierConfig
from claimcheck.extract import make_name
from claimcheck.fallback.analyzer import FallbackAnalyzer
from claimcheck.collect.collectors import RegistryConfig
from claimcheck.score.scorer import Scorer
from claimcheck.schema import (
    Ecosystem, RegistryStatus, Verdict, PRIORITY_CRITICAL,
)


def _scorer(**cfg):
    return Scorer(Classifier(ClassifierConfig(**cfg)))


def _fb(name, reg_config=None):
    return FallbackAnalyzer(reg_config or RegistryConfig()).analyze(name)


def test_unclaimed_internal_with_fallback_is_claimable():
    s = _scorer(internal_prefixes=["acme-"])
    name = make_name("acme-internal-auth", Ecosystem.PYPI)
    status = RegistryStatus(exists=False)
    finding = s.score(name, status, _fb(name))
    assert finding.verdict is Verdict.CLAIMABLE
    assert finding.priority == PRIORITY_CRITICAL
    assert finding.action


def test_unclaimed_internal_protected_scope():
    reg = RegistryConfig(npm_scope_registries={"@acme": "https://npm.internal/"})
    s = _scorer(private_scopes={"@acme"})
    name = make_name("@acme/secrets", Ecosystem.NPM)
    status = RegistryStatus(exists=False)
    finding = s.score(name, status, _fb(name, reg))
    assert finding.verdict is Verdict.PROTECTED


def test_public_not_yours_is_taken():
    s = _scorer(internal_prefixes=["acme-"])
    name = make_name("acme-internal-utils", Ecosystem.PYPI)
    status = RegistryStatus(exists=True, owner="mallory",
                            first_published="2026-09-25", recently_published=True)
    finding = s.score(name, status, _fb(name))
    assert finding.verdict is Verdict.TAKEN_NOT_YOURS
    assert finding.priority == PRIORITY_CRITICAL  # recent + exploitable


def test_owned_public_is_safe():
    s = _scorer(internal_prefixes=["acme-"], owned_public_names={"acme-sdk"})
    name = make_name("acme-sdk", Ecosystem.PYPI)
    status = RegistryStatus(exists=True, owner="acme")
    finding = s.score(name, status, _fb(name))
    assert finding.verdict is Verdict.SAFE


def test_wellknown_is_safe():
    s = _scorer()
    name = make_name("requests", Ecosystem.PYPI)
    status = RegistryStatus(exists=True, owner="community")
    finding = s.score(name, status, _fb(name))
    assert finding.verdict is Verdict.SAFE


def test_evidence_is_present_for_claimable():
    s = _scorer(internal_prefixes=["acme-"])
    name = make_name("acme-internal-auth", Ecosystem.PYPI)
    finding = s.score(name, RegistryStatus(exists=False), _fb(name))
    assert any("classification" in e for e in finding.evidence)
    assert any("registry" in e.lower() for e in finding.evidence)
