from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QTimer, QPropertyAnimation, QEasingCurve, QSize
from PyQt6.QtGui import QCursor, QColor
from neurax.gui.widgets.glass_card import GlassCard
from neurax.gui.icons import IconEngine
from neurax.core.config import ConfigManager
from neurax.core.logger import Logger
import requests
import json
import time
import hashlib
from datetime import datetime

BUCKET_ID = "01a01614-9c73-7a29-8196-7c861ed5b2c8"
ALT_BUCKET_ID = "7c861ed5b2c8"
JSONBLOB_URL = f"https://jsonblob.com/api/jsonBlob/{BUCKET_ID}"
JSONBLOB_ALT_URL = f"https://jsonblob.com/api/jsonBlob/{ALT_BUCKET_ID}"
KV_URL = JSONBLOB_URL
KV_ALT_URL = JSONBLOB_ALT_URL
KEYVALUE_XYZ_URL = f"https://keyvalue.xyz/g/{BUCKET_ID}"
KEYVALUE_XYZ_ALT_URL = f"https://keyvalue.xyz/g/{ALT_BUCKET_ID}"

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

SPECIALTIES = [
    {
        "name": "SYSTEM UPDATE",
        "icon_type": "zap",
        "color": "#00F0FF",
        "bg": "rgba(0, 240, 255, 0.12)",
        "border": "rgba(0, 240, 255, 0.35)",
        "keywords": ["update", "patch", "changelog", "system", "v1.", "v2.", "version"]
    },
    {
        "name": "MAJOR RELEASE",
        "icon_type": "sparkles",
        "color": "#A100FF",
        "bg": "rgba(161, 0, 255, 0.15)",
        "border": "rgba(161, 0, 255, 0.4)",
        "keywords": ["release", "launch", "new", "major", "feature", "edition"]
    },
    {
        "name": "MAINTENANCE",
        "icon_type": "settings",
        "color": "#FF6600",
        "bg": "rgba(255, 102, 0, 0.12)",
        "border": "rgba(255, 102, 0, 0.35)",
        "keywords": ["maintenance", "server", "downtime", "fix", "hotfix", "status", "offline"]
    },
    {
        "name": "SPECIAL EVENT",
        "icon_type": "package",
        "color": "#00FF99",
        "bg": "rgba(0, 255, 153, 0.12)",
        "border": "rgba(0, 255, 153, 0.35)",
        "keywords": ["event", "reward", "giveaway", "community", "contest", "party", "bonus"]
    },
    {
        "name": "IMPORTANT ALERT",
        "icon_type": "warning",
        "color": "#FF3366",
        "bg": "rgba(255, 51, 102, 0.12)",
        "border": "rgba(255, 51, 102, 0.35)",
        "keywords": ["alert", "urgent", "important", "warning", "security", "notice"]
    },
    {
        "name": "FEATURE HIGHLIGHT",
        "icon_type": "news",
        "color": "#FFD700",
        "bg": "rgba(255, 215, 0, 0.12)",
        "border": "rgba(255, 215, 0, 0.35)",
        "keywords": ["highlight", "tip", "guide", "mod", "skin", "launcher", "welcome"]
    }
]

def get_specialty(title_or_ann, message: str = "", ann_id: str = "") -> dict:
    if isinstance(title_or_ann, dict):
        ann = title_or_ann
        title = ann.get("title", "")
        message = ann.get("message", "")
        ann_id = ann.get("id", "")
        is_update = ann.get("update", False)
        is_major = ann.get("major", False)
    else: 
        title = title_or_ann
        is_update = False
        is_major = False

    if is_update:
        return SPECIALTIES[0]

    if is_major:
        return SPECIALTIES[1]

    allowed_specialties = SPECIALTIES[2:]
    text = f"{title} {message}".lower()
    for spec in allowed_specialties:
        if any(kw in text for kw in spec["keywords"]):
            return spec
    idx = abs(hash(ann_id or title)) % len(allowed_specialties)
    return allowed_specialties[idx]

def parse_date_to_timestamp(date_str: str) -> int:
    if not date_str or not isinstance(date_str, str):
        return 0
    date_str = date_str.strip()
    try:
        val = float(date_str)
        if val > 0:
            return int(val)
    except ValueError:
        pass
    formats = [
        "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d.%m.%Y",
        "%d-%m-%Y %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S",
        "%d-%m-%Y %H:%M", "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ",
        "%b %d, %Y", "%B %d, %Y", "%d %b %Y", "%d %B %Y"
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return int(dt.timestamp())
        except Exception:
            pass
    return 0

def format_time_ago(ts: int, date_str: str = "") -> str:
    if date_str:
        return date_str
    if not ts:
        return "Unknown Date"
    now = time.time()
    diff = now - ts
    if diff < 0:
        return time.strftime("%d-%m-%Y", time.localtime(ts))
    if diff < 60:
        return "Just now"
    elif diff < 3600:
        m = int(diff / 60)
        return f"{m}m ago"
    elif diff < 86400:
        h = int(diff / 3600)
        return f"{h}h ago"
    elif diff < 604800:
        d = int(diff / 86400)
        return f"{d}d ago"
    else:
        return time.strftime("%d-%m-%Y", time.localtime(ts))

def parse_announcements_raw(raw_data) -> list:
    if not raw_data:
        return []
    if isinstance(raw_data, str):
        try:
            data = json.loads(raw_data)
        except Exception:
            return []
    else:
        data = raw_data

    ann_list = []

    def extract_from_dict(d: dict):
        for k in ("announcements", "data", "items", "posts", "messages"):
            if k in d and isinstance(d[k], list):
                ann_list.extend(d[k])
                return
        if "title" in d or "message" in d or "date" in d:
            ann_list.append(d)

    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                extract_from_dict(item)
    elif isinstance(data, dict):
        extract_from_dict(data)

    results = []
    seen_ids = set()
    for idx, item in enumerate(ann_list):
        if isinstance(item, dict) and (item.get("title") or item.get("message") or item.get("date")):
            title = str(item.get("title") or "Untitled").strip()
            message = str(item.get("message") or "").strip()
            date_str = str(item.get("date") or "").strip()
            
            ts_raw = item.get("timestamp")
            ts = 0
            if ts_raw is not None:
                try:
                    ts = int(float(ts_raw))
                except (ValueError, TypeError):
                    ts = 0
            
            if not ts and date_str:
                ts = parse_date_to_timestamp(date_str)
            if not date_str and ts:
                date_str = time.strftime("%d-%m-%Y", time.localtime(ts))
            
            raw_id = item.get("id")
            if raw_id:
                ann_id = str(raw_id)
            else:
                ann_id = f"{ts}_{idx}_{hash(title + message + date_str)}"
            
            if ann_id in seen_ids:
                continue
            seen_ids.add(ann_id)

            is_update = bool(item.get("update", item.get("Update", item.get("UPDATE", False))))
            is_important = bool(item.get("important", item.get("Important", item.get("IMPORTANT", False))))
            is_major = bool(item.get("major", item.get("Major", item.get("MAJOR", False))))
            is_special_event = bool(item.get("special_event", item.get("SpecialEvent", item.get("SPECIAL_EVENT", False))))

            results.append({
                "id": ann_id,
                "title": title,
                "message": message,
                "timestamp": ts,
                "date": date_str,
                "update": is_update,
                "important": is_important,
                "major": is_major,
                "special_event": is_special_event
            })

    results.sort(key=lambda x: x["timestamp"], reverse=True)
    return results

class AnnouncementWorker(QThread):
    finished = pyqtSignal(bool, str, list)

    def run(self):
        endpoints = (
            KV_URL,
            KV_ALT_URL,
            f"https://kvdb.io/{ALT_BUCKET_ID}/announcements",
            KEYVALUE_XYZ_URL,
            KEYVALUE_XYZ_ALT_URL,
            f"https://api.restful-api.dev/objects/{BUCKET_ID}",
            "https://api.restful-api.dev/objects"
        )
        best_announcements = []
        max_ts = -1.0

        for url in endpoints:
            try:
                resp = requests.get(url, headers=HEADERS, timeout=8)
                if resp.status_code == 200:
                    anns = parse_announcements_raw(resp.text)
                    if anns:
                        ep_max_ts = max((a.get("timestamp", 0) for a in anns), default=0)
                        if ep_max_ts >= max_ts:
                            max_ts = ep_max_ts
                            best_announcements = anns
            except Exception:
                pass

        if best_announcements:
            self.finished.emit(True, f"Fetched {len(best_announcements)} live announcement(s).", best_announcements)
        else:
            self.finished.emit(True, "No live announcements on server.", [])


class AnnouncementCard(QFrame):
    def __init__(self, ann: dict, parent=None):
        super().__init__(parent)
        self.ann = ann
        self.is_expanded = False
        self.specialty = get_specialty(ann)
        self.expand_anim = None
        self.init_ui()

    def init_ui(self):
        self.setObjectName("AnnouncementCard")
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._update_card_style()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)

        spec_badge = QLabel(f" {self.specialty['name']}")
        spec_badge.setStyleSheet(f"""
            background-color: {self.specialty['bg']};
            color: {self.specialty['color']};
            border: 1px solid {self.specialty['border']};
            border-radius: 6px;
            padding: 4px 10px;
            font-size: 11px;
            font-weight: 800;
            letter-spacing: 0.5px;
            min-height: 20px;
        """)
        header_layout.addWidget(spec_badge)

        if self.ann.get("important", False):
            imp_badge = QLabel("IMPORTANT")
            imp_badge.setStyleSheet("""
                background-color: rgba(255, 51, 102, 0.2);
                color: #FF3366;
                border: 1px solid rgba(255, 51, 102, 0.5);
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 900;
                letter-spacing: 0.5px;
                min-height: 20px;
            """)
            header_layout.addWidget(imp_badge)

        if self.ann.get("special_event", False):
            sev_badge = QLabel("SPECIAL EVENT")
            sev_badge.setStyleSheet("""
                background-color: rgba(0, 255, 153, 0.12);
                color: #00FF99;
                border: 1px solid rgba(0, 255, 153, 0.35);
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 800;
                letter-spacing: 0.5px;
                min-height: 20px;
            """)
            header_layout.addWidget(sev_badge)

        title_text = self.ann.get("title", "Untitled")
        self.title_lbl = QLabel(title_text)
        self.title_lbl.setStyleSheet("font-size: 16px; font-weight: 800;")
        self.title_lbl.setWordWrap(True)
        header_layout.addWidget(self.title_lbl, stretch=1)

        ts = self.ann.get("timestamp", 0)
        date_str = self.ann.get("date", "")
        time_str = format_time_ago(ts, date_str)
        self.time_lbl = QLabel(time_str)
        self.time_lbl.setStyleSheet("font-size: 12px; font-weight: 600;")
        header_layout.addWidget(self.time_lbl)

        self.chevron_lbl = QLabel("▼")
        self.chevron_lbl.setStyleSheet(f"color: {self.specialty['color']}; font-size: 12px; font-weight: bold; padding-left: 4px;")
        header_layout.addWidget(self.chevron_lbl)

        layout.addLayout(header_layout)

        self.separator = QFrame()
        self.separator.setFrameShape(QFrame.Shape.HLine)
        self.separator.setStyleSheet(f"background-color: {self.specialty['border']}; max-height: 1px; border: none;")
        self.separator.setVisible(False)
        layout.addWidget(self.separator)

        self.body_widget = QWidget()
        body_layout = QVBoxLayout(self.body_widget)
        body_layout.setContentsMargins(4, 6, 4, 4)
        body_layout.setSpacing(10)

        self.msg_lbl = QLabel(self.ann.get("message", ""))
        self.msg_lbl.setStyleSheet("font-size: 14px;")
        self.msg_lbl.setWordWrap(True)
        self.msg_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.LinksAccessibleByMouse)
        self.msg_lbl.setOpenExternalLinks(True)
        body_layout.addWidget(self.msg_lbl)

        if ts or date_str:
            display_date = date_str if date_str else time.strftime("%B %d, %Y at %I:%M %p", time.localtime(ts))
            exact_lbl = QLabel(f"Published on {display_date}")
            exact_lbl.setStyleSheet("color: #64748B; font-size: 11px; font-style: italic;")
            body_layout.addWidget(exact_lbl)

        self.body_widget.setVisible(False)
        self.body_widget.setMaximumHeight(0)
        layout.addWidget(self.body_widget)

    def _update_card_style(self):
        if self.is_expanded:
            self.setStyleSheet(f"""
                QFrame#AnnouncementCard {{
                    background-color: rgba(14, 18, 26, 0.92);
                    border: 1px solid {self.specialty['color']};
                    border-radius: 12px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QFrame#AnnouncementCard {{
                    background-color: rgba(14, 18, 26, 0.75);
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 12px;
                }}
                QFrame#AnnouncementCard:hover {{
                    background-color: rgba(22, 28, 40, 0.88);
                    border: 1px solid {self.specialty['border']};
                }}
            """)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_expand()
        super().mousePressEvent(event)

    def set_expanded(self, expanded: bool, animate: bool = True):
        if getattr(self, "expand_anim", None) and self.expand_anim.state() == QPropertyAnimation.State.Running:
            self.expand_anim.stop()

        self.is_expanded = expanded
        self.separator.setVisible(expanded)
        self.chevron_lbl.setText("▲" if expanded else "▼")
        self._update_card_style()
        
        if animate:
            self.body_widget.setVisible(True)
            if expanded:
                self.body_widget.setMaximumHeight(16777215)
                target_h = max(self.body_widget.sizeHint().height(), self.body_widget.layout().sizeHint().height())
                start_h = self.body_widget.height()
            else:
                start_h = self.body_widget.height()
                target_h = 0
            
            self.body_widget.setMaximumHeight(start_h)
            self.expand_anim = QPropertyAnimation(self.body_widget, b"maximumHeight", self)
            self.expand_anim.setDuration(250)
            self.expand_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            self.expand_anim.setStartValue(start_h)
            self.expand_anim.setEndValue(target_h)
            
            def on_finished():
                if not expanded:
                    self.body_widget.setVisible(False)
                else:
                    self.body_widget.setMaximumHeight(16777215)
                    
            self.expand_anim.finished.connect(on_finished)
            self.expand_anim.start()
        else:
            self.body_widget.setVisible(expanded)
            if expanded:
                self.body_widget.setMaximumHeight(16777215)
            else:
                self.body_widget.setMaximumHeight(0)

    def toggle_expand(self):
        self.set_expanded(not self.is_expanded, animate=True)


class AnnouncementView(QWidget):
    def __init__(self, config: ConfigManager, main_window, parent=None):
        super().__init__(parent)
        self.config = config
        self.main_window = main_window
        self.logger = Logger.get_instance()
        self.latest_announcements = []
        self.cards = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        header = QHBoxLayout()
        header.setSpacing(10)

        title_col = QVBoxLayout()
        title = QLabel("Announcements & News")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        title_col.addWidget(title)

        subtitle = QLabel("Click any announcement card to expand full details")
        subtitle.setStyleSheet("font-size: 12px;")
        title_col.addWidget(subtitle)

        header.addLayout(title_col)
        header.addStretch()

        accent = self.config.get("accent_color", "#00F0FF")
        self.expand_all_btn = QPushButton(" Expand All")
        self.expand_all_btn.setObjectName("SecondaryButton")
        self.expand_all_btn.setIcon(IconEngine.get_icon("chevron_down", QColor("#94A3B8"), QColor(accent), 14))
        self.expand_all_btn.setIconSize(QSize(14, 14))
        self.expand_all_btn.clicked.connect(self._toggle_expand_all)
        header.addWidget(self.expand_all_btn)

        self.refresh_btn = QPushButton(" Refresh")
        self.refresh_btn.setObjectName("SecondaryButton")
        self.refresh_btn.setIcon(IconEngine.get_icon("refresh", QColor("#94A3B8"), QColor(accent), 14))
        self.refresh_btn.setIconSize(QSize(14, 14))
        self.refresh_btn.clicked.connect(self.fetch_announcement)
        header.addWidget(self.refresh_btn)

        layout.addLayout(header)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        
        self.scroll_widget = QWidget()
        self.scroll_widget.setStyleSheet("background: transparent;")
        self.cards_layout = QVBoxLayout(self.scroll_widget)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(12)
        self.cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_area.setWidget(self.scroll_widget)
        
        layout.addWidget(self.scroll_area)

        self.status_lbl = QLabel("Checking for announcements...")
        self.status_lbl.setStyleSheet("font-size: 12px; font-style: italic;")
        layout.addWidget(self.status_lbl)

        self.all_expanded = False
        self.fetch_announcement()

        self.timer = QTimer(self)
        self.timer.setInterval(120000)
        self.timer.timeout.connect(self.fetch_announcement)
        self.timer.start()

    def _get_cache_file_paths(self):
        neurax_dir = self.config.neurax_dir
        return [
            neurax_dir / "announcements_cache.json"
        ]

    def _load_announcements_cache(self):
        for path in self._get_cache_file_paths():
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            return data
                        elif isinstance(data, dict) and "announcements" in data:
                            return data["announcements"]
                except Exception:
                    pass
        return None

    def _save_announcements_cache(self, announcements: list):
        try:
            path = self.config.neurax_dir / "announcements_cache.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(announcements, indent=2, ensure_ascii=False)
            with open(path, "w", encoding="utf-8") as f:
                f.write(payload)
        except Exception as e:
            self.logger.warning(f"Failed to save announcements cache: {e}")

    def fetch_announcement(self):
        if hasattr(self, "worker") and self.worker and self.worker.isRunning():
            return
        self.status_lbl.setText("Connecting to server...")
        self.refresh_btn.setEnabled(False)
        self.worker = AnnouncementWorker()
        self.worker.finished.connect(self._on_fetch_finished)
        self.worker.start()

    def _on_fetch_finished(self, success: bool, message: str, announcements: list):
        self.refresh_btn.setEnabled(True)
        self.status_lbl.setText(message)
        
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        self.latest_announcements = announcements if success else []
        self.cards.clear()
        self.all_expanded = False
        self.expand_all_btn.setText(" Expand All")

        if success and announcements:
            for i, ann in enumerate(announcements):
                card = AnnouncementCard(ann)
                if i == 0:
                    card.set_expanded(True, animate=False)
                self.cards.append(card)
                self.cards_layout.addWidget(card)

            cached_announcements = self._load_announcements_cache()

            if cached_announcements is None:
                self._save_announcements_cache(announcements)
                cached_announcements = announcements
                has_new = False
            else:
                cached_ids = set(a.get("id") for a in cached_announcements if isinstance(a, dict) and a.get("id"))
                live_ids = set(a.get("id") for a in announcements if isinstance(a, dict) and a.get("id"))
                cached_map = {a.get("id"): a for a in cached_announcements if isinstance(a, dict) and a.get("id")}
                
                has_new = False
                for ann in announcements:
                    ann_id = ann.get("id")
                    if ann_id not in cached_map:
                        has_new = True
                        break
                    else:
                        cached_item = cached_map[ann_id]
                        if (ann.get("title") != cached_item.get("title") or
                            ann.get("message") != cached_item.get("message") or
                            ann.get("timestamp") != cached_item.get("timestamp")):
                            has_new = True
                            break

                if not has_new and set(cached_map.keys()) != live_ids:
                    self._save_announcements_cache(announcements)

            current_tab = -1
            if self.main_window and hasattr(self.main_window, "stacked_widget"):
                current_tab = self.main_window.stacked_widget.currentIndex()

            if current_tab == 7:
                self.mark_as_read()
            elif has_new:
                if self.main_window and hasattr(self.main_window, "nav_bar"):
                    self.main_window.nav_bar.set_announcement_notification(True)
            else:
                if self.main_window and hasattr(self.main_window, "nav_bar"):
                    self.main_window.nav_bar.set_announcement_notification(False)
        else:
            card = GlassCard()
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(25, 25, 25, 25)
            card_layout.setSpacing(10)

            ann_title = QLabel("No Announcements" if success else "Connection Offline")
            ann_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #00F0FF;")
            card_layout.addWidget(ann_title)

            msg = "No active announcements published." if success else f"Could not retrieve announcements. Please check your network connection.\n\nDetails: {message}"
            ann_body = QLabel(msg)
            ann_body.setStyleSheet("color: #E2E8F0; font-size: 14px;")
            ann_body.setWordWrap(True)
            card_layout.addWidget(ann_body)

            self.cards_layout.addWidget(card)

            if success:
                self._save_announcements_cache([])

            if self.main_window and hasattr(self.main_window, "nav_bar"):
                self.main_window.nav_bar.set_announcement_notification(False)

    def _toggle_expand_all(self):
        if not self.cards:
            return
        self.all_expanded = not self.all_expanded
        for card in self.cards:
            card.set_expanded(self.all_expanded, animate=True)
        self.expand_all_btn.setText(" Collapse All" if self.all_expanded else " Expand All")

    def mark_as_read(self):
        latest = getattr(self, "latest_announcements", [])
        if latest:
            max_ts = max((a.get("timestamp", 0) for a in latest), default=0)
            ann_data_str = json.dumps(latest, sort_keys=True)
            current_hash = hashlib.md5(ann_data_str.encode("utf-8")).hexdigest()
            current_ids = [a["id"] for a in latest if a.get("id")]
            self.config.set("last_read_announcement_timestamp", max_ts)
            self.config.set("last_read_announcement_hash", current_hash)
            self.config.set("last_read_announcement_ids", current_ids)
            self._save_announcements_cache(latest)
        else:
            self.config.set("last_read_announcement_timestamp", 0)
            self.config.set("last_read_announcement_hash", "")
            self.config.set("last_read_announcement_ids", [])
            self._save_announcements_cache([])

        if hasattr(self, "main_window") and self.main_window and hasattr(self.main_window, "nav_bar"):
            self.main_window.nav_bar.set_announcement_notification(False)
