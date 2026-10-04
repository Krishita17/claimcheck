"""End-to-end scan pipeline.

repo / manifests
      -> collect (source collectors + registry config)
      -> extract/normalize + dedup
      -> classify (internal vs external)
      -> probe (read-only registry oracle)
      -> fallback (config fallback analysis)
      -> score (verdict engine)
      -> ScanResult

This is the single entry point used by the CLI, the benchmark, and the tests.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .classify.classifier import Classifier, ClassifierConfig
from .collect.collectors import collect_from_path, CollectionResult
from .extract import merge_names
from .fallback.analyzer import FallbackAnalyzer
from .registry.oracle import RegistryOracle, MockRegistryOracle
from .score.scorer import Scorer
from .schema import ScanResult


def run_scan(
    target: str | Path,
    oracle: Optional[RegistryOracle] = None,
    classifier_config: Optional[ClassifierConfig] = None,
    collection: Optional[CollectionResult] = None,
) -> ScanResult:
    """Run the full ClaimCheck pipeline against ``target``.

    Parameters
    ----------
    target:
        A repository directory or a single manifest/config file.
    oracle:
        Read-only registry probe. Defaults to an empty :class:`MockRegistryOracle`
        (everything looks unclaimed) if not supplied.
    classifier_config:
        Operator hints about which names are internal / owned.
    collection:
        Pre-computed collection result (used by tests); if omitted, the target
        is walked and collected.
    """
    oracle = oracle or MockRegistryOracle()
    classifier_config = classifier_config or ClassifierConfig()

    if collection is None:
        collection = collect_from_path(target)

    # Merge discovered private scopes into the classifier so .npmrc-reserved
    # scopes count as internal signals automatically.
    discovered_private_scopes = collection.config.private_npm_scopes()
    classifier = Classifier(classifier_config, discovered_private_scopes)
    scorer = Scorer(classifier=classifier)
    fallback = FallbackAnalyzer(collection.config)

    names = merge_names(collection.names)

    result = ScanResult(target=str(target), mode=oracle.source_label)
    for name in names:
        status = oracle.lookup(name.normalized, name.ecosystem)
        fb = fallback.analyze(name)
        finding = scorer.score(name, status, fb)
        result.findings.append(finding)
    return result
