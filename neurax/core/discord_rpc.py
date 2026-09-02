<<<<<<< HEAD
import os
=======
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
import time
import threading
import queue
import asyncio
<<<<<<< HEAD
import subprocess
import ipaddress
import re
import sys
import shutil
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from neurax.core.logger import Logger
from neurax.core.config import (
    get_logo_dir,
    get_discord_asset_dir,
    get_cached_logo_path,
    get_logo_url,
    seed_default_logos,
)
=======
import ipaddress
import re
import sys
from neurax.core.logger import Logger
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0

# Windows asyncio ProactorEventLoop Pipe deallocator safety patch
if sys.platform == "win32":
    try:
        import asyncio.windows_utils
        from asyncio.proactor_events import _ProactorBasePipeTransport

        _orig_del = _ProactorBasePipeTransport.__del__

        def _safe_del(self, *args, **kwargs):
            try:
                _orig_del(self, *args, **kwargs)
            except BaseException:
                pass

        _ProactorBasePipeTransport.__del__ = _safe_del
        _orig_fileno = asyncio.windows_utils.PipeHandle.fileno

        def _safe_fileno(self):
            try:
                return _orig_fileno(self)
            except (ValueError, OSError):
                return -1

        asyncio.windows_utils.PipeHandle.fileno = _safe_fileno
    except Exception:
        pass

try:
    import pypresence
    PYPRESENCE_AVAILABLE = True
except ImportError:
    PYPRESENCE_AVAILABLE = False

<<<<<<< HEAD

# ---------------------------------------------------------------------------
# Client IDs
# ---------------------------------------------------------------------------
# Legacy NeuraX application IDs. These are kept so an out-of-the-box build
# still *tries* to connect, but most of them are no longer registered
# (Discord returns `Error Code: 4000 - Client ID is Invalid` for any ID
# that has been deleted from the developer portal). Set
# `discord_client_id` in the user's config to a freshly registered
# application to override.
LEGACY_CLIENT_IDS = [
=======
CLIENT_IDS = [
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
    "1089247653258100806",
    "1115278784742838342",
    "1077677906477527130",
    "943488506840223764",
<<<<<<< HEAD
    "1218520338780770304",
]

# Asset keys we expect each Client ID to have uploaded. Discord only
# displays an asset if (a) the application has it registered under this
# exact key and (b) the value is a `file://` URL on disk or a publicly
# reachable URL. We mirror those keys locally below.
ASSET_KEY_LARGE = "nx_logo"
ASSET_KEY_SMALL = "nx_logo_small"

# Discord only accepts asset keys it knows about on the application page.
# We upload our bundled `nx.ico` / `nx.png` automatically the first time
# RPC connects, by writing them into `neurax/logos/` and pointing Discord
# at `file://` URLs.
REMOTE_ASSET_FALLBACKS = [
    "https://raw.githubusercontent.com/Dytalmc/NeuraX/main/n2/nx.ico",
    "https://raw.githubusercontent.com/Dytalmc/NeuraX/main/nx.ico",
    "https://raw.githubusercontent.com/Dytalmc/NeuraX/main/n2/nx.png",
]
=======
    "1218520338780770304"
]

ASSET_NEURAX = "https://raw.githubusercontent.com/Dytalmc/NeuraX/main/n2/nx.ico"
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0

KNOWN_SERVERS = {
    "hypixel.net": "Hypixel Network",
    "wynncraft.com": "Wynncraft MMORPG",
    "donutsmp.net": "Donut SMP",
    "originrealms.com": "Origin Realms",
    "cobblemon.com": "Cobblemon Islands",
    "manacube.com": "ManaCube Network",
    "massivecraft.com": "MassiveCraft Folia",
    "leafmc.eu": "LeafMC Network",
    "cosmicpvp.me": "CosmicPvP",
    "pumpkinmc.com": "PumpkinMC Network",
    "2b2t.org": "2b2t Anarchy",
}

<<<<<<< HEAD

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
=======
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
def is_private_ip(host: str) -> bool:
    if not host:
        return True
    host_clean = host.strip().lower()
    if host_clean in ("localhost", "127.0.0.1", "::1", "lan") or host_clean.endswith(".local") or host_clean.endswith(".lan"):
        return True
    try:
        ip = ipaddress.ip_address(host_clean)
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        pass
    if re.match(r"^10\.", host_clean) or re.match(r"^192\.168\.", host_clean) or re.match(r"^172\.(1[6-9]|2[0-9]|3[0-1])\.", host_clean):
        return True
    return False

<<<<<<< HEAD

=======
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
def resolve_friendly_server_name(host: str) -> str:
    if not host:
        return "Multiplayer"
    host_clean = host.strip().lower()
    for domain, name in KNOWN_SERVERS.items():
        if domain in host_clean:
            return name
    parts = host_clean.split(".")
    if len(parts) >= 2:
        return parts[-2].capitalize() + " Server"
    return host

<<<<<<< HEAD

def _discord_is_running() -> bool:
    """Best-effort, stdlib-only check for whether the Discord desktop
    client is currently running on this machine. We avoid `psutil` so we
    do not introduce a new top-level dependency."""
    try:
        if sys.platform == "win32":
            try:
                from neurax.core._silent_proc import check_output_silent
                out = check_output_silent(
                    ["tasklist", "/FI", "IMAGENAME eq Discord.exe", "/NH"],
                    timeout=1.5,
                    stderr_target=subprocess.DEVNULL,
                ).decode("utf-8", errors="ignore")
                return "Discord.exe" in out
            except Exception:
                # Fall back to iterating the process table via ctypes if
                # tasklist is filtered too aggressively.
                try:
                    import ctypes
                    from ctypes import wintypes

                    TH32CS_SNAPPROCESS = 0x00000002

                    class PROCESSENTRY32W(ctypes.Structure):
                        _fields_ = [
                            ("dwSize", wintypes.DWORD),
                            ("cntUsage", wintypes.DWORD),
                            ("th32ProcessID", wintypes.DWORD),
                            ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_void_p)),
                            ("th32ModuleID", wintypes.DWORD),
                            ("cntThreads", wintypes.DWORD),
                            ("th32ParentProcessID", wintypes.DWORD),
                            ("pcPriClassBase", ctypes.c_long),
                            ("dwFlags", wintypes.DWORD),
                            ("szExeFile", ctypes.c_wchar * 260),
                        ]

                    CreateToolhelp32Snapshot = ctypes.windll.kernel32.CreateToolhelp32Snapshot
                    Process32FirstW = ctypes.windll.kernel32.Process32FirstW
                    Process32NextW = ctypes.windll.kernel32.Process32NextW
                    CloseHandle = ctypes.windll.kernel32.CloseHandle

                    snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
                    if snap == -1 or snap == 0:
                        return False
                    try:
                        entry = PROCESSENTRY32W()
                        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
                        if not Process32FirstW(snap, ctypes.byref(entry)):
                            return False
                        while True:
                            if "Discord.exe" in entry.szExeFile:
                                return True
                            if not Process32NextW(snap, ctypes.byref(entry)):
                                break
                    finally:
                        CloseHandle(snap)
                    return False
                except Exception:
                    return False
        else:
            import subprocess
            try:
                out = subprocess.check_output(["pgrep", "-fl", "Discord"], timeout=1.5, stderr=subprocess.DEVNULL).decode("utf-8", errors="ignore")
                return "Discord" in out
            except Exception:
                return False
    except Exception:
        return False


def _pipelines_running() -> bool:
    """Return True if any Discord IPC pipe is actually mounted. On
    Windows the pipes live under `\\\\.\\pipe\\discord-ipc-0` …
    `discord-ipc-9`. We do not touch them, only enumerate the directory."""
    if sys.platform != "win32":
        # On macOS / Linux Discord publishes a unix socket. We do not
        # attempt to enumerate; pypresence handles discovery.
        return True
    try:
        import ctypes
        import ctypes.wintypes as wintypes

        FindFirstFileW = ctypes.windll.kernel32.FindFirstFileW
        FindNextFileW = ctypes.windll.kernel32.FindNextFileW
        FindClose = ctypes.windll.kernel32.FindClose

        class WIN32_FIND_DATAW(ctypes.Structure):
            _fields_ = [
                ("dwFileAttributes", wintypes.DWORD),
                ("ftCreationTime", wintypes.FILETIME),
                ("ftLastAccessTime", wintypes.FILETIME),
                ("ftLastWriteTime", wintypes.FILETIME),
                ("nFileSizeHigh", wintypes.DWORD),
                ("nFileSizeLow", wintypes.DWORD),
                ("dwReserved0", wintypes.DWORD),
                ("dwReserved1", wintypes.DWORD),
                ("cFileName", wintypes.WCHAR * 260),
                ("cAlternateFileName", wintypes.WCHAR * 14),
            ]

        path = "\\\\.\\pipe\\"
        data = WIN32_FIND_DATAW()
        h = FindFirstFileW(path + "*", ctypes.byref(data))
        if h == -1 or h == 0:
            err = GetLastError()
            return err not in (ERROR_FILE_NOT_FOUND,)
        try:
            while True:
                name = data.cFileName
                if name.startswith("discord-ipc-"):
                    return True
                if not FindNextFileW(h, ctypes.byref(data)):
                    break
        finally:
            FindClose(h)
        return False
    except Exception:
        return True  # If we cannot enumerate, do not block — let pypresence try.


def _file_url_for(path: str) -> str:
    """Convert a Windows path to a Discord-safe `file://` URL with
    forward slashes and a leading slash before the drive letter."""
    if not path:
        return ""
    p = path.replace("\\", "/")
    if not p.startswith("/"):
        p = "/" + p
    return "file://" + p


def _seed_remote_asset_to_cache(remote_url: str, dest: Path, timeout: float = 4.0) -> bool:
    """Best-effort download of a remote asset into `dest`. Returns True
    on success. We only do this on the first run when no bundled copy
    was located; after that the file lives in the cache."""
    try:
        req = Request(remote_url, headers={"User-Agent": "NeuraX-Launcher/1.0"})
        with urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        if not data or len(data) < 16:
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        with open(tmp, "wb") as f:
            f.write(data)
        tmp.replace(dest)
        return dest.exists() and dest.stat().st_size > 0
    except (URLError, HTTPError, TimeoutError, OSError, ValueError):
        return False


def _resolve_local_asset(filenames):
    """Resolve one of `filenames` to a cached on-disk path inside
    `neurax/logos/`. Falls back to `seed_default_logos()` if missing.
    Returns the absolute path or an empty string if nothing was located
    on disk and the remote fallback failed too."""
    logo_dir = get_logo_dir()
    logo_dir.mkdir(parents=True, exist_ok=True)

    for fname in filenames:
        candidate = logo_dir / fname
        if candidate.exists() and candidate.stat().st_size > 0:
            return str(candidate)
        # Try the central seed (bundled copies under `n2/`, project root, etc.)
        try:
            seeded = seed_default_logos(force=False)
        except Exception:
            seeded = {}
        for v in seeded.values():
            if v and Path(v).name == fname and Path(v).exists() and Path(v).stat().st_size > 0:
                # Mirror into logos/ for stable canonical location.
                try:
                    shutil.copy2(v, candidate)
                except Exception:
                    pass
                if candidate.exists() and candidate.stat().st_size > 0:
                    return str(candidate)

    # As a last resort, try downloading one of the GitHub raw URLs.
    discord_cache = get_discord_asset_dir()
    discord_cache.mkdir(parents=True, exist_ok=True)
    fname = filenames[0]
    remote_target = discord_cache / fname
    if not remote_target.exists() or remote_target.stat().st_size == 0:
        for url in REMOTE_ASSET_FALLBACKS:
            if url.lower().endswith(fname.lower()):
                if _seed_remote_asset_to_cache(url, remote_target):
                    break
    if remote_target.exists() and remote_target.stat().st_size > 0:
        # Also mirror into logos/ so future runs hit the local cache.
        try:
            shutil.copy2(remote_target, logo_dir / fname)
        except Exception:
            pass
        return str(remote_target)
    return ""


def get_cached_discord_asset(name: str = ASSET_KEY_LARGE) -> str:
    """Return a Discord-ready reference (a `file://` URL) for a named
    asset. The first call seeds the cache from the bundled launcher
    art; subsequent calls hit the local file directly so Discord does
    not need to make an outbound HTTP request."""
    if name == ASSET_KEY_SMALL:
        local = _resolve_local_asset(["nx.png", "nx.ico"])
    else:
        local = _resolve_local_asset(["nx.ico", "nx.png"])
    return _file_url_for(local) if local else ""


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------
class DiscordManager:
    """Thread-safe background manager for NeuraX Discord Rich Presence (RPC).

    Designed for resilience:

    * Detects whether Discord is even running before attempting a
      connection, so the user gets a clear log line instead of pypresence
      complaining about a missing IPC pipe every 45 s.
    * Falls back through all Client IDs × all 10 Discord IPC pipes
      before giving up on a single attempt.
    * Uses an exponential reconnect schedule (5 s → 15 s → 60 s) so the
      moment Discord opens, presence shows up within seconds.
    * Caches assets under `neurax/logos/` and `neurax/cache/discord_assets/`
      so Discord can pull them via `file://` URLs with zero outbound HTTP.
=======
class DiscordManager:
    """Thread-safe background manager for NeuraX Discord Rich Presence (RPC).
    Provides live in-game status, player skin avatar integration, modloader identification,
    server discovery reporting, and seamless error recovery.
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
    """
    _instance = None
    _lock = threading.Lock()

<<<<<<< HEAD
    # Exponential backoff between connect attempts (seconds).
    RECONNECT_BACKOFF = (5.0, 15.0, 60.0)
    RATE_LIMIT_MIN_INTERVAL = 1.5
    PRESENCE_DEDUPE_INTERVAL = 15.0
    PIPE_RANGE = range(0, 10)

    def _candidate_client_ids(self):
        """Return the list of Discord application Client IDs we should
        try on this boot, in priority order:

        1. The user's own `discord_client_id` from config (highest priority).
        2. The bundled legacy IDs, minus any that Discord has already
           marked dead during this session.
        """
        ids = []
        seen = set()
        own = ""
        if self.config is not None:
            try:
                own = (self.config.get("discord_client_id", "") or "").strip()
            except Exception:
                own = ""
        if own and own.isdigit() and own not in seen:
            ids.append(own)
            seen.add(own)
        for legacy in LEGACY_CLIENT_IDS:
            if legacy in self._dead_client_ids:
                continue
            if legacy not in seen:
                ids.append(legacy)
                seen.add(legacy)
        return ids

    def _mark_client_id_dead(self, client_id: str):
        """Mark a Client ID as invalid for this session so we don't keep
        retrying it. Reset when the user updates the config or restarts."""
        if client_id and client_id not in self._dead_client_ids:
            self._dead_client_ids.add(client_id)

=======
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
    def __init__(self):
        self.logger = Logger.get_instance()
        self.rpc = None
        self.connected = False
        self.config = None
        self.start_time = int(time.time())
        self.game_start_time = None
<<<<<<< HEAD

=======
        
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
        self.in_game = False
        self.game_info = {}
        self.launcher_state = "Exploring NeuraX"
        self.launcher_details = "Dashboard"
<<<<<<< HEAD

        self._last_update_time = 0.0
        self._last_payload = {}
        self._reconnect_cooldown = 0.0
        self._reconnect_attempts = 0
        self._last_log_error = ""
        self._testing = False
        # Client IDs that Discord has explicitly rejected this session.
        self._dead_client_ids = set()
        # Track whether we've logged a fatal "all IDs rejected" so we
        # don't spam the log every retry.
        self._fatal_logged = False
=======
        
        self._last_update_time = 0.0
        self._last_payload = {}
        self._reconnect_cooldown = 0.0
        self._last_log_error = ""
        self._testing = False
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0

        self._queue = queue.Queue()
        self._running = True
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True, name="DiscordRPCWorker")
        self._worker_thread.start()

<<<<<<< HEAD
    # --- Singleton --------------------------------------------------------
=======
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
    @classmethod
    def get_instance(cls, config=None):
        with cls._lock:
            if cls._instance is None:
                cls._instance = DiscordManager()
            if config is not None:
                cls._instance.initialize(config)
            return cls._instance

<<<<<<< HEAD
    # --- Worker loop ------------------------------------------------------
    def _worker_loop(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            while self._running:
                now = time.time()
                if self.is_enabled() and not self.connected and now >= self._reconnect_cooldown and not self._testing:
                    self._do_connect(loop)
                try:
                    cmd, data = self._queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                try:
                    if cmd == "CONNECT":
                        if not self.connected:
                            self._do_connect(loop)
                    elif cmd == "UPDATE":
                        payload, force = data
                        self._do_update(payload, force)
                    elif cmd == "CLEAR":
                        self._do_clear()
                    elif cmd == "CLOSE":
                        self._do_clear()
                        self._do_close()
                        break
                except Exception as e:
                    self.logger.warning(f"Discord RPC worker command error: {e}")
                finally:
                    self._queue.task_done()
        finally:
            try:
                loop.close()
            except Exception:
                pass

    # --- Connect ----------------------------------------------------------
=======
    def _worker_loop(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        while self._running:
            now = time.time()
            if self.is_enabled() and not self.connected and now >= self._reconnect_cooldown and not self._testing:
                self._do_connect(loop)

            try:
                cmd, data = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                if cmd == "CONNECT":
                    if not self.connected:
                        self._do_connect(loop)
                elif cmd == "UPDATE":
                    payload, force = data
                    self._do_update(payload, force)
                elif cmd == "CLEAR":
                    self._do_clear()
                elif cmd == "CLOSE":
                    self._do_clear()
                    self._do_close()
                    break
            except Exception as e:
                self.logger.warning(f"Discord RPC worker command error: {e}")
            finally:
                self._queue.task_done()

        try:
            loop.close()
        except Exception:
            pass

>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
    def _do_connect(self, loop):
        if not PYPRESENCE_AVAILABLE or self.connected:
            return

        now = time.time()
        if now < self._reconnect_cooldown:
            return

<<<<<<< HEAD
        # Pre-flight: is Discord actually running?
        discord_running = _discord_is_running()
        if not discord_running:
            # Schedule a faster retry so the moment Discord opens we
            # light up. This is by far the most common case (the user
            # opens the launcher before Discord).
            self._schedule_retry(force_quick=True)
            msg = "Discord is not running — start the Discord desktop client to enable Rich Presence."
            if msg != self._last_log_error:
                self._last_log_error = msg
                self.logger.info(msg)
            return

        candidate_ids = self._candidate_client_ids()
        if not candidate_ids:
            # Every Client ID we know about has been rejected this
            # session. Stop hammering Discord and tell the user how to
            # fix it once.
            if not self._fatal_logged:
                self._fatal_logged = True
                own_hint = (
                    "Open Settings → Discord → set 'My Client ID' to a freshly "
                    "registered application at discord.com/developers."
                )
                self.logger.warning(
                    "No valid Discord Client ID available. " + own_hint
                )
            self._schedule_retry(force_quick=False)
            return

        connected = False
        last_error = ""

        for cid in candidate_ids:
            if connected:
                break
            rejected_4000 = False
            for pipe_idx in self.PIPE_RANGE:
=======
        connected = False
        last_error = ""

        for cid in CLIENT_IDS:
            if connected:
                break
            for pipe_idx in range(10):
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
                try:
                    if self.rpc:
                        try:
                            self.rpc.close()
                        except Exception:
                            pass
                        self.rpc = None
<<<<<<< HEAD
=======

>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
                    presence = pypresence.Presence(cid, pipe=pipe_idx, loop=loop)
                    presence.connect()
                    self.rpc = presence
                    self.connected = True
                    connected = True
                    self._reconnect_cooldown = 0.0
<<<<<<< HEAD
                    self._reconnect_attempts = 0
                    self._fatal_logged = False
                    self._last_log_error = ""
                    self.logger.info(
                        f"Discord Rich Presence connected using Client ID {cid} on pipe {pipe_idx}."
                    )
                    try:
                        self._warm_assets_for_client(cid)
                    except Exception:
                        pass
=======
                    self._last_log_error = ""
                    self.logger.info(f"Discord Rich Presence connected successfully using Client ID {cid} on pipe {pipe_idx}.")
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
                    self._build_and_send_presence(force=True)
                    break
                except Exception as e:
                    err_msg = str(e)
                    last_error = err_msg
                    if self.rpc:
                        try:
                            self.rpc.close()
                        except Exception:
                            pass
                        self.rpc = None
<<<<<<< HEAD
                    if "4000" in err_msg or "Invalid" in err_msg or "client_id" in err_msg.lower():
                        # Client ID is provably dead — stop trying pipes
                        # for it and mark it dead for the rest of the
                        # session so the next attempt tries the next ID
                        # immediately.
                        self._mark_client_id_dead(cid)
                        rejected_4000 = True
                        break
                    if "Pipe not found" in err_msg or "Connection refused" in err_msg:
=======

                    if "4000" in err_msg or "Invalid" in err_msg or "client_id" in err_msg.lower():
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
                        break

        if not connected:
            self.connected = False
<<<<<<< HEAD
            self._schedule_retry(force_quick=False)
            if not last_error:
                last_error = (
                    "Connected to Discord process but no IPC pipe responded "
                    "(pipes 0-9 all refused)."
                )
            # Friendly translations of pypresence's more cryptic messages.
            if "Could not find Discord installed and running" in last_error:
                friendly = (
                    "Discord is running but the IPC pipe handshake was rejected. "
                    "This usually means the Discord app needs a restart, or the "
                    "registered Client ID no longer has matching Rich Presence "
                    "assets. Will keep retrying."
                )
            elif rejected_4000:
                remaining = len(self._candidate_client_ids())
                if remaining == 0:
                    friendly = (
                        "Every Discord Client ID we know about has been rejected "
                        "with 'Client ID is Invalid' (Error Code: 4000). Open "
                        "Settings → Discord and paste a fresh Client ID from "
                        "discord.com/developers."
                    )
                else:
                    friendly = (
                        f"One or more Client IDs were rejected (Error Code: 4000). "
                        f"Trying {remaining} remaining ID(s)."
                    )
            else:
                friendly = last_error
            if friendly != self._last_log_error:
                self._last_log_error = friendly
                self.logger.warning(
                    f"Discord RPC connect failed (will retry): {friendly}"
                )

    def _warm_assets_for_client(self, client_id: str):
        """Best-effort: ensure `nx.ico` / `nx.png` exist locally and
        surface their `file://` URLs on the payload. We cannot upload
        to Discord's asset store from the client (that requires a
        developer portal login), but we *can* make sure our local
        payload points to a local file so the connected app — if the
        user has registered matching keys in the portal — renders it
        without any HTTP fetch."""
        try:
            seed_default_logos(force=False)
        except Exception:
            pass

    def _schedule_retry(self, force_quick: bool):
        """Bump the cooldown based on how many times we have failed in
        a row. Index 0 = first retry, last index = permanent cadence."""
        idx = self._reconnect_attempts
        if force_quick:
            # Discord isn't running — poll more often so the moment the
            # user launches Discord we connect.
            backoff = 5.0
        else:
            backoff = self.RECONNECT_BACKOFF[min(idx, len(self.RECONNECT_BACKOFF) - 1)]
        self._reconnect_cooldown = time.time() + backoff
        self._reconnect_attempts += 1

    # --- Update / clear / close ------------------------------------------
=======
            self._reconnect_cooldown = now + 45.0
            if last_error and last_error != self._last_log_error:
                self._last_log_error = last_error
                self.logger.warning(f"Discord RPC connection skipped or failed: {last_error}")

>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
    def _do_update(self, payload: dict, force: bool):
        if not self.connected or not self.rpc:
            return

        now = time.time()
        if not force:
<<<<<<< HEAD
            if payload == self._last_payload and (now - self._last_update_time < self.PRESENCE_DEDUPE_INTERVAL):
                return
            if (now - self._last_update_time) < self.RATE_LIMIT_MIN_INTERVAL:
=======
            if payload == self._last_payload and (now - self._last_update_time < 15.0):
                return
            if (now - self._last_update_time) < 1.5:
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
                return

        try:
            self.rpc.update(**payload)
            self._last_update_time = now
            self._last_payload = payload
        except Exception as e:
            self.logger.warning(f"Failed to update Discord presence: {e}")
            self.connected = False
            if self.rpc:
                try:
                    self.rpc.close()
                except Exception:
                    pass
            self.rpc = None
<<<<<<< HEAD
            # Quick reconnect on disconnect mid-update.
            self._reconnect_cooldown = time.time() + 5.0
=======
            self._reconnect_cooldown = now + 30.0
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0

    def _do_clear(self):
        if self.connected and self.rpc:
            try:
                self.rpc.clear()
                self._last_payload = {}
                self.logger.info("Cleared Discord RPC status.")
            except Exception as e:
                self.logger.warning(f"Failed to clear Discord RPC status: {e}")

    def _do_close(self):
        if self.rpc:
            try:
                if self.connected:
                    self.rpc.clear()
            except Exception:
                pass
            try:
                self.rpc.close()
            except Exception:
                pass
            self.connected = False
            self.rpc = None
            self._last_payload = {}

<<<<<<< HEAD
    # --- Public API -------------------------------------------------------
=======
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
    def initialize(self, config):
        self.config = config
        if self.config:
            try:
                self.config.config_changed.connect(self._on_config_changed)
            except Exception:
                pass
<<<<<<< HEAD
        # Seed logos on every boot so the cache is always fresh if the
        # user replaced a bundled asset.
        try:
            seed_default_logos(force=False)
        except Exception:
            pass
=======
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
        if self.is_enabled():
            self.connect()

    def is_enabled(self) -> bool:
        if not PYPRESENCE_AVAILABLE:
            return False
        if self.config:
            return bool(self.config.get("discord_rpc", True))
        return True

    def connect(self):
        if not PYPRESENCE_AVAILABLE:
<<<<<<< HEAD
            return False, "pypresence is not installed."
        # Reset backoff so a manual connect actually tries immediately.
        self._reconnect_cooldown = 0.0
        self._reconnect_attempts = 0
        self._fatal_logged = False
        # A manual "reconnect" from settings is the user's signal that
        # they may have changed the Client ID or restarted Discord, so
        # forget the dead-ID cache and try everything fresh.
        self._dead_client_ids = set()
        # If Discord isn't even running, skip the queue entirely so the
        # caller can show an immediate message instead of waiting for the
        # worker loop to come around.
        if not _discord_is_running():
            msg = "Discord is not running — start the Discord desktop client first."
            self.logger.info(msg)
            return False, msg
        self._queue.put(("CONNECT", None))
        return True, "queued"
=======
            return
        self._queue.put(("CONNECT", None))
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0

    def _on_config_changed(self, key: str, value):
        if key == "discord_rpc":
            if value:
                self.connect()
            else:
                self.clear_presence()
<<<<<<< HEAD
        elif key == "discord_client_id":
            # New Client ID — anything previously marked dead is
            # potentially fine again, so clear the list and reconnect.
            self._dead_client_ids = set()
            self._fatal_logged = False
            if self.is_enabled():
                self.connect()
=======
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
        elif key.startswith("discord_"):
            self.refresh_presence(force=True)

    def on_tab_changed(self, index: int):
        tab_names = {
            0: ("Exploring NeuraX", "Dashboard"),
            1: ("Managing Instances", "Instance Studio"),
            2: ("Exploring Version Manifest", "Version & AI Radar"),
            3: ("Scanning Market Servers", "Server Browser & AI Monitor"),
            4: ("Browsing Modrinth Hub", "Mods, Shaders & Modpacks"),
            5: ("Customizing Skin & Cape", "Skin Studio"),
            6: ("Viewing Screenshot Gallery", "Photo Canvas"),
            7: ("Reading Announcements", "News & Updates"),
            8: ("Configuring Launcher", "Settings & Optimization"),
            9: ("Managing Local Servers", "+ New Local Server"),
<<<<<<< HEAD
            10: ("Resting", "AFK Zone"),
=======
            10: ("Resting", "AFK Zone")
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
        }
        state, details = tab_names.get(index, ("Exploring NeuraX", "Dashboard"))
        self.set_launcher_activity(state, details)

    def set_launcher_activity(self, state: str, details: str = ""):
        self.launcher_state = state
        self.launcher_details = details or "Dashboard"
        if not self.in_game and not self._testing:
            self.refresh_presence()

    def set_game_activity(self, version: str, instance_name: str = "Default", loader: str = "Vanilla", server_ip: str = "", server_port: int = 25565):
        self.in_game = True
        self.game_start_time = int(time.time())
        self.game_info = {
            "version": version,
            "instance_name": instance_name,
            "loader": loader,
            "server_ip": server_ip,
            "server_port": server_port,
<<<<<<< HEAD
            "crashed": False,
=======
            "crashed": False
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
        }
        self.refresh_presence(force=True)

    def set_crashed_activity(self, version: str, instance_name: str = "Default"):
        self.in_game = True
        self.game_info = {
            "version": version,
            "instance_name": instance_name,
            "loader": "Vanilla",
            "server_ip": "",
            "server_port": 25565,
<<<<<<< HEAD
            "crashed": True,
        }
        self.refresh_presence(force=True)

        def revert():
            self.clear_game_activity()

=======
            "crashed": True
        }
        self.refresh_presence(force=True)
        def revert():
            self.clear_game_activity()
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
        threading.Timer(6.0, revert).start()

    def clear_game_activity(self):
        self.in_game = False
        self.game_start_time = None
        self.game_info = {}
        self.refresh_presence(force=True)

    def test_presence(self):
        self._testing = True
<<<<<<< HEAD
        large = get_cached_discord_asset(ASSET_KEY_LARGE)
        small = get_cached_discord_asset(ASSET_KEY_SMALL) or large
        payload = {
            "details": "Playing NeuraX Launcher",
            "state": "Discord RPC Test Successful",
            "large_image": large or "",
            "large_text": "NeuraX Launcher by Dytalmc",
            "small_image": small or "",
            "small_text": "All Systems Operational",
            "start": int(time.time()),
=======
        payload = {
            "details": "Playing NeuraX Launcher",
            "state": "Discord RPC Test Successful",
            "large_image": ASSET_NEURAX,
            "large_text": "NeuraX Launcher by Dytalmc",
            "small_image": ASSET_NEURAX,
            "small_text": "All Systems Operational",
            "start": int(time.time())
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
        }
        self._queue.put(("UPDATE", (payload, True)))

        def restore():
            self._testing = False
            self.refresh_presence(force=True)

        threading.Timer(4.0, restore).start()

    def refresh_presence(self, force: bool = False):
        if self._testing or not self.is_enabled():
            return
        self._build_and_send_presence(force=force)

    def _build_and_send_presence(self, force: bool = False):
        cfg = self.config
        mode = cfg.get("discord_mode", "Full") if cfg else "Full"
        if mode == "Disabled":
            self.clear_presence()
            return

        show_version = cfg.get("discord_show_version", True) if cfg else True
        show_loader = cfg.get("discord_show_loader", True) if cfg else True
        show_instance = cfg.get("discord_show_instance", True) if cfg else True
        show_server = cfg.get("discord_show_server", True) if cfg else True
        show_time = cfg.get("discord_show_time", True) if cfg else True
        show_private = cfg.get("discord_show_private_servers", False) if cfg else False
        show_buttons = cfg.get("discord_show_buttons", True) if cfg else True
        mc_activity_enabled = cfg.get("discord_mc_activity", True) if cfg else True
        launcher_activity_enabled = cfg.get("discord_launcher_activity", True) if cfg else True

        username = cfg.get("username", "NeuraPlayer") if cfg else "NeuraPlayer"
<<<<<<< HEAD

        # Resolve all the URLs up front so the payload is consistent
        # across the various branches below.
        large_image = get_cached_discord_asset(ASSET_KEY_LARGE)
        small_image = get_cached_discord_asset(ASSET_KEY_SMALL)
        avatar_url = (
            f"https://minotar.net/helm/{username}/64.png"
            if username and username != "NeuraPlayer"
            else small_image or large_image
        )
=======
        avatar_url = f"https://minotar.net/helm/{username}/64.png" if username and username != "NeuraPlayer" else ASSET_NEURAX
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0

        payload = {}

        if self.in_game and mc_activity_enabled:
            g = self.game_info
            if g.get("crashed"):
                payload["details"] = f"Minecraft {g.get('version', '')} Crashed"
                payload["state"] = f"Instance: {g.get('instance_name', 'Default')}"
<<<<<<< HEAD
                if large_image:
                    payload["large_image"] = large_image
=======
                payload["large_image"] = ASSET_NEURAX
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
                payload["large_text"] = "NeuraX Launcher"
            elif mode == "Private":
                payload["details"] = "Playing Minecraft"
                payload["state"] = "In Game"
<<<<<<< HEAD
                if large_image:
                    payload["large_image"] = large_image
=======
                payload["large_image"] = ASSET_NEURAX
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
                payload["large_text"] = "NeuraX Launcher"
            elif mode == "Minimal":
                v_str = f" {g.get('version')}" if show_version and g.get("version") else ""
                payload["details"] = f"Playing Minecraft{v_str}"
                payload["state"] = "In Game"
<<<<<<< HEAD
                if large_image:
                    payload["large_image"] = large_image
=======
                payload["large_image"] = ASSET_NEURAX
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
                payload["large_text"] = "NeuraX Launcher"
            else:
                inst_name = g.get("instance_name", "Default")
                ver = g.get("version", "")
                loader = g.get("loader", "Vanilla")
                server_ip = g.get("server_ip", "")

                if show_instance and inst_name and inst_name != "Default":
                    details = f"Playing {inst_name}"
                else:
                    details = "Playing Minecraft"

                if show_version and ver:
                    details += f" {ver}"

                state_parts = []
                if server_ip:
                    if is_private_ip(server_ip) and not show_private:
                        state_parts.append("Multiplayer")
                    elif show_server:
                        fname = resolve_friendly_server_name(server_ip)
                        state_parts.append(f"On {fname}")
                    else:
                        state_parts.append("Multiplayer")
                else:
                    state_parts.append("Singleplayer")

                if show_loader and loader and loader != "Vanilla":
                    state_parts.append(loader)

                payload["details"] = details
                payload["state"] = " • ".join(state_parts)
<<<<<<< HEAD
                if large_image:
                    payload["large_image"] = large_image
                payload["large_text"] = f"NeuraX Launcher • {ver} ({loader})"
                if avatar_url:
                    payload["small_image"] = avatar_url
=======
                payload["large_image"] = ASSET_NEURAX
                payload["large_text"] = f"NeuraX Launcher • {ver} ({loader})"
                payload["small_image"] = avatar_url
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
                payload["small_text"] = f"{username} ({loader})"

                if show_time and self.game_start_time:
                    payload["start"] = self.game_start_time

                if show_buttons and mode == "Full":
<<<<<<< HEAD
                    payload["buttons"] = [
                        {"label": "NeuraX Launcher", "url": "https://github.com/Dytalmc/NeuraX"}
                    ]
=======
                    payload["buttons"] = [{"label": "NeuraX Launcher", "url": "https://github.com/Dytalmc/NeuraX"}]
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0

        elif not self.in_game and launcher_activity_enabled:
            payload["details"] = self.launcher_details or "Dashboard"
            payload["state"] = self.launcher_state or "Exploring NeuraX"
<<<<<<< HEAD
            if large_image:
                payload["large_image"] = large_image
            payload["large_text"] = "NeuraX Launcher"
            if avatar_url:
                payload["small_image"] = avatar_url
=======
            payload["large_image"] = ASSET_NEURAX
            payload["large_text"] = "NeuraX Launcher"
            payload["small_image"] = avatar_url
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
            payload["small_text"] = username
            if show_time and self.start_time:
                payload["start"] = self.start_time
            if show_buttons and mode == "Full":
<<<<<<< HEAD
                payload["buttons"] = [
                    {"label": "NeuraX Launcher", "url": "https://github.com/Dytalmc/NeuraX"}
                ]

        if payload:
            # Drop empty string values — pypresence rejects "" for
            # image keys.
            payload = {k: v for k, v in payload.items() if v != ""}
=======
                payload["buttons"] = [{"label": "NeuraX Launcher", "url": "https://github.com/Dytalmc/NeuraX"}]

        if payload:
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
            self._queue.put(("UPDATE", (payload, force)))
        else:
            self.clear_presence()

    def update_launcher_presence(self):
        self.refresh_presence(force=True)

    def update_presence(self, version: str, state_text: str = "via NeuraX Launcher"):
        self.set_game_activity(version=version)

    def clear_presence(self):
        self._queue.put(("CLEAR", None))

    def close(self):
        self._running = False
<<<<<<< HEAD
        self._queue.put(("CLOSE", None))
=======
        self._queue.put(("CLOSE", None))
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
