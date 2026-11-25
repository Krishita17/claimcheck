"""Test that the pipeline warms the cache via prefetch when the oracle offers it."""

from claimcheck.classify.classifier import ClassifierConfig
from claimcheck.data.generate import materialize_org
from claimcheck.data.synth_org import generate_org
from claimcheck.pipeline import run_scan
from claimcheck.registry.oracle import MockRegistryOracle
from claimcheck.schema import Ecosystem


class RecordingOracle(MockRegistryOracle):
    source_label = "mock"

    def __init__(self, data):
        super().__init__(data)
        self.prefetched: list[tuple[str, Ecosystem]] = []

    def prefetch(self, names):
        self.prefetched = list(names)


def test_pipeline_calls_prefetch(tmp_path):
    org = generate_org(seed=0)
    repo = tmp_path / org.slug
    materialize_org(org, repo, public_fallback=True)
    oracle = RecordingOracle(org.registry_fixture())
    config = ClassifierConfig.from_dict(org.classifier_config_dict())
    run_scan(repo, oracle=oracle, classifier_config=config)
    # every scanned name should have been handed to prefetch exactly once
    assert oracle.prefetched
    names = {n for n, _ in oracle.prefetched}
    assert "acme-internal-auth" in names
    assert len(oracle.prefetched) == len(set(oracle.prefetched))
