"""Reproducible benchmark: run ClaimCheck on every labeled synthetic org and
score it against ground truth.

Outputs (written to ``results/``):

* ``metrics.json``          — headline metrics (classification accuracy, verdict
  precision/recall/F1 per class, false-positive rate on public packages).
* ``findings.csv``          — every finding across all orgs (name, source,
  registry status, predicted + true verdict, correct?).
* ``confusion_verdict.csv`` — true-vs-predicted verdict confusion matrix.
* ``by_ecosystem.csv`` / ``by_source.csv`` — exposure breakdowns.

Usage::

    python experiments/benchmark.py --samples samples --out results
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

# Make src importable when run as a plain script.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from claimcheck.classify.classifier import ClassifierConfig  # noqa: E402
from claimcheck.extract import canonicalize_npm, canonicalize_pypi  # noqa: E402
from claimcheck.pipeline import run_scan  # noqa: E402
from claimcheck.registry.oracle import MockRegistryOracle  # noqa: E402
from claimcheck.schema import Classification, Verdict  # noqa: E402
from claimcheck.data.synth_org import PUBLIC_CATEGORIES  # noqa: E402


def _label_key(label: dict) -> tuple[str, str]:
    eco = label["ecosystem"]
    norm = canonicalize_pypi(label["raw"]) if eco == "pypi" else canonicalize_npm(label["raw"])
    return (eco, norm)


def discover_orgs(samples: Path) -> list[str]:
    return sorted(p.name[: -len(".labels.json")]
                  for p in samples.glob("*.labels.json"))


def run_org(samples: Path, slug: str):
    labels = json.loads((samples / f"{slug}.labels.json").read_text())
    oracle = MockRegistryOracle.from_file(samples / f"{slug}.oracle.json")
    config = ClassifierConfig.from_dict(
        json.loads((samples / f"{slug}.config.json").read_text()))
    result = run_scan(samples / slug, oracle=oracle, classifier_config=config)

    label_by_key = {_label_key(l): l for l in labels}
    rows = []
    for f in result.findings:
        key = f.name.key()
        label = label_by_key.get(key)
        if label is None:
            continue  # name not in ground truth (shouldn't happen for samples)
        rows.append({
            "org": slug,
            "ecosystem": f.name.ecosystem.value,
            "name": f.name.normalized,
            "source": f.name.sources[0].source_type.value if f.name.sources else "-",
            "category": label["category"],
            "registry": "taken" if (f.registry and f.registry.exists) else "unclaimed",
            "pred_classification": f.classification.value,
            "true_classification": label["true_classification"],
            "pred_verdict": f.verdict.value if f.verdict else "-",
            "true_verdict": label["true_verdict"],
            "verdict_correct": (f.verdict and f.verdict.value == label["true_verdict"]),
            "classification_correct": (
                f.classification.value == label["true_classification"]),
            "exploitable": bool(f.fallback and f.fallback.exploitable),
        })
    return rows


def prf(rows, field_pred, field_true, positive):
    tp = sum(1 for r in rows if r[field_pred] == positive and r[field_true] == positive)
    fp = sum(1 for r in rows if r[field_pred] == positive and r[field_true] != positive)
    fn = sum(1 for r in rows if r[field_pred] != positive and r[field_true] == positive)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {"precision": round(precision, 4), "recall": round(recall, 4),
            "f1": round(f1, 4), "support": tp + fn}


def compute_metrics(rows) -> dict:
    n = len(rows)
    cls_acc = sum(1 for r in rows if r["classification_correct"]) / n if n else 0.0
    ver_acc = sum(1 for r in rows if r["verdict_correct"]) / n if n else 0.0

    verdict_prf = {
        v.value: prf(rows, "pred_verdict", "true_verdict", v.value) for v in Verdict
    }
    class_prf = {
        c.value: prf(rows, "pred_classification", "true_classification", c.value)
        for c in (Classification.INTERNAL, Classification.EXTERNAL)
    }

    # False-positive rate on public packages: public names flagged non-SAFE.
    public = [r for r in rows if r["category"] in PUBLIC_CATEGORIES]
    public_fp = [r for r in public if r["pred_verdict"] != Verdict.SAFE.value]
    fp_rate = len(public_fp) / len(public) if public else 0.0

    by_eco = defaultdict(Counter)
    for r in rows:
        by_eco[r["ecosystem"]][r["pred_verdict"]] += 1
    by_source = defaultdict(Counter)
    for r in rows:
        by_source[r["source"]][r["pred_verdict"]] += 1

    exploitable = sum(1 for r in rows
                      if r["pred_verdict"] == Verdict.CLAIMABLE.value and r["exploitable"])
    protected = sum(1 for r in rows if r["pred_verdict"] == Verdict.PROTECTED.value)

    return {
        "n_names": n,
        "classification_accuracy": round(cls_acc, 4),
        "verdict_accuracy": round(ver_acc, 4),
        "verdict_prf": verdict_prf,
        "classification_prf": class_prf,
        "public_false_positive_rate": round(fp_rate, 4),
        "public_false_positives": [f"{r['ecosystem']}:{r['name']}" for r in public_fp],
        "verdict_distribution": dict(Counter(r["pred_verdict"] for r in rows)),
        "by_ecosystem": {k: dict(v) for k, v in by_eco.items()},
        "by_source": {k: dict(v) for k, v in by_source.items()},
        "fallback_impact": {"claimable_exploitable": exploitable, "protected": protected},
    }


def write_csvs(rows, metrics, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)

    with (out / "findings.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # Verdict confusion matrix.
    verdicts = [v.value for v in Verdict]
    conf = {t: Counter() for t in verdicts}
    for r in rows:
        conf[r["true_verdict"]][r["pred_verdict"]] += 1
    with (out / "confusion_verdict.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["true\\pred", *verdicts])
        for t in verdicts:
            w.writerow([t, *(conf[t][p] for p in verdicts)])

    with (out / "by_ecosystem.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ecosystem", *verdicts])
        for eco, counts in metrics["by_ecosystem"].items():
            w.writerow([eco, *(counts.get(v, 0) for v in verdicts)])

    with (out / "by_source.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["source", *verdicts])
        for src, counts in metrics["by_source"].items():
            w.writerow([src, *(counts.get(v, 0) for v in verdicts)])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="ClaimCheck benchmark against labeled orgs.")
    ap.add_argument("--samples", default="samples")
    ap.add_argument("--out", default="results")
    args = ap.parse_args(argv)

    samples = Path(args.samples)
    orgs = discover_orgs(samples)
    if not orgs:
        print(f"no labeled orgs found in {samples} (run generate-data first)",
              file=sys.stderr)
        return 1

    all_rows = []
    for slug in orgs:
        all_rows.extend(run_org(samples, slug))

    metrics = compute_metrics(all_rows)
    metrics["orgs"] = orgs
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    write_csvs(all_rows, metrics, out)

    print(f"orgs scanned        : {len(orgs)}  ({', '.join(orgs)})")
    print(f"names analyzed      : {metrics['n_names']}")
    print(f"classification acc. : {metrics['classification_accuracy']:.1%}")
    print(f"verdict accuracy    : {metrics['verdict_accuracy']:.1%}")
    print(f"public FP rate      : {metrics['public_false_positive_rate']:.1%}")
    print(f"verdict distribution: {metrics['verdict_distribution']}")
    print(f"metrics + CSVs      -> {out}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
