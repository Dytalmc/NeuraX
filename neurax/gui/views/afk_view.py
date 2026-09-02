import time
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGridLayout
from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices
from neurax.gui.widgets.glass_card import GlassCard

class AFKView(QWidget):
    """AFK View: live AFK stopwatch and immersive ad prototypes.

    The lock-launcher control used to live in this tab, but locking is
    now exclusive to ``nx.py`` — only ``nx.py`` can lock or unlock a
    specific ``device_uuid``. The launcher itself has no lock UI."""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.main_window = parent
        self.start_time = time.time()
        self.afk_seconds = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Header Section
        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title = QLabel("AFK Rest Zone")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        title_col.addWidget(title)

        subtitle = QLabel("Rest your eyes while NeuraX monitors your sessions and optimizes system resources.")
        subtitle.setStyleSheet("font-size: 12px;")
        title_col.addWidget(subtitle)
        header.addLayout(title_col)
        header.addStretch()

        layout.addLayout(header)

        # Stopwatch Card (lock control removed; the card now hosts the
        # stopwatch alone instead of stopwatch + lock button).
        core_card = GlassCard()
        core_card.setObjectName("GlassCard")
        core_layout = QVBoxLayout(core_card)
        core_layout.setContentsMargins(30, 25, 30, 25)
        core_layout.setSpacing(25)

        timer_lbl = QLabel("ELAPSED AFK TIME")
        timer_lbl.setStyleSheet("font-size: 11px; font-weight: 800; letter-spacing: 1.5px;")
        core_layout.addWidget(timer_lbl)

        self.time_display = QLabel("00:00:00")
        self.time_display.setStyleSheet("font-size: 48px; font-weight: 900; font-family: 'Consolas', monospace;")
        core_layout.addWidget(self.time_display)

        self.stats_lbl = QLabel("Power consumption optimized • Disk sync idle")
        self.stats_lbl.setStyleSheet("font-size: 12px; color: #00FF99; font-style: italic;")
        core_layout.addWidget(self.stats_lbl)

        layout.addWidget(core_card)

        # Ads Prototype Section
        ads_header = QLabel("SPONSORED PROTOTYPES")
        ads_header.setStyleSheet("font-size: 11px; font-weight: 800; letter-spacing: 1.5px; margin-top: 10px;")
        layout.addWidget(ads_header)

        ads_grid = QGridLayout()
        ads_grid.setSpacing(15)

        # Ad Card 1: NeuraHost
        ad1 = GlassCard()
        ad1.setObjectName("GlassCard")
        ad1_layout = QVBoxLayout(ad1)
        ad1_layout.setContentsMargins(15, 15, 15, 15)
        ad1_layout.setSpacing(8)

        ad_tag1 = QLabel("ADVERTISEMENT PROTOTYPE")
        ad_tag1.setStyleSheet("font-size: 9px; font-weight: 900; letter-spacing: 1px;")
        ad1_layout.addWidget(ad_tag1)

        ad_title1 = QLabel("NeuraHost Gaming Servers")
        ad_title1.setStyleSheet("font-size: 15px; font-weight: bold;")
        ad1_layout.addWidget(ad_title1)

        ad_desc1 = QLabel("Deploy instant high-performance Minecraft servers with G1GC optimized runtimes and DDoS protection.")
        ad_desc1.setStyleSheet("font-size: 11px;")
        ad_desc1.setWordWrap(True)
        ad1_layout.addWidget(ad_desc1)

        ad_btn1 = QPushButton("Learn More")
        ad_btn1.setObjectName("SecondaryButton")
        ad_btn1.setCursor(Qt.CursorShape.PointingHandCursor)
        ad_btn1.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://github.com/Dytalmc/NeuraX")))
        ad1_layout.addWidget(ad_btn1)

        ads_grid.addWidget(ad1, 0, 0)

        # Ad Card 2: MinePro Gear
        ad2 = GlassCard()
        ad2.setObjectName("GlassCard")
        ad2_layout = QVBoxLayout(ad2)
        ad2_layout.setContentsMargins(15, 15, 15, 15)
        ad2_layout.setSpacing(8)

        ad_tag2 = QLabel("ADVERTISEMENT PROTOTYPE")
        ad_tag2.setStyleSheet("font-size: 9px; font-weight: 900; color: #FF3366; letter-spacing: 1px;")
        ad2_layout.addWidget(ad_tag2)

        ad_title2 = QLabel("MinePro Mechanical Keyboards")
        ad_title2.setStyleSheet("font-size: 15px; font-weight: bold;")
        ad2_layout.addWidget(ad_title2)

        ad_desc2 = QLabel("Get 20% off high-fidelity optical switches designed to maximize APM and zero-latency inputs.")
        ad_desc2.setStyleSheet("font-size: 11px;")
        ad_desc2.setWordWrap(True)
        ad2_layout.addWidget(ad_desc2)

        ad_btn2 = QPushButton("Shop Gear")
        ad_btn2.setObjectName("SecondaryButton")
        ad_btn2.setCursor(Qt.CursorShape.PointingHandCursor)
        ad_btn2.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://github.com/Dytalmc/NeuraX")))
        ad2_layout.addWidget(ad_btn2)

        ads_grid.addWidget(ad2, 0, 1)

        layout.addLayout(ads_grid)
        layout.addStretch()

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._update_clock)
        self.timer.start()

    def reset_timer(self):
        self.start_time = time.time()
        self.afk_seconds = 0
        self.time_display.setText("00:00:00")

    def _update_clock(self):
        self.afk_seconds = int(time.time() - self.start_time)
        hrs = self.afk_seconds // 3600
        mins = (self.afk_seconds % 3600) // 60
        secs = self.afk_seconds % 60
        self.time_display.setText(f"{hrs:02d}:{mins:02d}:{secs:02d}")
