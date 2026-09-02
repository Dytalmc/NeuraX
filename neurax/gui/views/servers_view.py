from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QLineEdit, QDialog, QComboBox, QMessageBox, QApplication,
    QProgressBar
)
from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui import QCursor, QColor
from neurax.gui.widgets.glass_card import GlassCard
from neurax.gui.icons import IconEngine
from neurax.core.config import ConfigManager
from neurax.core.instances import InstanceManager
from neurax.core.auth import AuthManager
from neurax.core.server_pinger import BatchServerPinger
from neurax.core.ai.ai_server_radar import AIServerRadar, AIServerSearchWorker
from neurax.core.logger import Logger

DEFAULT_SERVERS = [
    {
        "name": "Donut SMP",
        "host": "play.donutsmp.net",
        "port": 25565,
        "gamemode": "Hardcore SMP",
        "loader": "Paper",
        "popularity": 98,
        "rating": 4.9,
        "baseline_players": 2200,
        "description": "Popular Minecraft Hardcore SMP server by DrDonut featuring active economy and custom weapons."
    },
    {
        "name": "Origin Realms",
        "host": "play.originrealms.com",
        "port": 25565,
        "gamemode": "Fabric SMP",
        "loader": "Fabric",
        "popularity": 98,
        "rating": 4.9,
        "baseline_players": 1450,
        "description": "Custom Fabric-driven vanilla+ MMORPG survival experience with custom biomes, blocks, and quests."
    },
    {
        "name": "Cobblemon Islands",
        "host": "play.cobblemon.com",
        "port": 25565,
        "gamemode": "Cobblemon",
        "loader": "Fabric",
        "popularity": 95,
        "rating": 4.8,
        "baseline_players": 820,
        "description": "The premier Fabric Cobblemon server with open world exploration, catching, and battles."
    },
    {
        "name": "Wynncraft MMORPG",
        "host": "play.wynncraft.com",
        "port": 25565,
        "gamemode": "MMORPG",
        "loader": "Paper",
        "popularity": 99,
        "rating": 4.9,
        "baseline_players": 2400,
        "description": "The largest and most detailed Minecraft MMORPG server running optimized Paper API."
    },
    {
        "name": "ManaCube Network",
        "host": "play.manacube.com",
        "port": 25565,
        "gamemode": "Towny / Skyblock",
        "loader": "Spigot",
        "popularity": 97,
        "rating": 4.8,
        "baseline_players": 1200,
        "description": "Famous custom Spigot-based server featuring parkour, survival, prison, and active community."
    },
    {
        "name": "MassiveCraft Folia",
        "host": "play.massivecraft.com",
        "port": 25565,
        "gamemode": "Factions / RPG",
        "loader": "Folia",
        "popularity": 91,
        "rating": 4.6,
        "baseline_players": 350,
        "description": "High performance multi-threaded Folia API server featuring original Factions and immersive RPG elements."
    },
    {
        "name": "LeafMC Network",
        "host": "play.leafmc.eu",
        "port": 25565,
        "gamemode": "Survival SMP",
        "loader": "Leaf",
        "popularity": 89,
        "rating": 4.5,
        "baseline_players": 120,
        "description": "Clean, lightweight Leaf API server delivering modern gameplay with custom enhancements."
    },
    {
        "name": "CosmicPvP Classic",
        "host": "cosmicpvp.me",
        "port": 25565,
        "gamemode": "Factions",
        "loader": "Bukkit",
        "popularity": 88,
        "rating": 4.4,
        "baseline_players": 150,
        "description": "Classic Bukkit-based competitive Factions server with custom plugins and intense PvP."
    },
    {
        "name": "PumpkinMC Network",
        "host": "play.pumpkinmc.com",
        "port": 25565,
        "gamemode": "Survival / Minigames",
        "loader": "PumpkinMC",
        "popularity": 87,
        "rating": 4.5,
        "baseline_players": 80,
        "description": "Innovative PumpkinMC server API offering modular, performant survival and arcade modes."
    },
    {
        "name": "Hypixel Network",
        "host": "mc.hypixel.net",
        "port": 25565,
        "gamemode": "Minigames",
        "loader": "Spigot",
        "popularity": 100,
        "rating": 4.9,
        "baseline_players": 35000,
        "description": "The world's largest Minecraft server network featuring SkyBlock, BedWars, and endless custom minigames."
    },
    {
        "name": "2b2t Anarchy",
        "host": "2b2t.org",
        "port": 25565,
        "gamemode": "Anarchy",
        "loader": "Paper",
        "popularity": 95,
        "rating": 4.3,
        "baseline_players": 250,
        "description": "The oldest anarchy server in Minecraft, running Paper optimizations to handle massive player loads."
    }
]

class AddServerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Custom Server")
        self.resize(420, 280)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        layout.addWidget(QLabel("Server Name:"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("My Favorite Server")
        layout.addWidget(self.name_input)

        layout.addWidget(QLabel("Server IP Address:"))
        self.host_input = QLineEdit()
        self.host_input.setPlaceholderText("play.example.com")
        layout.addWidget(self.host_input)

        layout.addWidget(QLabel("Server Port (Default: 25565):"))
        self.port_input = QLineEdit("25565")
        layout.addWidget(self.port_input)

        layout.addWidget(QLabel("Server Loader API:"))
        self.loader_combo = QComboBox()
        self.loader_combo.addItems(["Paper", "Vanilla", "Fabric", "Purpur", "Quilt", "Forge", "NeoForge", "Folia", "Leaf", "Spigot"])
        layout.addWidget(self.loader_combo)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        
        save_btn = QPushButton("Save Server")
        save_btn.setObjectName("PrimaryButton")
        save_btn.setIcon(IconEngine.get_icon("save", QColor("#FFFFFF"), QColor("#FFFFFF"), 14))
        save_btn.setIconSize(QSize(14, 14))
        save_btn.clicked.connect(self.accept)
        btn_row.addWidget(save_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("SecondaryButton")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        layout.addLayout(btn_row)

    def get_data(self) -> dict:
        port = 25565
        try:
            port = int(self.port_input.text().strip())
        except ValueError:
            pass

        return {
            "name": self.name_input.text().strip() or "Custom Server",
            "host": self.host_input.text().strip(),
            "port": port,
            "gamemode": "Custom",
            "loader": self.loader_combo.currentText(),
            "popularity": 50,
            "rating": 5.0,
            "description": "User custom added server."
        }


class ServerCard(GlassCard):
    """High-Tech Cyber Server Card with live ping indicators and vector badges."""

    def __init__(self, server_info: dict, quick_join_cb=None, remove_cb=None, parent=None):
        super().__init__(parent)
        self.setObjectName("GlassCard")
        self.server_info = dict(server_info)
        self.quick_join_cb = quick_join_cb
        self.remove_cb = remove_cb

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(14)

        # Status Indicator Light
        online = self.server_info.get("online", False)
        status_light = QFrame()
        status_light.setFixedSize(10, 10)
        status_light.setStyleSheet(f"""
            background-color: {'#00FF99' if online else '#FF3366'};
            border-radius: 5px;
        """)
        layout.addWidget(status_light, alignment=Qt.AlignmentFlag.AlignTop)

        info_col = QVBoxLayout()
        info_col.setSpacing(6)

        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        # Loader Badge
        loader = self.server_info.get("loader", "Vanilla")
        loader_badge = QLabel(loader)
        loader_lower = loader.lower()
        if loader_lower == "fabric":
            loader_style = "background-color: rgba(0, 240, 255, 0.15); color: #00F0FF; border: 1px solid rgba(0, 240, 255, 0.4); border-radius: 6px; padding: 2px 8px; font-size: 11px; font-weight: 800;"
        elif loader_lower in ("paper", "folia", "leaf", "spigot", "bukkit", "pumpkinmc"):
            loader_style = "background-color: rgba(0, 255, 153, 0.15); color: #00FF99; border: 1px solid rgba(0, 255, 153, 0.4); border-radius: 6px; padding: 2px 8px; font-size: 11px; font-weight: 800;"
        else:
            loader_style = "background-color: rgba(255, 255, 255, 0.1); color: #94A3B8; border: 1px solid rgba(255, 255, 255, 0.2); border-radius: 6px; padding: 2px 8px; font-size: 11px; font-weight: 800;"
        loader_badge.setStyleSheet(loader_style)
        header_row.addWidget(loader_badge)

        gamemode = self.server_info.get("gamemode", "Survival")
        gm_badge = QLabel(gamemode)
        gm_badge.setStyleSheet("background-color: rgba(161, 0, 255, 0.15); color: #A100FF; border: 1px solid rgba(161, 0, 255, 0.4); border-radius: 6px; padding: 2px 8px; font-size: 11px; font-weight: 700;")
        header_row.addWidget(gm_badge)

        ai_score = self.server_info.get("ai_health_score", 90)
        health_color = "#00FF99" if ai_score >= 80 else ("#F59E0B" if ai_score >= 50 else "#FF3366")
        health_badge = QLabel(f"Health: {ai_score}%")
        health_badge.setStyleSheet(f"background-color: rgba(0, 255, 153, 0.12); color: {health_color}; border: 1px solid rgba(0, 255, 153, 0.35); border-radius: 6px; padding: 2px 8px; font-size: 11px; font-weight: 800;")
        header_row.addWidget(health_badge)

        name_lbl = QLabel(self.server_info.get("name", "Minecraft Server"))
        name_lbl.setStyleSheet("font-size: 16px; font-weight: bold;")
        header_row.addWidget(name_lbl)
        header_row.addStretch()
        info_col.addLayout(header_row)

        ip_row = QHBoxLayout()
        ip_row.setSpacing(8)
        host = self.server_info.get("host", "")
        port = self.server_info.get("port", 25565)
        full_ip = f"{host}:{port}" if port != 25565 else host
        ip_lbl = QLabel(f"IP: {full_ip}")
        ip_lbl.setStyleSheet("font-size: 12px; font-weight: 700; font-family: 'Consolas', monospace;")
        ip_row.addWidget(ip_lbl)

        copy_ip_btn = QPushButton(" Copy IP")
        copy_ip_btn.setObjectName("SecondaryButton")
        copy_ip_btn.setIcon(IconEngine.get_icon("copy", QColor("#8A94A6"), QColor("#FFFFFF"), 12))
        copy_ip_btn.setIconSize(QSize(12, 12))
        copy_ip_btn.setFixedHeight(22)
        copy_ip_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        copy_ip_btn.setStyleSheet("font-size: 10px; padding: 2px 6px;")
        copy_ip_btn.clicked.connect(lambda: self._copy_to_clipboard(full_ip))
        ip_row.addWidget(copy_ip_btn)

        if online:
            players_online = self.server_info.get("players_online", 0)
            players_max = self.server_info.get("players_max", 0)
            ping = self.server_info.get("ping", -1)
            ping_str = f"{ping}ms" if ping >= 0 else "N/A"
            stats_lbl = QLabel(f"Players: {players_online:,} / {players_max:,}  •  Ping: {ping_str}")
            stats_lbl.setStyleSheet("font-size: 12px; font-weight: 600;")
            ip_row.addWidget(stats_lbl)
        else:
            off_lbl = QLabel("Players: 0  •  Ping: -- (Offline)")
            off_lbl.setStyleSheet("color: #FF3366; font-size: 12px; font-weight: 600;")
            ip_row.addWidget(off_lbl)

        ip_row.addStretch()
        info_col.addLayout(ip_row)

        motd = self.server_info.get("motd") or self.server_info.get("description", "")
        if motd:
            desc_lbl = QLabel(motd)
            desc_lbl.setStyleSheet("font-size: 12px;")
            desc_lbl.setWordWrap(True)
            info_col.addWidget(desc_lbl)

        ai_reasons = self.server_info.get("ai_reasons", [])
        if ai_reasons:
            reasons_str = " • ".join(ai_reasons)
            reasons_lbl = QLabel(f"AI Insight: {reasons_str}")
            reasons_lbl.setStyleSheet("color: #00FF99; font-size: 11px; font-style: italic;")
            info_col.addWidget(reasons_lbl)

        layout.addLayout(info_col, stretch=1)

        act_col = QVBoxLayout()
        act_col.setSpacing(8)
        act_col.setAlignment(Qt.AlignmentFlag.AlignCenter)

        join_btn = QPushButton(" Quick Join")
        join_btn.setObjectName("PrimaryButton")
        join_btn.setIcon(IconEngine.get_icon("play_triangle", QColor("#FFFFFF"), QColor("#FFFFFF"), 14))
        join_btn.setIconSize(QSize(14, 14))
        join_btn.setMinimumWidth(110)
        join_btn.setMinimumHeight(36)
        join_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        join_btn.clicked.connect(lambda: self.quick_join_cb(host, port))
        act_col.addWidget(join_btn)

        if self.remove_cb:
            rem_btn = QPushButton(" Remove")
            rem_btn.setObjectName("SecondaryButton")
            rem_btn.setIcon(IconEngine.get_icon("trash", QColor("#94A3B8"), QColor("#FF3366"), 12))
            rem_btn.setIconSize(QSize(12, 12))
            rem_btn.setMinimumWidth(110)
            rem_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            rem_btn.clicked.connect(lambda: self.remove_cb(self.server_info))
            act_col.addWidget(rem_btn)

        layout.addLayout(act_col)

    def _copy_to_clipboard(self, text: str):
        QApplication.clipboard().setText(text)


class ServersView(QWidget):
    def __init__(self, config: ConfigManager, instance_mgr: InstanceManager = None, auth_mgr: AuthManager = None, main_window = None, parent = None):
        super().__init__(parent)
        self.config = config
        self.instance_mgr = instance_mgr
        self.auth_mgr = auth_mgr
        self.main_window = main_window
        self.logger = Logger.get_instance()

        self.custom_servers = self.config.get("servers", [])
        if not isinstance(self.custom_servers, list):
            self.custom_servers = []

        self.all_servers = list(DEFAULT_SERVERS)
        for cs in self.custom_servers:
            if isinstance(cs, dict) and cs not in self.all_servers:
                self.all_servers.append(cs)

        self.ping_worker = None
        self.search_worker = None
        self.server_data_cache = list(self.all_servers)

        self.spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.spinner_idx = 0
        self.anim_timer = QTimer(self)
        self.anim_timer.setInterval(100)
        self.anim_timer.timeout.connect(self._on_anim_tick)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Header Row
        header = QHBoxLayout()
        header.setSpacing(10)

        title_col = QVBoxLayout()
        title = QLabel("Market Server Browser & AI Monitoring")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        title_col.addWidget(title)

        subtitle = QLabel("Live 0-Token AI Server Health Monitoring, Latency Checks & Market Intelligence")
        subtitle.setStyleSheet("font-size: 12px;")
        title_col.addWidget(subtitle)

        header.addLayout(title_col)
        header.addStretch()

        add_btn = QPushButton(" Add Custom Server")
        add_btn.setObjectName("PrimaryButton")
        add_btn.setIcon(IconEngine.get_icon("plus", QColor("#FFFFFF"), QColor("#FFFFFF"), 14))
        add_btn.setIconSize(QSize(14, 14))
        add_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        add_btn.clicked.connect(self._open_add_server_dialog)
        header.addWidget(add_btn)

        refresh_btn = QPushButton(" Refresh Monitor")
        refresh_btn.setObjectName("SecondaryButton")
        refresh_btn.setIcon(IconEngine.get_icon("refresh", QColor("#94A3B8"), QColor("#00F0FF"), 14))
        refresh_btn.setIconSize(QSize(14, 14))
        refresh_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        refresh_btn.clicked.connect(self.refresh_servers)
        header.addWidget(refresh_btn)

        layout.addLayout(header)

        # 0-Token AI Server Monitoring & Market Intelligence Glass Card Panel
        self.ai_card = GlassCard()
        ai_layout = QVBoxLayout(self.ai_card)
        ai_layout.setContentsMargins(18, 14, 18, 14)
        ai_layout.setSpacing(10)

        ai_header_row = QHBoxLayout()
        ai_icon_lbl = QLabel("0-Token Local AI Server Monitor & Market Intelligence")
        ai_icon_lbl.setStyleSheet("font-size: 14px; font-weight: 800; letter-spacing: 0.5px;")
        ai_header_row.addWidget(ai_icon_lbl)
        ai_header_row.addStretch()

        self.ai_status_badge = QLabel("TELEMETRY RADAR ACTIVE")
        self.ai_status_badge.setStyleSheet("""
            background-color: rgba(0, 255, 153, 0.15);
            color: #00FF99;
            border: 1px solid rgba(0, 255, 153, 0.4);
            border-radius: 6px;
            padding: 3px 8px;
            font-size: 10px;
            font-weight: 800;
        """)
        ai_header_row.addWidget(self.ai_status_badge)
        ai_layout.addLayout(ai_header_row)

        self.ai_summary_lbl = QLabel("Initializing local AI server monitor...")
        self.ai_summary_lbl.setStyleSheet("font-size: 13px; font-weight: 600;")
        self.ai_summary_lbl.setWordWrap(True)
        ai_layout.addWidget(self.ai_summary_lbl)

        # Animated progress bar
        self.search_progress_bar = QProgressBar()
        self.search_progress_bar.setFixedHeight(4)
        self.search_progress_bar.setMinimum(0)
        self.search_progress_bar.setMaximum(0)
        self.search_progress_bar.setTextVisible(False)
        self.search_progress_bar.setVisible(False)
        ai_layout.addWidget(self.search_progress_bar)

        # AI Search Bar with Send Button
        search_row = QHBoxLayout()
        search_row.setSpacing(10)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Ask AI to find servers (e.g. 'high player fabric survival', 'skyblock', 'low ping anarchy', 'folia rpg')...")
        self.search_input.returnPressed.connect(self._submit_ai_search)
        search_row.addWidget(self.search_input, stretch=1)

        self.send_btn = QPushButton(" Search")
        self.send_btn.setObjectName("PrimaryButton")
        self.send_btn.setIcon(IconEngine.get_icon("search", QColor("#FFFFFF"), QColor("#FFFFFF"), 14))
        self.send_btn.setIconSize(QSize(14, 14))
        self.send_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.send_btn.clicked.connect(self._submit_ai_search)
        search_row.addWidget(self.send_btn)

        search_clear_btn = QPushButton("Clear")
        search_clear_btn.setObjectName("SecondaryButton")
        search_clear_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        search_clear_btn.clicked.connect(self._clear_search)
        search_row.addWidget(search_clear_btn)

        ai_layout.addLayout(search_row)
        layout.addWidget(self.ai_card)

        # Scroll Area for Server Cards
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

        # Auto-monitoring timer (pings servers every 45 seconds)
        self.monitor_timer = QTimer(self)
        self.monitor_timer.setInterval(45000)
        self.monitor_timer.timeout.connect(self.refresh_servers)
        self.monitor_timer.start()

        # Initial ping scan
        self.refresh_servers()

    def _on_anim_tick(self):
        frame = self.spinner_frames[self.spinner_idx % len(self.spinner_frames)]
        self.spinner_idx += 1
        self.ai_status_badge.setText(f"AI SEARCHING [ {frame} ]")
        self.ai_status_badge.setStyleSheet("""
            background-color: rgba(0, 240, 255, 0.25);
            color: #00F0FF;
            border: 1.5px solid #00F0FF;
            border-radius: 6px;
            padding: 3px 8px;
            font-size: 10px;
            font-weight: 900;
        """)

    def refresh_servers(self):
        if self.ping_worker and self.ping_worker.isRunning():
            return
        if not self.search_input.text().strip():
            self.ai_summary_lbl.setText("AI Engine Scanning & Monitoring market Minecraft servers...")
        self.ping_worker = BatchServerPinger(self.all_servers)
        self.ping_worker.results_ready.connect(self._on_servers_pinged)
        self.ping_worker.start()

    def _on_servers_pinged(self, results: list):
        self.server_data_cache = results
        query = self.search_input.text().strip()
        if query and not (self.search_worker and self.search_worker.isRunning()):
            self._submit_ai_search()
        elif not query:
            ai_info = AIServerRadar.generate_ai_summary(results, "")
            self.ai_summary_lbl.setText(ai_info.get("summary", "AI Monitoring Active."))
            self._render_cards(results)

    def _submit_ai_search(self):
        query = self.search_input.text().strip()
        if not query:
            self._clear_search()
            return

        if self.search_worker and self.search_worker.isRunning():
            return

        self.send_btn.setEnabled(False)
        self.send_btn.setText("Searching...")
        self.search_progress_bar.setVisible(True)

        self.spinner_idx = 0
        self.anim_timer.start()

        self.ai_summary_lbl.setText(f"AI Engine evaluating market servers for '{query}'...")

        self.search_worker = AIServerSearchWorker(query, self.server_data_cache, enable_web_search=True)
        self.search_worker.results_ready.connect(self._on_ai_search_results)
        self.search_worker.search_status.connect(lambda msg: self.ai_summary_lbl.setText(f"🔍 {msg}"))
        self.search_worker.start()

    def _on_ai_search_results(self, evaluated: list, ai_info: dict):
        self.anim_timer.stop()
        self.search_progress_bar.setVisible(False)
        self.send_btn.setEnabled(True)
        self.send_btn.setText(" Search")

        self.ai_status_badge.setText("AI SEARCH COMPLETE")
        self.ai_status_badge.setStyleSheet("""
            background-color: rgba(0, 255, 153, 0.2);
            color: #00FF99;
            border: 1.5px solid #00FF99;
            border-radius: 6px;
            padding: 3px 8px;
            font-size: 10px;
            font-weight: 900;
        """)

        self.ai_summary_lbl.setText(ai_info.get("summary", "AI Search Complete."))
        self._render_cards(evaluated)

    def _clear_search(self):
        if self.search_worker and self.search_worker.isRunning():
            try:
                self.search_worker.results_ready.disconnect(self._on_ai_search_results)
            except Exception:
                pass

        self.anim_timer.stop()
        self.search_progress_bar.setVisible(False)
        self.search_input.clear()
        self.send_btn.setEnabled(True)
        self.send_btn.setText(" Search")

        self.ai_status_badge.setText("100% LOCAL • 0 TOKENS • ACTIVE MONITORING")
        self.ai_status_badge.setStyleSheet("""
            background-color: rgba(0, 240, 255, 0.12);
            color: #00F0FF;
            border: 1px solid rgba(0, 240, 255, 0.35);
            border-radius: 6px;
            padding: 3px 8px;
            font-size: 10px;
            font-weight: 800;
        """)

        ai_info = AIServerRadar.generate_ai_summary(self.server_data_cache, "")
        self.ai_summary_lbl.setText(ai_info.get("summary", "AI Monitoring Active."))
        self._render_cards(self.server_data_cache)

    def _render_cards(self, servers: list):
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        for s_info in servers:
            is_custom = s_info in self.custom_servers or any(
                c.get("host") == s_info.get("host") and c.get("port") == s_info.get("port")
                for c in self.custom_servers if isinstance(c, dict)
            )
            remove_cb = self._remove_custom_server if is_custom else None
            card = ServerCard(s_info, quick_join_cb=self._quick_join, remove_cb=remove_cb)
            self.cards_layout.addWidget(card)

    def _open_add_server_dialog(self):
        dialog = AddServerDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_srv = dialog.get_data()
            if new_srv.get("host"):
                self.custom_servers.append(new_srv)
                if new_srv not in self.all_servers:
                    self.all_servers.append(new_srv)
                self.config.set("servers", self.custom_servers)
                self.logger.user_action(f"Added custom server '{new_srv['name']}' ({new_srv['host']}:{new_srv['port']})")
                self.refresh_servers()

    def _remove_custom_server(self, server_info: dict):
        reply = QMessageBox.question(
            self, "Remove Server", f"Remove custom server '{server_info.get('name')}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.custom_servers = [
                c for c in self.custom_servers 
                if not (c.get("host") == server_info.get("host") and c.get("port") == server_info.get("port"))
            ]
            self.all_servers = [
                s for s in self.all_servers 
                if not (s.get("host") == server_info.get("host") and s.get("port") == server_info.get("port"))
            ]
            self.config.set("servers", self.custom_servers)
            self.logger.user_action(f"Removed custom server '{server_info.get('name')}'")
            self.refresh_servers()

    def _quick_join(self, host: str, port: int):
        self.logger.user_action(f"Quick Joining server: {host}:{port}")
        if self.main_window and hasattr(self.main_window, "quick_join"):
            self.main_window.quick_join(host, port)
