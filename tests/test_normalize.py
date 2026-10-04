"""Tests for name extraction and PEP 503 / npm normalization."""

from claimcheck.extract import (
    canonicalize_pypi,
    canonicalize_npm,
    split_npm_scope,
    make_name,
    merge_names,
)
from claimcheck.schema import Ecosystem, SourceRef, SourceType


def test_pep503_canonicalization():
    assert canonicalize_pypi("Acme_Internal.Auth") == "acme-internal-auth"
    assert canonicalize_pypi("Flask") == "flask"
    assert canonicalize_pypi("ruamel.yaml") == "ruamel-yaml"
    assert canonicalize_pypi("a--b__c") == "a-b-c"


def test_pep503_equivalence_classes_match():
    variants = ["acme-internal-auth", "acme_internal_auth", "Acme.Internal.Auth"]
    canon = {canonicalize_pypi(v) for v in variants}
    assert canon == {"acme-internal-auth"}


def test_npm_scope_split():
    assert split_npm_scope("@acme/billing") == ("@acme", "billing")
    assert split_npm_scope("lodash") == (None, "lodash")
    assert canonicalize_npm("@Acme/Billing") == "@acme/billing"


def test_make_name_rejects_non_names():
    assert make_name("", Ecosystem.PYPI) is None
    assert make_name("-e", Ecosystem.PYPI) is None
    assert make_name("https://example.com/x.tgz", Ecosystem.NPM) is None
    assert make_name("git+https://x", Ecosystem.PYPI) is None
    assert make_name("${VAR}", Ecosystem.NPM) is None


def test_make_name_sets_scope():
    dn = make_name("@acme/billing", Ecosystem.NPM)
    assert dn is not None
    assert dn.scope == "@acme"
    assert dn.normalized == "@acme/billing"


def test_merge_names_unions_sources():
    a = make_name("acme-auth", Ecosystem.PYPI,
                  SourceRef("req.txt", 1, SourceType.REQUIREMENTS_TXT))
    b = make_name("Acme_Auth", Ecosystem.PYPI,
                  SourceRef("Dockerfile", 9, SourceType.DOCKERFILE))
    merged = merge_names([a, b])
    assert len(merged) == 1
    assert len(merged[0].sources) == 2
    assert merged[0].normalized == "acme-auth"
