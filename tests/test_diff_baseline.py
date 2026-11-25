"""Tests for the scan-diff regression gate and baseline suppression."""

import json

from claimcheck.baseline import write_baseline, load_baseline, apply_baseline, finding_key
from claimcheck.classify.classifier import ClassifierConfig
from claimcheck.data.generate import materialize_org
from claimcheck.data.synth_org import generate_org
from claimcheck.pipeline import run_scan
from claimcheck.registry.oracle import MockRegistryOracle
from claimcheck.report import render_json
from claimcheck.report.diff import diff_reports
from claimcheck.schema import Verdict


def _scan(tmp_path, seed=0):
    org = generate_org(seed=seed)
    repo = tmp_path / org.slug
    materialize_org(org, repo, public_fallback=True)
    oracle = MockRegistryOracle(org.registry_fixture())
    config = ClassifierConfig.from_dict(org.classifier_config_dict())
    return run_scan(repo, oracle=oracle, classifier_config=config)


def test_diff_detects_new_exposure(tmp_path):
    result = _scan(tmp_path)
    base = json.loads(render_json(result))
    pr = json.loads(render_json(result))
    pr["findings"].append({
        "name": {"normalized": "acme-brand-new", "ecosystem": "pypi", "scope": None,
                 "sources": []},
        "verdict": "CLAIMABLE",
    })
    d = diff_reports(base, pr)
    assert d["is_regression"] is True
    keys = [k for k, _, _ in d["new_exposures"]]
    assert "pypi:acme-brand-new" in keys


def test_diff_no_regression_when_identical(tmp_path):
    result = _scan(tmp_path)
    base = json.loads(render_json(result))
    d = diff_reports(base, json.loads(json.dumps(base)))
    assert d["is_regression"] is False


def test_diff_flags_worsened_verdict(tmp_path):
    result = _scan(tmp_path)
    base = json.loads(render_json(result))
    pr = json.loads(json.dumps(base))
    # flip one SAFE finding to CLAIMABLE
    for f in pr["findings"]:
        if f.get("verdict") == "SAFE":
            f["verdict"] = "CLAIMABLE"
            break
    d = diff_reports(base, pr)
    assert d["is_regression"] is True
    assert d["worsened"]


def test_baseline_roundtrip_and_suppression(tmp_path):
    result = _scan(tmp_path)
    path = tmp_path / "baseline.json"
    n = write_baseline(result, path)
    assert n > 0
    baseline = load_baseline(path)
    remaining = apply_baseline(result, baseline)
    # every non-SAFE finding was accepted, so only SAFE findings remain
    assert all(f.verdict is Verdict.SAFE for f in remaining)


def test_baseline_lets_new_finding_through(tmp_path):
    result = _scan(tmp_path)
    baseline = {finding_key(f) for f in result.findings if f.verdict is not Verdict.SAFE}
    # drop one accepted key to simulate a brand-new exposure not in the baseline
    claimable = [f for f in result.findings if f.verdict is Verdict.CLAIMABLE]
    baseline.discard(finding_key(claimable[0]))
    remaining = apply_baseline(result, baseline)
    assert claimable[0] in remaining
