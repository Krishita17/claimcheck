"""ClaimCheck command-line interface.

Examples
--------
Offline scan of a bundled sample with its mock oracle::

    claimcheck scan samples/acme \\
        --oracle samples/acme.oracle.json \\
        --config samples/acme.config.json

Live scan against public PyPI/npm (requires ``requests``)::

    claimcheck scan /path/to/repo --live --config myorg.yml

CI gate — fail the build on any claimable internal name, emit SARIF::

    claimcheck scan . --oracle oracle.json --format sarif -o claimcheck.sarif \\
        --fail-on claimable
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from . import __version__
from .classify.classifier import ClassifierConfig
from .pipeline import run_scan
from .registry.oracle import load_oracle
from .report import render_text, render_markdown, render_json, render_sarif, render_html
from .schema import Verdict


def _load_config(path: Optional[str]) -> ClassifierConfig:
    if not path:
        return ClassifierConfig()
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix in (".yml", ".yaml"):
        try:
            import yaml
            data = yaml.safe_load(text) or {}
        except ImportError:
            print("warning: PyYAML not installed; treating config as JSON",
                  file=sys.stderr)
            data = json.loads(text)
    else:
        data = json.loads(text)
    # Allow the config to live under a 'classifier' key or at top level.
    if "classifier" in data:
        data = data["classifier"]
    return ClassifierConfig.from_dict(data)


_RENDERERS = {
    "table": render_text,
    "text": render_text,
    "markdown": render_markdown,
    "md": render_markdown,
    "json": render_json,
    "sarif": render_sarif,
    "html": render_html,
}

_FAIL_LEVELS = {
    "claimable": {Verdict.CLAIMABLE},
    "taken": {Verdict.CLAIMABLE, Verdict.TAKEN_NOT_YOURS},
    "any": {Verdict.CLAIMABLE, Verdict.TAKEN_NOT_YOURS, Verdict.PROTECTED},
    "none": set(),
}


def _cmd_scan(args: argparse.Namespace) -> int:
    mode = "live" if args.live else "mock"
    oracle = load_oracle(mode, oracle_file=args.oracle, cache_dir=args.cache_dir)
    config = _load_config(args.config)

    result = run_scan(args.target, oracle=oracle, classifier_config=config,
                      detect_typosquats=args.typosquat)

    renderer = _RENDERERS.get(args.format)
    if renderer is None:
        print(f"error: unknown format '{args.format}'", file=sys.stderr)
        return 1
    rendered = renderer(result)

    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
        print(f"wrote {args.format} report to {args.output}", file=sys.stderr)
    else:
        print(rendered)

    # CI guard.
    fail_on = _FAIL_LEVELS.get(args.fail_on, set())
    if fail_on:
        hits = [f for f in result.findings if f.verdict in fail_on]
        if hits:
            print(
                f"\nCI GUARD: {len(hits)} finding(s) at or above '{args.fail_on}' "
                f"-> failing (exit 2).", file=sys.stderr,
            )
            return 2
    return 0


def _cmd_generate(args: argparse.Namespace) -> int:
    from .data.generate import main as gen_main
    gen_main(["--out", args.out, "--seeds", *map(str, args.seeds)])
    return 0


def _cmd_init_config(args: argparse.Namespace) -> int:
    """Scaffold a starter classifier config from what a scan discovers."""
    from collections import Counter
    from .collect.collectors import collect_from_path
    from .data.wellknown import is_wellknown
    from .extract import merge_names

    collection = collect_from_path(args.target)
    names = merge_names(collection.names)
    scopes = sorted(collection.config.private_npm_scopes())

    # Suggest internal prefixes: the most common leading token (before the first
    # '-') among non-well-known, non-scoped names.
    prefix_counts: Counter[str] = Counter()
    for n in names:
        if n.scope or is_wellknown(n.normalized, n.ecosystem.value):
            continue
        head = n.normalized.split("/", 1)[-1].split("-", 1)[0]
        if len(head) >= 3:
            prefix_counts[f"{head}-"] += 1
    suggested = [p for p, c in prefix_counts.most_common(5) if c >= 2]

    def _yaml_list(items):
        return "\n".join(f'    - "{i}"' for i in items) if items else "    []"

    config_yaml = (
        "# ClaimCheck config scaffolded from a scan. REVIEW before use:\n"
        "# confirm these prefixes/scopes are really yours, and add owned public names.\n"
        "classifier:\n"
        "  internal_names: []\n"
        "  internal_prefixes:\n"
        f"{_yaml_list(suggested)}\n"
        "  private_scopes:\n"
        f"{_yaml_list(scopes)}\n"
        "  owned_public_names: []\n"
    )
    if args.output:
        Path(args.output).write_text(config_yaml, encoding="utf-8")
        print(f"wrote scaffolded config to {args.output}", file=sys.stderr)
        print(f"  discovered private scopes : {scopes or 'none'}", file=sys.stderr)
        print(f"  suggested prefixes        : {suggested or 'none'}", file=sys.stderr)
    else:
        print(config_yaml)
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="claimcheck",
        description="Defensive, read-only dependency-confusion exposure checker.",
    )
    ap.add_argument("--version", action="version", version=f"ClaimCheck {__version__}")
    sub = ap.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="scan a repo/manifest for exposure")
    scan.add_argument("target", help="repository directory or manifest/config file")
    scan.add_argument("--live", action="store_true",
                      help="probe live public PyPI/npm (read-only; needs requests)")
    scan.add_argument("--oracle", help="mock registry fixture JSON (mock mode)")
    scan.add_argument("--config", help="classifier config (YAML or JSON)")
    scan.add_argument("--format", default="table",
                      choices=sorted(_RENDERERS.keys()),
                      help="output format (default: table)")
    scan.add_argument("-o", "--output", help="write report to a file instead of stdout")
    scan.add_argument("--fail-on", default="none",
                      choices=sorted(_FAIL_LEVELS.keys()),
                      help="CI guard: exit 2 if findings at/above this level exist")
    scan.add_argument("--cache-dir", default=".claimcheck_cache",
                      help="cache directory for live lookups")
    scan.add_argument("--typosquat", action="store_true",
                      help="also probe confusable near-miss variants of internal names")
    scan.set_defaults(func=_cmd_scan)

    gen = sub.add_parser("generate-data", help="(re)generate synthetic samples")
    gen.add_argument("--out", default="samples")
    gen.add_argument("--seeds", nargs="*", type=int, default=[0, 1, 2])
    gen.set_defaults(func=_cmd_generate)

    init = sub.add_parser("init-config",
                          help="scaffold a classifier config from a repo scan")
    init.add_argument("target", help="repository directory or manifest/config file")
    init.add_argument("-o", "--output", help="write YAML config to a file")
    init.set_defaults(func=_cmd_init_config)

    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
