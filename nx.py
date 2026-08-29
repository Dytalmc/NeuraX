"""
nx.py — NeuraX Community Console (cross-device admin UI)
========================================================
A standalone PyQt6 dashboard that shows every device that has ever checked
in to your NeuraX Community Supabase project, regardless of which machine
this script is run on. No launcher required. No local files needed
beyond `nx_config.json` (URL + key) sitting next to this script.

Run:
    pip install PyQt6 requests
    python nx.py

What you'll see:
    * Big "Online / Total / Mods / Playtime" counters across the top
    * A scrollable list of device cards, one per device_id
    * Each card shows: UUID, OS, launcher version, last seen (live countdown),
      online dot, instance folder names, per-instance mod slugs, total playtime
    * Auto-refreshes every 10s for the online counters and 60s for the full list
    * "Refresh now" button + "Configure..." button if URL/key are missing
    * "Open in browser" button to jump to the SQL editor / project page

Configuration (in priority order):
    1. Environment variables  NX_SUPABASE_URL, NX_SUPABASE_ANON_KEY
    2. nx_config.json next to this script:
           {
             "supabase_url": "https://xxxxx.supabase.co",
             "supabase_anon_key": "sb_publishable_..."
           }
    3. If neither is set, the "Configure..." button in the UI lets you paste
       them, and the values are written to nx_config.json for next time.

Schema expected in Supabase (already created in the main project):
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
    create policy "anon read"   on public.heartbeats for select using (true);
    create policy "anon upsert" on public.heartbeats for insert with check (true);
    create policy "anon update" on public.heartbeats for update using (true);
"""
from __future__ import annotations

import json
import os
import sys
import time
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

try:
    from PyQt6.QtCore import Qt, QTimer, QSize
    from PyQt6.QtGui import QColor, QFont, QCursor, QIcon
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QPushButton, QFrame, QScrollArea, QGridLayout, QMessageBox,
        QInputDialog, QSizePolicy, QStatusBar,
    )
    _PYQT_OK = True
except Exception:
    _PYQT_OK = False

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
_THIS_DIR = Path(__file__).resolve().parent
_CFG_PATH = _THIS_DIR / "nx_config.json"

_LAUNCHER_ACCENT = "#00F0FF"
_ONLINE_GREEN = "#00FF99"
_OFFLINE_GREY = "#94A3B8"
_DANGER = "#FF3366"


def _load_cfg() -> Dict[str, str]:
    env_url = os.environ.get("NX_SUPABASE_URL", "").strip()
    env_key = os.environ.get("NX_SUPABASE_ANON_KEY", "").strip()
    cfg: Dict[str, str] = {}
    if _CFG_PATH.exists():
        try:
            cfg = json.loads(_CFG_PATH.read_text(encoding="utf-8")) or {}
        except Exception:
            cfg = {}
    return {
        "supabase_url": (env_url or cfg.get("supabase_url", "")).strip().rstrip("/"),
        "supabase_anon_key": (env_key or cfg.get("supabase_anon_key", "")).strip(),
    }


def _save_cfg(url: str, key: str) -> None:
    _CFG_PATH.write_text(
        json.dumps({"supabase_url": url.strip().rstrip("/"),
                    "supabase_anon_key": key.strip()},
                   indent=2),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Data layer
# ---------------------------------------------------------------------------
class NXClient:
    """Thin REST wrapper around the Supabase heartbeats table."""

    def __init__(self, supabase_url: str, supabase_anon_key: str):
        self.supabase_url = supabase_url.rstrip("/")
        self.supabase_anon_key = supabase_anon_key

    def is_configured(self) -> bool:
        return bool(self.supabase_url) and bool(self.supabase_anon_key)

    def _headers(self) -> Dict[str, str]:
        return {
            "apikey": self.supabase_anon_key,
            "Authorization": f"Bearer {self.supabase_anon_key}",
            "Content-Type": "application/json",
        }

    def _url(self, path: str, query: str = "") -> str:
        return f"{self.supabase_url}/rest/v1/{path}{query}"

    def fetch_devices(self, limit: int = 200) -> List[Dict[str, Any]]:
        """Return all devices, most recent first."""
        if not self.is_configured():
            return []
        try:
            r = requests.get(
                self._url(
                    "heartbeats",
                    f"?select=device_id,os,launcher_version,instance_count,mod_count,"
                    f"total_playtime_seconds,instance_names,instance_mods,last_seen,online"
                    f"&order=last_seen.desc&limit={int(limit)}",
                ),
                headers=self._headers(),
                timeout=15,
            )
            self.last_status = r.status_code
            self.last_error = "" if r.status_code == 200 else (r.text or "")[:200]
            if r.status_code != 200:
                return []
            return r.json() or []
        except Exception as e:
            self.last_status = 0
            self.last_error = str(e)
            return []


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------
def fmt_age(iso_ts: str) -> str:
    """Return 'just now' / '3m ago' / '2h ago' / '4d ago'."""
    if not iso_ts:
        return "never"
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
    except Exception:
        return iso_ts
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - dt
    secs = int(delta.total_seconds())
    if secs < 0:
        return "just now"
    if secs < 60:
        return f"{secs}s ago"
    mins = secs // 60
    if mins < 60:
        return f"{mins}m ago"
    hours = mins // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"


def fmt_playtime(seconds: int) -> str:
    seconds = max(0, int(seconds or 0))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
if not _PYQT_OK:
    sys.stderr.write(
        "PyQt6 is required for nx.py. Install it with:\n"
        "    pip install PyQt6 requests\n"
    )
    sys.exit(1)


# Dark theme QSS — matches the NeuraX launcher look.
_QSS = f"""
QMainWindow, QWidget#Root {{
    background-color: #0B0F17;
    color: #E2E8F0;
}}
QLabel {{ color: #E2E8F0; }}
QLabel#HeaderTitle {{
    font-size: 20px;
    font-weight: 900;
    letter-spacing: 3px;
    color: #FFFFFF;
}}
QLabel#HeaderSub {{
    font-size: 11px;
    color: #94A3B8;
    letter-spacing: 1px;
}}
QLabel#CounterValue {{
    font-size: 30px;
    font-weight: 900;
}}
QLabel#CounterCaption {{
    font-size: 11px;
    color: #94A3B8;
    letter-spacing: 1px;
}}
QFrame#CounterCard {{
    background-color: #111827;
    border: 1px solid #1F2937;
    border-radius: 12px;
}}
QFrame#DeviceCard {{
    background-color: #111827;
    border: 1px solid #1F2937;
    border-radius: 12px;
}}
QFrame#DeviceCard[online="true"] {{
    border: 1px solid rgba(0, 255, 153, 0.35);
}}
QLabel#DeviceUUID {{
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 12px;
    color: #00F0FF;
}}
QLabel#Meta {{
    color: #94A3B8;
    font-size: 11px;
}}
QLabel#StatusOnline {{
    color: { _ONLINE_GREEN };
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 1px;
    background-color: rgba(0, 255, 153, 0.12);
    border: 1px solid rgba(0, 255, 153, 0.4);
    border-radius: 4px;
    padding: 2px 8px;
}}
QLabel#StatusOffline {{
    color: { _OFFLINE_GREY };
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 1px;
    background-color: rgba(148, 163, 184, 0.12);
    border: 1px solid rgba(148, 163, 184, 0.4);
    border-radius: 4px;
    padding: 2px 8px;
}}
QPushButton {{
    background-color: rgba(0, 240, 255, 0.10);
    color: { _LAUNCHER_ACCENT };
    border: 1px solid rgba(0, 240, 255, 0.4);
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 0.5px;
}}
QPushButton:hover {{
    background-color: rgba(0, 240, 255, 0.20);
}}
QPushButton:pressed {{
    background-color: rgba(0, 240, 255, 0.30);
}}
QPushButton[role="ghost"] {{
    background-color: transparent;
    color: #94A3B8;
    border: 1px solid #1F2937;
}}
QPushButton[role="ghost"]:hover {{
    color: #E2E8F0;
    border: 1px solid #374151;
}}
QScrollArea {{
    background-color: transparent;
    border: none;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 4px 2px 4px 0;
}}
QScrollBar::handle:vertical {{
    background: #1F2937;
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: #374151;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    background: none; height: 0;
}}
QStatusBar {{
    background-color: #0B0F17;
    color: #94A3B8;
    border-top: 1px solid #1F2937;
}}
"""


class DeviceCard(QFrame):
    """A single device's full snapshot: UUID, OS, instances, mods, playtime."""

    def __init__(self, row: Dict[str, Any]):
        super().__init__()
        self.setObjectName("DeviceCard")
        self.setProperty("online", "true" if row.get("online") else "false")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(8)

        # ---- Top row: UUID + online badge ----
        top = QHBoxLayout()
        uuid_lbl = QLabel(row.get("device_id", "—"))
        uuid_lbl.setObjectName("DeviceUUID")
        uuid_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        top.addWidget(uuid_lbl)
        top.addStretch()
        if row.get("online"):
            badge = QLabel("ONLINE")
            badge.setObjectName("StatusOnline")
        else:
            badge = QLabel("OFFLINE")
            badge.setObjectName("StatusOffline")
        top.addWidget(badge)
        outer.addLayout(top)

        # ---- Meta line ----
        os_ = row.get("os") or "Unknown OS"
        lv = row.get("launcher_version") or "?"
        ic = int(row.get("instance_count") or 0)
        mc = int(row.get("mod_count") or 0)
        pt = fmt_playtime(row.get("total_playtime_seconds") or 0)
        meta = QLabel(
            f"{os_}  •  Launcher {lv}  •  {ic} instance(s)  •  {mc} mod(s)  •  {pt} playtime"
        )
        meta.setObjectName("Meta")
        outer.addWidget(meta)

        sub = QLabel(
            f"Last seen: {fmt_age(row.get('last_seen', ''))}"
        )
        sub.setObjectName("Meta")
        outer.addWidget(sub)

        # ---- Instances + their mods ----
        instance_names: List[str] = row.get("instance_names") or []
        instance_mods: Dict[str, List[str]] = row.get("instance_mods") or {}

        if not instance_names:
            none_lbl = QLabel("No instances reported yet.")
            none_lbl.setObjectName("Meta")
            outer.addWidget(none_lbl)
        else:
            for folder in instance_names:
                inst_lbl = QLabel(f"▸ {folder}")
                inst_lbl.setStyleSheet(
                    "font-size: 12px; font-weight: 800; color: #FFFFFF; margin-top: 4px;"
                )
                outer.addWidget(inst_lbl)
                mods = instance_mods.get(folder) or []
                if not mods:
                    empty = QLabel("   (no mods)")
                    empty.setObjectName("Meta")
                    outer.addWidget(empty)
                else:
                    # Show up to 50 mods inline, then a "+N more" if there are more.
                    visible = mods[:50]
                    mods_text = "   " + "\n   ".join(visible)
                    if len(mods) > 50:
                        mods_text += f"\n   … and {len(mods) - 50} more"
                    mods_lbl = QLabel(mods_text)
                    mods_lbl.setObjectName("Meta")
                    mods_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                    mods_lbl.setWordWrap(True)
                    outer.addWidget(mods_lbl)


class NXWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NeuraX Community Console")
        self.resize(1080, 820)
        self.setStyleSheet(_QSS)

        cfg = _load_cfg()
        self.client = NXClient(cfg["supabase_url"], cfg["supabase_anon_key"])

        # Root
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(20, 20, 20, 12)
        v.setSpacing(14)

        # ---- Header ----
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("NEURAX COMMUNITY CONSOLE")
        title.setObjectName("HeaderTitle")
        sub = QLabel("Live view of every device on your NeuraX Community Supabase project")
        sub.setObjectName("HeaderSub")
        title_box.addWidget(title)
        title_box.addWidget(sub)
        header.addLayout(title_box)
        header.addStretch()

        self.refresh_btn = QPushButton("Refresh now")
        self.refresh_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.refresh_btn.clicked.connect(self._refresh_full)
        header.addWidget(self.refresh_btn)

        self.configure_btn = QPushButton("Configure…")
        self.configure_btn.setProperty("role", "ghost")
        self.configure_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.configure_btn.clicked.connect(self._on_configure)
        header.addWidget(self.configure_btn)

        v.addLayout(header)

        # ---- Counter cards ----
        counters = QHBoxLayout()
        counters.setSpacing(10)
        self.c_online = self._make_counter("ONLINE NOW", _ONLINE_GREEN, "0")
        self.c_total = self._make_counter("TOTAL USERS", _LAUNCHER_ACCENT, "0")
        self.c_mods = self._make_counter("TOTAL MODS", "#FACC15", "0")
        self.c_play = self._make_counter("TOTAL PLAYTIME", "#A78BFA", "0s")
        for w in (self.c_online["card"], self.c_total["card"],
                  self.c_mods["card"], self.c_play["card"]):
            counters.addWidget(w, stretch=1)
        v.addLayout(counters)

        # ---- Device list scroll area ----
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll_inner = QWidget()
        self.scroll_inner.setStyleSheet("background: transparent;")
        self.list_layout = QVBoxLayout(self.scroll_inner)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(10)
        self.list_layout.addStretch()
        self.scroll.setWidget(self.scroll_inner)
        v.addWidget(self.scroll, stretch=1)

        # ---- Status bar ----
        self.setStatusBar(QStatusBar())
        self._set_status("Initializing…")

        # ---- Timers ----
        # Counters: every 10s.
        self._counter_timer = QTimer(self)
        self._counter_timer.setInterval(10_000)
        self._counter_timer.timeout.connect(self._refresh_counters)
        self._counter_timer.start()
        # Full device list: every 60s.
        self._full_timer = QTimer(self)
        self._full_timer.setInterval(60_000)
        self._full_timer.timeout.connect(self._refresh_full)
        self._full_timer.start()

        # First loads: full list after 200ms, then counters every 5s during dev.
        QTimer.singleShot(200, self._refresh_full)
        QTimer.singleShot(800, self._refresh_counters)

        # Live "last seen" tick — every 1s, just re-renders the age labels.
        self._age_timer = QTimer(self)
        self._age_timer.setInterval(1_000)
        self._age_timer.timeout.connect(self._update_ages)
        self._age_timer.start()

        self._last_devices: List[Dict[str, Any]] = []

    def _make_counter(self, caption: str, color: str, initial: str) -> Dict[str, QWidget]:
        card = QFrame()
        card.setObjectName("CounterCard")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(2)
        val = QLabel(initial)
        val.setObjectName("CounterValue")
        val.setStyleSheet(f"color: {color};")
        cap = QLabel(caption)
        cap.setObjectName("CounterCaption")
        lay.addWidget(val)
        lay.addWidget(cap)
        return {"card": card, "value": val}

    def _set_status(self, text: str) -> None:
        self.statusBar().showMessage(text)

    # ----- Refresh paths -----
    def _refresh_full(self) -> None:
        if not self.client.is_configured():
            self._set_status("Not configured — click 'Configure…' to paste your Supabase URL + key.")
            self._render_empty()
            return
        devices = self.client.fetch_devices(limit=200)
        self._last_devices = devices
        self._render_devices(devices)
        if devices is None or self.client.last_status == 200:
            self._set_status(
                f"Loaded {len(devices)} device(s) at {datetime.now().strftime('%H:%M:%S')}"
            )
        else:
            self._set_status(
                f"Error loading devices — HTTP {self.client.last_status}: {self.client.last_error[:120]}"
            )
        # Counters update too.
        self._refresh_counters()

    def _refresh_counters(self) -> None:
        if not self.client.is_configured():
            return
        if not self._last_devices:
            # No full fetch yet — pull a minimal row set for the counters.
            self._last_devices = self.client.fetch_devices(limit=500)
            self._render_devices(self._last_devices)
        self._update_counters(self._last_devices)
        self._update_ages()

    def _update_counters(self, devices: List[Dict[str, Any]]) -> None:
        from datetime import timedelta
        threshold = datetime.now(timezone.utc) - timedelta(minutes=5)
        online = 0
        total_mods = 0
        total_play = 0
        for row in devices:
            ls = row.get("last_seen")
            if ls:
                try:
                    dt = datetime.fromisoformat(ls.replace("Z", "+00:00"))
                    if dt >= threshold:
                        online += 1
                except Exception:
                    pass
            total_mods += int(row.get("mod_count") or 0)
            total_play += int(row.get("total_playtime_seconds") or 0)
        self.c_online["value"].setText(f"{online:,}")
        self.c_total["value"].setText(f"{len(devices):,}")
        self.c_mods["value"].setText(f"{total_mods:,}")
        self.c_play["value"].setText(fmt_playtime(total_play))

    def _update_ages(self) -> None:
        # Re-render cards so the "last seen" labels tick. Cheap because we
        # just rebuild the same widgets with updated text.
        if not self._last_devices:
            return
        # Only re-render once per minute-tick to avoid label thrash.
        if not hasattr(self, "_last_age_update") or (time.time() - self._last_age_update) > 1.0:
            self._last_age_update = time.time()
            self._render_devices(self._last_devices)

    def _render_empty(self) -> None:
        self._clear_list()
        placeholder = QLabel(
            "NeuraX Community Console is not configured yet.\n\n"
            "Click 'Configure…' to paste your Supabase Project URL + anon key,\n"
            "or set NX_SUPABASE_URL and NX_SUPABASE_ANON_KEY environment variables."
        )
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setStyleSheet("color: #94A3B8; font-size: 13px; padding: 60px;")
        self.list_layout.insertWidget(0, placeholder)

    def _clear_list(self) -> None:
        while self.list_layout.count() > 1:  # keep the trailing stretch
            item = self.list_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _render_devices(self, devices: List[Dict[str, Any]]) -> None:
        self._clear_list()
        if not devices:
            placeholder = QLabel("No devices have checked in yet.")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setStyleSheet("color: #94A3B8; font-size: 13px; padding: 60px;")
            self.list_layout.insertWidget(0, placeholder)
            return
        for row in devices:
            card = DeviceCard(row)
            self.list_layout.insertWidget(self.list_layout.count() - 1, card)

    # ----- Configure dialog -----
    def _on_configure(self) -> None:
        cfg = _load_cfg()
        url, ok = QInputDialog.getText(
            self, "NeuraX Community Console",
            "Supabase Project URL\n(e.g. https://xxxxx.supabase.co):",
            text=cfg.get("supabase_url", ""),
        )
        if not ok:
            return
        key, ok = QInputDialog.getText(
            self, "NeuraX Community Console",
            "Supabase publishable / anon key:",
            text=cfg.get("supabase_anon_key", ""),
        )
        if not ok:
            return
        url = (url or "").strip().rstrip("/")
        key = (key or "").strip()
        if not url or not key:
            QMessageBox.warning(self, "NeuraX Community Console",
                                "Both URL and key are required.")
            return
        _save_cfg(url, key)
        self.client = NXClient(url, key)
        QMessageBox.information(
            self, "NeuraX Community Console",
            "Saved. Fetching devices now.",
        )
        self._refresh_full()

    # ----- Open project in browser -----
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F5:
            self._refresh_full()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("NeuraX Community Console")
    win = NXWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
