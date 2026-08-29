import time
import threading
import queue
import asyncio
import ipaddress
import re
import sys
from neurax.core.logger import Logger

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

CLIENT_IDS = [
    "1089247653258100806",
    "1115278784742838342",
    "1077677906477527130",
    "943488506840223764",
    "1218520338780770304"
]

ASSET_NEURAX = "https://raw.githubusercontent.com/Dytalmc/NeuraX/main/n2/nx.ico"

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

class DiscordManager:
    """Thread-safe background manager for NeuraX Discord Rich Presence (RPC).
    Provides live in-game status, player skin avatar integration, modloader identification,
    server discovery reporting, and seamless error recovery.
    """
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self.logger = Logger.get_instance()
        self.rpc = None
        self.connected = False
        self.config = None
        self.start_time = int(time.time())
        self.game_start_time = None
        
        self.in_game = False
        self.game_info = {}
        self.launcher_state = "Exploring NeuraX"
        self.launcher_details = "Dashboard"
        
        self._last_update_time = 0.0
        self._last_payload = {}
        self._reconnect_cooldown = 0.0
        self._last_log_error = ""
        self._testing = False

        self._queue = queue.Queue()
        self._running = True
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True, name="DiscordRPCWorker")
        self._worker_thread.start()

    @classmethod
    def get_instance(cls, config=None):
        with cls._lock:
            if cls._instance is None:
                cls._instance = DiscordManager()
            if config is not None:
                cls._instance.initialize(config)
            return cls._instance

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

    def _do_connect(self, loop):
        if not PYPRESENCE_AVAILABLE or self.connected:
            return

        now = time.time()
        if now < self._reconnect_cooldown:
            return

        connected = False
        last_error = ""

        for cid in CLIENT_IDS:
            if connected:
                break
            for pipe_idx in range(10):
                try:
                    if self.rpc:
                        try:
                            self.rpc.close()
                        except Exception:
                            pass
                        self.rpc = None

                    presence = pypresence.Presence(cid, pipe=pipe_idx, loop=loop)
                    presence.connect()
                    self.rpc = presence
                    self.connected = True
                    connected = True
                    self._reconnect_cooldown = 0.0
                    self._last_log_error = ""
                    self.logger.info(f"Discord Rich Presence connected successfully using Client ID {cid} on pipe {pipe_idx}.")
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

                    if "4000" in err_msg or "Invalid" in err_msg or "client_id" in err_msg.lower():
                        break

        if not connected:
            self.connected = False
            self._reconnect_cooldown = now + 45.0
            if last_error and last_error != self._last_log_error:
                self._last_log_error = last_error
                self.logger.warning(f"Discord RPC connection skipped or failed: {last_error}")

    def _do_update(self, payload: dict, force: bool):
        if not self.connected or not self.rpc:
            return

        now = time.time()
        if not force:
            if payload == self._last_payload and (now - self._last_update_time < 15.0):
                return
            if (now - self._last_update_time) < 1.5:
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
            self._reconnect_cooldown = now + 30.0

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

    def initialize(self, config):
        self.config = config
        if self.config:
            try:
                self.config.config_changed.connect(self._on_config_changed)
            except Exception:
                pass
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
            return
        self._queue.put(("CONNECT", None))

    def _on_config_changed(self, key: str, value):
        if key == "discord_rpc":
            if value:
                self.connect()
            else:
                self.clear_presence()
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
            10: ("Resting", "AFK Zone")
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
            "crashed": False
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
            "crashed": True
        }
        self.refresh_presence(force=True)
        def revert():
            self.clear_game_activity()
        threading.Timer(6.0, revert).start()

    def clear_game_activity(self):
        self.in_game = False
        self.game_start_time = None
        self.game_info = {}
        self.refresh_presence(force=True)

    def test_presence(self):
        self._testing = True
        payload = {
            "details": "Playing NeuraX Launcher",
            "state": "Discord RPC Test Successful",
            "large_image": ASSET_NEURAX,
            "large_text": "NeuraX Launcher by Dytalmc",
            "small_image": ASSET_NEURAX,
            "small_text": "All Systems Operational",
            "start": int(time.time())
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
        avatar_url = f"https://minotar.net/helm/{username}/64.png" if username and username != "NeuraPlayer" else ASSET_NEURAX

        payload = {}

        if self.in_game and mc_activity_enabled:
            g = self.game_info
            if g.get("crashed"):
                payload["details"] = f"Minecraft {g.get('version', '')} Crashed"
                payload["state"] = f"Instance: {g.get('instance_name', 'Default')}"
                payload["large_image"] = ASSET_NEURAX
                payload["large_text"] = "NeuraX Launcher"
            elif mode == "Private":
                payload["details"] = "Playing Minecraft"
                payload["state"] = "In Game"
                payload["large_image"] = ASSET_NEURAX
                payload["large_text"] = "NeuraX Launcher"
            elif mode == "Minimal":
                v_str = f" {g.get('version')}" if show_version and g.get("version") else ""
                payload["details"] = f"Playing Minecraft{v_str}"
                payload["state"] = "In Game"
                payload["large_image"] = ASSET_NEURAX
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
                payload["large_image"] = ASSET_NEURAX
                payload["large_text"] = f"NeuraX Launcher • {ver} ({loader})"
                payload["small_image"] = avatar_url
                payload["small_text"] = f"{username} ({loader})"

                if show_time and self.game_start_time:
                    payload["start"] = self.game_start_time

                if show_buttons and mode == "Full":
                    payload["buttons"] = [{"label": "NeuraX Launcher", "url": "https://github.com/Dytalmc/NeuraX"}]

        elif not self.in_game and launcher_activity_enabled:
            payload["details"] = self.launcher_details or "Dashboard"
            payload["state"] = self.launcher_state or "Exploring NeuraX"
            payload["large_image"] = ASSET_NEURAX
            payload["large_text"] = "NeuraX Launcher"
            payload["small_image"] = avatar_url
            payload["small_text"] = username
            if show_time and self.start_time:
                payload["start"] = self.start_time
            if show_buttons and mode == "Full":
                payload["buttons"] = [{"label": "NeuraX Launcher", "url": "https://github.com/Dytalmc/NeuraX"}]

        if payload:
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
        self._queue.put(("CLOSE", None))
