"""
users.py — NeuraX Community Stats Client & PyQt6 Community View
================================================================
Single source of truth for:

  1. Per-device UUID (generated on first launch, persisted in keyring or
     `users_config.json` as fallback). One UUID per device, never changes.
  2. CommunityClient — Supabase REST heartbeat + counter fetcher. Runs on a
     QThread so the GUI never blocks. Graceful no-op when not configured.
  3. CommunityView — full PyQt6 view showing your UUID, last heartbeat,
     online count, total users, and a list of recently active devices.
  4. update_users_file() — backward-compatible entry point the existing
     `app.py` already calls at startup. Now triggers the first heartbeat
     instead of just a stub.

Backend schema (run once in Supabase SQL editor):

  create table if not exists public.heartbeats (
    device_id text primary key,
    os text,
    launcher_version text,
    instance_count int,
    mod_count int,
    total_playtime_seconds int,
    last_seen timestamptz not null default now(),
    online boolean not null default false,
    instance_names jsonb default '[]'::jsonb,
    instance_mods jsonb default '{}'::jsonb,
    created_at timestamptz not null default now()
  );

  alter table public.heartbeats enable row level security;

  -- Anon read/write access (safe to expose since the only data is the
  -- anonymous device's own metadata; no PII, no auth tokens).
  create policy "anon read" on public.heartbeats for select using (true);
  create policy "anon upsert" on public.heartbeats for insert with check (true);
  create policy "anon update" on public.heartbeats for update using (true);

The anon key is OK to embed because the row-level security policies above
explicitly permit the operations we need and nothing else. If you ever
want to lock this down further, the device UUID is the right bearer token
to use in a stricter policy.
"""
from __future__ import annotations

# Canonical setup SQL — kept in sync with the docstring above. The launcher
# itself only needs this if a user re-provisions a brand-new Supabase project
# later; the first-run helper that copied it to the clipboard is no longer
# surfaced in the Community view UI.
_SETUP_SQL = """-- NeuraX Community heartbeats table (improved)
create extension if not exists "pgcrypto";

create table if not exists public.heartbeats (
  device_id text primary key,
  os text,
  launcher_version text,
  instance_count int default 0,
  mod_count int default 0,
  total_playtime_seconds int default 0,
  last_seen timestamptz not null default now(),
  online boolean not null default false,
  instance_names jsonb default '[]'::jsonb,
  instance_mods jsonb default '{}'::jsonb,
  payload jsonb default '{}'::jsonb,
  created_at timestamptz not null default now(),
  constraint heartbeats_device_id_len check (char_length(device_id) between 8 and 64)
);

create index if not exists heartbeats_last_seen_idx
  on public.heartbeats (last_seen desc);

create or replace function public.community_online_window()
returns interval language sql immutable as $$ select '90 seconds'::interval $$;

create or replace function public.heartbeats_expire_online()
returns trigger language plpgsql as $$
begin
  if new.online is true and new.last_seen < (now() - public.community_online_window()) then
    new.online := false;
  end if;
  return new;
end $$;

drop trigger if exists heartbeats_expire_online_trg on public.heartbeats;
create trigger heartbeats_expire_online_trg
  before insert or update on public.heartbeats
  for each row execute function public.heartbeats_expire_online();

create or replace view public.community_online_count as
  select count(*) filter (where online) as online_count, count(*) as total_count
  from public.heartbeats;

alter table public.heartbeats enable row level security;

drop policy if exists "anon_read"   on public.heartbeats;
drop policy if exists "anon_upsert" on public.heartbeats;
drop policy if exists "anon_update" on public.heartbeats;
drop policy if exists "anon_delete" on public.heartbeats;

create policy "anon_read"   on public.heartbeats for select to anon using (true);
create policy "anon_upsert" on public.heartbeats for insert to anon with check (true);
create policy "anon_update" on public.heartbeats for update to anon using (true) with check (true);
create policy "anon_delete" on public.heartbeats for delete to anon using (false);
"""

import json
import os
import platform
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

try:
    import requests
    _REQUESTS_OK = True
except Exception:
    _REQUESTS_OK = False

try:
    import keyring
    _KEYRING_OK = True
except Exception:
    _KEYRING_OK = False

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
def _project_root() -> Path:
    """Locate the .neurax config dir, or fall back to the user's home."""
    try:
        from neurax.core.config import get_dot_neurax_dir
        return get_dot_neurax_dir()
    except Exception:
        if sys.platform == "win32":
            base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
            return Path(base) / ".neurax"
        return Path.home() / ".neurax"


def _project_file_search_roots() -> List[Path]:
    """Directories to scan for fallback ``users_config.json`` /
    ``nx_config.json`` when the canonical ``%APPDATA%\\.neurax``
    folder is missing or empty (e.g. the user just wiped it).

    The runtime data dir is the *user* config — it lives under
    ``%APPDATA%\\.neurax``. The *project* config — where the
    bundled launcher ships its default credentials — lives next
    to ``users.py`` (the workspace root, ``C:\\Users\\arush\\Downloads\\neurax\\n2 - Copy``
    in dev) and may also be packed next to the frozen ``.exe`` in
    production. We return both so a missing ``.neurax`` doesn't
    leave the launcher with no credentials at all.
    """
    roots: List[Path] = []
    try:
        # The directory containing this file (``users.py``) — in dev
        # this is the workspace root; in a frozen build, ``users.py``
        # is bundled and ``__file__`` points inside ``sys._MEIPASS``,
        # which PyInstaller places next to the exe.
        roots.append(Path(__file__).resolve().parent)
    except Exception:
        pass
    # Also scan the current working directory and one level up —
    # convenient for both dev (``n2 - Copy``) and a typical install
    # layout where the exe and the config share a folder.
    try:
        cwd = Path.cwd().resolve()
        if cwd not in roots:
            roots.append(cwd)
    except Exception:
        pass
    try:
        # Common: exe lives in ``Program Files\\NeuraX`` and the
        # config sits one level up at ``Program Files``.
        exe_parent = Path(sys.executable).resolve().parent
        if exe_parent not in roots:
            roots.append(exe_parent)
        exe_grand = exe_parent.parent
        if exe_grand not in roots:
            roots.append(exe_grand)
    except Exception:
        pass
    return roots


def _users_config_path() -> Path:
    return _project_root() / "users_config.json"


# Extra fallback paths the chip's refresh logic searches for a Supabase
# config. Some installs ship the credentials in the workspace-level
# ``nx_config.json`` (used by ``nx.py`` and the standalone dashboard) but
# never copy them into ``%APPDATA%\.neurax\users_config.json``; without
# this fallback the chip would read empty creds, mark the device as
# "offline" and refuse to query the backend, even though the credentials
# are sitting one folder away. Order matters: ``users_config.json`` is
# the runtime source of truth, ``nx_config.json`` is the legacy fallback.
_EXTRA_CONFIG_FALLBACK_PATHS = (
    "nx_config.json",
    "../nx_config.json",
    "../../nx_config.json",
)


def _load_users_config() -> Dict[str, Any]:
    p = _users_config_path()
    if not p.exists():
        return dict(_DEFAULT_USERS_CONFIG)
    try:
        with open(p, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        merged = dict(_DEFAULT_USERS_CONFIG)
        merged.update({k: v for k, v in data.items() if k in _DEFAULT_USERS_CONFIG})
        # Normalise out-of-range intervals to the 5s default. Legacy
        # configs may have 10s / 30s / 300s values; we always migrate them
        # down on read so users get the fresh 5s cadence on next launch
        # (one round-trip every 5s keeps the online count fresh enough
        # for the chip to feel real-time without hammering Supabase).
        try:
            cur = int(merged.get("heartbeat_interval_seconds", 5) or 5)
        except Exception:
            cur = 5
        if cur > 5:
            merged["heartbeat_interval_seconds"] = 5
        return merged
    except Exception:
        return dict(_DEFAULT_USERS_CONFIG)


def _load_effective_users_config() -> Dict[str, Any]:
    """Return the merged users config, walking fallback paths if the
    canonical ``users_config.json`` is missing Supabase credentials.

    The runtime data path is the single source of truth, but the
    chip is purely a status indicator — there's no harm in quietly
    filling in the URL / anon key from the workspace-level
    ``nx_config.json`` when those keys are blank. The heartbeats and
    community API calls in ``update_users_file`` continue to use the
    canonical path; only the chip's status display benefits from this
    fallback, so a user with valid credentials at either location sees a
    live "N online" count instead of a permanent "offline" badge.

    Fallback walks three layers of directories:
      1. The runtime dir (legacy, same as before — kept for back-compat).
      2. The directory containing ``users.py`` (the project root in
         dev; ``sys._MEIPASS`` in a frozen build) — this is where the
         bundled launcher ships its default ``users_config.json``.
      3. The current working directory and the exe parent / grandparent.

    If the canonical ``users_config.json`` is missing OR doesn't have
    credentials, and we successfully recovered them from a fallback,
    we also write the merged config back to the canonical path so
    subsequent ticks don't have to walk the fallback chain. This is
    what fixes "chip says offline after the user wiped %APPDATA%\\.neurax".
    """
    cfg = _load_users_config()
    if cfg.get("supabase_url") and cfg.get("supabase_anon_key"):
        return cfg
    had_credentials_from_fallback = False
    # Build a deduplicated list of search roots, with the project
    # roots FIRST so the bundled default wins over the empty runtime
    # dir when the user has just wiped it.
    search_roots: List[Path] = []
    seen: set = set()
    for root in _project_file_search_roots():
        try:
            key = str(root.resolve())
        except Exception:
            continue
        if key in seen:
            continue
        seen.add(key)
        search_roots.append(root)
    # Legacy: the runtime dir. If it doesn't exist (user wiped it),
    # every ``(base / rel)`` resolves to a non-existent file and
    # we skip — no harm.
    try:
        rt_root = _project_root()
        rt_key = str(rt_root.resolve())
        if rt_key not in seen:
            search_roots.append(rt_root)
            seen.add(rt_key)
    except Exception:
        pass
    for base in search_roots:
        for rel in _EXTRA_CONFIG_FALLBACK_PATHS + ("users_config.json",):
            try:
                candidate = (base / rel).resolve()
            except Exception:
                continue
            if not candidate.exists():
                continue
            try:
                with open(candidate, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except Exception:
                continue
            url = (data.get("supabase_url") or "").strip()
            key = (data.get("supabase_anon_key") or "").strip()
            if url and key:
                if not cfg.get("supabase_url"):
                    cfg["supabase_url"] = url
                    had_credentials_from_fallback = True
                if not cfg.get("supabase_anon_key"):
                    cfg["supabase_anon_key"] = key
                    had_credentials_from_fallback = True
                break  # first fallback with both keys wins
        if had_credentials_from_fallback:
            break
    # Persist the recovered credentials to the canonical path so the
    # next launch (and the next heartbeat tick) finds them locally
    # without walking the fallback chain again.
    if had_credentials_from_fallback:
        try:
            _save_users_config(cfg)
        except Exception:
            pass
    return cfg


# ---------------------------------------------------------------------------
# Device UUID
# ---------------------------------------------------------------------------
_KEYRING_SERVICE = "neurax_launcher"
_KEYRING_USER = "device_uuid"


def _load_uuid_from_keyring() -> Optional[str]:
    if not _KEYRING_OK:
        return None
    try:
        v = keyring.get_password(_KEYRING_SERVICE, _KEYRING_USER)
        if v:
            return v.strip()
    except Exception:
        return None
    return None


def _store_uuid_in_keyring(device_uuid: str) -> None:
    if not _KEYRING_OK:
        return
    try:
        keyring.set_password(_KEYRING_SERVICE, _KEYRING_USER, device_uuid)
    except Exception:
        pass


def _load_uuid_from_file() -> Optional[str]:
    p = _project_root() / "device_uuid.txt"
    if p.exists():
        try:
            v = p.read_text(encoding="utf-8").strip()
            if v:
                return v
        except Exception:
            return None
    return None


def _store_uuid_in_file(device_uuid: str) -> None:
    p = _project_root() / "device_uuid.txt"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(device_uuid, encoding="utf-8")
    except Exception:
        pass


def _clear_uuid_from_keyring() -> None:
    """Best-effort: drop the keychain entry so a regenerated UUID
    can take its place. Failures are ignored (some Windows sessions
    can't write to the credential store at all)."""
    if not _KEYRING_OK:
        return
    try:
        keyring.delete_password(_KEYRING_SERVICE, _KEYRING_USER)
    except Exception:
        pass


def _clear_uuid_from_file() -> None:
    """Best-effort: remove the sidecar file so get_or_create_device_uuid()
    will generate a fresh value on its next call."""
    p = _project_root() / "device_uuid.txt"
    try:
        if p.exists():
            p.unlink()
    except Exception:
        pass


def force_regenerate_device_uuid() -> str:
    """Discard the persisted UUID and mint a fresh one.

    Called when the launcher learns (via the ``recycled`` flag in
    the beat() response) that its current UUID is older than the
    1-month staleness threshold on the server. Wipes both the
    keychain entry and the sidecar file, then writes a fresh uuid4
    into both storage locations and returns it.
    """
    _clear_uuid_from_keyring()
    _clear_uuid_from_file()
    new_uuid = str(uuid.uuid4())
    _store_uuid_in_keyring(new_uuid)
    _store_uuid_in_file(new_uuid)
    return new_uuid


def get_or_create_device_uuid() -> str:
    """Return this device's persistent UUID, generating one on first call.

    Storage order: OS keychain -> users_config.json -> device_uuid.txt.
    Once written, the UUID is never rotated by this code path.
    Use :func:`force_regenerate_device_uuid` to deliberately rotate
    (e.g. when the server reports a 1-month-stale UUID).
    """
    # 1. Keychain.
    v = _load_uuid_from_keyring()
    if v:
        return v
    # 2. Sidecar file (most reliable cross-platform).
    v = _load_uuid_from_file()
    if v:
        # Promote to keychain opportunistically.
        _store_uuid_in_keyring(v)
        return v
    # 3. Generate.
    new_uuid = str(uuid.uuid4())
    _store_uuid_in_keyring(new_uuid)
    _store_uuid_in_file(new_uuid)
    return new_uuid


# ---------------------------------------------------------------------------
# users_config.json — Supabase URL + anon key, no API key required at runtime
# ---------------------------------------------------------------------------
_DEFAULT_USERS_CONFIG: Dict[str, Any] = {
    "supabase_url": "",
    "supabase_anon_key": "",
    "heartbeat_interval_seconds": 5,  # chip auto-refreshes + heartbeat fires every 5s
    "offline_mode": False,
}


def _save_users_config(cfg: Dict[str, Any]) -> None:
    p = _users_config_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=2)
    except Exception:
        pass


def configure_supabase(supabase_url: str, supabase_anon_key: str) -> None:
    """Persist Supabase credentials. URL + anon key only; no service_role key."""
    cfg = _load_users_config()
    cfg["supabase_url"] = (supabase_url or "").strip()
    cfg["supabase_anon_key"] = (supabase_anon_key or "").strip()
    cfg["offline_mode"] = False
    _save_users_config(cfg)


def set_offline_mode(offline: bool) -> None:
    cfg = _load_users_config()
    cfg["offline_mode"] = bool(offline)
    _save_users_config(cfg)


def get_users_config() -> Dict[str, Any]:
    """Public config reader. Walks the fallback paths so a launcher
    that just had its ``%APPDATA%\\.neurax\\users_config.json`` deleted
    (or never had one) still picks up credentials from the
    project-root ``nx_config.json`` / ``users_config.json``.

    Returns the merged dict that includes every
    ``_DEFAULT_USERS_CONFIG`` key (URL, anon key, interval, etc.).
    Callers that need the raw file can call :func:`_load_users_config`.
    """
    return _load_effective_users_config()


# ---------------------------------------------------------------------------
# Telemetry assembly
# ---------------------------------------------------------------------------
_LAUNCHER_VERSION = "4.0.0"


def _safe_call(fn: Callable[[], Any], default: Any = None) -> Any:
    try:
        return fn()
    except Exception:
        return default


def assemble_heartbeat_payload() -> Dict[str, Any]:
    """Build the payload to send to Supabase. Best-effort: any failure in a
    sub-collector results in a sensible default, never a crash."""
    device_id = get_or_create_device_uuid()
    payload: Dict[str, Any] = {
        "device_id": device_id,
        "os": f"{platform.system()} {platform.release()}",
        "launcher_version": _LAUNCHER_VERSION,
        "instance_count": 0,
        "mod_count": 0,
        "total_playtime_seconds": 0,
        "instance_names": [],
        "instance_mods": {},
        "online": True,
    }

    # Pull instances + playtime from the launcher's own modules if available.
    try:
        from neurax.core.config import ConfigManager
        cfg = ConfigManager()
        analytics = cfg.get("analytics", {}) or {}
        total_seconds = 0
        for _inst, data in analytics.items():
            if isinstance(data, dict):
                total_seconds += int(data.get("total_seconds", 0) or 0)
        payload["total_playtime_seconds"] = total_seconds
    except Exception:
        pass

    try:
        from neurax.core.config import get_dot_neurax_dir
        from neurax.core.instances import InstanceManager
        mgr = InstanceManager(get_dot_neurax_dir() / "instances")
        instances = mgr.list_instances()
        payload["instance_count"] = len(instances)
        names = []
        mods_total = 0
        per_instance: Dict[str, List[str]] = {}
        for inst in instances:
            folder = inst.get("folder_name") or inst.get("name") or "unknown"
            names.append(folder)
            mods_dir = Path(inst.get("game_dir", "")) / "mods"
            slugs: List[str] = []
            if mods_dir.exists():
                for jar in mods_dir.glob("*.jar"):
                    # minecraft-mod filenames are typically like
                    #   "fabric-api-0.92.0.jar" or "modid-1.2.3.jar"
                    stem = jar.stem
                    parts = stem.split("-")
                    # Heuristic: drop trailing version-looking tokens.
                    while parts and parts[-1][0:1].isdigit():
                        parts.pop()
                    slug = "-".join(parts) if parts else stem
                    slugs.append(slug)
                    mods_total += 1
            per_instance[folder] = sorted(slugs)
        payload["instance_names"] = sorted(names)
        payload["instance_mods"] = per_instance
        payload["mod_count"] = mods_total
    except Exception:
        # The data fields stay at their default zeros; the heartbeat still
        # sends, so the user stays in the online counter.
        pass

    return payload


# ---------------------------------------------------------------------------
# CommunityClient — Supabase REST + Qt signals
# ---------------------------------------------------------------------------
class CommunityClient:
    """Thin synchronous wrapper around the Supabase REST endpoint. Heavy
    work is meant to run on a QThread; the wrapper itself is just
    request/response glue so it stays testable."""

    def __init__(self, supabase_url: str, supabase_anon_key: str,
                 timeout: int = 6):
        self.supabase_url = (supabase_url or "").rstrip("/")
        self.supabase_anon_key = supabase_anon_key or ""
        self.timeout = timeout

    def is_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_anon_key and _REQUESTS_OK)

    def _headers(self) -> Dict[str, str]:
        return {
            "apikey": self.supabase_anon_key,
            "Authorization": f"Bearer {self.supabase_anon_key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        }

    def _url(self, path: str, query: str = "") -> str:
        return f"{self.supabase_url}/rest/v1/{path}{query}"

    def beat(self, payload: Dict[str, Any], *, rotate_on_recycle: bool = True) -> Optional[Dict[str, Any]]:
        """Single send+receive round trip against the v2 ``beat()``
        RPC. Returns the full response payload on success
        (``{self, counters, recent, flags, recycled}``) or ``None`` on failure.

        This is the only call nx.py and the launcher make on their
        timer. Everything they need (lock state, online count, feature
        flags, recent community activity) comes back in the same
        response — no extra GETs, no race window.

        If the server reports ``recycled=true`` (meaning our UUID's row
        was older than the 1-month staleness threshold and got purged),
        we rotate the local UUID and re-call beat() once with the new
        id so the response we hand back to callers always reflects the
        UUID that's now live on the server. Pass
        ``rotate_on_recycle=False`` from one-shot smoke tests that
        don't want the rotation side-effect.
        """
        if not self.is_configured():
            self.last_status = 0
            self.last_error = "not configured"
            return None
        rpc_url = f"{self.supabase_url}/rest/v1/rpc/beat"
        rpc_body = {
            "p_device_id":              payload.get("device_id", ""),
            "p_os":                     payload.get("os", "") or "",
            "p_launcher_version":       payload.get("launcher_version", "") or "",
            "p_instance_count":         int(payload.get("instance_count", 0) or 0),
            "p_mod_count":              int(payload.get("mod_count", 0) or 0),
            "p_total_playtime_seconds": int(payload.get("total_playtime_seconds", 0) or 0),
            "p_instance_names":         payload.get("instance_names", []) or [],
            "p_instance_mods":          payload.get("instance_mods", {}) or {},
            "p_display_name":           payload.get("display_name", "") or "",
            "p_country":                payload.get("country", "") or "",
        }
        try:
            r = requests.post(
                rpc_url,
                json=rpc_body,
                headers=self._headers(),
                timeout=self.timeout,
            )
        except Exception as e:
            self.last_status = 0
            self.last_error = str(e)
            return None

        self.last_status = r.status_code
        if not (200 <= r.status_code < 300):
            self.last_error = (r.text or "")[:300]
            return None
        try:
            body = r.json()
        except Exception as e:
            self.last_error = f"decode error: {e}"
            return None
        if not isinstance(body, dict):
            self.last_error = "unexpected response shape"
            return None

        # Cache the parts callers want to read without re-parsing.
        self.last_beat = body
        self.last_error = ""
        try:
            self_self = body.get("self") or {}
            self.last_locked = bool(self_self.get("is_locked", False))
            self.last_lock_message = str(self_self.get("lock_message", "") or "")
        except Exception:
            pass

        # 1-month UUID recycle. If our row was stale and got dropped,
        # the server tells us via recycled=true. We then mint a new
        # UUID locally and re-fire beat() once so the response we
        # return reflects the identity that's now live on the server.
        # Guarded against infinite recursion via the
        # _rotate_in_progress flag set by force_regenerate_device_uuid.
        if (
            rotate_on_recycle
            and body.get("recycled") is True
            and not getattr(self, "_rotate_in_progress", False)
        ):
            try:
                new_uuid = force_regenerate_device_uuid()
            except Exception:
                return body
            new_payload = dict(payload)
            new_payload["device_id"] = new_uuid
            self._rotate_in_progress = True
            try:
                rotated = self.beat(new_payload, rotate_on_recycle=False)
                if rotated is not None:
                    return rotated
            finally:
                self._rotate_in_progress = False
        return body

    def send_heartbeat(self, payload: Dict[str, Any]) -> bool:
        """Compatibility shim around :meth:`beat`. Returns True on
        success.

        Callers that want the full response (lock state, counters,
        feature flags) should call :meth:`beat` directly and inspect
        ``client.last_beat``.
        """
        return self.beat(payload) is not None

    def needs_table(self) -> bool:
        """True if the last response was 404 / PGRST205 (table missing)."""
        try:
            return int(getattr(self, "last_status", 0)) == 404
        except Exception:
            return False

    def set_offline(self, device_id: str) -> bool:
        """Mark this device offline (called on graceful shutdown).

        Tries the ``set_offline(text)`` RPC first (security definer,
        so it always has permission), then falls back to a direct
        ``PATCH /rest/v1/heartbeats?device_id=eq.<id>`` for users on
        the older schema.
        """
        if not self.is_configured():
            return False
        # 1. RPC.
        try:
            r = requests.post(
                f"{self.supabase_url}/rest/v1/rpc/set_offline",
                json={"p_device_id": device_id},
                headers=self._headers(),
                timeout=self.timeout,
            )
            if 200 <= r.status_code < 300:
                self.last_status = r.status_code
                self.last_error = ""
                return True
            if r.status_code != 404:
                self.last_status = r.status_code
                self.last_error = (r.text or "")[:300]
                return False
        except Exception:
            # RPC errored — fall through to REST.
            pass
        # 2. REST fallback.
        try:
            r = requests.patch(
                self._url("heartbeats", query=f"?device_id=eq.{device_id}"),
                json={"online": False, "last_seen": datetime.now(timezone.utc).isoformat()},
                headers=self._headers(),
                timeout=self.timeout,
            )
            self.last_status = r.status_code
            self.last_error = "" if 200 <= r.status_code < 300 else (r.text or "")[:300]
            return 200 <= r.status_code < 300
        except Exception as e:
            self.last_status = 0
            self.last_error = str(e)
            return False

    def check_lock_status(self, device_id: str) -> Dict[str, Any]:
        """Fetch this device's lock state from Supabase.

        Returns ``{"locked": bool, "message": str, "locked_at": str,
        "locked_by": str}``. Defaults to "not locked" if the device row
        doesn't exist yet or the network fails. The launcher calls this
        on every heartbeat so a lock applied from `nx.py` takes effect
        within ~10 seconds.

        Note: the underlying PostgreSQL column is `is_locked` (not
        `locked`) because `LOCKED` is a reserved SQL keyword. The Python
        dict shape keeps the friendlier `locked`/`locked_at`/`locked_by`
        keys for the UI.
        """
        out = {"locked": False, "message": "", "locked_at": "", "locked_by": ""}
        if not self.is_configured() or not device_id:
            return out
        try:
            r = requests.get(
                self._url(
                    "heartbeats",
                    query=f"?select=is_locked,lock_message,lock_at,lock_by&device_id=eq.{device_id}&limit=1",
                ),
                headers=self._headers(),
                timeout=self.timeout,
            )
            if not (200 <= r.status_code < 300):
                return out
            rows = r.json() or []
            if not rows:
                return out
            row = rows[0]
            return {
                "locked": bool(row.get("is_locked", False)),
                "message": (row.get("lock_message") or "").strip(),
                "locked_at": row.get("lock_at") or "",
                "locked_by": row.get("lock_by") or "",
            }
        except Exception:
            return out

    def fetch_counters(self) -> Dict[str, Any]:
        """Return the cached counters from the most recent ``beat()``
        round trip, or fall back to a live GET against the
        ``community_online_count`` view when no cache is available.

        The v2 schema's ``beat()`` RPC returns the community counters
        inline in the same response, so the chip and dashboard
        usually don't need a separate GET. But the chip's own
        ``_refresh`` runs on a 5-minute timer that constructs a
        *fresh* ``CommunityClient`` every time — a fresh client has
        no ``last_beat`` cache, so before this fallback the chip
        always painted itself as "0 online" right after a successful
        beat, because ``fetch_counters()`` returned an empty dict
        from the empty cache.

        Cache-first behaviour (read ``self.last_beat`` when present)
        is preserved. Only when the cache is missing do we hit the
        network. On failure, returns an empty counters dict so the
        chip can show "offline" instead of a stale zero.
        """
        empty = {"online_count": 0, "total_count": 0, "recent": []}
        last = getattr(self, "last_beat", None)
        if last and isinstance(last, dict):
            counters = last.get("counters") or {}
            recent = last.get("recent") or []
            return {
                "online_count": int(counters.get("online_count", 0) or 0),
                "total_count": int(counters.get("total_count", 0) or 0),
                "locked_count": int(counters.get("locked_count", 0) or 0),
                "country_count": int(counters.get("country_count", 0) or 0),
                "recent": list(recent[:25]),
                "via_cache": True,
            }
        # No cache — fall back to a real GET against the
        # community_online_count view. This is exactly one extra
        # round trip on a fresh client and zero on the steady state.
        if not self.is_configured() or not _REQUESTS_OK:
            return empty
        try:
            r = requests.get(
                self._url("community_online_count", "?select=online_count,total_count,locked_count,country_count"),
                headers=self._headers(),
                timeout=self.timeout,
            )
            self.last_status = r.status_code
            if not (200 <= r.status_code < 300):
                self.last_error = (r.text or "")[:300]
                return empty
            data = r.json()
            if not isinstance(data, list) or not data:
                return empty
            row = data[0] if isinstance(data[0], dict) else {}
            return {
                "online_count": int(row.get("online_count", 0) or 0),
                "total_count": int(row.get("total_count", 0) or 0),
                "locked_count": int(row.get("locked_count", 0) or 0),
                "country_count": int(row.get("country_count", 0) or 0),
                "recent": [],
                "via_cache": False,
            }
        except Exception as e:
            self.last_status = 0
            self.last_error = f"{type(e).__name__}: {e}"
            return empty


# ---------------------------------------------------------------------------
# CommunityWorker — QThread that drives the heartbeat
# ---------------------------------------------------------------------------
try:
    from PyQt6.QtCore import QObject, QThread, pyqtSignal
    _PYQT_OK = True
except Exception:
    _PYQT_OK = False


if _PYQT_OK:
    class CommunityWorker(QObject):
        """Lives on a QThread; emits signals when heartbeats complete."""

        heartbeat_ok = pyqtSignal()
        heartbeat_failed = pyqtSignal(str)
        counters_ready = pyqtSignal(dict)
        # Emitted every time we re-check the lock state. UI listens for
        # this to show / hide the lock screen overlay.
        lock_state_ready = pyqtSignal(dict)

        def __init__(self, client: CommunityClient):
            super().__init__()
            self.client = client
            self._last_payload: Optional[Dict[str, Any]] = None

        def on_thread_start(self):
            """Slot called when the QThread starts."""
            self.send_heartbeat()
            self.fetch_counters()
            self.check_lock()

        def send_heartbeat(self):
            # Re-check the lock state *first* — if the device is locked
            # we must NOT send a heartbeat (the launcher must show as
            # offline and the lock must not be silently cleared by a
            # stray upsert).
            if self._last_payload:
                try:
                    st = self.client.check_lock_status(self._last_payload.get("device_id", ""))
                    self.lock_state_ready.emit(st)
                    if st.get("locked"):
                        # Still fetch counters so the chip stays fresh.
                        try:
                            self.fetch_counters()
                        except Exception:
                            pass
                        return
                except Exception:
                    pass
            payload = assemble_heartbeat_payload()
            self._last_payload = payload
            if self.client.send_heartbeat(payload):
                self.heartbeat_ok.emit()
            else:
                status = int(getattr(self.client, "last_status", 0) or 0)
                err = (getattr(self.client, "last_error", "") or "").strip()
                if status == 404:
                    msg = "Supabase returned 404 — the 'heartbeats' table doesn't exist yet. Run the setup SQL in your Supabase project's SQL editor."
                elif status == 401:
                    msg = "Supabase rejected the API key (401). Re-check the project URL and the publishable/anon key."
                elif status == 0:
                    msg = "Could not reach Supabase — check your internet connection."
                else:
                    msg = f"Heartbeat failed (HTTP {status}): {err[:160]}" if err else f"Heartbeat failed (HTTP {status})"
                self.heartbeat_failed.emit(msg)

        def check_lock(self):
            """Standalone lock check — exposed so the UI can poll more
            often than the heartbeat cadence if it wants."""
            device_id = ""
            try:
                device_id = get_or_create_device_uuid()
            except Exception:
                device_id = ""
            if not device_id:
                self.lock_state_ready.emit({"locked": False, "message": "", "locked_at": "", "locked_by": ""})
                return
            try:
                st = self.client.check_lock_status(device_id)
                self.lock_state_ready.emit(st)
            except Exception:
                self.lock_state_ready.emit({"locked": False, "message": "", "locked_at": "", "locked_by": ""})

        def fetch_counters(self):
            data = self.client.fetch_counters()
            self.counters_ready.emit(data)

        def mark_offline(self):
            if not self._last_payload:
                return
            self.client.set_offline(self._last_payload.get("device_id", ""))


# ---------------------------------------------------------------------------
# Backward-compatible shim that app.py already calls
# ---------------------------------------------------------------------------
def bootstrap_users_config() -> bool:
    """Mirror Supabase credentials from the workspace into the runtime
    users_config.json if they're missing there.

    The chip and the heartbeat path both read from the canonical
    ``%APPDATA%/.neurax/users_config.json`` file. A user who has set up
    the workspace ``nx_config.json`` (e.g. via the standalone dashboard
    in ``nx.py``) but never copied those credentials into the runtime
    location would otherwise see a permanent "offline" badge. This
    helper runs once at app startup and quietly copies the credentials
    over so the chip has a chance of going green on first launch.

    The merge is one-way (workspace -> runtime) and never overwrites a
    non-empty value in the runtime file, so a user who deliberately
    blanked their runtime config won't get it back without their say-so.
    """
    try:
        canonical = _load_users_config()
        if canonical.get("supabase_url") and canonical.get("supabase_anon_key"):
            return False
        # Look for credentials in any of the workspace-level fallback paths.
        base = _project_root()
        for rel in _EXTRA_CONFIG_FALLBACK_PATHS:
            try:
                cand = (base / rel).resolve()
            except Exception:
                continue
            if not cand.exists():
                continue
            try:
                with open(cand, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except Exception:
                continue
            url = (data.get("supabase_url") or "").strip()
            key = (data.get("supabase_anon_key") or "").strip()
            if url and key:
                merged = dict(canonical)
                if not merged.get("supabase_url"):
                    merged["supabase_url"] = url
                if not merged.get("supabase_anon_key"):
                    merged["supabase_anon_key"] = key
                _save_users_config(merged)
                return True
        return False
    except Exception:
        return False


def update_users_file() -> bool:
    """Sync update entry point. Kept for `app.py`'s existing import.

    Performs one heartbeat + counter fetch synchronously. Returns True on
    success. Safe to call when Supabase is not configured (returns False,
    no exception).

    Locking gate:
        Before sending a heartbeat we re-check `check_lock_status()`.
        If the device is locked we *deliberately do not* send a heartbeat
        (the launcher's lock overlay is already up and the lock must not
        be cleared by the launcher). The launcher UI reads the lock
        state via the `CommunityWorker.lock_state_ready` signal.
    """
    try:
        cfg = _load_users_config()
        if cfg.get("offline_mode"):
            return False
        client = CommunityClient(cfg.get("supabase_url", ""), cfg.get("supabase_anon_key", ""))
        if not client.is_configured():
            return False
        # Even though `assemble_heartbeat_payload` is cheap, we still
        # want to skip it when the device is locked — the launcher on a
        # locked device must not appear "online" in the counters view.
        try:
            device_id = get_or_create_device_uuid()
        except Exception:
            device_id = ""
        if device_id:
            try:
                st = client.check_lock_status(device_id)
                if st.get("locked"):
                    return False
            except Exception:
                # Network error during lock check — fall through and
                # send the heartbeat as usual. A momentary outage must
                # not freeze the launcher; the next heartbeat will
                # re-check.
                pass
        payload = assemble_heartbeat_payload()
        return client.send_heartbeat(payload)
    except Exception:
        return False


def is_current_device_locked() -> Dict[str, Any]:
    """Synchronous helper the launcher calls on every UI tick to decide
    whether to show the lock overlay. Same return shape as
    `CommunityClient.check_lock_status`.
    """
    try:
        cfg = _load_users_config()
        if cfg.get("offline_mode"):
            return {"locked": False, "message": "", "locked_at": "", "locked_by": ""}
        client = CommunityClient(cfg.get("supabase_url", ""), cfg.get("supabase_anon_key", ""))
        if not client.is_configured():
            return {"locked": False, "message": "", "locked_at": "", "locked_by": ""}
        device_id = get_or_create_device_uuid()
        if not device_id:
            return {"locked": False, "message": "", "locked_at": "", "locked_by": ""}
        return client.check_lock_status(device_id)
    except Exception:
        return {"locked": False, "message": "", "locked_at": "", "locked_by": ""}


# ---------------------------------------------------------------------------
# PyQt6 Community View
# ---------------------------------------------------------------------------
if _PYQT_OK:
    from PyQt6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
        QScrollArea, QGridLayout, QSizePolicy, QApplication, QMessageBox,
    )
    from PyQt6.QtCore import Qt, QTimer, QThread, QPropertyAnimation
    from PyQt6.QtGui import QColor, QFont, QCursor
    try:
        from neurax.gui.widgets.glass_card import GlassCard
    except Exception:
        GlassCard = QFrame  # type: ignore
    try:
        from neurax.gui.icons import IconEngine
    except Exception:
        class _IconFallback:
            @staticmethod
            def get_icon(name, color, hover, size):
                return None
            @staticmethod
            def get_pixmap(name, color, size):
                return None
        IconEngine = _IconFallback()

    class CommunityView(QWidget):
        """Full PyQt6 view showing community stats and the device UUID.

        Layout:
            ┌─ Your Device (GlassCard) ───────────────────────┐
            │  Device UUID (mono)                             │
            │  Last heartbeat, OS, launcher version           │
            │  [Send heartbeat] [Toggle offline]              │
            └─────────────────────────────────────────────────┘
            ┌─ Community (GlassCard) ─────────────────────────┐
            │  Online: 12   Total: 4,328                      │
            │  [Refresh]  Auto-refresh every 5 min            │
            │  Recent activity list (scrollable)              │
            └─────────────────────────────────────────────────┘
        """

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setObjectName("CommunityViewRoot")
            self.worker = None
            self.thread = None
            self._build_ui()
            self._start_worker()

        def _build_ui(self):
            outer = QVBoxLayout(self)
            outer.setContentsMargins(20, 20, 20, 20)
            outer.setSpacing(15)

            title = QLabel("NeuraX Community")
            title.setStyleSheet("font-size: 22px; font-weight: bold;")
            outer.addWidget(title)
            subtitle = QLabel("Live online user stats from the NeuraX network.")
            subtitle.setStyleSheet("font-size: 12px; color: #94A3B8;")
            outer.addWidget(subtitle)

            # ---------- Your Device card ----------
            device_card = GlassCard() if GlassCard is not QFrame else QFrame()
            device_card.setObjectName("ModrinthCard")
            dv = QVBoxLayout(device_card)
            dv.setContentsMargins(18, 14, 18, 14)
            dv.setSpacing(8)

            dh = QHBoxLayout()
            dh_lbl = QLabel("YOUR DEVICE")
            dh_lbl.setStyleSheet("font-size: 12px; font-weight: 800; letter-spacing: 1px; color: #00F0FF;")
            dh.addWidget(dh_lbl)
            dh.addStretch()
            self.device_online_badge = QLabel("OFFLINE")
            self.device_online_badge.setStyleSheet(
                "background-color: rgba(255, 51, 102, 0.15);"
                "color: #FF3366; border: 1px solid rgba(255, 51, 102, 0.4);"
                "border-radius: 4px; padding: 2px 8px; font-size: 10px; font-weight: 800;"
            )
            dh.addWidget(self.device_online_badge)
            dv.addLayout(dh)

            self.device_uuid_lbl = QLabel(get_or_create_device_uuid())
            self.device_uuid_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.device_uuid_lbl.setStyleSheet(
                "font-family: 'Consolas', 'Courier New', monospace; font-size: 12px;"
                "color: #00FF99; padding: 6px; background: rgba(0, 255, 153, 0.06);"
                "border: 1px solid rgba(0, 255, 153, 0.2); border-radius: 4px;"
            )
            dv.addWidget(self.device_uuid_lbl)

            self.device_meta_lbl = QLabel("Heartbeat: never  •  OS: ?  •  Launcher: ?")
            self.device_meta_lbl.setStyleSheet("font-size: 11px; color: #94A3B8;")
            dv.addWidget(self.device_meta_lbl)

            btn_row = QHBoxLayout()
            self.send_btn = QPushButton("Send Heartbeat Now")
            self.send_btn.setObjectName("PrimaryButton")
            self.send_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            self.send_btn.clicked.connect(self._on_send_clicked)
            btn_row.addWidget(self.send_btn)
            btn_row.addStretch()
            dv.addLayout(btn_row)

            outer.addWidget(device_card)

            # ---------- Community counters card ----------
            count_card = GlassCard() if GlassCard is not QFrame else QFrame()
            count_card.setObjectName("ModrinthCard")
            cv = QVBoxLayout(count_card)
            cv.setContentsMargins(18, 14, 18, 14)
            cv.setSpacing(8)

            ch = QHBoxLayout()
            cl = QLabel("COMMUNITY")
            cl.setStyleSheet("font-size: 12px; font-weight: 800; letter-spacing: 1px; color: #00F0FF;")
            ch.addWidget(cl)
            ch.addStretch()
            self.refresh_btn = QPushButton("Refresh")
            self.refresh_btn.setObjectName("SecondaryButton")
            self.refresh_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            self.refresh_btn.clicked.connect(self._on_refresh_clicked)
            ch.addWidget(self.refresh_btn)
            cv.addLayout(ch)

            counters_row = QHBoxLayout()
            self.online_lbl = QLabel("—")
            self.online_lbl.setStyleSheet("font-size: 32px; font-weight: 900; color: #00FF99;")
            self.online_caption = QLabel("online")
            self.online_caption.setStyleSheet("font-size: 12px; color: #94A3B8;")
            ol_col = QVBoxLayout()
            ol_col.addWidget(self.online_lbl)
            ol_col.addWidget(self.online_caption)
            counters_row.addLayout(ol_col)
            counters_row.addSpacing(40)
            self.total_lbl = QLabel("—")
            self.total_lbl.setStyleSheet("font-size: 32px; font-weight: 900; color: #00F0FF;")
            self.total_caption = QLabel("total users")
            self.total_caption.setStyleSheet("font-size: 12px; color: #94A3B8;")
            tl_col = QVBoxLayout()
            tl_col.addWidget(self.total_lbl)
            tl_col.addWidget(self.total_caption)
            counters_row.addLayout(tl_col)
            counters_row.addStretch()
            self.status_lbl = QLabel("Offline")
            self.status_lbl.setStyleSheet("font-size: 11px; color: #94A3B8;")
            self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
            counters_row.addWidget(self.status_lbl)
            cv.addLayout(counters_row)

            outer.addWidget(count_card)

            # ---------- Recent activity ----------
            self.activity_scroll = QScrollArea()
            self.activity_scroll.setWidgetResizable(True)
            self.activity_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
            self.activity_widget = QWidget()
            self.activity_widget.setStyleSheet("background: transparent;")
            self.activity_layout = QVBoxLayout(self.activity_widget)
            self.activity_layout.setContentsMargins(0, 0, 0, 0)
            self.activity_layout.setSpacing(6)
            self.activity_layout.addStretch()
            self.activity_scroll.setWidget(self.activity_widget)
            outer.addWidget(self.activity_scroll, stretch=1)

            # Auto-refresh every 5 minutes.
            self._refresh_timer = QTimer(self)
            self._refresh_timer.setInterval(5 * 60 * 1000)
            self._refresh_timer.timeout.connect(self._on_refresh_clicked)
            self._refresh_timer.start()

        def _start_worker(self):
            cfg = _load_users_config()
            client = CommunityClient(cfg.get("supabase_url", ""), cfg.get("supabase_anon_key", ""))
            self.thread = QThread()
            self.worker = CommunityWorker(client)
            self.worker.moveToThread(self.thread)
            self.thread.started.connect(self.worker.on_thread_start)
            self.worker.heartbeat_ok.connect(self._on_heartbeat_ok)
            self.worker.heartbeat_failed.connect(self._on_heartbeat_failed)
            self.worker.counters_ready.connect(self._on_counters_ready)
            self.thread.start()
            if not client.is_configured():
                self.status_lbl.setText("Offline — Supabase URL + key not configured.")

        def set_device_uuid(self, device_uuid: str) -> None:
            """Update the YOUR DEVICE label to reflect a UUID that was
            rotated locally (e.g. after a 1-month-stale recycle).

            Called from :meth:`MainWindow._apply_telemetry_result` when
            the launcher learns the previous UUID is no longer live on
            Supabase. Safe to call with the current UUID — it's a no-op.
            """
            try:
                new_uuid = (device_uuid or "").strip()
                if not new_uuid:
                    return
                cur = self.device_uuid_lbl.text().strip() if self.device_uuid_lbl else ""
                if new_uuid == cur:
                    return
                self.device_uuid_lbl.setText(new_uuid)
            except Exception:
                pass

        def _on_send_clicked(self):
            if self.worker:
                self.worker.send_heartbeat()

        def _on_refresh_clicked(self):
            if self.worker:
                self.worker.fetch_counters()

        def _on_heartbeat_ok(self):
            self._set_device_badge(True)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur = self.device_meta_lbl.text()
            base = cur.split("  •  ")[0]
            os_part = f"  •  OS: {platform.system()} {platform.release()}" if "OS:" in cur else cur
            if "OS:" not in cur:
                os_part = f"  •  OS: {platform.system()} {platform.release()}"
            self.device_meta_lbl.setText(f"Heartbeat: {ts}  •  OS: {platform.system()} {platform.release()}  •  Launcher: {_LAUNCHER_VERSION}")

        def _on_heartbeat_failed(self, msg: str):
            self._set_device_badge(False)
            # Binary offline — keep the message short. The chip on the
            # nav bar already says "offline", so the view only adds the
            # last update time once a fresh beat lands again.
            self.status_lbl.setText("Offline")

        def _on_counters_ready(self, data: dict):
            online = int(data.get("online_count", 0) or 0)
            total = int(data.get("total_count", 0) or 0)
            self.online_lbl.setText(f"{online:,}")
            self.total_lbl.setText(f"{total:,}")
            self.status_lbl.setText(f"Last updated: {datetime.now().strftime('%H:%M:%S')}")
            self._render_activity(data.get("recent", []) or [])

        def _set_device_badge(self, online: bool):
            if online:
                self.device_online_badge.setText("ONLINE")
                self.device_online_badge.setStyleSheet(
                    "background-color: rgba(0, 255, 153, 0.15);"
                    "color: #00FF99; border: 1px solid rgba(0, 255, 153, 0.4);"
                    "border-radius: 4px; padding: 2px 8px; font-size: 10px; font-weight: 800;"
                )
            else:
                self.device_online_badge.setText("OFFLINE")
                self.device_online_badge.setStyleSheet(
                    "background-color: rgba(255, 51, 102, 0.15);"
                    "color: #FF3366; border: 1px solid rgba(255, 51, 102, 0.4);"
                    "border-radius: 4px; padding: 2px 8px; font-size: 10px; font-weight: 800;"
                )

        def _render_activity(self, recent: list):
            # Clear existing items
            while self.activity_layout.count():
                item = self.activity_layout.takeAt(0)
                w = item.widget()
                if w:
                    w.deleteLater()

            if not recent:
                lbl = QLabel("No community activity yet — invite a friend!")
                lbl.setStyleSheet("color: #94A3B8; font-size: 12px; padding: 12px;")
                self.activity_layout.addWidget(lbl)
                self.activity_layout.addStretch()
                return

            for row in recent:
                card = QFrame()
                card.setObjectName("ModrinthCard")
                card.setStyleSheet(
                    "QFrame#ModrinthCard {"
                    " background-color: rgba(14, 18, 26, 0.6);"
                    " border: 1px solid rgba(255, 255, 255, 0.06);"
                    " border-radius: 8px;"
                    " padding: 8px 12px;"
                    " }"
                )
                h = QHBoxLayout(card)
                h.setContentsMargins(0, 0, 0, 0)
                h.setSpacing(8)
                badge = QLabel("●" if row.get("online") else "○")
                badge.setStyleSheet(
                    "color: #00FF99;" if row.get("online") else "color: #64748B;"
                    " font-size: 14px;"
                )
                badge.setFixedWidth(14)
                h.addWidget(badge)
                uuid_short = (row.get("device_id", "") or "")[:8] + "…"
                dev_lbl = QLabel(uuid_short)
                dev_lbl.setStyleSheet(
                    "font-family: 'Consolas', monospace; font-size: 11px; color: #94A3B8;"
                )
                h.addWidget(dev_lbl)
                meta = QLabel(
                    f"{row.get('os', '?')}  •  {row.get('instance_count', 0)} inst  •  "
                    f"{row.get('mod_count', 0)} mods  •  "
                    f"{int(row.get('total_playtime_seconds', 0) or 0) // 3600}h playtime"
                )
                meta.setStyleSheet("font-size: 11px; color: #94A3B8;")
                h.addWidget(meta, stretch=1)
                self.activity_layout.addWidget(card)
            self.activity_layout.addStretch()

        def closeEvent(self, event):
            try:
                if self.worker:
                    self.worker.mark_offline()
            except Exception:
                pass
            try:
                if self.thread:
                    self.thread.quit()
                    self.thread.wait(2000)
            except Exception:
                pass
            super().closeEvent(event)


# ---------------------------------------------------------------------------
# Sidebar chip widget — small "Online: N" badge in the nav bar
# ---------------------------------------------------------------------------
if _PYQT_OK:
    class CommunityChip(QPushButton):
        """Tiny chip showing a binary online/offline status + click
        trigger for an on-demand beat.

        Behaviour:
          * The chip starts red ("● offline") until the first successful
            fetch completes, then flips to green ("● N online") and stays
            green for the rest of the session.
          * The chip auto-refreshes on its own timer (default 10s). A
            failed fetch flips it back to red immediately; a successful
            fetch flips it back to green. There are no intermediate
            states — no "connecting…", no "cached", no "retrying", no
            grace period.
          * Clicking the chip fires a fresh ``beat()`` round trip
            against Supabase. The main window wires this up via the
            :attr:`beat_requested` signal — the same worker that
            runs on the 10s timer handles the click. The chip
            pulses briefly as silent feedback (no popup, no
            status bar message, no dialog). Clicks within 2s of
            the previous click (or the previous timer tick) are
            debounced so a quick double-click doesn't fire two
            redundant round trips.

        The heartbeat / lock-poll in the main window keeps firing on
        its own timer regardless of the chip's visual state, so the
        network path always makes progress; the chip is purely the
        user-facing indicator.
        """

        # Emitted when the user clicks the chip. The main window
        # listens for this and runs the same _TelemetryJob worker
        # that powers the 10s timer.
        beat_requested = pyqtSignal()

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setObjectName("CommunityChip")
            # Clickable: pointing-hand cursor + a quiet pulse on click
            # so the user knows something happened.
            self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            # Default to "offline" so the chip is *never* blank.
            # The first fetch will overwrite this on the next event-loop
            # tick if the backend is reachable.
            self.setText("\u2022 offline")
            self.setToolTip(
                "Live online count from the NeuraX Community backend.\n"
                "Click to send a fresh beat and refresh the count."
            )
            self._apply_style("offline")
            self._client = None
            self._last_state: str = "offline"
            self._last_error: str = ""
            self._last_online_count: int = 0
            # Sticky-online latch — flipped to True the first time the
            # launcher's own heartbeat round-trip is acknowledged by
            # Supabase (or nx.py sends a beat). Once set, the chip
            # stays green for the rest of the session; transient
            # counter fetches no longer flip it back to red. Without
            # this latch the user would see the chip bounce red every
            # time a single GET hiccups, which is the very thing the
            # user complained about.
            self._acknowledged: bool = False
            self._acknowledged_count: int = 0
            # Auto-refresh: honour the user's config but never go slower
            # than 5s (the launcher default — fresh chip counts on every
            # tick) and never faster than 5s (so the chip doesn't hammer
            # Supabase).
            cfg = _load_users_config()
            try:
                interval_ms = max(5_000, int(cfg.get("heartbeat_interval_seconds", 5) or 5) * 1000)
            except Exception:
                interval_ms = 5_000
            self._timer = QTimer(self)
            self._timer.setInterval(interval_ms)
            self._timer.timeout.connect(self._refresh)
            self._timer.start()
            # Fire the first fetch on the next event-loop tick so the chip
            # updates as soon as the main window is shown.
            QTimer.singleShot(0, self._refresh)

        def mark_acknowledged(self, online_count: int = 0) -> None:
            """Called by the heartbeat worker when ``send_heartbeat``
            returns ``True`` (Supabase acknowledged our beat, or nx.py
            just sent one that the launcher observed).

            Once called at least once in this session the chip stays
            green forever, regardless of subsequent counter-fetch
            failures. nx.py is the source of truth for "this device is
            online" — a single acknowledged beat is enough to prove
            the link is alive and the row is fresh.
            """
            try:
                self._acknowledged = True
                if online_count > 0:
                    self._acknowledged_count = int(online_count)
                # Paint green immediately with whatever count we know.
                self._render_online(
                    self._acknowledged_count or self._last_online_count or 0,
                    self._acknowledged_count or 0,
                )
            except Exception:
                pass

        # ------------------------------------------------------------------
        # Click handling
        # ------------------------------------------------------------------
        # Wall-clock of the most recent click / timer tick that fired a
        # beat. Used to debounce so a fast double-click doesn't dispatch
        # two redundant round trips (the 10s timer would fire shortly
        # anyway).
        _last_beat_request_ts: float = 0.0

        def mousePressEvent(self, event):
            """Handle a left-click anywhere on the chip. Debounced
            so a quick double-click only fires one beat; subsequent
            clicks within 2s are silent."""
            try:
                if event.button() == Qt.MouseButton.LeftButton:
                    self._on_click()
            finally:
                # Let QPushButton's default behaviour run too (it
                # applies the pressed/hover styles).
                super().mousePressEvent(event)

        def _on_click(self) -> None:
            """Debounced click handler. Emits ``beat_requested`` and
            pulses the chip so the user sees feedback without a
            popup, status bar message, or dialog."""
            try:
                import time as _time
                now = _time.time()
                if now - float(self._last_beat_request_ts or 0.0) < 2.0:
                    return
                self._last_beat_request_ts = now
                # Pulse the chip so the click is visibly acknowledged
                # without bothering the user with text.
                self._pulse()
                # Tell the main window to run a beat round trip.
                self.beat_requested.emit()
            except Exception:
                # Click handling is best-effort — never crash the UI
                # on a stray exception.
                pass

        def _pulse(self) -> None:
            """Briefly scale the chip up + back down to confirm the
            click registered. No text, no popup, no status bar."""
            try:
                anim = QPropertyAnimation(self, b"geometry", self)
                geom = self.geometry()
                anim.setDuration(180)
                anim.setStartValue(geom)
                anim.setKeyValueAt(0.5, geom.adjusted(-2, -1, 2, 1))
                anim.setEndValue(geom)
                anim.start()
                # Hold a reference so the animation isn't GC'd mid-flight.
                self._pulse_anim = anim
            except Exception:
                pass

        def notify_beat_dispatched(self) -> None:
            """Called by the main window right after it dispatches a
            beat worker in response to ``beat_requested``. We use it
            to (a) reset the debounce window and (b) avoid letting
            the click animation outlast the actual work."""
            try:
                import time as _time
                self._last_beat_request_ts = _time.time()
            except Exception:
                pass

        # ---------------------------------------------------------------
        # Lock-state observation
        # ---------------------------------------------------------------
        # When ``nx.py --lock`` (or its dashboard's LOCK button) flips
        # this device's ``is_locked`` flag in Supabase, the launcher's
        # next ``beat()`` round trip sees ``self.is_locked = true`` in
        # the response. The launcher doesn't have any lock UI (that's
        # exclusive to ``nx.py``) but the chip should at least reflect
        # the lock state so the user knows their launcher is locked and
        # what message the admin left — otherwise locking looks like it
        # "doesn't work" because nothing visible changes.
        #
        # The chip shows ``● locked`` in a muted red when locked, and
        # falls back to the regular ``● N online`` green pill as soon
        # as the lock clears. The lock message + admin name go on the
        # tooltip so the user has the full context.
        _last_locked: bool = False
        _last_lock_message: str = ""

        def apply_lock_state(self, is_locked: bool, lock_message: str = "") -> None:
            """Reflect this device's remote-lock state on the chip.

            Called from ``MainWindow._apply_telemetry_result`` after every
            successful ``beat()``. Sticky-green latch logic still wins —
            if the chip is acknowledged-online we don't fall through to
            offline. Locked is its own visual state.
            """
            try:
                self._last_locked = bool(is_locked)
                self._last_lock_message = str(lock_message or "")
                if self._last_locked:
                    self._render_locked(self._last_lock_message)
                else:
                    # Drop back to the green pill using whatever count
                    # we last knew about. ``_render_online`` is a no-op
                    # when ``_acknowledged`` is False, so a device that
                    # has never had a successful beat stays offline.
                    n = int(self._acknowledged_count or self._last_online_count or 0)
                    total = int(self._acknowledged_count or 0)
                    self._render_online(n, total)
            except Exception:
                pass

        def _render_locked(self, message: str) -> None:
            """Flip the chip to a muted-red "locked" pill. The pill is
            intentionally distinct from the bright-red "offline" state
            so the user knows the chip is reporting a remote lock, not
            a network problem."""
            self._last_state = "locked"
            self.setText("\u2022 locked")
            # Same shape as online/offline but a muted red so it reads
            # as "you've been locked", not "your network is broken".
            self.setStyleSheet(
                f"QPushButton#CommunityChip {{"
                f" background: transparent;"
                f" color: #B91C1C;"
                f" font-size: 11px; font-weight: 800; letter-spacing: 0.5px;"
                f" border: 1px solid rgba(185, 28, 28, 0.45);"
                f" border-radius: 10px;"
                f" padding: 3px 10px;"
                f" }}"
                f"QPushButton#CommunityChip:hover {{"
                f" background: rgba(185, 28, 28, 0.10);"
                f" }}"
            )
            tip = (
                "This launcher's device is locked by an admin.\n"
                f"Message: {(message or '(no message)').strip()[:200]}\n"
                "Unlock from the NeuraX Community Console (nx.py)."
            )
            self.setToolTip(tip)

        def _apply_style(self, state):
            """state is one of: 'online' or 'offline'."""
            palette = {
                "online":  ("#00FF99", "0, 255, 153"),
                "offline": ("#FF3366", "255, 51, 102"),
            }
            color, rgb = palette.get(state, palette["offline"])
            self.setStyleSheet(
                f"QPushButton#CommunityChip {{"
                f" background: transparent;"
                f" color: {color};"
                f" font-size: 11px; font-weight: 800; letter-spacing: 0.5px;"
                f" border: 1px solid rgba({rgb}, 0.4);"
                f" border-radius: 10px;"
                f" padding: 3px 10px;"
                f" }}"
                f"QPushButton#CommunityChip:hover {{"
                f" background: rgba({rgb}, 0.1);"
                f" }}"
            )

        def _render_online(self, n: int, total: int) -> None:
            """Flip the chip to the green online state."""
            self._last_state = "online"
            self._last_error = ""
            self._last_online_count = n
            self.setText(f"\u2022 {n:,} online")
            self._apply_style("online")
            self.setToolTip(
                "Live online count from the NeuraX Community backend\n"
                f"Total devices: {total}\n"
                "Last refresh: just now"
            )

        def _render_offline(self, reason: str) -> None:
            """Flip the chip to the red offline state.

            This is the single failure path. There is no "retrying" /
            "cached" / grace state — any failure goes straight here.
            The reason is preserved on the tooltip so the user can
            debug if they hover.
            """
            self._last_state = "offline"
            self._last_error = reason
            self.setText("\u2022 offline")
            self._apply_style("offline")
            tip = (
                "Live online count from the NeuraX Community backend\n"
                f"Last error: {reason}\n"
                "The launcher keeps retrying automatically."
            )
            if not _REQUESTS_OK:
                tip = (
                    "Live online count from the NeuraX Community backend (read-only)\n"
                    "Reason: the `requests` Python module is not installed in this launcher."
                )
            self.setToolTip(tip)

        def _refresh(self):
            """Fetch the live counter and update the chip.

            State machine:
              * user requested offline_mode -> red "offline"
              * any successful 2xx         -> green "N online"
              * any failure (4xx, 5xx,
                network, exception)        -> red "offline"
              * BUT if ``_acknowledged`` is True (some heartbeat has
                been acknowledged by Supabase in this session), we
                stay green forever. The chip no longer bounces red on
                a transient fetch failure once we've proven the link
                is alive.

            No intermediate states. The heartbeat in the main window
            keeps firing on its own timer regardless of what this
            method does.
            """
            try:
                cfg = _load_effective_users_config()
                if cfg.get("offline_mode"):
                    self._acknowledged = False
                    self._render_offline("user-set offline mode")
                    return

                url = (cfg.get("supabase_url") or "").strip()
                key = (cfg.get("supabase_anon_key") or "").strip()
                if not url or not key:
                    self._acknowledged = False
                    self._render_offline(
                        "no Supabase URL / anon key configured (run nx.py or set NX_SUPABASE_URL + NX_SUPABASE_ANON_KEY)"
                    )
                    return
                if not _REQUESTS_OK:
                    self._acknowledged = False
                    self._render_offline("`requests` module not installed")
                    return

                client = CommunityClient(url, key)
                data = client.fetch_counters()
                status = int(getattr(client, "last_status", 0) or 0)
                err = (getattr(client, "last_error", "") or "").strip()
                if status and not (200 <= status < 300):
                    # Fetch failed, but if we've already proven the
                    # link alive this session we stay green.
                    if self._acknowledged:
                        return
                    self._render_offline(err or f"HTTP {status}")
                    return
                n = int((data or {}).get("online_count", 0) or 0)
                total = int((data or {}).get("total_count", 0) or 0)
                self._render_online(n, total)
            except Exception as e:
                # Fetch threw, but if we've already proven the link
                # alive this session we stay green.
                if self._acknowledged:
                    return
                self._render_offline(f"{type(e).__name__}: {e}")
