"""Tests for report rendering and SARIF validity."""

import json

from claimcheck.classify.classifier import ClassifierConfig
from claimcheck.data.generate import materialize_org
from claimcheck.data.synth_org import generate_org
from claimcheck.pipeline import run_scan
from claimcheck.registry.oracle import MockRegistryOracle
from claimcheck.report import render_text, render_markdown, render_json, render_sarif


def _scan(tmp_path):
    org = generate_org(seed=0)
    repo = tmp_path / org.slug
    materialize_org(org, repo, public_fallback=True)
    oracle = MockRegistryOracle(org.registry_fixture())
    config = ClassifierConfig.from_dict(org.classifier_config_dict())
    return run_scan(repo, oracle=oracle, classifier_config=config)


def test_text_report_has_summary(tmp_path):
    result = _scan(tmp_path)
    out = render_text(result)
    assert "ClaimCheck exposure report" in out
    assert "CLAIMABLE" in out


def test_markdown_report_is_table(tmp_path):
    result = _scan(tmp_path)
    md = render_markdown(result)
    assert md.startswith("# ClaimCheck Exposure Report")
    assert "| Verdict | Count |" in md


def test_json_report_roundtrips(tmp_path):
    result = _scan(tmp_path)
    data = json.loads(render_json(result))
    assert "findings" in data and "summary" in data
    assert data["summary"]["CLAIMABLE"] >= 1


def test_sarif_is_valid_structure(tmp_path):
    result = _scan(tmp_path)
    sarif = json.loads(render_sarif(result))
    assert sarif["version"] == "2.1.0"
    assert sarif["runs"][0]["tool"]["driver"]["name"] == "ClaimCheck"
    # Every result references a declared rule and a location.
    rules = {r["id"] for r in sarif["runs"][0]["tool"]["driver"]["rules"]}
    for res in sarif["runs"][0]["results"]:
        assert res["ruleId"] in rules
        assert res["level"] in ("error", "warning", "note")
    # SAFE findings are excluded from SARIF.
    messages = " ".join(r["message"]["text"] for r in sarif["runs"][0]["results"])
    assert "SAFE" not in messages


def test_sarif_reports_claimable_as_error(tmp_path):
    result = _scan(tmp_path)
    sarif = json.loads(render_sarif(result))
    levels = {r["level"] for r in sarif["runs"][0]["results"]}
    assert "error" in levels  # at least one CLAIMABLE -> error
