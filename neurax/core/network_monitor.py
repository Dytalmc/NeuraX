"""Network health monitor for the launcher.

The launcher has several online features (Modrinth mod browser, AI Version
Radar, Supabase community chip, Discord RPC, telemetry heartbeats). On a
slow or missing internet connection each of these can hang the GUI thread
or surface confusing errors. This module wraps a tiny state machine:

    State.UNKNOWN  ──probe──▶  State.ONLINE    (latency <  slow_threshold)
                        │
                        └──▶  State.SLOW      (probe took too long)
                        │
                        └──▶  State.OFFLINE   (probe raised an exception)

Transitions are emitted as a ``state_changed(State, str)`` Qt signal so the
rest of the app can disable online-only views when the link is bad. A 5-minute
timer keeps re-probing; when we transition OFFLINE→ONLINE we notify all the
subscribed features so they can re-enable themselves.

A probe is a single HTTP HEAD against a small, fast endpoint with a short
timeout. The endpoints are deliberately chosen for low latency and small
payload: Cloudflare's ``1.1.1.1`` and the Mojang version manifest host. We
also do a DNS lookup for ``api.minecraft.net`` as a fallback signal because
sometimes HTTP is firewalled but DNS still resolves.

The monitor is intentionally minimal — it does not own any Qt widgets and
can be instantiated and probed from any thread.
"""
from __future__ import annotations

import socket
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Iterable, Optional

from PyQt6.QtCore import QObject, QTimer, pyqtSignal


class State(str, Enum):
    UNKNOWN = "unknown"
    ONLINE = "online"
    SLOW = "slow"
    OFFLINE = "offline"


# Probe configuration. The slow threshold is intentionally generous — we
# only mark the link "slow" if a single HEAD request takes more than this,
# which is well above what a normal link should see even on a congested
# mobile connection.
SLOW_THRESHOLD_SECONDS = 4.0
PROBE_TIMEOUT_SECONDS = 6.0

# Five-minute re-probe interval while in SLOW/OFFLINE so we don't burn the
# user's battery hammering probes.
REPROBE_INTERVAL_MS = 5 * 60 * 1000

# Quick re-probe interval after ONLINE for catching flapping without being
# aggressive about it.
QUICK_REPROBE_INTERVAL_MS = 60 * 1000

# Probe endpoints — small, fast, and high-availability.
_PROBE_URLS = (
    "https://1.1.1.1/cdn-cgi/trace",
    "https://www.minecraft.net/",
    "https://piston-meta.mojang.com/mcpe/v1/manifest.json",
)


@dataclass
class ProbeResult:
    state: State
    latency_seconds: float
    detail: str


def _probe_blocking(timeout: float = PROBE_TIMEOUT_SECONDS) -> ProbeResult:
    """Synchronous probe — runs on a worker thread.

    Tries each probe URL in order. The first one that returns within the
    timeout wins. If all raise, we try a DNS lookup against
    ``api.minecraft.net`` as a last-ditch signal that the machine can
    reach at least the public internet. If everything fails we report
    OFFLINE.
    """
    started = time.monotonic()
    last_err = ""
    for url in _PROBE_URLS:
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                # Any HTTP response means we reached the server. The latency
                # measurement is the time-to-first-byte.
                latency = time.monotonic() - started
                detail = f"{url} → {resp.status}"
                state = State.ONLINE if latency <= SLOW_THRESHOLD_SECONDS else State.SLOW
                return ProbeResult(state=state, latency_seconds=latency, detail=detail)
        except urllib.error.URLError as exc:
            last_err = f"{type(exc).__name__}: {exc}"
        except (TimeoutError, socket.timeout):
            last_err = "timeout"
        except Exception as exc:  # noqa: BLE001 — last-resort probe
            last_err = f"{type(exc).__name__}: {exc}"

    # Fall back to DNS. We don't need the address, just confirmation that
    # the resolver could reach the public internet.
    try:
        socket.getaddrinfo("api.minecraft.net", 443, type=socket.SOCK_STREAM)
        latency = time.monotonic() - started
        detail = f"dns ok; http probes failed: {last_err}"
        state = State.ONLINE if latency <= SLOW_THRESHOLD_SECONDS else State.SLOW
        return ProbeResult(state=state, latency_seconds=latency, detail=detail)
    except Exception as exc:  # noqa: BLE001
        return ProbeResult(
            state=State.OFFLINE,
            latency_seconds=time.monotonic() - started,
            detail=f"all probes failed; last_err={last_err}; dns={type(exc).__name__}: {exc}",
        )


class NetworkMonitor(QObject):
    """Singleton-ish network health monitor with Qt signals.

    The monitor is created once by the main window and lives for the
    lifetime of the launcher. Anyone interested in state changes connects
    to ``state_changed``. The monitor is also a QObject so it can be moved
    to a thread if needed, but by default it lives on the GUI thread and
    schedules probes on a background QThreadPool worker.
    """

    state_changed = pyqtSignal(object, str)  # (State, detail_str)

    _instance: "Optional[NetworkMonitor]" = None
    _instance_lock = threading.Lock()

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._state = State.UNKNOWN
        self._detail = ""
        self._lock = threading.Lock()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_timer)
        # Always do an initial probe immediately on startup so the rest of
        # the app can decide whether to enable online features.
        QTimer.singleShot(0, self.probe_async)

    # ----------------------------------------------------------- Singleton
    @classmethod
    def instance(cls) -> "NetworkMonitor":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    # --------------------------------------------------------------- State
    @property
    def state(self) -> State:
        return self._state

    @property
    def detail(self) -> str:
        return self._detail

    def is_online(self) -> bool:
        return self._state == State.ONLINE

    def is_offline(self) -> bool:
        return self._state in (State.OFFLINE, State.UNKNOWN)

    def is_slow(self) -> bool:
        return self._state == State.SLOW

    def online_features_enabled(self) -> bool:
        """Single source of truth for "should online features run right now"."""
        return self._state in (State.ONLINE, State.SLOW)

    # ----------------------------------------------------------- Probing
    def probe_async(self) -> None:
        """Schedule a probe on a worker thread and emit a state change when done."""
        from PyQt6.QtCore import QThreadPool, QRunnable

        class _ProbeJob(QRunnable):
            def __init__(self, monitor: "NetworkMonitor"):
                super().__init__()
                self.setAutoDelete(True)
                self._monitor = monitor

            def run(self) -> None:  # type: ignore[override]
                try:
                    result = _probe_blocking()
                except Exception as exc:  # noqa: BLE001
                    result = ProbeResult(
                        state=State.OFFLINE,
                        latency_seconds=0.0,
                        detail=f"probe crashed: {type(exc).__name__}: {exc}",
                    )
                # Hand the result back to the GUI thread.
                self._monitor._apply_probe(result)

        QThreadPool.globalInstance().start(_ProbeJob(self))

    def _apply_probe(self, result: ProbeResult) -> None:
        """GUI-thread slot: update internal state and emit the signal."""
        with self._lock:
            prev = self._state
            self._state = result.state
            self._detail = result.detail
        if result.state != prev:
            self.state_changed.emit(result.state, result.detail)
        self._reschedule(result.state)

    def _reschedule(self, state: State) -> None:
        self._timer.stop()
        if state == State.ONLINE:
            self._timer.start(QUICK_REPROBE_INTERVAL_MS)
        else:
            self._timer.start(REPROBE_INTERVAL_MS)

    def _on_timer(self) -> None:
        self.probe_async()

    # --------------------------------------------------- Subscriber model
    def subscribe(self, callback: Callable[[State, str], None]) -> None:
        """Connect ``callback`` to ``state_changed`` in a Python-friendly way."""
        self.state_changed.connect(callback)

    def unsubscribe(self, callback: Callable[[State, str], None]) -> None:
        try:
            self.state_changed.disconnect(callback)
        except (TypeError, RuntimeError):
            pass


def force_probe_now() -> None:
    """Convenience for callers that want to trigger an immediate probe."""
    NetworkMonitor.instance().probe_async()