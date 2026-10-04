"""Manifest / config generator + mock-oracle fixture writer.

Materializes a :class:`~claimcheck.data.synth_org.SyntheticOrg` into a real,
scannable repository tree (``requirements.txt``, ``pyproject.toml``,
``package.json``, ``Dockerfile``, ``.npmrc``, ``pip.conf``, and a CI workflow),
plus sibling metadata files the scanner does NOT read:

* ``<slug>.oracle.json``  — the mock registry fixture (which names exist publicly)
* ``<slug>.labels.json``  — ground-truth classification + verdict per name
* ``<slug>.config.json``  — the classifier config (prefixes, private scope, owned)

Run as a module to (re)generate the bundled samples::

    python -m claimcheck.data.generate --out samples --seeds 0 1 2
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from .synth_org import SyntheticOrg, generate_org


def _group(org: SyntheticOrg):
    by_place = defaultdict(list)
    for n in org.names:
        by_place[(n.place, n.ecosystem)].append(n)
    return by_place


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def materialize_org(org: SyntheticOrg, repo_dir: Path, public_fallback: bool = True) -> None:
    by_place = _group(org)

    # --- requirements.txt (pip names placed here) ------------------------ #
    pip_req = [n for n in org.names if n.place == "requirements.txt" and n.ecosystem == "pypi"]
    if pip_req:
        lines = ["# Generated synthetic requirements for ClaimCheck evaluation",
                 "# (fictional org; names are operator-controlled placeholders)"]
        for i, n in enumerate(pip_req):
            lines.append(f"{n.raw}=={1 + i}.{i}.0")
        _write(repo_dir / "requirements.txt", "\n".join(lines) + "\n")

    # --- pyproject.toml (owned public pip packages) ---------------------- #
    pyproj = [n for n in org.names if n.place == "pyproject.toml" and n.ecosystem == "pypi"]
    deps = "\n".join(f'  "{n.raw}>=1.0",' for n in pyproj)
    _write(repo_dir / "pyproject.toml",
           "[project]\n"
           f'name = "{org.slug}-app"\n'
           'version = "0.1.0"\n'
           "dependencies = [\n"
           f"{deps}\n"
           "]\n")

    # --- package.json (npm names placed here) ---------------------------- #
    npm_pkg = [n for n in org.names if n.place == "package.json" and n.ecosystem == "npm"]
    dependencies = {n.raw: f"^{1 + i}.0.0" for i, n in enumerate(npm_pkg)}
    _write(repo_dir / "package.json",
           json.dumps({
               "name": f"{org.slug}-frontend",
               "version": "0.1.0",
               "dependencies": dependencies,
           }, indent=2) + "\n")

    # --- Dockerfile (install lines) -------------------------------------- #
    docker_names = [n for n in org.names if n.place == "Dockerfile"]
    docker_lines = ["FROM python:3.12-slim", "WORKDIR /app"]
    pip_docker = [n.raw for n in docker_names if n.ecosystem == "pypi"]
    npm_docker = [n.raw for n in docker_names if n.ecosystem == "npm"]
    if pip_docker:
        docker_lines.append("RUN pip install " + " ".join(pip_docker))
    if npm_docker:
        docker_lines.append("RUN npm install " + " ".join(npm_docker))
    docker_lines.append('CMD ["python", "-m", "app"]')
    _write(repo_dir / "Dockerfile", "\n".join(docker_lines) + "\n")

    # --- CI workflow (install lines) ------------------------------------- #
    ci_names = [n for n in org.names if n.place == "ci"]
    ci_pip = [n.raw for n in ci_names if n.ecosystem == "pypi"]
    ci_npm = [n.raw for n in ci_names if n.ecosystem == "npm"]
    steps = ["      - uses: actions/checkout@v4"]
    if ci_pip:
        steps.append(f"      - run: pip install {' '.join(ci_pip)}")
    if ci_npm:
        steps.append(f"      - run: npm install {' '.join(ci_npm)}")
    _write(repo_dir / ".github" / "workflows" / "ci.yml",
           "name: ci\n"
           "on: [push]\n"
           "jobs:\n"
           "  build:\n"
           "    runs-on: ubuntu-latest\n"
           "    steps:\n"
           + "\n".join(steps) + "\n")

    # --- .npmrc (reserve the private scope) ------------------------------ #
    _write(repo_dir / ".npmrc",
           f"{org.private_scope}:registry={org.private_npm_registry}\n"
           "always-auth=true\n")

    # --- pip.conf (fallback-enabled vs pinned) --------------------------- #
    if public_fallback:
        pip_conf = ("[global]\n"
                    f"index-url = {org.private_pip_index}\n"
                    "extra-index-url = https://pypi.org/simple/\n")
    else:
        pip_conf = ("[global]\n"
                    f"index-url = {org.private_pip_index}\n")
    _write(repo_dir / "pip.conf", pip_conf)


def write_metadata(org: SyntheticOrg, meta_dir: Path) -> None:
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / f"{org.slug}.oracle.json").write_text(
        json.dumps(org.registry_fixture(), indent=2), encoding="utf-8")
    (meta_dir / f"{org.slug}.labels.json").write_text(
        json.dumps(org.labels(), indent=2), encoding="utf-8")
    (meta_dir / f"{org.slug}.config.json").write_text(
        json.dumps(org.classifier_config_dict(), indent=2), encoding="utf-8")


def generate_sample(seed: int, out_dir: Path) -> SyntheticOrg:
    slug = "acme" if seed == 0 else f"acme{seed}"
    org = generate_org(seed=seed, slug=slug)
    repo_dir = out_dir / slug
    materialize_org(org, repo_dir, public_fallback=org.public_fallback)
    write_metadata(org, out_dir)
    return org


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate synthetic ClaimCheck samples.")
    ap.add_argument("--out", default="samples", help="output directory")
    ap.add_argument("--seeds", nargs="*", type=int, default=[0, 1, 2],
                    help="seeds; one labeled org per seed")
    args = ap.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    generated = []
    for seed in args.seeds:
        org = generate_sample(seed, out_dir)
        generated.append(org.slug)
        print(f"generated samples/{org.slug}/ ({len(org.names)} names) + metadata")
    print(f"done: {len(generated)} org(s) -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
