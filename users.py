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
_SETUP_SQL = """-- NeuraX Community heartbeats table
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

drop policy if exists "anon read" on public.heartbeats;
drop policy if exists "anon upsert" on public.heartbeats;
drop policy if exists "anon update" on public.heartbeats;
create policy "anon read"   on public.heartbeats for select using (true);
create policy "anon upsert" on public.heartbeats for insert with check (true);
create policy "anon update" on public.heartbeats for update using (true);
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


def _users_config_path() -> Path:
    return _project_root() / "users_config.json"


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


def get_or_create_device_uuid() -> str:
    """Return this device's persistent UUID, generating one on first call.

    Storage order: OS keychain -> users_config.json -> device_uuid.txt.
    Once written, the UUID is never rotated by this code path.
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
    "heartbeat_interval_seconds": 300,  # 5 min
    "offline_mode": False,
}


def _load_users_config() -> Dict[str, Any]:
    p = _users_config_path()
    if not p.exists():
        return dict(_DEFAULT_USERS_CONFIG)
    try:
        with open(p, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        merged = dict(_DEFAULT_USERS_CONFIG)
        merged.update({k: v for k, v in data.items() if k in _DEFAULT_USERS_CONFIG})
        return merged
    except Exception:
        return dict(_DEFAULT_USERS_CONFIG)


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
    return _load_users_config()


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

    def send_heartbeat(self, payload: Dict[str, Any]) -> bool:
        """Upsert a heartbeat row keyed by device_id. Returns True on success."""
        if not self.is_configured():
            return False
        try:
            r = requests.post(
                self._url("heartbeats"),
                params={"on_conflict": "device_id"},
                json=payload,
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

    def needs_table(self) -> bool:
        """True if the last response was 404 / PGRST205 (table missing)."""
        try:
            return int(getattr(self, "last_status", 0)) == 404
        except Exception:
            return False

    def set_offline(self, device_id: str) -> bool:
        """Mark this device offline (called on graceful shutdown)."""
        if not self.is_configured():
            return False
        try:
            r = requests.patch(
                self._url("heartbeats", query=f"?device_id=eq.{device_id}"),
                json={"online": False, "last_seen": datetime.now(timezone.utc).isoformat()},
                headers=self._headers(),
                timeout=self.timeout,
            )
            return 200 <= r.status_code < 300
        except Exception:
            return False

    def fetch_counters(self) -> Dict[str, Any]:
        """Return a dict with `online_count` and `total_count`."""
        out = {"online_count": 0, "total_count": 0, "recent": []}
        if not self.is_configured():
            return out
        try:
            # Online = seen in the last 5 minutes. Supabase REST supports
            # the `now() - interval '5 minutes'` form via the RPC endpoint
            # but for portability we filter on a conservative ISO cutoff.
            # The backend `last_seen` is timestamptz so this works.
            cutoff = datetime.now(timezone.utc).isoformat()
            # The "last 5 min" filter: we ask for rows where last_seen > cutoff - 5m
            # using the server-side `now() - interval '5 minutes'` operator.
            online_q = (
                f"?select=device_id,os,launcher_version,instance_count,mod_count,"
                f"total_playtime_seconds,last_seen&last_seen=gt.{(cutoff[:19])}Z"
            )
            # The above filter isn't reliable for relative math; use a
            # server-side filter instead. Supabase PostgREST supports
            # `now() - interval` via the `and=` operator with a separate
            # server-side function, but the simplest portable approach is
            # to fetch the last N rows and filter client-side. The
            # heartbeats table will rarely exceed a few thousand rows.
            r = requests.get(
                self._url("heartbeats", "?select=device_id,os,last_seen,instance_count,mod_count,total_playtime_seconds&order=last_seen.desc&limit=500"),
                headers=self._headers(),
                timeout=self.timeout,
            )
            self.last_status = r.status_code
            self.last_error = "" if 200 <= r.status_code < 300 else (r.text or "")[:300]
            if not (200 <= r.status_code < 300):
                return out
            rows = r.json() or []
            from datetime import timedelta
            threshold = datetime.now(timezone.utc) - timedelta(minutes=5)
            online = 0
            recent: List[Dict[str, Any]] = []
            for row in rows:
                ls = row.get("last_seen")
                is_online = False
                if ls:
                    try:
                        # Strip trailing Z, treat as UTC
                        ls_dt = datetime.fromisoformat(ls.replace("Z", "+00:00"))
                        is_online = ls_dt >= threshold
                    except Exception:
                        is_online = False
                if is_online:
                    online += 1
                recent.append({
                    "device_id": row.get("device_id", ""),
                    "os": row.get("os", ""),
                    "online": is_online,
                    "instance_count": row.get("instance_count", 0),
                    "mod_count": row.get("mod_count", 0),
                    "total_playtime_seconds": row.get("total_playtime_seconds", 0),
                    "last_seen": ls or "",
                })
            out["online_count"] = online
            out["total_count"] = len({r.get("device_id") for r in rows if r.get("device_id")})
            out["recent"] = recent[:25]
            return out
        except Exception:
            return out


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

        def __init__(self, client: CommunityClient):
            super().__init__()
            self.client = client
            self._last_payload: Optional[Dict[str, Any]] = None

        def on_thread_start(self):
            """Slot called when the QThread starts."""
            self.send_heartbeat()
            self.fetch_counters()

        def send_heartbeat(self):
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
def update_users_file() -> bool:
    """Sync update entry point. Kept for `app.py`'s existing import.

    Performs one heartbeat + counter fetch synchronously. Returns True on
    success. Safe to call when Supabase is not configured (returns False,
    no exception).
    """
    try:
        cfg = _load_users_config()
        if cfg.get("offline_mode"):
            return False
        client = CommunityClient(cfg.get("supabase_url", ""), cfg.get("supabase_anon_key", ""))
        if not client.is_configured():
            return False
        payload = assemble_heartbeat_payload()
        return client.send_heartbeat(payload)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# PyQt6 Community View
# ---------------------------------------------------------------------------
if _PYQT_OK:
    from PyQt6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
        QScrollArea, QGridLayout, QSizePolicy, QApplication, QMessageBox,
    )
    from PyQt6.QtCore import Qt, QTimer, QThread
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
            self.status_lbl = QLabel("Connecting…")
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
            self.status_lbl.setText(f"Heartbeat failed: {msg}")

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
        """Tiny clickable chip showing the live online count."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setObjectName("CommunityChip")
            self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            self.setText("● —")
            self.setToolTip("Click to open the NeuraX Community view")
            self._apply_style(False)
            self._client = None
            self._timer = QTimer(self)
            self._timer.setInterval(5 * 60 * 1000)
            self._timer.timeout.connect(self._refresh)
            self._timer.start()
            # Initial async fetch.
            QTimer.singleShot(800, self._refresh)

        def _apply_style(self, online: bool):
            color = "#00FF99" if online else "#94A3B8"
            self.setStyleSheet(
                f"QPushButton#CommunityChip {{"
                f" background: transparent;"
                f" color: {color};"
                f" font-size: 11px; font-weight: 800; letter-spacing: 0.5px;"
                f" border: 1px solid rgba(0, 255, 153, 0.4);"
                f" border-radius: 10px;"
                f" padding: 3px 10px;"
                f" }}"
                f"QPushButton#CommunityChip:hover {{"
                f" background: rgba(0, 255, 153, 0.1);"
                f" }}"
            )

        def _refresh(self):
            cfg = _load_users_config()
            client = CommunityClient(cfg.get("supabase_url", ""), cfg.get("supabase_anon_key", ""))
            if not client.is_configured():
                self.setText("● offline")
                self._apply_style(False)
                return
            data = client.fetch_counters()
            n = int(data.get("online_count", 0) or 0)
            self.setText(f"● {n:,} online")
            self._apply_style(n > 0)
