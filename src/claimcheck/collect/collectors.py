"""Source collectors.

Finding the names is half the battle in dependency confusion: internal names
hide in manifests, lockfiles, registry-scope configs, CI files, and Dockerfiles.
Reading *more* sources means catching *more* exposure, so ClaimCheck ships a
collector for each.

Each collector is pure (string/path in, structured data out) and therefore
trivially testable and mockable. The top-level :func:`collect_from_path` walks a
directory, dispatches by filename, and returns a :class:`CollectionResult`
holding every discovered name plus the registry configuration (``.npmrc`` scope
mappings and ``pip`` index settings) needed by the classifier and the
fallback analyzer downstream.
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..extract import make_name
from ..schema import DependencyName, Ecosystem, SourceRef, SourceType

# Filenames (and glob-ish suffixes) the walker recognizes.
DEFAULT_FILENAMES = {
    "requirements.txt": SourceType.REQUIREMENTS_TXT,
    "pyproject.toml": SourceType.PYPROJECT_TOML,
    "setup.py": SourceType.SETUP_PY,
    "setup.cfg": SourceType.SETUP_CFG,
    "Pipfile": SourceType.PIPFILE,
    "poetry.lock": SourceType.POETRY_LOCK,
    "package.json": SourceType.PACKAGE_JSON,
    "package-lock.json": SourceType.PACKAGE_LOCK_JSON,
    "yarn.lock": SourceType.YARN_LOCK,
    ".npmrc": SourceType.NPMRC,
    "pip.conf": SourceType.PIP_CONF,
    "Dockerfile": SourceType.DOCKERFILE,
}

# Directories we never descend into.
_SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build"}


# --------------------------------------------------------------------------- #
# Result containers
# --------------------------------------------------------------------------- #
@dataclass
class RegistryConfig:
    """Registry configuration discovered from ``.npmrc`` / ``pip.conf``."""

    # npm: scope ("@acme") -> registry URL it is pinned to.
    npm_scope_registries: dict[str, str] = field(default_factory=dict)
    npm_default_registry: Optional[str] = None
    # pip: the primary index and any extra indexes.
    pip_index_url: Optional[str] = None
    pip_extra_index_urls: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)

    def private_npm_scopes(self) -> set[str]:
        """Scopes mapped to a non-public (private) registry."""
        return {
            scope
            for scope, url in self.npm_scope_registries.items()
            if not _is_public_npm_registry(url)
        }


@dataclass
class CollectionResult:
    names: list[DependencyName] = field(default_factory=list)
    config: RegistryConfig = field(default_factory=RegistryConfig)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
_PUBLIC_NPM = ("registry.npmjs.org", "registry.yarnpkg.com")
_PUBLIC_PYPI = ("pypi.org", "pypi.python.org", "files.pythonhosted.org")


def _is_public_npm_registry(url: str) -> bool:
    return any(h in url for h in _PUBLIC_NPM)


def _is_public_pypi_index(url: str) -> bool:
    return any(h in url for h in _PUBLIC_PYPI)


# A requirements specifier: capture the leading name, drop everything from the
# first version operator / extras bracket / marker / whitespace.
_REQ_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


# --------------------------------------------------------------------------- #
# Python collectors
# --------------------------------------------------------------------------- #
def parse_requirements(text: str, path: str) -> list[DependencyName]:
    names: list[DependencyName] = []
    for i, line in enumerate(text.splitlines(), start=1):
        line = line.split(" #", 1)[0].rstrip()  # strip trailing comment
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "-", "--")):
            continue
        # Drop environment markers and URLs.
        stripped = stripped.split(";", 1)[0].strip()
        if "@" in stripped and "://" in stripped:  # name @ url form
            stripped = stripped.split("@", 1)[0].strip()
        m = _REQ_NAME.match(stripped)
        if not m:
            continue
        ref = SourceRef(path, i, SourceType.REQUIREMENTS_TXT)
        dn = make_name(m.group(1), Ecosystem.PYPI, ref)
        if dn:
            names.append(dn)
    return names


def parse_pyproject(text: str, path: str) -> list[DependencyName]:
    names: list[DependencyName] = []
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return names
    ref = SourceRef(path, 1, SourceType.PYPROJECT_TOML)

    def add_specs(specs):
        for spec in specs or []:
            m = _REQ_NAME.match(str(spec))
            if m:
                dn = make_name(m.group(1), Ecosystem.PYPI, ref)
                if dn:
                    names.append(dn)

    project = data.get("project", {})
    add_specs(project.get("dependencies"))
    for extra in (project.get("optional-dependencies") or {}).values():
        add_specs(extra)

    # Poetry style
    poetry = data.get("tool", {}).get("poetry", {})
    for group_key in ("dependencies", "dev-dependencies"):
        for name in (poetry.get(group_key) or {}):
            if name.lower() == "python":
                continue
            dn = make_name(name, Ecosystem.PYPI, ref)
            if dn:
                names.append(dn)
    return names


def parse_setup_py(text: str, path: str) -> list[DependencyName]:
    names: list[DependencyName] = []
    ref = SourceRef(path, 1, SourceType.SETUP_PY)
    # Best-effort: find install_requires / extras_require list contents.
    for block in re.findall(r"(?:install_requires|extras_require)\s*=\s*(\[.*?\]|\{.*?\})", text, re.DOTALL):
        for quoted in re.findall(r"""['"]([^'"]+)['"]""", block):
            m = _REQ_NAME.match(quoted)
            if m:
                dn = make_name(m.group(1), Ecosystem.PYPI, ref)
                if dn:
                    names.append(dn)
    return names


def parse_setup_cfg(text: str, path: str) -> list[DependencyName]:
    names: list[DependencyName] = []
    ref = SourceRef(path, 1, SourceType.SETUP_CFG)
    in_requires = False
    for line in text.splitlines():
        if re.match(r"\s*(install_requires|tests_require)\s*=", line):
            in_requires = True
            tail = line.split("=", 1)[1].strip()
            if tail:
                m = _REQ_NAME.match(tail)
                if m:
                    dn = make_name(m.group(1), Ecosystem.PYPI, ref)
                    if dn:
                        names.append(dn)
            continue
        if in_requires:
            if line and not line[0].isspace():
                in_requires = False
                continue
            m = _REQ_NAME.match(line.strip())
            if m:
                dn = make_name(m.group(1), Ecosystem.PYPI, ref)
                if dn:
                    names.append(dn)
    return names


def parse_pipfile(text: str, path: str) -> list[DependencyName]:
    names: list[DependencyName] = []
    ref = SourceRef(path, 1, SourceType.PIPFILE)
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return names
    for section in ("packages", "dev-packages"):
        for name in (data.get(section) or {}):
            dn = make_name(name, Ecosystem.PYPI, ref)
            if dn:
                names.append(dn)
    return names


def parse_poetry_lock(text: str, path: str) -> list[DependencyName]:
    names: list[DependencyName] = []
    ref = SourceRef(path, 1, SourceType.POETRY_LOCK)
    try:
        data = tomllib.loads(text)
        for pkg in data.get("package", []):
            name = pkg.get("name")
            if name:
                dn = make_name(name, Ecosystem.PYPI, ref)
                if dn:
                    names.append(dn)
    except tomllib.TOMLDecodeError:
        # Fall back to a line scan for malformed locks.
        for i, line in enumerate(text.splitlines(), start=1):
            m = re.match(r'\s*name\s*=\s*"([^"]+)"', line)
            if m:
                dn = make_name(m.group(1), Ecosystem.PYPI,
                               SourceRef(path, i, SourceType.POETRY_LOCK))
                if dn:
                    names.append(dn)
    return names


# --------------------------------------------------------------------------- #
# npm collectors
# --------------------------------------------------------------------------- #
_NPM_DEP_SECTIONS = (
    "dependencies",
    "devDependencies",
    "optionalDependencies",
    "peerDependencies",
)


def parse_package_json(text: str, path: str) -> list[DependencyName]:
    names: list[DependencyName] = []
    ref = SourceRef(path, 1, SourceType.PACKAGE_JSON)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return names
    for section in _NPM_DEP_SECTIONS:
        for name in (data.get(section) or {}):
            dn = make_name(name, Ecosystem.NPM, ref)
            if dn:
                names.append(dn)
    return names


def parse_package_lock(text: str, path: str) -> list[DependencyName]:
    names: list[DependencyName] = []
    ref = SourceRef(path, 1, SourceType.PACKAGE_LOCK_JSON)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return names

    # lockfile v1: top-level "dependencies"
    for name in (data.get("dependencies") or {}):
        dn = make_name(name, Ecosystem.NPM, ref)
        if dn:
            names.append(dn)
    # lockfile v2/v3: "packages" keyed by node_modules path
    for pkgpath in (data.get("packages") or {}):
        if not pkgpath:
            continue
        # e.g. "node_modules/@acme/billing" -> "@acme/billing"
        marker = "node_modules/"
        idx = pkgpath.rfind(marker)
        name = pkgpath[idx + len(marker):] if idx != -1 else pkgpath
        if name:
            dn = make_name(name, Ecosystem.NPM, ref)
            if dn:
                names.append(dn)
    return names


_YARN_ENTRY = re.compile(r'^"?((?:@[^/]+/)?[^@"\s]+)@')


def parse_yarn_lock(text: str, path: str) -> list[DependencyName]:
    names: list[DependencyName] = []
    for i, line in enumerate(text.splitlines(), start=1):
        if not line or line[0].isspace() or line.startswith("#"):
            continue
        # A yarn entry header may list several specs comma-separated.
        for spec in line.rstrip(":").split(","):
            m = _YARN_ENTRY.match(spec.strip())
            if m:
                dn = make_name(m.group(1), Ecosystem.NPM,
                               SourceRef(path, i, SourceType.YARN_LOCK))
                if dn:
                    names.append(dn)
    return names


# --------------------------------------------------------------------------- #
# Registry config collectors (.npmrc / pip.conf)
# --------------------------------------------------------------------------- #
def parse_npmrc(text: str, config: RegistryConfig, path: str) -> None:
    for i, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        # Scoped registry: @acme:registry=https://npm.internal/
        m = re.match(r"(@[^:=\s]+):registry\s*=\s*(\S+)", line)
        if m:
            config.npm_scope_registries[m.group(1).lower()] = m.group(2)
            config.evidence.append(f"{path}:{i} scope {m.group(1)} -> {m.group(2)}")
            continue
        m = re.match(r"registry\s*=\s*(\S+)", line)
        if m:
            config.npm_default_registry = m.group(1)
            config.evidence.append(f"{path}:{i} default registry -> {m.group(1)}")


def parse_pip_conf(text: str, config: RegistryConfig, path: str) -> None:
    for i, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith(("#", ";", "[")):
            continue
        m = re.match(r"(extra-index-url|index-url)\s*=\s*(.+)", line)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        urls = val.split()
        if key == "index-url":
            config.pip_index_url = urls[0] if urls else val
            config.evidence.append(f"{path}:{i} index-url -> {config.pip_index_url}")
            for extra in urls[1:]:
                config.pip_extra_index_urls.append(extra)
        else:
            config.pip_extra_index_urls.extend(urls)
            config.evidence.append(f"{path}:{i} extra-index-url -> {', '.join(urls)}")


# --------------------------------------------------------------------------- #
# Dockerfile / CI collectors
# --------------------------------------------------------------------------- #
_PIP_INSTALL = re.compile(r"pip3?\s+install\s+(.+)")
_NPM_INSTALL = re.compile(r"(?:npm|pnpm)\s+(?:install|i|add)\s+(.+)")
_YARN_ADD = re.compile(r"yarn\s+add\s+(.+)")


def _tokens_after_install(tail: str) -> list[str]:
    """Split an install command tail into package tokens, dropping flags."""
    tokens = []
    for tok in re.split(r"\s+", tail.strip()):
        tok = tok.strip().rstrip("\\").strip()
        if not tok or tok.startswith("-"):
            continue
        if tok in ("&&", "||", "|", ";"):
            break
        tokens.append(tok)
    return tokens


def _parse_install_lines(text: str, path: str, source_type: SourceType) -> list[DependencyName]:
    names: list[DependencyName] = []
    for i, line in enumerate(text.splitlines(), start=1):
        for rx, eco in ((_PIP_INSTALL, Ecosystem.PYPI),
                        (_NPM_INSTALL, Ecosystem.NPM),
                        (_YARN_ADD, Ecosystem.NPM)):
            m = rx.search(line)
            if not m:
                continue
            for tok in _tokens_after_install(m.group(1)):
                # strip pip version pins
                tok = re.split(r"[=<>!~@\[]", tok, maxsplit=1)[0] if eco is Ecosystem.PYPI else tok
                dn = make_name(tok, eco, SourceRef(path, i, source_type))
                if dn:
                    names.append(dn)
    return names


def parse_dockerfile(text: str, path: str) -> list[DependencyName]:
    return _parse_install_lines(text, path, SourceType.DOCKERFILE)


def parse_ci_file(text: str, path: str) -> list[DependencyName]:
    return _parse_install_lines(text, path, SourceType.CI_FILE)


# --------------------------------------------------------------------------- #
# Dispatch
# --------------------------------------------------------------------------- #
_PY_NAME_PARSERS = {
    SourceType.REQUIREMENTS_TXT: parse_requirements,
    SourceType.PYPROJECT_TOML: parse_pyproject,
    SourceType.SETUP_PY: parse_setup_py,
    SourceType.SETUP_CFG: parse_setup_cfg,
    SourceType.PIPFILE: parse_pipfile,
    SourceType.POETRY_LOCK: parse_poetry_lock,
    SourceType.PACKAGE_JSON: parse_package_json,
    SourceType.PACKAGE_LOCK_JSON: parse_package_lock,
    SourceType.YARN_LOCK: parse_yarn_lock,
}


def _looks_like_ci(path: Path) -> bool:
    parts = {p.lower() for p in path.parts}
    if ".github" in parts or ".gitlab-ci.yml" == path.name.lower():
        return True
    if "workflows" in parts and path.suffix.lower() in (".yml", ".yaml"):
        return True
    if path.name.lower() in (".gitlab-ci.yml", "azure-pipelines.yml", ".travis.yml"):
        return True
    return False


def collect_from_file(path: Path, config: RegistryConfig) -> list[DependencyName]:
    """Collect names from a single file, updating ``config`` in place."""
    text = _read(path)
    if not text:
        return []
    rel = str(path)
    name = path.name

    if name == ".npmrc":
        parse_npmrc(text, config, rel)
        return []
    if name == "pip.conf" or name == "pip.ini":
        parse_pip_conf(text, config, rel)
        return []

    source_type = DEFAULT_FILENAMES.get(name)
    if source_type and source_type in _PY_NAME_PARSERS:
        return _PY_NAME_PARSERS[source_type](text, rel)
    if name == "Dockerfile" or name.startswith("Dockerfile"):
        return parse_dockerfile(text, rel)
    if _looks_like_ci(path):
        return parse_ci_file(text, rel)
    return []


def collect_from_path(root: str | Path) -> CollectionResult:
    """Walk ``root`` (file or directory) and collect all names + registry config."""
    root = Path(root)
    result = CollectionResult()

    paths: list[Path]
    if root.is_file():
        paths = [root]
    else:
        paths = []
        for p in root.rglob("*"):
            if p.is_dir():
                continue
            if any(part in _SKIP_DIRS for part in p.parts):
                continue
            paths.append(p)

    for p in paths:
        name = p.name
        is_known = (
            name in DEFAULT_FILENAMES
            or name in ("pip.ini",)
            or name.startswith("Dockerfile")
            or _looks_like_ci(p)
        )
        if not is_known:
            continue
        result.names.extend(collect_from_file(p, result.config))

    return result
