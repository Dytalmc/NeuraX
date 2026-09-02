"""
loader_versions.py — NeuraX Loader Version Manager
====================================================

Single source of truth for per-loader software version selection:

  * Fabric Loader (loader-only: 0.16.x ...)
  * Quilt Loader
  * Forge (combined "<mc>-<forge>" string)
  * NeoForge (combined "<mc>-<neoforge>" string)

The manager exposes:

  * `fetch_available_versions(loader)` — list every loader version available
    from the upstream meta endpoint, in newest-first order.
  * `get_desired_loader_version(loader, mc_version)` — return the version
    the user pinned for a loader, falling back to "latest compatible".
  * `queue_reinstall(loader, mc_version, loader_version)` — store the
    target version in the user's config. The next launch will:
        1. Wipe the per-instance loader directories for the (loader, mc_version) pair.
        2. Re-run the loader install with the queued version.

The LaunchWorker reads `pending_loader_reinstall` from config on startup
and processes the queue before the per-loader install block runs.
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

# minecraft_launcher_lib is an optional dep at runtime; treat it as such.
try:
    import minecraft_launcher_lib  # type: ignore
    MCLIB_AVAILABLE = True
except Exception:  # pragma: no cover - import guard
    MCLIB_AVAILABLE = False


SUPPORTED_LOADERS: Tuple[str, ...] = ("fabric", "quilt", "forge", "neoforge")


# ---------------------------------------------------------------------------
# Network helpers — newest-first version lists per loader
# ---------------------------------------------------------------------------
def _sort_newest_first(items: List[str]) -> List[str]:
    """Sort a list of version-like strings newest-first.

    The primary key is the leading ``a.b.c`` triple, ignoring suffixes
    like ``+build.214`` or ``-beta.7``. The build/suffix digits are
    used only as a tie-breaker so that ``0.19.5+build.99`` still sorts
    above ``0.19.5`` but below ``0.19.6``.
    """

    def key(v: str):
        # Strip suffixes: +build.N, -beta.N, -rc.N, -SNAPSHOT, etc.
        core = re.split(r"[+\-]", v, maxsplit=1)[0]
        nums = [int(n) for n in re.findall(r"\d+", core)]
        # Pad to length 5 so 0.19.5 > 0.19.5.1 doesn't happen by accident.
        padded = (nums + [0] * 5)[:5]
        suffix_nums = [
            int(n) for n in re.findall(r"\d+", v[len(core):])
        ]
        return (padded, suffix_nums, v)

    return sorted(items, key=key, reverse=True)


def is_version_newer(candidate: str, baseline: str) -> bool:
    """Digit-aware compare. Returns True if ``candidate`` is strictly newer
    than ``baseline``. Empty/whitespace strings are treated as 'unknown',
    never as 'newer'. Handles ``<mc>-<forge>`` style strings too — only the
    trailing ``<loader>`` portion is compared for Forge/NeoForge so that an
    older MC version with a newer Forge build is still considered newer.
    """
    def parse(v: str) -> tuple:
        s = (v or "").strip()
        if not s:
            return ()
        # For forge/neoforge the upstream strings are "<mc>-<forge>" (e.g.
        # "1.21.4-54.1.6"). Compare only the loader half — that matches the
        # way maven-metadata.xml lists them and what the launcher actually
        # cares about.
        if re.match(r"^\d+\.\d+(\.\d+)?-\d", s):
            head, _, tail = s.partition("-")
            # If the second half itself contains dots, treat as forge build.
            if re.search(r"\d+\.\d+", tail):
                return parse(tail)
        nums = [int(n) for n in re.findall(r"\d+", s)]
        return tuple(nums) if nums else (0,)

    a = parse(candidate)
    b = parse(baseline)
    if not a or not b:
        return False
    return a > b


def is_version_outdated(current: str, latest: str) -> bool:
    """Return True if ``current`` is strictly behind ``latest``. An empty
    ``current`` (i.e. the loader isn't installed yet, or the version is
    unknown) counts as outdated — we want the launcher to fetch the latest
    stable build in that case."""
    cur = (current or "").strip()
    lat = (latest or "").strip()
    if not lat:
        # No upstream info — can't say it's outdated.
        return False
    if not cur:
        return True
    return is_version_newer(lat, cur)


def _fetch_fabric_loader_versions() -> List[str]:
    try:
        r = requests.get("https://meta.fabricmc.net/v2/versions/loader", timeout=10)
        if r.status_code == 200:
            data = r.json() or []
            return [str(d.get("version", "")).strip() for d in data if d.get("version")]
    except Exception:
        pass
    return []


def _fetch_quilt_loader_versions() -> List[str]:
    try:
        r = requests.get("https://meta.quiltmc.org/v2/versions/loader", timeout=10)
        if r.status_code == 200:
            data = r.json() or []
            return [str(d.get("version", "")).strip() for d in data if d.get("version")]
    except Exception:
        pass
    return []


def _fetch_forge_loader_versions() -> List[str]:
    """Forge doesn't publish a single 'all loaders' feed — versions are
    bound to a Minecraft version. We scrape the maven-metadata for a
    recent set and return unique sorted entries."""
    out: List[str] = []
    try:
        # Pull the full maven listing of forge artifacts.
        r = requests.get(
            "https://maven.minecraftforge.net/net/minecraftforge/forge/maven-metadata.xml",
            timeout=12,
        )
        if r.status_code == 200:
            out = re.findall(r"<version>([^<]+)</version>", r.text)
    except Exception:
        pass
    if not out:
        try:
            r = requests.get(
                "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json",
                timeout=10,
            )
            if r.status_code == 200:
                promos = (r.json() or {}).get("promos", {})
                out = [
                    f"{ver.split('-recommended')[0]}-{promos[ver]}"
                    for ver in promos.keys()
                    if ver.endswith("-latest") or ver.endswith("-recommended")
                ]
        except Exception:
            pass
    return _sort_newest_first(out)


def _fetch_neoforge_loader_versions() -> List[str]:
    out: List[str] = []
    try:
        r = requests.get(
            "https://maven.neoforged.net/releases/net/neoforged/neoforge/maven-metadata.xml",
            timeout=12,
        )
        if r.status_code == 200:
            out = re.findall(r"<version>([^<]+)</version>", r.text)
    except Exception:
        pass
    return _sort_newest_first(out)


def fetch_available_versions(loader: str) -> List[str]:
    """Return newest-first list of loader versions available upstream."""
    loader_l = (loader or "").lower().strip()
    if loader_l == "fabric":
        return _sort_newest_first(_fetch_fabric_loader_versions())
    if loader_l == "quilt":
        return _sort_newest_first(_fetch_quilt_loader_versions())
    if loader_l == "forge":
        return _fetch_forge_loader_versions()
    if loader_l == "neoforge":
        return _fetch_neoforge_loader_versions()
    return []


def fetch_latest_loader_version(loader: str, mc_version: str = "") -> str:
    """Return the upstream latest loader version string for a given loader
    family. For loader-only families (Fabric, Quilt) ``mc_version`` is
    unused. For Forge/NeoForge ``mc_version`` filters to the highest build
    compatible with that MC version when available; if not, returns the
    upstream-latest build (which may be tied to a different MC version).

    The result is in the same string format the upstream uses (e.g.
    ``0.19.5`` for Fabric, ``54.1.6`` for NeoForge, ``1.21.4-54.1.6`` for
    Forge). Empty string is returned when no upstream info is reachable.
    """
    loader_l = (loader or "").lower().strip()
    versions = fetch_available_versions(loader_l)
    if not versions:
        return ""
    if loader_l in ("fabric", "quilt"):
        # Loader-only — first entry is newest.
        return versions[0]
    # Forge / NeoForge — entries are like "<mc>-<build>" or sometimes
    # just "<build>". If we have an mc_version, prefer entries whose
    # prefix matches.
    mc = (mc_version or "").strip()
    if mc:
        prefix_matches = [v for v in versions if v.startswith(f"{mc}-")]
        if prefix_matches:
            # Sort the prefix matches by build-version numbers so the
            # "latest" really is the latest. ``_sort_newest_first``
            # compares whole-string, which is correct for "<mc>-<build>"
            # because all share the same prefix.
            return prefix_matches[0]
    # Fallback: newest overall.
    return versions[0]


# ---------------------------------------------------------------------------
# Desired-version storage
# ---------------------------------------------------------------------------
def _normalise_loader(loader: str) -> str:
    return (loader or "").strip().lower()


def get_desired_loader_version(config, loader: str, mc_version: str) -> str:
    """Return the loader version the user wants installed for (loader, mc).
    Priority:
      1. `loader_versions.<loader>.<mc>` from config (user pinned).
      2. `loader_versions.<loader>.__default__` (global default for loader).
      3. "" (meaning: use upstream latest).
    """
    if config is None:
        return ""
    pinned = (config.get("loader_versions", {}) or {}).get(_normalise_loader(loader), {}) or {}
    val = pinned.get(str(mc_version).strip(), "")
    if val:
        return str(val).strip()
    val = pinned.get("__default__", "")
    return str(val).strip() if val else ""


def set_desired_loader_version(config, loader: str, mc_version: str, version: str) -> None:
    """Persist the user's choice. Empty string clears the pin."""
    if config is None:
        return
    all_pins = dict(config.get("loader_versions", {}) or {})
    bucket = dict(all_pins.get(_normalise_loader(loader), {}) or {})
    if version:
        bucket[str(mc_version).strip()] = str(version).strip()
    else:
        bucket.pop(str(mc_version).strip(), None)
    if bucket:
        all_pins[_normalise_loader(loader)] = bucket
    else:
        all_pins.pop(_normalise_loader(loader), None)
    config.set("loader_versions", all_pins)


def set_desired_loader_default(config, loader: str, version: str) -> None:
    """Set the loader-wide default version (applies when no per-MC pin exists)."""
    if config is None:
        return
    all_pins = dict(config.get("loader_versions", {}) or {})
    bucket = dict(all_pins.get(_normalise_loader(loader), {}) or {})
    if version:
        bucket["__default__"] = str(version).strip()
    else:
        bucket.pop("__default__", None)
    if bucket:
        all_pins[_normalise_loader(loader)] = bucket
    else:
        all_pins.pop(_normalise_loader(loader), None)
    config.set("loader_versions", all_pins)


# ---------------------------------------------------------------------------
# Reinstall queue — read by LaunchWorker before the install step
# ---------------------------------------------------------------------------
def queue_reinstall(config, loader: str, mc_version: str, loader_version: str) -> None:
    """Mark (loader, mc_version) for a fresh install on next launch.

    The next launch will:
        - Delete the existing loader-installed directories for that pair.
        - Re-install the loader using `loader_version` (or upstream latest
          if loader_version is empty).
    """
    if config is None:
        return
    queue = list(config.get("pending_loader_reinstall", []) or [])
    entry = {
        "loader": _normalise_loader(loader),
        "mc_version": str(mc_version).strip(),
        "loader_version": str(loader_version).strip(),
        "queued_at": int(time.time()),
    }
    # Replace any existing entry for the same (loader, mc) pair.
    queue = [
        e for e in queue
        if not (e.get("loader") == entry["loader"] and e.get("mc_version") == entry["mc_version"])
    ]
    queue.append(entry)
    config.set("pending_loader_reinstall", queue)


def pop_reinstall(config, loader: str, mc_version: str) -> Optional[Dict[str, str]]:
    """Pop one queued reinstall for the given pair, if any."""
    if config is None:
        return None
    queue = list(config.get("pending_loader_reinstall", []) or [])
    target_loader = _normalise_loader(loader)
    target_mc = str(mc_version).strip()
    kept: List[Dict[str, str]] = []
    found: Optional[Dict[str, str]] = None
    for entry in queue:
        if found is None and entry.get("loader") == target_loader and entry.get("mc_version") == target_mc:
            found = entry
        else:
            kept.append(entry)
    config.set("pending_loader_reinstall", kept)
    return found


# ---------------------------------------------------------------------------
# Filesystem wipe — remove old loader artifacts before reinstalling
# ---------------------------------------------------------------------------
_LOADER_NAME_TOKENS = {
    "fabric": ("fabric",),
    "quilt": ("quilt",),
    "forge": ("forge",),
    "neoforge": ("neoforge",),
}


def _is_loader_version_dir(dir_name: str, loader_l: str) -> bool:
    d = dir_name.lower()
    tokens = _LOADER_NAME_TOKENS.get(loader_l, ())
    return any(tok in d for tok in tokens)


def _wipe_loader_dirs(game_dir: Path, loader: str, mc_version: str) -> List[str]:
    """Delete every directory under game_dir/versions/ whose name looks like
    a previous install of `loader` for `mc_version`. Returns the names
    of the removed directories so the caller can log them."""
    removed: List[str] = []
    versions_dir = Path(game_dir) / "versions"
    if not versions_dir.exists():
        return removed
    loader_l = _normalise_loader(loader)
    mc_clean = str(mc_version).strip()
    for entry in versions_dir.iterdir():
        if not entry.is_dir():
            continue
        name = entry.name
        n_low = name.lower()
        if not _is_loader_version_dir(n_low, loader_l):
            continue
        # Match by Minecraft version substring.
        if mc_clean and mc_clean not in name:
            continue
        try:
            import shutil
            shutil.rmtree(entry, ignore_errors=True)
            removed.append(name)
        except Exception:
            pass
    return removed


def wipe_and_queue_reinstall(
    config,
    game_dir: Path,
    loader: str,
    mc_version: str,
    loader_version: str,
) -> List[str]:
    """Wipe old loader directories under game_dir and persist the queued
    reinstall in config. Returns the names of the removed directories."""
    removed = _wipe_loader_dirs(game_dir, loader, mc_version)
    queue_reinstall(config, loader, mc_version, loader_version)
    return removed


__all__ = [
    "SUPPORTED_LOADERS",
    "fetch_available_versions",
    "get_desired_loader_version",
    "set_desired_loader_version",
    "set_desired_loader_default",
    "queue_reinstall",
    "pop_reinstall",
    "wipe_and_queue_reinstall",
    "is_version_newer",
    "is_version_outdated",
]