"""Tests for the internal/external classifier."""

from claimcheck.classify.classifier import Classifier, ClassifierConfig
from claimcheck.extract import make_name
from claimcheck.schema import Classification, Ecosystem, RegistryStatus


def _name(raw, eco=Ecosystem.PYPI):
    return make_name(raw, eco)


def test_wellknown_is_external():
    c = Classifier(ClassifierConfig())
    cls, _ = c.classify(_name("requests"))
    assert cls is Classification.EXTERNAL
    cls, _ = c.classify(_name("lodash", Ecosystem.NPM))
    assert cls is Classification.EXTERNAL


def test_prefix_is_internal():
    c = Classifier(ClassifierConfig(internal_prefixes=["acme-"]))
    cls, reason = c.classify(_name("acme-secret-service"))
    assert cls is Classification.INTERNAL
    assert "prefix" in reason


def test_private_scope_is_internal():
    c = Classifier(ClassifierConfig(private_scopes={"@acme"}))
    cls, _ = c.classify(_name("@acme/billing", Ecosystem.NPM))
    assert cls is Classification.INTERNAL


def test_discovered_scope_merged():
    c = Classifier(ClassifierConfig(), discovered_private_scopes={"@acme"})
    cls, _ = c.classify(_name("@acme/x", Ecosystem.NPM))
    assert cls is Classification.INTERNAL


def test_owned_public_beats_prefix():
    c = Classifier(ClassifierConfig(internal_prefixes=["acme-"],
                                    owned_public_names={"acme-sdk"}))
    cls, reason = c.classify(_name("acme-sdk"))
    assert cls is Classification.EXTERNAL
    assert "owned" in reason


def test_registry_heuristic_marks_absent_as_internal():
    c = Classifier(ClassifierConfig())
    absent = RegistryStatus(exists=False)
    cls, reason = c.classify_with_registry(_name("mystery-internal-lib"), absent)
    assert cls is Classification.INTERNAL
    assert "absent" in reason


def test_registry_heuristic_marks_present_as_external():
    c = Classifier(ClassifierConfig())
    present = RegistryStatus(exists=True, owner="someone")
    cls, _ = c.classify_with_registry(_name("some-public-lib"), present)
    assert cls is Classification.EXTERNAL
