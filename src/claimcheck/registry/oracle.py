"""Read-only public-registry probe.

A :class:`RegistryOracle` answers one question per name: *does this name exist on
the public registry, and if so, who owns it and when was it first published?*

SAFETY — this module is strictly read-only. It only issues HTTP **GET** requests
to public registry JSON endpoints. There is no code path that publishes,
registers, reserves, or otherwise mutates registry state anywhere in ClaimCheck.
A test (``tests/test_readonly.py``) enforces this by scanning the source.

Two implementations:

* :class:`MockRegistryOracle` — reads a bundled JSON fixture. The full pipeline
  runs offline on synthetic data with no network access.
* :class:`LiveRegistryOracle` — queries public PyPI and npm with on-disk caching
  and polite rate limiting. Requires ``requests`` (``pip install requests``).
"""

from __future__ import annotations

import abc
import datetime as _dt
import json
import time
from pathlib import Path
from typing import Optional

from ..schema import Ecosystem, RegistryStatus

# A package first published within this many days is "recently published",
# a red flag when it matches an internal name (possible fresh squat).
RECENT_WINDOW_DAYS = 90


def _is_recent(iso_date: Optional[str], window_days: int = RECENT_WINDOW_DAYS) -> bool:
    if not iso_date:
        return False
    try:
        d = _dt.datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
    except ValueError:
        return False
    if d.tzinfo is None:
        d = d.replace(tzinfo=_dt.timezone.utc)
    now = _dt.datetime.now(_dt.timezone.utc)
    return (now - d).days <= window_days


class RegistryOracle(abc.ABC):
    """Abstract read-only registry probe."""

    #: Human-readable mode label recorded on each RegistryStatus.
    source_label = "mock"

    @abc.abstractmethod
    def lookup(self, normalized_name: str, ecosystem: Ecosystem) -> RegistryStatus:
        """Return the public-registry status of a single name. Read-only."""
        raise NotImplementedError


# --------------------------------------------------------------------------- #
# Mock oracle
# --------------------------------------------------------------------------- #
class MockRegistryOracle(RegistryOracle):
    """Answers lookups from an in-memory/JSON fixture. No network.

    Fixture format::

        {
          "pypi": {
            "acme-utils": {"owner": "mallory", "first_published": "2026-09-20"}
          },
          "npm": {
            "@acme/public-sdk": {"owner": "acme", "first_published": "2024-01-01"}
          }
        }

    A name present in the fixture "exists"; a name absent from it does not.
    """

    source_label = "mock"

    def __init__(self, data: Optional[dict] = None):
        self._data = data or {"pypi": {}, "npm": {}}

    @classmethod
    def from_file(cls, path: str | Path) -> "MockRegistryOracle":
        with open(path, encoding="utf-8") as fh:
            return cls(json.load(fh))

    def lookup(self, normalized_name: str, ecosystem: Ecosystem) -> RegistryStatus:
        table = self._data.get(ecosystem.value, {})
        entry = table.get(normalized_name)
        if entry is None:
            return RegistryStatus(exists=False, source="mock")
        first = entry.get("first_published")
        # Honor an explicit flag so committed fixtures stay reproducible over
        # time; otherwise derive recency from the publish date.
        if "recently_published" in entry:
            recent = bool(entry["recently_published"])
        else:
            recent = _is_recent(first)
        return RegistryStatus(
            exists=True,
            owner=entry.get("owner"),
            first_published=first,
            recently_published=recent,
            source="mock",
        )


# --------------------------------------------------------------------------- #
# Live oracle (read-only HTTP GET only)
# --------------------------------------------------------------------------- #
class LiveRegistryOracle(RegistryOracle):
    """Queries public PyPI and npm read-only, with on-disk caching.

    Only HTTP GET is used. Responses are cached to ``cache_dir`` so re-scans and
    CI runs are fast and gentle on the registries.
    """

    source_label = "live"
    PYPI_URL = "https://pypi.org/pypi/{name}/json"
    NPM_URL = "https://registry.npmjs.org/{name}"

    def __init__(self, cache_dir: str | Path = ".claimcheck_cache",
                 min_interval: float = 0.1, timeout: float = 10.0):
        try:
            import requests  # noqa: F401  (imported lazily; live mode only)
        except ImportError as exc:  # pragma: no cover - env dependent
            raise RuntimeError(
                "Live mode requires the 'requests' package. "
                "Install it with: pip install requests"
            ) from exc
        self._requests = __import__("requests")
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.min_interval = min_interval
        self.timeout = timeout
        self._last_call = 0.0

    # -- caching ---------------------------------------------------------- #
    def _cache_path(self, ecosystem: Ecosystem, name: str) -> Path:
        safe = name.replace("/", "__").replace("@", "at__")
        return self.cache_dir / f"{ecosystem.value}__{safe}.json"

    def _throttle(self) -> None:
        delta = time.monotonic() - self._last_call
        if delta < self.min_interval:
            time.sleep(self.min_interval - delta)
        self._last_call = time.monotonic()

    def _get(self, url: str) -> tuple[int, Optional[dict]]:
        self._throttle()
        resp = self._requests.get(
            url, timeout=self.timeout,
            headers={"Accept": "application/json",
                     "User-Agent": "ClaimCheck/0.1 (+read-only exposure audit)"},
        )
        if resp.status_code == 200:
            try:
                return 200, resp.json()
            except ValueError:
                return 200, None
        return resp.status_code, None

    # -- lookup ----------------------------------------------------------- #
    def lookup(self, normalized_name: str, ecosystem: Ecosystem) -> RegistryStatus:
        cache_path = self._cache_path(ecosystem, normalized_name)
        if cache_path.exists():
            try:
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
                status = RegistryStatus(**cached)
                status.source = "cache"
                return status
            except (ValueError, TypeError):
                pass  # fall through and re-fetch on a corrupt cache entry

        if ecosystem is Ecosystem.PYPI:
            status = self._lookup_pypi(normalized_name)
        else:
            status = self._lookup_npm(normalized_name)

        cache_path.write_text(json.dumps(status.to_dict()), encoding="utf-8")
        return status

    def _lookup_pypi(self, name: str) -> RegistryStatus:
        code, data = self._get(self.PYPI_URL.format(name=name))
        if code == 404 or data is None:
            return RegistryStatus(exists=False, source="live")
        info = data.get("info", {})
        owner = info.get("author") or info.get("maintainer") or None
        first = _earliest_pypi_release(data)
        return RegistryStatus(
            exists=True, owner=owner, first_published=first,
            recently_published=_is_recent(first), source="live",
        )

    def _lookup_npm(self, name: str) -> RegistryStatus:
        code, data = self._get(self.NPM_URL.format(name=name))
        if code == 404 or data is None:
            return RegistryStatus(exists=False, source="live")
        maintainers = data.get("maintainers") or []
        owner = None
        if maintainers and isinstance(maintainers, list):
            first_m = maintainers[0]
            owner = first_m.get("name") if isinstance(first_m, dict) else str(first_m)
        created = (data.get("time") or {}).get("created")
        return RegistryStatus(
            exists=True, owner=owner, first_published=created,
            recently_published=_is_recent(created), source="live",
        )


def _earliest_pypi_release(data: dict) -> Optional[str]:
    releases = data.get("releases") or {}
    dates: list[str] = []
    for files in releases.values():
        for f in files or []:
            t = f.get("upload_time_iso_8601") or f.get("upload_time")
            if t:
                dates.append(t)
    return min(dates) if dates else None


def load_oracle(mode: str, oracle_file: Optional[str] = None,
                cache_dir: str = ".claimcheck_cache") -> RegistryOracle:
    """Factory: build the oracle for a scan mode ('mock' or 'live')."""
    if mode == "live":
        return LiveRegistryOracle(cache_dir=cache_dir)
    if oracle_file:
        return MockRegistryOracle.from_file(oracle_file)
    return MockRegistryOracle()
