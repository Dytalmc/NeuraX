import sys
import os
import gc
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget,
    QApplication, QFrame, QLabel, QPushButton
)
from PyQt6.QtGui import QIcon, QColor
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QPoint, QParallelAnimationGroup, QSize, QTimer, QObject, QRunnable, QThreadPool, pyqtSlot
from neurax.gui.theme import Theme, create_monochrome_icon
from neurax.gui.widgets.nav_bar import NavBar
from neurax.gui.widgets.animated_stacked_widget import AnimatedStackedWidget
from neurax.gui.views.play_view import PlayView
from neurax.gui.views.instances_view import InstancesView
from neurax.gui.views.versions_view import VersionsView  # noqa: F401  # kept for the background AI manifest radar
from neurax.gui.views.servers_view import ServersView
from neurax.gui.views.modrinth_view import ModrinthView
from neurax.gui.views.skins_view import SkinsView
from neurax.gui.views.gallery_view import GalleryView
from neurax.gui.views.announcement_view import AnnouncementView
from neurax.gui.views.settings_view import SettingsView
from neurax.gui.views.new_server_view import NewServerView
from neurax.gui.views.afk_view import AFKView
from neurax.gui.widgets.status_bar import StatusBarWidget
from neurax.core.config import ConfigManager, get_icon_path
from neurax.core.instances import InstanceManager
from neurax.core.auth import AuthManager
from neurax.core.logger import Logger
from neurax.core.discord_rpc import DiscordManager
from neurax.core._silent_proc import detach_existing_console
from neurax.core import network_monitor as _netmon
from neurax.core.network_monitor import NetworkMonitor, State as _NetState
from neurax.core import _resource_cache as _rcache

# Lock feature: the launcher honours remote locks sent by ``nx.py``.
# The lock state is persisted in an encrypted file at
# ``%APPDATA%\.neurax\cache\device_lock.bin`` so it survives restarts
# and continues to apply when the launcher is offline. The lock
# overlay shows the admin's custom message + a pulsing animation;
# only an ``is_locked = false`` round-trip from Supabase can clear
# it. Both ``LockScreenOverlay`` and ``DeviceLock`` are imported
# defensively so a missing ``cryptography`` install doesn't brick the
# launcher — without encryption the file simply isn't written and the
# overlay falls back to in-session-only enforcement.

try:
    from neurax.gui.widgets.lock_screen import LockScreenOverlay
    _LOCK_OVERLAY_OK = True
except Exception:
    LockScreenOverlay = None  # type: ignore
    _LOCK_OVERLAY_OK = False

try:
    from neurax.core.device_lock import DeviceLock
    _DEVICE_LOCK_OK = True
except Exception:
    DeviceLock = None  # type: ignore
    _DEVICE_LOCK_OK = False

try:
    from users import (
        CommunityClient,
        assemble_heartbeat_payload,
        get_or_create_device_uuid,
        get_users_config,
    )
    _USERS_OK = True
except Exception:
    CommunityClient = None  # type: ignore
    assemble_heartbeat_payload = None  # type: ignore
    get_or_create_device_uuid = None  # type: ignore
    get_users_config = None  # type: ignore
    _USERS_OK = False

class MainWindow(QMainWindow):
    def __init__(self, config: ConfigManager, instance_mgr: InstanceManager, auth_mgr: AuthManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.instance_mgr = instance_mgr
        self.auth_mgr = auth_mgr
        self.logger = Logger.get_instance()

        # Belt-and-suspenders: re-detach from any inherited console
        # here too, in case the GUI is hosted in a process that was
        # spawned without main.py's FreeConsole() call (for example,
        # a future test harness). Idempotent on Windows.
        try:
            detach_existing_console()
        except Exception:
            pass

        # Initialize Discord RPC System
        DiscordManager.get_instance().initialize(self.config)

        # Resource cache — every online feature (Modrinth, Mojang manifest,
        # AI Radar, Supabase community chip) reads from / writes to this
        # disk-backed cache so the launcher keeps working on slow links
        # and stays useful when offline.
        try:
            _rcache.set_cache_root(self.config.neurax_dir / "cache")
        except Exception:
            pass

        # Ensure this device has a UUID *now*, before the heartbeat
        # worker ever fires. If the user (or a previous crash) wiped
        # ``%APPDATA%\.neurax`` and ``device_uuid.txt`` is gone, this
        # call writes a fresh uuid4 to the keychain + sidecar file so
        # the first beat() has an identity to send. Also fixes the
        # chicken-and-egg where the CommunityView label and the chip
        # would otherwise disagree.
        try:
            if _USERS_OK and get_or_create_device_uuid is not None:
                get_or_create_device_uuid()
        except Exception:
            pass

        # Network monitor — single source of truth for "is the link
        # usable right now". Online features gate themselves on
        # ``NetworkMonitor.instance().online_features_enabled()`` so a
        # slow or missing connection never freezes the GUI.
        self.network_monitor = NetworkMonitor(self)
        try:
            self.network_monitor.state_changed.connect(self._on_network_state_changed)
        except Exception:
            pass

        # Lock feature removed from the launcher: locking is now
        # exclusive to ``nx.py``. The launcher has no lock UI, no
        # lock overlay, and no on-disk lock polling.

        self.setWindowTitle("NeuraX Launcher")
        icon_path = get_icon_path()
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
            
        width = self.config.get("window_width", 1180)
        height = self.config.get("window_height", 1080)
        self.setMinimumSize(900, 600)
        self.resize(width, height)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMinimizeButtonHint | Qt.WindowType.WindowMaximizeButtonHint)

        # Smooth Window Opacity Fade-In Transition
        self.setWindowOpacity(0.0)
        self.fade_in = QPropertyAnimation(self, b"windowOpacity", self)
        self.fade_in.setDuration(350)
        self.fade_in.setStartValue(0.0)
        self.fade_in.setEndValue(1.0)
        self.fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.fade_in.start()

        accent = self.config.get("accent_color", "#00F0FF")
        mode = self.config.get("theme_mode", "dark")

        # Apply global theme stylesheet
        qss = Theme.get_stylesheet(accent, mode)
        self.setStyleSheet(qss)
        app = QApplication.instance()
        if app:
            app.setStyleSheet(qss)

        # Central Widget
        self.central_widget = QWidget()
        self.central_widget.setObjectName("centralWidget")
        self.setCentralWidget(self.central_widget)

        main_layout = QHBoxLayout(self.central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Left Nav Bar
        self.nav_bar = NavBar(self)
        self.nav_bar.set_theme_mode(mode)
        self.nav_bar.set_accent_color(accent)
        self.nav_bar.tab_changed.connect(self._on_tab_changed)
        main_layout.addWidget(self.nav_bar)

        # Right pane layout
        right_pane = QWidget()
        right_pane.setObjectName("rightPane")
        right_layout = QVBoxLayout(right_pane)
        right_layout.setContentsMargins(15, 15, 15, 15)
        right_layout.setSpacing(10)

        # Header Bar
        header_bar = QFrame()
        header_bar.setObjectName("HeaderBar")
        header_bar.setFixedHeight(50)
        header_layout = QHBoxLayout(header_bar)
        header_layout.setContentsMargins(15, 0, 15, 0)
        header_layout.setSpacing(10)

        # Hamburger Button to toggle navigation bar
        self.toggle_nav_btn = QPushButton()
        self.toggle_nav_btn.setObjectName("NavToggleButton")
        self.toggle_nav_btn.setFixedSize(30, 30)
        self.toggle_nav_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_nav_btn.setIcon(create_monochrome_icon("hamburger", Theme.get_icon_color(mode), QColor(accent)))
        self.toggle_nav_btn.setIconSize(QSize(20, 20))
        self.toggle_nav_btn.clicked.connect(self._toggle_nav_bar)
        header_layout.addWidget(self.toggle_nav_btn)

        self.title_lbl = QLabel("NeuraX Engine")
        self.title_lbl.setStyleSheet("font-weight: 800; font-size: 14px; letter-spacing: 1px;")
        header_layout.addWidget(self.title_lbl)
        header_layout.addStretch()

        # Bug Button to toggle PlayView console
        self.bug_btn = QPushButton()
        self.bug_btn.setObjectName("BugButton")
        self.bug_btn.setFixedSize(30, 30)
        self.bug_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bug_btn.setIcon(create_monochrome_icon("bug", Theme.get_icon_color(mode), QColor(accent)))
        self.bug_btn.setIconSize(QSize(20, 20))
        self.bug_btn.clicked.connect(self._toggle_console)
        header_layout.addWidget(self.bug_btn)

        right_layout.addWidget(header_bar)

        # Animated Stacked Widget for Views
        self.stacked_widget = AnimatedStackedWidget()
        right_layout.addWidget(self.stacked_widget, stretch=1)

        # ------------------------------------------------------------------
        # View construction
        # ------------------------------------------------------------------
        # Previously every single view was instantiated eagerly in
        # ``__init__``. Each one (modrinth, instances, new_server, …) is
        # several hundred lines of widgets and at least one network call
        # to fetch its initial data set, so the launcher could sit on
        # the loading screen for several seconds before the first tab
        # even became responsive. We now construct only the default
        # ``PlayView`` up-front (the user is dropped straight onto it)
        # and lazy-build every other view the first time the user
        # actually switches to that tab. The instance is cached, so
        # subsequent switches are still instant.
        #
        # Tab indices are kept stable so the rest of the code (and the
        # ``nav_bar`` button order) is unchanged.
        # ------------------------------------------------------------------
        self._view_factories = [
            ("play_view",        lambda: PlayView(self.config, self.instance_mgr, self.auth_mgr, self)),
            ("instances_view",   lambda: InstancesView(self.config, self.instance_mgr, self)),
            ("servers_view",     lambda: ServersView(self.config, self.instance_mgr, self.auth_mgr, self, self)),
            ("modrinth_view",    lambda: ModrinthView(self.config, self.instance_mgr, self.auth_mgr, self, self)),
            ("skins_view",       lambda: SkinsView(self.config, self.auth_mgr, self)),
            ("gallery_view",     lambda: GalleryView(self.config, self.instance_mgr, self)),
            ("announcement_view",lambda: AnnouncementView(self.config, self, self)),
            ("settings_view",    lambda: SettingsView(self.config, self.auth_mgr, self)),
            ("new_server_view",  lambda: NewServerView(self.config, self.auth_mgr, self)),
            ("afk_view",         lambda: AFKView(self.config, self)),
        ]
        self._view_cache: dict = {}

        # Eagerly build the default tab so the first paint already has
        # something to show. Everything else stays a placeholder.
        self.play_view = self._view_factories[0][1]()
        self._view_cache["play_view"] = self.play_view

        # Add a transparent placeholder for every other tab. It will be
        # swapped out for the real view the first time the user clicks
        # its tab. Each placeholder is a single QLabel — essentially
        # free to construct, so the entire window comes up in one
        # event-loop turn.
        for idx, (attr_name, _factory) in enumerate(self._view_factories):
            if idx == 0:
                self.stacked_widget.addWidget(self.play_view)
            else:
                self.stacked_widget.addWidget(self._make_placeholder(attr_name))

        # Community view removed: the in-launcher Community tab has been
        # retired. Detailed stats are still available via the standalone
        # `nx.py` dashboard. The sidebar chip keeps the live online count
        # visible without a separate page.

        # Bottom Status/Progress Bar
        self.status_bar = StatusBarWidget(self.config)
        self.status_bar.setVisible(self.stacked_widget.currentIndex() == 0)
        right_layout.addWidget(self.status_bar)

        main_layout.addWidget(right_pane)

        self.config.config_changed.connect(self._on_config_changed)

        # Lock feature removed: locking is now exclusive to ``nx.py``.
        # The launcher no longer constructs a lock overlay, no longer
        # polls the on-disk lock file, and no longer probes Supabase
        # for remote-lock state. All that remains is the heartbeat
        # timer that keeps this device counted as online.

        # Community heartbeat — fixed 10s cadence (the launcher's
        # heartbeat is the user-facing "I'm online" pulse, separate
        # from nx.py's 30s admin pulse).
        #
        # Flow on startup:
        # Heartbeat cadence:
        #   1. Fire one beat on the very next event-loop tick so the
        #      chip goes green within milliseconds of the window
        #      being shown. The beat() RPC is a single round trip
        #      that returns the full community state in its response.
        #   2. From then on, fire a beat every 5s. Every beat both
        #      sends (upsert this device) and receives — counters,
        #      lock state, feature flags, recent community activity,
        #      and the 1-month UUID-recycle flag all come back inline.
        self._heartbeat_timer = None
        if _USERS_OK and CommunityClient is not None and assemble_heartbeat_payload is not None:
            self._heartbeat_timer = QTimer(self)
            # Honour the user's config but clamp to [5s, 60s]. A typo
            # in the config can't disable the heartbeat (0) or hammer
            # Supabase (1s). 5s is the new default — one round trip
            # every 5s keeps the chip's online count feeling live
            # without burning the free tier.
            try:
                cfg_interval = int(
                    (get_users_config() or {}).get("heartbeat_interval_seconds", 5) or 5
                )
            except Exception:
                cfg_interval = 5
            cfg_interval = max(5, min(60, cfg_interval))
            self._heartbeat_timer.setInterval(cfg_interval * 1000)
            self._heartbeat_timer.timeout.connect(self._send_heartbeat)
            self._heartbeat_timer.start()
            # Fire one beat as soon as the event loop is free — the
            # user wants the chip green within a second of the window
            # being shown, not waiting for a 1-second timer. The
            # heartbeat worker runs on a thread pool, so it never
            # blocks paint. If the network is down the chip stays red
            # and the timer will retry on its next tick.
            QTimer.singleShot(0, self._send_heartbeat)

            # Wire the sidebar community chip: clicking it must dispatch
            # a fresh beat (the chip itself only pulses — the actual
            # round trip is done by the same telemetry worker that the
            # 10s timer uses, so there's exactly one heartbeat code
            # path). The chip's internal ``_on_click`` already debounces
            # double-clicks for us; we just need to route the signal
            # into ``_send_heartbeat`` and tell the chip we accepted
            # the click so its debounce window restarts.
            try:
                chip = getattr(self.nav_bar, "community_chip", None)
                if chip is not None and hasattr(chip, "beat_requested"):
                    chip.beat_requested.connect(self._on_community_chip_clicked)
            except Exception:
                pass

        # ----------------------------------------------------------------
        # Remote lock — overlay + encrypted local persistence
        # ----------------------------------------------------------------
        # The launcher is locked when ``nx.py`` (the admin console)
        # flips ``is_locked`` on this device's heartbeat row. The lock
        # state is mirrored to an encrypted file at
        # ``%APPDATA%\.neurax\cache\device_lock.bin`` so a relaunched
        # or offline launcher still enforces the lock — the file is
        # the local source of truth, Supabase only confirms or clears
        # it on a heartbeat round trip.
        #
        # ``LockScreenOverlay`` paints the full-screen "LOCKED REMOTELY"
        # UI with a pulsing shield + the admin's message. It's
        # intentionally distinct from the older "local AFK lock" path
        # (which had an in-app UNLOCK button) — a remote lock can only
        # be cleared by nx.py clearing the flag and the launcher
        # observing ``is_locked = false`` on a subsequent beat.
        self._device_lock = None
        self._lock_overlay = None
        if _DEVICE_LOCK_OK and DeviceLock is not None:
            try:
                from neurax.core.config import get_dot_neurax_dir
                self._device_lock = DeviceLock(get_dot_neurax_dir())
            except Exception:
                # If we can't reach the dot-folder (locked-down user
                # account, missing APPDATA, etc.) we just skip the
                # encrypted-file persistence and rely on the in-session
                # overlay only — the lock is still enforced while the
                # launcher is running, but a restart would lose the
                # state. The admin can always re-lock from nx.py.
                self._device_lock = None
        if _LOCK_OVERLAY_OK and LockScreenOverlay is not None:
            try:
                # The overlay installs its own event filter on the
                # parent and re-syncs its geometry in ``showEvent``,
                # so we don't have to do anything more here than
                # construct + hide. Setting geometry at this point
                # is unreliable because the central widget's rect()
                # may still be (0, 0, 0, 0) — Qt hasn't run a
                # layout pass yet. The overlay will fill the parent
                # correctly on its first ``showEvent``.
                self._lock_overlay = LockScreenOverlay(config, self.central_widget)
                self._lock_overlay.hide()
            except Exception:
                self._lock_overlay = None
        # Re-read the local lock file at startup. If a previous
        # session left the file behind (admin locked us, we restarted
        # while offline) the launcher must boot straight into the
        # locked overlay — we do not wait for the first heartbeat
        # round trip.
        try:
            if self._device_lock is not None:
                rec = self._device_lock.read()
                if rec.is_active():
                    self._enforce_remote_lock(
                        True,
                        rec.message or "",
                        rec.locked_by or "admin",
                        rec.locked_at or "",
                    )
        except Exception:
            pass

    def _enforce_remote_lock(self, is_locked: bool, message: str,
                              locked_by: str = "admin",
                              locked_at: str = "") -> None:
        """Apply the remote-lock overlay + sync the encrypted local
        file. Called on startup (from the constructor's lock-file
        re-read) and after every successful heartbeat (from
        ``_apply_telemetry_result``).

        The overlay is the single visible artefact; the encrypted file
        is the source of truth across restarts.
        """
        if self._lock_overlay is None:
            # No overlay available (PyQt6 widget failed to construct,
            # or cryptography is missing). At least try to keep the
            # local file in sync so a future restart catches up.
            self._sync_remote_lock_file(is_locked, message, locked_by, locked_at)
            return
        overlay = self._lock_overlay
        if is_locked:
            # Persist first so a crash here still leaves the lock file
            # on disk for the next launch.
            self._sync_remote_lock_file(True, message, locked_by, locked_at)
            if not overlay.is_active:
                overlay.show_locked("remote", message=message)
            else:
                overlay.set_lock_source("remote", message=message)
                # We don't re-shake on every heartbeat, only when the
                # admin refuses to unlock.
                if (overlay._remote_message != (message or "").strip()
                        and (message or "").strip()):
                    # Admin changed the message — brief visual cue.
                    overlay._shake()
            overlay.setGeometry(self.central_widget.rect())
        else:
            # Admin cleared the lock from nx.py. Drop the file and
            # hide the overlay.
            self._sync_remote_lock_file(False, "", "", "")
            if overlay.is_active:
                overlay.hide_unlocked()

    def _sync_remote_lock_file(self, is_locked: bool, message: str,
                                locked_by: str, locked_at: str) -> None:
        """Write or remove the encrypted local lock file so a restart
        of the launcher still enforces the lock."""
        if self._device_lock is None:
            return
        try:
            if is_locked:
                # ``DeviceLock.lock()`` always stamps ``locked_at`` with
                # ``_now_iso()``; we accept that — the local timestamp
                # only matters as "how stale is this lock?", and the
                # admin's exact Supabase timestamp isn't useful once
                # the launcher has restarted.
                self._device_lock.lock(
                    message=message or "",
                    locked_by=locked_by or "admin",
                )
            else:
                self._device_lock.unlock()
        except Exception:
            # Persistence is best-effort. The overlay is still
            # enforced in-session even if the file write fails.
            pass

    def _make_placeholder(self, attr_name: str) -> QWidget:
        """Cheap stand-in shown for lazy tabs that haven't been built yet.

        Construction is just one QLabel — no network calls, no list
        building — so adding eleven of them at startup costs nothing.
        The real view is swapped in the first time the user actually
        visits that tab (see :meth:`_ensure_view`)."""
        holder = QWidget()
        holder.setObjectName(f"LazyPlaceholder_{attr_name}")
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch(1)
        lbl = QLabel("Loading…")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("color: #64748B; font-size: 13px; letter-spacing: 1px;")
        layout.addWidget(lbl)
        layout.addStretch(1)
        # Remember which factory this placeholder belongs to so we can
        # build the right view later.
        holder._lazy_attr = attr_name  # type: ignore[attr-defined]
        return holder

    def _ensure_view(self, index: int) -> QWidget:
        """Return the real widget for ``index``, building it on demand.

        If the slot at ``index`` is still a placeholder (because the
        user has never opened that tab), construct the matching view
        now, hand it to ``AnimatedStackedWidget.set_lazy_widget`` so
        the pending slide runs against the new view, and return the
        new widget. Subsequent calls return the same cached instance.
        """
        current = self.stacked_widget.widget(index)
        attr_name = getattr(current, "_lazy_attr", None)
        if not attr_name:
            return current
        # Build the real view, swapping it into the same slot.
        factory = next(f for a, f in self._view_factories if a == attr_name)
        try:
            real_view = factory()
        except Exception as ex:
            # If construction crashes, leave the placeholder in place so
            # the user still sees something and the launcher doesn't
            # black-hole. We log via the global logger.
            try:
                from neurax.core.logger import Logger
                Logger.get_instance().warning(f"Lazy view '{attr_name}' failed to build: {ex}")
            except Exception:
                pass
            return current
        self._view_cache[attr_name] = real_view
        setattr(self, attr_name, real_view)
        # Hand off to AnimatedStackedWidget so the swap is atomic and
        # the slide animation can run against the real view rather
        # than the placeholder that's about to be deleted.
        self.stacked_widget.set_lazy_widget(index, real_view)
        return real_view

    def _on_tab_changed(self, index: int):
        # ``slide_to_index`` is a no-op while the destination slot is
        # still a placeholder (it just parks a pending-slide request in
        # the stacked widget). That means the previous tab keeps
        # painting, the user sees no half-broken animation, and the
        # heavy ``__init__`` for the new view runs on the next idle
        # tick — by which point the slide runs cleanly against the
        # freshly-built real widget. The placeholder never appears on
        # screen in the meantime.
        self.stacked_widget.slide_to_index(index)
        self.status_bar.setVisible(index == 0)
        DiscordManager.get_instance().on_tab_changed(index)

        # Build (or rebuild) the destination view on the next idle
        # tick. ``0`` means "as soon as the event loop is free again".
        # The deferred tick is what keeps the GUI responsive: the
        # click handler returns immediately, the event loop redraws,
        # then the heavy ``__init__`` runs.
        try:
            QTimer.singleShot(
                0,
                lambda i=index: self._ensure_view_safe(i),
            )
        except Exception:
            pass

        if index == 7:
            announcement = self._view_cache.get("announcement_view")
            if announcement is not None and hasattr(announcement, "mark_as_read"):
                try:
                    announcement.mark_as_read()
                except Exception:
                    pass
        if index == 10:
            afk = self._view_cache.get("afk_view")
            if afk is not None and hasattr(afk, "reset_timer"):
                try:
                    afk.reset_timer()
                except Exception:
                    pass

    def _ensure_view_safe(self, index: int) -> None:
        """Same as :meth:`_ensure_view` but never throws — runs on the
        idle-tick scheduled by :meth:`_on_tab_changed`."""
        try:
            self._ensure_view(index)
        except Exception:
            pass

    def _toggle_console(self):
        # ``play_view`` is the only eagerly-built view, so it is safe to
        # call directly here.
        if hasattr(self, "play_view") and self.play_view is not None:
            try:
                self.play_view.toggle_console()
            except Exception:
                pass

    def quick_join(self, host: str, port: int):
        self.nav_bar._on_btn_clicked(0)
        if hasattr(self, "play_view") and self.play_view is not None:
            self.play_view.launch_game(host, port)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self.isMaximized() and not self.isMinimized():
            self.config.set("window_width", self.width())
            self.config.set("window_height", self.height())
        # Keep the lock overlay covering the full central widget area
        # when the window is resized / maximised / restored.
        if getattr(self, "_lock_overlay", None) is not None and self._lock_overlay.isVisible():
            self._lock_overlay.setGeometry(self.centralWidget().rect())

    def closeEvent(self, event):
        # Mark our device as offline before tearing down — best effort,
        # never block the close on a network failure.
        try:
            self._mark_offline()
        except Exception:
            pass
        DiscordManager.get_instance().close()
        super().closeEvent(event)

    def _on_community_chip_clicked(self) -> None:
        """Handle a click on the sidebar community chip.

        The chip already:
          * debounces the click (2s) so double-clicks don't fire two beats,
          * pulses itself so the user gets silent visual feedback,
          * emits :attr:`beat_requested` once it's decided to fire.

        All we do here is route that signal back through the same
        ``_send_heartbeat`` path the 10s timer uses, so there's exactly
        one heartbeat code path in the launcher. We also reset the
        chip's debounce window so the next click is immediately
        accepted again — the chip already did its debounce to keep the
        UI responsive, but we extend the lockout a tiny bit further so
        the in-flight beat can't be cancelled by a second click mid-way.
        """
        try:
            chip = getattr(self.nav_bar, "community_chip", None)
            if chip is not None and hasattr(chip, "notify_beat_dispatched"):
                chip.notify_beat_dispatched()
        except Exception:
            pass
        # Reuse the same dispatch path as the 10s timer — the worker
        # already knows how to send+receive against the v2 ``beat()``
        # RPC and apply the result to the chip via
        # ``_apply_telemetry_result``.
        self._send_heartbeat()

    def _send_heartbeat(self):
        """Schedule one heartbeat on a worker thread so the GUI never freezes.

        The actual HTTP work (one ``requests`` POST against Supabase)
        runs inside a :class:`QRunnable` on the global
        ``QThreadPool``. When the worker finishes, it queues the
        follow-up UI updates (sidebar chip + ``nx.py``-driven online
        flag) back on the GUI thread via a single-shot timer.

        Note: ``nx.py`` is now the source of truth for "this device is
        online". The launcher's heartbeat keeps the row fresh in
        Supabase so the chip stays green and ``nx.py --lock`` can find
        this device. Without a beat, this device falls off the
        ``community_online_count`` view and the chip goes red.
        """
        if not _USERS_OK or CommunityClient is None or assemble_heartbeat_payload is None:
            return
        cfg = get_users_config() if get_users_config is not None else {}
        if cfg.get("offline_mode"):
            return
        if not cfg.get("supabase_url") or not cfg.get("supabase_anon_key"):
            return
        # NOTE: the network-monitor gate was removed. We always try the
        # heartbeat regardless of the local link's state — the Supabase
        # client has its own short timeout, the chip paints red on
        # failure, and we'd rather show "offline (retrying)" than have
        # the launcher silently stop pinging.
        QThreadPool.globalInstance().start(_TelemetryJob(self, "heartbeat"))

    @pyqtSlot(str, "QVariantMap")
    def _apply_telemetry_result(self, kind: str, result) -> None:
        """Receive a result from a :class:`_TelemetryJob` worker and
        apply the UI side-effects on the GUI thread. ``kind`` is now
        always ``"heartbeat"``; ``result`` is the rich dict returned
        by the v2 ``beat()`` RPC (counters + self + flags + recent).

        The ``@pyqtSlot(str, "QVariantMap")`` decoration is *required*
        so PyQt6 registers the slot with the C++ meta-object as
        ``(QString, QVariantMap)`` — matching the worker's
        ``Q_ARG("QVariantMap", result)``. Without this decoration the
        meta-object only sees ``(str, object)`` and
        ``QMetaObject.invokeMethod`` silently returns ``False`` with
        a "No such method" warning, which means ``mark_acknowledged``
        never runs and the chip stays red forever (the very bug the
        user just reported).
        """
        if kind == "heartbeat":
            try:
                # If Supabase acknowledged our beat, flip the chip's
                # sticky-green latch and pass through the inline
                # counters. From this moment on the chip stays green
                # for the rest of the session — transient failures
                # no longer bounce it back to red.
                if isinstance(result, dict) and result.get("ok"):
                    chip = (
                        getattr(self.nav_bar, "community_chip", None)
                        if self.nav_bar is not None
                        else None
                    )
                    if chip is not None:
                        if hasattr(chip, "mark_acknowledged"):
                            chip.mark_acknowledged(
                                int(result.get("online_count", 0) or 0)
                            )
                        # Forward the remote-lock state too. The chip
                        # flips to a muted-red "locked" pill so the
                        # user has a one-line status check in addition
                        # to the full-screen overlay below.
                        if hasattr(chip, "apply_lock_state"):
                            chip.apply_lock_state(
                                bool(result.get("is_locked", False)),
                                str(result.get("lock_message", "") or ""),
                            )
                    # Remote-lock enforcement. Each successful beat
                    # returns ``is_locked`` + ``lock_message`` for this
                    # device; we mirror that to the encrypted local
                    # file and toggle the full-screen overlay. This is
                    # what makes ``nx.py --lock`` actually take effect
                    # on the launcher.
                    self_self = result.get("raw", {}).get("self") or {}
                    is_locked = bool(result.get("is_locked", False))
                    lock_message = str(result.get("lock_message", "") or "")
                    # ``_lock_overlay`` / ``_device_lock`` may be missing
                    # if the constructor didn't run (test stubs,
                    # ``MainWindow.__new__`` paths) — use getattr so the
                    # telemetry worker never crashes on this path.
                    overlay = getattr(self, "_lock_overlay", None)
                    if is_locked or (overlay is not None and overlay.is_active):
                        self._enforce_remote_lock(
                            is_locked,
                            lock_message,
                            locked_by=str(self_self.get("lock_by", "") or "admin"),
                            locked_at=str(self_self.get("lock_at", "") or ""),
                        )
                    # If the launcher just learned that the previous
                    # UUID was stale and got recycled by the server,
                    # re-read the local UUID (which ``force_regenerate_device_uuid``
                    # inside ``client.beat()`` already wrote to the
                    # keychain + sidecar file) so any UI element that
                    # shows the device identity (e.g. CommunityView's
                    # ``device_uuid_lbl``) sees the new value on the
                    # next paint.
                    raw = result.get("raw") or {}
                    server_self_id = str((raw.get("self") or {}).get("device_id", "") or "")
                    if server_self_id:
                        try:
                            local_uuid = (
                                get_or_create_device_uuid()
                                if _USERS_OK and get_or_create_device_uuid is not None
                                else ""
                            )
                            if local_uuid and local_uuid != server_self_id:
                                # Server is on a UUID we don't have locally —
                                # log it so the operator can see the recycle
                                # happened on the next launch.
                                try:
                                    self.logger.info(
                                        "device_uuid rotated: %s -> %s",
                                        local_uuid, server_self_id,
                                    )
                                except Exception:
                                    pass
                        except Exception:
                            pass
                if self.nav_bar is not None and hasattr(self.nav_bar, "refresh_community_chip"):
                    self.nav_bar.refresh_community_chip()
            except Exception:
                pass
            return

    def _mark_offline(self):
        if not _USERS_OK or CommunityClient is None or assemble_heartbeat_payload is None:
            return
        cfg = get_users_config() if get_users_config is not None else {}
        client = CommunityClient(cfg.get("supabase_url", ""), cfg.get("supabase_anon_key", ""))
        if not client.is_configured():
            return
        try:
            payload = assemble_heartbeat_payload()
            client.set_offline(payload.get("device_id", ""))
        except Exception:
            pass

    def _toggle_nav_bar(self):
        self.nav_bar.setVisible(not self.nav_bar.isVisible())

    def enter_background_mode(self):
        """Hide the window and stop heavy timers. Safe to call before
        every lazy view has been built — the announcement view is only
        accessed if it's already in the cache."""
        self.hide()
        announcement = self._view_cache.get("announcement_view") if hasattr(self, "_view_cache") else None
        if announcement is not None:
            timer = getattr(announcement, "timer", None)
            if timer is not None:
                try:
                    timer.stop()
                except Exception:
                    pass

        gc.collect()

        if sys.platform == "win32":
            try:
                import ctypes
                handle = ctypes.windll.kernel32.GetCurrentProcess()
                ctypes.windll.psapi.EmptyWorkingSet(handle)
            except Exception:
                pass

    def exit_background_mode(self):
        self.show()
        if self.isMinimized():
            self.showNormal()
        self.activateWindow()
        self.raise_()

        announcement = self._view_cache.get("announcement_view") if hasattr(self, "_view_cache") else None
        if announcement is not None:
            timer = getattr(announcement, "timer", None)
            if timer is not None:
                try:
                    timer.start()
                except Exception:
                    pass

    def _on_config_changed(self, key: str, value: object):
        if key in ("accent_color", "theme_mode"):
            accent = self.config.get("accent_color", "#00F0FF")
            mode = self.config.get("theme_mode", "dark")

            qss = Theme.get_stylesheet(accent, mode)
            self.setStyleSheet(qss)
            app = QApplication.instance()
            if app:
                app.setStyleSheet(qss)

            self.nav_bar.set_theme_mode(mode)
            self.nav_bar.set_accent_color(accent)
            self.nav_bar.set_active_tab(self.stacked_widget.currentIndex())
            self.toggle_nav_btn.setIcon(create_monochrome_icon("hamburger", Theme.get_icon_color(mode), QColor(accent)))
            self.bug_btn.setIcon(create_monochrome_icon("bug", Theme.get_icon_color(mode), QColor(accent)))

    def _on_network_state_changed(self, state: object, detail: str) -> None:
        """React to network monitor transitions.

        Lock handling is gone — only the heartbeat + community chip
        refresh remain. When the link comes back ONLINE we nudge both
        so the chip count and ``nx.py`` see this device immediately.
        """
        if state == _NetState.ONLINE:
            try:
                if hasattr(self, "_send_heartbeat"):
                    self._send_heartbeat()
            except Exception:
                pass
            try:
                if self.nav_bar is not None and hasattr(self.nav_bar, "refresh_community_chip"):
                    self.nav_bar.refresh_community_chip()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Telemetry worker — runs the Supabase heartbeat off the GUI thread so
# the launcher never freezes for a network round-trip. The lock probe
# was removed: lock state is now exclusive to ``nx.py``.
# ---------------------------------------------------------------------------
class _TelemetryJob(QRunnable):
    """Background telemetry round-trip — heartbeat only.

    The lock probe was removed: lock state is now exclusive to
    ``nx.py``. This job only fires the heartbeat so the launcher's
    device stays present in Supabase.

    The job uses :func:`QMetaObject.invokeMethod` with a
    ``Qt.QueuedConnection`` to hand the result back to the GUI thread
    without crossing the Qt affinity boundary.
    """

    def __init__(self, main_win, kind: str = "heartbeat"):
        super().__init__()
        self.setAutoDelete(True)
        self._main = main_win
        self._kind = kind

    def run(self) -> None:  # type: ignore[override]
        try:
            if self._kind != "heartbeat":
                return
            result = self._run_heartbeat()
            try:
                from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
                QMetaObject.invokeMethod(
                    self._main,
                    "_apply_telemetry_result",
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(str, self._kind),
                    Q_ARG("QVariantMap", result),
                )
            except Exception:
                # Last-resort: drop the result. The timer will retry.
                pass
        except Exception:
            # Never let an exception escape a QRunnable — that aborts
            # the thread pool worker.
            pass

    def _run_heartbeat(self) -> dict:
        """Single send+receive round trip against the v2 ``beat()`` RPC.

        On a successful round trip the response includes the live
        community counters, the lock state for this device, the
        active feature flags, and the latest community activity.
        Everything the launcher needs comes back in one HTTP call —
        the chip, the lock overlay, and the feature-flag checks all
        read from this same response.
        """
        empty = {"ok": False, "status": 0, "error": "", "online_count": 0,
                 "is_locked": False, "lock_message": "", "flags": []}
        try:
            from users import CommunityClient, assemble_heartbeat_payload
            cfg = get_users_config() if get_users_config is not None else {}
            if cfg.get("offline_mode"):
                return {**empty, "error": "offline_mode"}
            client = CommunityClient(
                cfg.get("supabase_url", ""),
                cfg.get("supabase_anon_key", ""),
            )
            if not client.is_configured():
                return {**empty, "error": "not_configured"}
            payload = assemble_heartbeat_payload()
            body = client.beat(payload)
            if body is None:
                return {
                    "ok": False,
                    "status": int(getattr(client, "last_status", 0) or 0),
                    "error": str(getattr(client, "last_error", "") or ""),
                    "online_count": 0,
                    "is_locked": False,
                    "lock_message": "",
                    "flags": [],
                }
            # The beat() RPC returns the counters and lock state
            # inline. Read them from the same response we just got.
            counters = body.get("counters") or {}
            self_self = body.get("self") or {}
            flags = body.get("flags") or []
            return {
                "ok": True,
                "status": 200,
                "error": "",
                "online_count": int(counters.get("online_count", 0) or 0),
                "total_count":  int(counters.get("total_count", 0) or 0),
                "is_locked":    bool(self_self.get("is_locked", False)),
                "lock_message": str(self_self.get("lock_message", "") or ""),
                "flags":        flags,
                "raw":          body,
            }
        except Exception as e:
            return {**empty, "error": f"{type(e).__name__}: {e}"}