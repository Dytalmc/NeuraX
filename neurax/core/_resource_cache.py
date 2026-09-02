"""Disk-backed cache for everything the launcher fetches over the network.

The whole point of this module is to keep the launcher useful when the user's
internet is slow or completely offline. Every JSON manifest we hit
(Mojang version manifest, Modrinth mod listings, AI Version Radar output,
Supabase community payloads, etc.) goes through :class:`ResourceCache` and is
mirrored to ``~/.neurax/cache/`` with a TTL. Whenever a feature is asked for
fresh data, we:

  1. Return the disk copy immediately if it's fresh enough.
  2. Otherwise kick off a network refresh in the background. While the
     refresh is in flight, the caller still gets the cached value so the
     UI never blocks.
  3. If there is no cache AND no network, we return ``None`` and the
     caller is expected to gracefully disable the feature.

Network behaviour is gated by :class:`neurax.core.network_monitor.NetworkMonitor`
so a slow-link launcher doesn't burn minutes waiting on Supabase just to
display a community chip.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

# A "fresh enough" TTL for cached payloads. Modrinth results are good for
# hours; the Mojang version manifest only changes a few times a week; AI
# Version Radar output we treat as good for an hour. We default to an hour
# and let the per-call ``ttl`` override.
_DEFAULT_TTL_SECONDS = 60 * 60


class ResourceCache:
    """Tiny disk-backed JSON cache with TTL and atomic writes.

    Two layers of files live under ``root``:

      ``<root>/json/<key>.json``  — JSON payloads we know how to re-parse
      ``<root>/raw/<key>.bin``    — opaque blobs (e.g. downloaded JARs)

    JSON writes are atomic: we write to ``<key>.json.tmp`` first then
    ``os.replace`` onto the final path so a crash mid-write can never
    leave a half-written file that the next read would treat as valid.
    """

    def __init__(self, root: Path):
        self.root = Path(root)
        self.json_dir = self.root / "json"
        self.raw_dir = self.root / "raw"
        self.json_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ JSON
    def get_json(self, key: str, default: Any = None, ttl: float = _DEFAULT_TTL_SECONDS) -> Any:
        """Return the cached JSON for ``key`` if it's younger than ``ttl``."""
        path = self._json_path(key)
        if not path.exists():
            return default
        try:
            age = time.time() - path.stat().st_mtime
            if age > ttl:
                return default
            with path.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            return default

    def get_json_any_age(self, key: str) -> Any:
        """Return the cached JSON for ``key`` regardless of age, or ``None``."""
        path = self._json_path(key)
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            return None

    def put_json(self, key: str, value: Any) -> None:
        """Atomically write ``value`` as JSON to ``<key>.json``."""
        path = self._json_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with self._lock:
            try:
                with tmp.open("w", encoding="utf-8") as fh:
                    json.dump(value, fh, ensure_ascii=False)
                os.replace(tmp, path)
            except OSError:
                # Best effort. We never want a cache write failure to break
                # the caller.
                try:
                    tmp.unlink()
                except OSError:
                    pass

    def invalidate_json(self, key: str) -> None:
        path = self._json_path(key)
        try:
            path.unlink()
        except OSError:
            pass

    # ------------------------------------------------------------------- Raw
    def get_raw_path(self, key: str) -> Optional[Path]:
        path = self._raw_path(key)
        return path if path.exists() else None

    def put_raw(self, key: str, data: bytes) -> Path:
        path = self._raw_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with self._lock:
            try:
                with tmp.open("wb") as fh:
                    fh.write(data)
                os.replace(tmp, path)
            except OSError:
                try:
                    tmp.unlink()
                except OSError:
                    pass
        return path

    # ----------------------------------------------------------------- Paths
    def _json_path(self, key: str) -> Path:
        # Sanitize the key so we can't escape the cache dir.
        safe = key.replace("..", "_").replace("/", "_").replace("\\", "_")
        return self.json_dir / f"{safe}.json"

    def _raw_path(self, key: str) -> Path:
        safe = key.replace("..", "_").replace("/", "_").replace("\\", "_")
        return self.raw_dir / f"{safe}.bin"


# ---------------------------------------------------------------------------
# High-level helpers — these are the public API the rest of the launcher uses.
# ---------------------------------------------------------------------------

# Module-level singleton, lazily created on first use. The cache root is the
# ``cache/`` folder under the user's ``~/.neurax/`` dir. Callers can override
# by calling :func:`set_cache_root` at startup.
_cache: Optional[ResourceCache] = None
_cache_root: Optional[Path] = None


def set_cache_root(root: Path) -> ResourceCache:
    """Set the cache root directory and return the singleton."""
    global _cache, _cache_root
    _cache_root = Path(root)
    _cache = ResourceCache(_cache_root)
    return _cache


def get_cache() -> ResourceCache:
    """Return the global cache, creating it under ``~/.neurax/cache`` if needed."""
    global _cache, _cache_root
    if _cache is None:
        if _cache_root is None:
            from .config import get_dot_neurax_dir
            _cache_root = get_dot_neurax_dir() / "cache"
        _cache = ResourceCache(_cache_root)
    return _cache


def cached_fetch(
    key: str,
    fetcher: Callable[[], Any],
    *,
    ttl: float = _DEFAULT_TTL_SECONDS,
    fallback_to_stale: bool = True,
) -> Any:
    """Return ``fetcher()``'s result, served from cache when possible.

    If the cache is fresh, return it without calling the fetcher. If the
    cache is stale or missing, try the fetcher; on success write through to
    the cache and return the fresh value. If the fetcher raises AND we have
    any cached value (even expired), return the cached value as a fallback
    so the UI keeps working during a network outage.
    """
    cache = get_cache()
    fresh = cache.get_json(key, default=None, ttl=ttl)
    if fresh is not None:
        return fresh
    try:
        value = fetcher()
    except Exception:
        if fallback_to_stale:
            stale = cache.get_json_any_age(key)
            if stale is not None:
                return stale
        return None
    try:
        cache.put_json(key, value)
    except Exception:
        pass
    return value