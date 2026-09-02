import json
import shutil
from pathlib import Path
from typing import List, Dict, Any, Tuple
from PyQt6.QtCore import QObject, pyqtSignal
from neurax.core.config import get_system_ram_info, get_dot_neurax_dir

# The single shared .minecraft root used by every vanilla-loader
# instance in NeuraX. Lives under the per-user NeuraX directory so
# survives launcher reinstalls but stays scoped to the Windows
# account. Vanilla instances share screenshots, saves, servers,
# libraries, options.txt, and every other Minecraft runtime file —
# there is no per-instance vanilla folder at all.
GLOBAL_VANILLA_DIR = get_dot_neurax_dir() / "global" / ".minecraft"


def _is_vanilla(loader: Any) -> bool:
    """True if the loader string is Vanilla / blank / unknown."""
    if loader is None:
        return True
    s = str(loader).strip().lower()
    return s in ("", "vanilla")


class InstanceManager(QObject):
    """Manages Minecraft instances under %APPDATA%/.neurax/instances/.

    Special case: any instance whose loader is "Vanilla" does **not**
    have its own per-instance ``.minecraft`` folder. All vanilla
    instances share a single ``.minecraft`` root at
    ``%APPDATA%/.neurax/global/.minecraft/`` — screenshots, saves,
    servers, libraries, options.txt, etc. are all written to and read
    from the same folder, regardless of which Minecraft version is
    being launched. This matches the user's mental model of a single
    vanilla Minecraft install.
    """
    instances_changed = pyqtSignal()

    def __init__(self, neurax_dir: Path):
        super().__init__()
        self.instances_dir = get_dot_neurax_dir() / "instances"
        self.instances_dir.mkdir(parents=True, exist_ok=True)
        # Migrate any pre-existing per-instance vanilla folders into
        # the shared global root FIRST so the default-instance
        # creation below doesn't poison the "global already has
        # files" guard. Originals are left on disk so the user can
        # manually verify nothing important was lost before cleaning
        # them up later.
        GLOBAL_VANILLA_DIR.mkdir(parents=True, exist_ok=True)
        self._migrate_legacy_vanilla_folders()
        self.ensure_default_instance()

    def _migrate_legacy_vanilla_folders(self):
        """One-shot copy from each per-instance ``.minecraft`` whose
        loader is ``Vanilla`` into the shared global root. Originals
        stay on disk untouched.

        Skips if the global root already has files in it (assume the
        user has been using the global folder for a while and the
        per-instance folders are stale leftovers)."""
        if not self.instances_dir.exists():
            return
        try:
            # Don't touch an already-populated global root.
            try:
                if any(GLOBAL_VANILLA_DIR.iterdir()):
                    return
            except Exception:
                return
            for folder in self.instances_dir.iterdir():
                if not folder.is_dir():
                    continue
                cfg_path = folder / "instance.json"
                loader = None
                if cfg_path.exists():
                    try:
                        with open(cfg_path, "r", encoding="utf-8") as fh:
                            loader = json.load(fh).get("loader")
                    except Exception:
                        loader = None
                if not _is_vanilla(loader):
                    continue
                src = folder / ".minecraft"
                if not src.exists() or not src.is_dir():
                    continue
                self._copy_tree(src, GLOBAL_VANILLA_DIR)
                # Best-effort: stamp the migration so we don't redo it
                # for the same instance on every launch.
                try:
                    (folder / ".migrated_to_global_vanilla").write_text(
                        f"copied {int(__import__('time').time())}",
                        encoding="utf-8",
                    )
                except Exception:
                    pass
        except Exception:
            # Migration is best-effort — never crash the launcher on it.
            pass

    @staticmethod
    def _copy_tree(src: Path, dst: Path) -> None:
        """Copy every file from src into dst, creating parent dirs as
        needed. Skips entries that already exist at the destination
        (global wins)."""
        dst.mkdir(parents=True, exist_ok=True)
        for entry in src.rglob("*"):
            try:
                rel = entry.relative_to(src)
            except Exception:
                continue
            target = dst / rel
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(entry, target)
            except Exception:
                continue

    @staticmethod
    def vanilla_game_dir() -> Path:
        """Return the single shared .minecraft root used by every
        vanilla-loader instance. Always returns an absolute Path."""
        return GLOBAL_VANILLA_DIR

    @staticmethod
    def resolve_game_dir(loader: Any, fallback: Path) -> Path:
        """If ``loader`` is vanilla, return the shared global
        ``.minecraft`` directory. Otherwise return ``fallback``
        unchanged (per-instance folder).
        """
        if _is_vanilla(loader):
            return GLOBAL_VANILLA_DIR
        return fallback

    def ensure_default_instance(self):
        default_path = self.instances_dir / "Default"
        if not default_path.exists():
            total_mb, max_allocable = get_system_ram_info()
            max_ram = min(8192 if total_mb >= 16384 else (6144 if total_mb >= 12288 else 4096), max_allocable)
            self.create_instance("Default", "1.20.4", loader="Vanilla", max_ram=max_ram)

    def list_instances(self) -> List[Dict[str, Any]]:
        instances = []
        for folder in self.instances_dir.iterdir():
            if folder.is_dir():
                cfg_path = folder / "instance.json"
                if cfg_path.exists():
                    try:
                        with open(cfg_path, "r", encoding="utf-8") as f:
                            cfg = json.load(f)
                            cfg["folder_name"] = folder.name
                            cfg["game_dir"] = str(
                                self.resolve_game_dir(
                                    cfg.get("loader", "Vanilla"),
                                    folder / ".minecraft",
                                )
                            )
                            cfg.setdefault("loader", "Vanilla")
                            cfg.setdefault("name", folder.name)
                            cfg.setdefault("loader_version", "")
                            instances.append(cfg)
                    except Exception:
                        pass
                else:
                    cfg = {
                        "name": folder.name,
                        "loader": "Vanilla",
                        "version": "1.20.4",
                        "max_ram": 4096,
                        "folder_name": folder.name,
                        "game_dir": str(self.resolve_game_dir("Vanilla", folder / ".minecraft")),
                        "loader_version": ""
                    }
                    instances.append(cfg)
        return instances

    def create_instance(self, name: str, version: str, loader: str = "Vanilla", max_ram: int = 4096, java_path: str = "auto", jvm_args: str = "", loader_version: str = ""):
        safe_name = "".join(c for c in name if c.isalnum() or c in (" ", "_", "-")).strip() or "New_Instance"
        base_name = safe_name
        suffix = 2
        inst_dir = self.instances_dir / safe_name
        while inst_dir.exists():
            safe_name = f"{base_name}_{suffix}"
            inst_dir = self.instances_dir / safe_name
            suffix += 1

        # For non-vanilla loaders we keep the per-instance .minecraft
        # folder so each modded instance is isolated. For vanilla
        # loaders we point at the single shared GLOBAL_VANILLA_DIR —
        # no instance-local .minecraft is created at all.
        if _is_vanilla(loader):
            mc_dir = GLOBAL_VANILLA_DIR
        else:
            mc_dir = inst_dir / ".minecraft"

        inst_dir.mkdir(parents=True, exist_ok=True)
        mc_dir.mkdir(parents=True, exist_ok=True)

        # Subdirs the launcher relies on (mods, saves, resourcepacks,
        # screenshots, etc.) live inside the shared vanilla root too
        # — that's where Minecraft actually reads them from.
        (mc_dir / "mods").mkdir(exist_ok=True)
        (mc_dir / "saves").mkdir(exist_ok=True)
        (mc_dir / "resourcepacks").mkdir(exist_ok=True)

        config_data = {
            "name": name.strip() or safe_name,
            "loader": loader or "Vanilla",
            "version": version,
            "max_ram": max_ram,
            "java_path": java_path,
            "jvm_args": jvm_args,
            "loader_version": (loader_version or "").strip()
        }

        with open(inst_dir / "instance.json", "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2)

        self.instances_changed.emit()
        return safe_name

    def delete_instance(self, folder_name: str):
        target = self.instances_dir / folder_name
        if target.exists() and target.is_dir():
            # Only nuke the per-instance folder — never the shared
            # vanilla root, even if this was the last vanilla instance.
            shutil.rmtree(target)
            self.instances_changed.emit()

    def get_instance(self, folder_name: str) -> Dict[str, Any]:
        target = self.instances_dir / folder_name / "instance.json"
        if target.exists():
            with open(target, "r", encoding="utf-8") as f:
                data = json.load(f)
                data["folder_name"] = folder_name
                data["game_dir"] = str(
                    self.resolve_game_dir(
                        data.get("loader", "Vanilla"),
                        self.instances_dir / folder_name / ".minecraft",
                    )
                )
                data.setdefault("loader", "Vanilla")
                data.setdefault("name", folder_name)
                data.setdefault("loader_version", "")
                return data
        return {
            "name": folder_name,
            "loader": "Vanilla",
            "version": "1.20.4",
            "max_ram": 4096,
            "java_path": "auto",
            "jvm_args": "",
            "loader_version": "",
            "folder_name": folder_name,
            "game_dir": str(self.resolve_game_dir("Vanilla", self.instances_dir / folder_name / ".minecraft"))
        }

    def update_instance(self, folder_name: str, **kwargs):
        target_dir = self.instances_dir / folder_name
        cfg_path = target_dir / "instance.json"
        data = self.get_instance(folder_name)
        for k, v in kwargs.items():
            data[k] = v
        data.pop("folder_name", None)
        data.pop("game_dir", None)
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        self.instances_changed.emit()

    def get_most_played_instance(self, analytics: dict) -> Dict[str, Any]:
        instances = self.list_instances()
        if not instances:
            return None

        best_inst = instances[0]
        max_seconds = -1

        for inst in instances:
            folder_name = inst.get("folder_name", "")
            name = inst.get("name", "")
            
            inst_analytics = analytics.get(name, {})
            if not inst_analytics and folder_name in analytics:
                inst_analytics = analytics.get(folder_name, {})
                
            sec = inst_analytics.get("total_seconds", 0) if isinstance(inst_analytics, dict) else 0
            if sec > max_seconds:
                max_seconds = sec
                best_inst = inst

        return best_inst

    def sync_global_data(self, config_mgr, target_folder_name: str = None) -> Tuple[bool, str]:
        sync_settings = config_mgr.get("global_sync_settings", True)
        sync_saves = config_mgr.get("global_sync_saves", True)
        sync_servers = config_mgr.get("global_sync_servers", True)

        if not (sync_settings or sync_saves or sync_servers):
            return False, "No sync items selected (Settings, Saves, and Servers are all disabled)."

        source_setting = config_mgr.get("global_sync_source", "auto")
        target_setting = config_mgr.get("global_sync_target", "all")

        analytics = config_mgr.get("analytics", {})
        
        if source_setting == "auto" or not source_setting:
            most_played = self.get_most_played_instance(analytics)
            if not most_played:
                return False, "No instances found to sync from."
            src_folder = most_played.get("folder_name")
            src_name = most_played.get("name", src_folder)
        else:
            src_folder = source_setting
            src_inst = self.get_instance(src_folder)
            src_name = src_inst.get("name", src_folder)

        src_mc = self.instances_dir / src_folder / ".minecraft"
        if not src_mc.exists():
            return False, f"Source directory for instance '{src_name}' does not exist."

        instances = self.list_instances()
        targets = []
        for inst in instances:
            fn = inst.get("folder_name")
            if fn == src_folder:
                continue

            if target_folder_name is not None:
                if target_setting != "all" and target_setting != target_folder_name:
                    continue
                if fn == target_folder_name:
                    targets.append(inst)
            else:
                if target_setting == "all" or target_setting == fn:
                    targets.append(inst)

        if not targets:
            return True, f"No target instances require syncing from '{src_name}'."

        synced_count = 0
        items_synced = []
        if sync_settings:
            items_synced.append("Settings")
        if sync_saves:
            items_synced.append("Saves")
        if sync_servers:
            items_synced.append("Servers")
        items_str = ", ".join(items_synced)

        for target in targets:
            target_mc = Path(target.get("game_dir", self.instances_dir / target["folder_name"] / ".minecraft"))
            target_mc.mkdir(parents=True, exist_ok=True)

            # 1. Settings (options.txt)
            if sync_settings:
                src_options = src_mc / "options.txt"
                if src_options.exists():
                    shutil.copy2(src_options, target_mc / "options.txt")

            # 2. Servers (servers.dat)
            if sync_servers:
                src_servers = src_mc / "servers.dat"
                if src_servers.exists():
                    shutil.copy2(src_servers, target_mc / "servers.dat")

            # 3. Saves (saves directory)
            if sync_saves:
                src_saves = src_mc / "saves"
                if src_saves.exists() and src_saves.is_dir():
                    target_saves = target_mc / "saves"
                    target_saves.mkdir(parents=True, exist_ok=True)
                    for item in src_saves.iterdir():
                        if item.is_dir():
                            shutil.copytree(item, target_saves / item.name, dirs_exist_ok=True)
                        elif item.is_file():
                            shutil.copy2(item, target_saves / item.name)

            synced_count += 1

        return True, f"Successfully synced {items_str} from '{src_name}' to {synced_count} instance(s)."
