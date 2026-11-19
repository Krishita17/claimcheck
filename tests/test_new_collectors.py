"""Tests for the pnpm, conda, and yarnrc.yml collectors."""

from claimcheck.collect.collectors import (
    parse_pnpm_lock,
    parse_environment_yml,
    parse_yarnrc_yml,
    _pnpm_name_from_key,
    RegistryConfig,
    collect_from_path,
)


def _norms(names):
    return {n.normalized for n in names}


def test_pnpm_name_from_key_variants():
    assert _pnpm_name_from_key("/lodash@4.17.21") == "lodash"
    assert _pnpm_name_from_key("@acme/billing@1.0.0") == "@acme/billing"
    assert _pnpm_name_from_key("/@acme/billing/1.0.0") == "@acme/billing"
    assert _pnpm_name_from_key("lodash@4.17.21") == "lodash"


def test_pnpm_lock_parsing():
    text = (
        "lockfileVersion: '9.0'\n"
        "packages:\n"
        "  '@acme/billing@1.0.0':\n"
        "    resolution: {integrity: xxx}\n"
        "  lodash@4.17.21:\n"
        "    resolution: {integrity: yyy}\n"
    )
    norms = _norms(parse_pnpm_lock(text, "pnpm-lock.yaml"))
    assert {"@acme/billing", "lodash"} <= norms


def test_environment_yml_extracts_pip_block():
    text = (
        "name: myenv\n"
        "dependencies:\n"
        "  - python=3.11\n"
        "  - numpy\n"
        "  - pip:\n"
        "      - requests\n"
        "      - acme-internal-secret==1.0\n"
    )
    norms = _norms(parse_environment_yml(text, "environment.yml"))
    assert "requests" in norms
    assert "acme-internal-secret" in norms
    # conda-only deps are NOT treated as PyPI names
    assert "numpy" not in norms


def test_yarnrc_yml_scope_mapping():
    cfg = RegistryConfig()
    text = (
        "npmScopes:\n"
        "  acme:\n"
        '    npmRegistryServer: "https://npm.acme.internal"\n'
        'npmRegistryServer: "https://registry.yarnpkg.com"\n'
    )
    parse_yarnrc_yml(text, cfg, ".yarnrc.yml")
    assert cfg.npm_scope_registries["@acme"] == "https://npm.acme.internal"
    assert "@acme" in cfg.private_npm_scopes()


def test_collect_from_path_picks_up_new_sources(tmp_path):
    (tmp_path / "pnpm-lock.yaml").write_text(
        "packages:\n  '@acme/x@1.0.0':\n    resolution: {integrity: z}\n")
    (tmp_path / "environment.yml").write_text(
        "dependencies:\n  - pip:\n      - acme-internal-y\n")
    (tmp_path / ".yarnrc.yml").write_text(
        'npmScopes:\n  acme:\n    npmRegistryServer: "https://npm.acme.internal"\n')
    result = collect_from_path(tmp_path)
    norms = _norms(result.names)
    assert "@acme/x" in norms
    assert "acme-internal-y" in norms
    assert "@acme" in result.config.private_npm_scopes()
