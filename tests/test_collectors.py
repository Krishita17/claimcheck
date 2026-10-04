"""Tests for the source collectors across ecosystems and source types."""

from claimcheck.collect.collectors import (
    parse_requirements,
    parse_pyproject,
    parse_package_json,
    parse_package_lock,
    parse_yarn_lock,
    parse_dockerfile,
    parse_npmrc,
    parse_pip_conf,
    collect_from_path,
    RegistryConfig,
)
from claimcheck.schema import Ecosystem


def _norms(names):
    return {n.normalized for n in names}


def test_requirements_parsing():
    text = (
        "# comment\n"
        "requests==2.31.0\n"
        "acme-internal-auth>=1.0,<2  # internal\n"
        "flask[async]==3.0\n"
        "-e .\n"
        "-r other.txt\n"
        "pkg ; python_version < '3.9'\n"
    )
    names = parse_requirements(text, "requirements.txt")
    norms = _norms(names)
    assert "requests" in norms
    assert "acme-internal-auth" in norms
    assert "flask" in norms
    assert "pkg" in norms
    # options are not names
    assert "-e" not in norms


def test_pyproject_parsing():
    text = (
        '[project]\n'
        'name = "app"\n'
        'dependencies = ["requests>=2", "acme-sdk==1.2.3"]\n'
        '[project.optional-dependencies]\n'
        'dev = ["pytest"]\n'
    )
    norms = _norms(parse_pyproject(text, "pyproject.toml"))
    assert {"requests", "acme-sdk", "pytest"} <= norms


def test_package_json_parsing():
    text = (
        '{"name":"f","dependencies":{"lodash":"^4","@acme/billing":"1.0.0"},'
        '"devDependencies":{"jest":"^29"}}'
    )
    names = parse_package_json(text, "package.json")
    norms = _norms(names)
    assert {"lodash", "@acme/billing", "jest"} <= norms
    scoped = [n for n in names if n.normalized == "@acme/billing"][0]
    assert scoped.scope == "@acme"
    assert scoped.ecosystem is Ecosystem.NPM


def test_package_lock_v3_parsing():
    text = (
        '{"packages":{"":{"name":"root"},'
        '"node_modules/@acme/secrets":{"version":"1.0.0"},'
        '"node_modules/lodash":{"version":"4.17.21"}}}'
    )
    norms = _norms(parse_package_lock(text, "package-lock.json"))
    assert "@acme/secrets" in norms
    assert "lodash" in norms


def test_yarn_lock_parsing():
    text = (
        '"@acme/billing@^1.0.0":\n'
        '  version "1.0.0"\n'
        'lodash@^4.17.0:\n'
        '  version "4.17.21"\n'
    )
    norms = _norms(parse_yarn_lock(text, "yarn.lock"))
    assert "@acme/billing" in norms
    assert "lodash" in norms


def test_dockerfile_install_lines():
    text = (
        "FROM python:3.12\n"
        "RUN pip install acme-internal-billing requests==2.31.0\n"
        "RUN npm install @acme/ui chalk\n"
    )
    norms = _norms(parse_dockerfile(text, "Dockerfile"))
    assert {"acme-internal-billing", "requests", "@acme/ui", "chalk"} <= norms


def test_npmrc_scope_and_pip_conf():
    cfg = RegistryConfig()
    parse_npmrc("@acme:registry=https://npm.acme.internal/\nregistry=https://npm.internal/",
                cfg, ".npmrc")
    assert cfg.npm_scope_registries["@acme"] == "https://npm.acme.internal/"
    assert "@acme" in cfg.private_npm_scopes()

    parse_pip_conf("[global]\nindex-url = https://pypi.acme.internal/simple/\n"
                   "extra-index-url = https://pypi.org/simple/", cfg, "pip.conf")
    assert cfg.pip_index_url == "https://pypi.acme.internal/simple/"
    assert any("pypi.org" in u for u in cfg.pip_extra_index_urls)


def test_collect_from_path_walks_tree(tmp_path):
    (tmp_path / "requirements.txt").write_text("acme-auth==1.0\nrequests\n")
    (tmp_path / "package.json").write_text('{"dependencies":{"@acme/x":"1"}}')
    (tmp_path / ".npmrc").write_text("@acme:registry=https://npm.acme.internal/\n")
    result = collect_from_path(tmp_path)
    norms = _norms(result.names)
    assert {"acme-auth", "requests", "@acme/x"} <= norms
    assert "@acme" in result.config.private_npm_scopes()
