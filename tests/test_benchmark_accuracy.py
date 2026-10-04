"""End-to-end accuracy tests on labeled synthetic orgs.

Ground-truth labels are assigned by construction in the generator, independent of
the scorer, so these tests check that the scorer reproduces the intended
semantics — not that it grades its own output.
"""

import sys
from pathlib import Path

import pytest

from claimcheck.classify.classifier import ClassifierConfig
from claimcheck.data.generate import materialize_org
from claimcheck.data.synth_org import generate_org, CATEGORIES
from claimcheck.extract import canonicalize_npm, canonicalize_pypi
from claimcheck.pipeline import run_scan
from claimcheck.registry.oracle import MockRegistryOracle

# Categories whose verdict the scorer is expected to get exactly right.
CLEAN_CATEGORIES = {
    "wellknown_public", "owned_public", "internal_claimable",
    "internal_protected", "internal_taken_squat", "looks_internal_public",
    "hard_internal_no_signal_unclaimed",
}


def _label_key(raw, eco):
    norm = canonicalize_pypi(raw) if eco == "pypi" else canonicalize_npm(raw)
    return (eco, norm)


def _scan_org(tmp_path, seed=0):
    org = generate_org(seed=seed)
    repo = tmp_path / org.slug
    materialize_org(org, repo, public_fallback=True)
    oracle = MockRegistryOracle(org.registry_fixture())
    config = ClassifierConfig.from_dict(org.classifier_config_dict())
    result = run_scan(repo, oracle=oracle, classifier_config=config)
    findings = {f.name.key(): f for f in result.findings}
    return org, findings


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_clean_categories_verdicts_exact(tmp_path, seed):
    org, findings = _scan_org(tmp_path, seed=seed)
    for n in org.names:
        if n.category not in CLEAN_CATEGORIES:
            continue
        key = _label_key(n.raw, n.ecosystem)
        f = findings[key]
        expected = CATEGORIES[n.category][1]
        assert f.verdict == expected, (
            f"{n.raw} ({n.category}): expected {expected}, got {f.verdict}")


def test_no_false_positive_on_wellknown(tmp_path):
    org, findings = _scan_org(tmp_path)
    for n in org.names:
        if n.category != "wellknown_public":
            continue
        f = findings[_label_key(n.raw, n.ecosystem)]
        assert f.verdict.value == "SAFE", f"well-known {n.raw} flagged {f.verdict}"


def test_overall_verdict_accuracy_threshold(tmp_path):
    """Across all categories (including adversarial), accuracy stays high."""
    total = correct = 0
    for seed in (0, 1, 2):
        org, findings = _scan_org(tmp_path / f"s{seed}", seed=seed)
        for n in org.names:
            f = findings[_label_key(n.raw, n.ecosystem)]
            total += 1
            if f.verdict == CATEGORIES[n.category][1]:
                correct += 1
    accuracy = correct / total
    # Clean categories are exact; only the two intentional hard cases per org
    # are expected to miss, so overall accuracy should be ~0.9.
    assert accuracy >= 0.85, f"verdict accuracy {accuracy:.2%} below threshold"
