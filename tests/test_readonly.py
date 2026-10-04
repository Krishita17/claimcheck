"""Safety test: ClaimCheck must be strictly read-only against registries.

This scans the entire source tree and fails if any code path could *mutate*
registry state — i.e. issue a mutating HTTP verb (POST/PUT/PATCH/DELETE) or shell
out to a publishing tool (twine, ``npm publish``, ``poetry publish``, etc.).

The deliverable is a report; there is no defensive registration or publishing in
this repository, by design, and this test enforces that invariant.
"""

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"

# Mutating HTTP verbs as *calls* (e.g. requests.post(, session.put(, .delete().
_MUTATING_HTTP = re.compile(r"\.(post|put|patch|delete)\s*\(", re.IGNORECASE)

# Publishing / registration tooling invoked via shell or API.
_PUBLISH_TOKENS = [
    "twine",
    "npm publish",
    "yarn publish",
    "pnpm publish",
    "poetry publish",
    "setup.py upload",
    "flit publish",
]


def _code_lines(path: Path):
    """Yield (lineno, line) for source lines, skipping comments.

    Docstrings are left in; the regex/token checks below only match *call*
    syntax or shell commands, which prose does not contain.
    """
    for i, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = raw.strip()
        if stripped.startswith("#"):
            continue
        yield i, raw


def test_no_mutating_http_calls():
    offenders = []
    for py in SRC.rglob("*.py"):
        for lineno, line in _code_lines(py):
            if _MUTATING_HTTP.search(line):
                offenders.append(f"{py.relative_to(SRC)}:{lineno}: {line.strip()}")
    assert not offenders, "Mutating HTTP verb found (must be read-only):\n" + "\n".join(offenders)


def test_no_publish_tooling():
    offenders = []
    for py in SRC.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for token in _PUBLISH_TOKENS:
            # Only flag tokens appearing in string literals / shell commands,
            # which would indicate an actual invocation.
            for lineno, line in _code_lines(py):
                if token in line and ('"' in line or "'" in line):
                    offenders.append(f"{py.relative_to(SRC)}:{lineno}: {token}")
    assert not offenders, "Publishing tooling referenced (must not publish):\n" + "\n".join(offenders)


def test_live_oracle_only_uses_get():
    """The live oracle's only network method is GET."""
    source = (SRC / "claimcheck" / "registry" / "oracle.py").read_text(encoding="utf-8")
    # It calls self._requests.get(...) and defines a _get helper; no mutating verbs.
    assert "self._requests.get(" in source
    assert not _MUTATING_HTTP.search(source)
