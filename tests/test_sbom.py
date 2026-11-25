"""Tests for the SBOM collector (CycloneDX + SPDX via package-URLs)."""

from claimcheck.collect.collectors import parse_purl, parse_sbom, collect_from_path
from claimcheck.schema import Ecosystem


def test_parse_purl_pypi_and_npm():
    assert parse_purl("pkg:pypi/requests@2.31.0") == (Ecosystem.PYPI, "requests")
    assert parse_purl("pkg:npm/lodash@4.17.21") == (Ecosystem.NPM, "lodash")
    assert parse_purl("pkg:npm/%40acme/billing@1.0.0") == (Ecosystem.NPM, "@acme/billing")
    assert parse_purl("pkg:cargo/serde@1.0") is None  # unsupported ecosystem
    assert parse_purl("not-a-purl") is None


def test_parse_cyclonedx():
    text = """
    {"bomFormat": "CycloneDX", "specVersion": "1.5", "components": [
      {"type": "library", "name": "requests", "purl": "pkg:pypi/requests@2.31.0"},
      {"type": "library", "name": "billing", "purl": "pkg:npm/%40acme/billing@1.0.0"},
      {"type": "library", "name": "nopurl"}
    ]}
    """
    norms = {n.normalized for n in parse_sbom(text, "bom.json")}
    assert "requests" in norms
    assert "@acme/billing" in norms


def test_parse_spdx():
    text = """
    {"spdxVersion": "SPDX-2.3", "packages": [
      {"name": "acme-internal-auth", "externalRefs": [
        {"referenceType": "purl", "referenceLocator": "pkg:pypi/acme-internal-auth@1.0"}]},
      {"name": "no-ref"}
    ]}
    """
    norms = {n.normalized for n in parse_sbom(text, "sbom.spdx.json")}
    assert "acme-internal-auth" in norms


def test_collect_picks_up_sbom_file(tmp_path):
    (tmp_path / "bom.json").write_text(
        '{"bomFormat":"CycloneDX","components":[{"name":"x","purl":"pkg:npm/%40acme/x@1"}]}')
    result = collect_from_path(tmp_path)
    assert "@acme/x" in {n.normalized for n in result.names}


def test_package_lock_not_misparsed_as_sbom(tmp_path):
    # package-lock.json also has a "packages" key but must NOT route to the SBOM
    # parser (it has no purls) — it should be parsed by the lockfile parser.
    (tmp_path / "package-lock.json").write_text(
        '{"packages":{"node_modules/lodash":{"version":"4.17.21"}}}')
    result = collect_from_path(tmp_path)
    assert "lodash" in {n.normalized for n in result.names}
