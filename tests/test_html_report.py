"""Tests for the HTML report renderer and the init-config CLI command."""

from claimcheck.classify.classifier import ClassifierConfig
from claimcheck.cli import main as cli_main
from claimcheck.data.generate import materialize_org
from claimcheck.data.synth_org import generate_org
from claimcheck.pipeline import run_scan
from claimcheck.registry.oracle import MockRegistryOracle
from claimcheck.report import render_html


def _scan(tmp_path, typosquats=True):
    org = generate_org(seed=0)
    repo = tmp_path / org.slug
    materialize_org(org, repo, public_fallback=True)
    oracle = MockRegistryOracle(org.registry_fixture())
    config = ClassifierConfig.from_dict(org.classifier_config_dict())
    return run_scan(repo, oracle=oracle, classifier_config=config,
                    detect_typosquats=typosquats)


def test_html_is_wellformed(tmp_path):
    html = render_html(_scan(tmp_path))
    assert html.startswith("<!DOCTYPE html>")
    assert html.rstrip().endswith("</html>")
    assert "ClaimCheck Exposure Report" in html
    assert "CLAIMABLE" in html
    # the typosquat section renders when present
    assert "Potential typosquats" in html


def test_html_escapes_content(tmp_path):
    html = render_html(_scan(tmp_path))
    # no raw unescaped angle brackets from data values leaking structure
    assert "<script>" not in html


def test_init_config_cli_writes_file(tmp_path, capsys):
    org = generate_org(seed=0)
    repo = tmp_path / org.slug
    materialize_org(org, repo, public_fallback=True)
    out = tmp_path / "scaffold.yml"
    rc = cli_main(["init-config", str(repo), "-o", str(out)])
    assert rc == 0
    text = out.read_text()
    assert "classifier:" in text
    assert "@acme" in text  # discovered private scope
    assert "acme-" in text  # suggested prefix
