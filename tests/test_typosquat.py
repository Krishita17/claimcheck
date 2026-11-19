"""Tests for typosquat-adjacency detection."""

from claimcheck.classify.classifier import ClassifierConfig
from claimcheck.data.generate import materialize_org
from claimcheck.data.synth_org import generate_org
from claimcheck.extract import make_name
from claimcheck.pipeline import run_scan
from claimcheck.registry.oracle import MockRegistryOracle
from claimcheck.schema import Ecosystem
from claimcheck.typosquat import edit_distance, generate_candidates, TyposquatDetector


def test_edit_distance():
    assert edit_distance("billing", "billing") == 0
    assert edit_distance("billing", "biling") == 1
    assert edit_distance("abc", "acb") == 2  # Levenshtein (not Damerau)
    assert edit_distance("", "abc") == 3


def test_candidates_npm_include_separator_swap():
    name = make_name("acmecorp-config-loader", Ecosystem.NPM)
    variants = {v for v, _ in generate_candidates(name)}
    assert "acmecorp-config_loader" in variants
    assert name.normalized not in variants


def test_candidates_pypi_drop_pure_separator_swaps():
    # PEP 503 collapses -/_/. so a pure separator swap is NOT a distinct name.
    name = make_name("acme-internal-auth", Ecosystem.PYPI)
    variants = {v for v, _ in generate_candidates(name)}
    assert "acme_internal_auth" not in variants  # canonicalizes back to original
    # a dropped letter IS a distinct candidate
    assert "acme-internal-ath" in variants or "acme-internal-auh" in variants


def test_candidates_npm_scope_drop():
    name = make_name("@acme/secrets", Ecosystem.NPM)
    kinds = {k for _, k in generate_candidates(name)}
    assert "scope-drop" in kinds


def test_detector_finds_planted_squats(tmp_path):
    org = generate_org(seed=0)
    repo = tmp_path / org.slug
    materialize_org(org, repo, public_fallback=True)
    oracle = MockRegistryOracle(org.registry_fixture())
    config = ClassifierConfig.from_dict(org.classifier_config_dict())
    result = run_scan(repo, oracle=oracle, classifier_config=config,
                      detect_typosquats=True)

    variants = {(t.ecosystem, t.variant) for t in result.typosquats}
    assert ("npm", "acmecorp-config_loader") in variants
    assert ("pypi", "acme-internal-biling") in variants
    # every typosquat is at a small edit distance and owned by someone else
    for t in result.typosquats:
        assert 1 <= t.distance <= 3
        assert t.registry.owner == "mallory"


def test_detector_skips_safe_names(tmp_path):
    """Well-known/SAFE names are not expanded into typosquat candidates."""
    org = generate_org(seed=1)
    repo = tmp_path / org.slug
    materialize_org(org, repo, public_fallback=True)
    oracle = MockRegistryOracle(org.registry_fixture())
    config = ClassifierConfig.from_dict(org.classifier_config_dict())
    result = run_scan(repo, oracle=oracle, classifier_config=config,
                      detect_typosquats=True)
    # No typosquat should reference a well-known base name.
    for t in result.typosquats:
        assert t.internal_name not in ("requests", "flask", "lodash", "express")
