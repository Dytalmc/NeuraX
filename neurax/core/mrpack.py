import os
import sys
import json
import shutil
import zipfile
import tempfile
import threading
import requests
from pathlib import Path
from typing import Dict, Any, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from PyQt6.QtCore import QThread, pyqtSignal
from neurax.core.logger import Logger

class MRPackConverterWorker(QThread):
    """Asynchronous worker to convert Modrinth .mrpack files to standard .zip archives or working instances."""
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str)

    def __init__(self, mrpack_path: str, mode: str, output_path: str = "", instance_name: str = "", instance_mgr = None):
        super().__init__()
        self.mrpack_path = Path(mrpack_path)
        self.mode = mode.lower()  # "zip" or "instance"
        self.output_path = Path(output_path) if output_path else None
        self.instance_name = instance_name.strip()
        self.instance_mgr = instance_mgr
        self.logger = Logger.get_instance()

    def run(self):
        temp_dir = None
        try:
            self.progress.emit(5, "Reading .mrpack index...")
            if not self.mrpack_path.exists():
                raise FileNotFoundError(f"File not found: {self.mrpack_path}")

            with zipfile.ZipFile(self.mrpack_path, "r") as zf:
                namelist = zf.namelist()
                if "modrinth.index.json" not in namelist:
                    raise ValueError("Invalid .mrpack file: modrinth.index.json not found inside package.")
                
                index_bytes = zf.read("modrinth.index.json")
                index_data = json.loads(index_bytes.decode("utf-8", errors="replace"))

            if not isinstance(index_data, dict):
                raise ValueError("Invalid .mrpack index: modrinth.index.json root must be an object.")

            name = index_data.get("name") or "Modpack"
            deps = index_data.get("dependencies") or {}
            if not isinstance(deps, dict):
                deps = {}
            mc_version = deps.get("minecraft") or "1.20.4"

            loader = "Vanilla"
            if "fabric-loader" in deps or "fabric" in deps:
                loader = "Fabric"
            elif "quilt-loader" in deps or "quilt" in deps:
                loader = "Quilt"
            elif "neoforge" in deps:
                loader = "NeoForge"
            elif "forge" in deps:
                loader = "Forge"

            self.logger.info(f"[MRPack] Converting '{name}' (MC {mc_version}, {loader}) in mode: {self.mode}")

            temp_dir = Path(tempfile.mkdtemp(prefix="mrpack_conv_"))
            temp_mc_dir = temp_dir / ".minecraft"
            temp_mc_dir.mkdir(parents=True, exist_ok=True)

            files_list = index_data.get("files") or []
            if not isinstance(files_list, list):
                files_list = []

            valid_files = []
            for f in files_list:
                if not isinstance(f, dict):
                    continue
                env = f.get("env") or {}
                client_env = env.get("client") if isinstance(env, dict) else None
                if client_env != "unsupported":
                    valid_files.append(f)

            total_files = len(valid_files)
            self.progress.emit(10, f"Downloading {total_files} modpack files...")

            completed = 0
            lock = threading.Lock()

            def download_single_file(file_obj):
                nonlocal completed
                if not isinstance(file_obj, dict):
                    return False
                rel_path = file_obj.get("path") or ""
                if not rel_path:
                    return True
                dest = temp_mc_dir / rel_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                urls = file_obj.get("downloads") or []
                if not isinstance(urls, list):
                    urls = []
                download_success = False
                for url in urls:
                    if not url or not isinstance(url, str):
                        continue
                    try:
                        r = requests.get(url, timeout=20)
                        if r.status_code == 200:
                            with open(dest, "wb") as f_out:
                                f_out.write(r.content)
                            download_success = True
                            break
                    except Exception:
                        pass

                with lock:
                    completed += 1
                    pct = int(10 + (completed / max(total_files, 1)) * 75)
                    self.progress.emit(pct, f"Downloaded {completed}/{total_files} files ({rel_path})")

                return download_success

            if valid_files:
                with ThreadPoolExecutor(max_workers=16) as executor:
                    futures = [executor.submit(download_single_file, f_obj) for f_obj in valid_files]
                    for fut in as_completed(futures):
                        try:
                            fut.result()
                        except Exception as ex:
                            self.logger.warning(f"[MRPack] File download notice: {ex}")

            self.progress.emit(85, "Extracting overrides...")
            with zipfile.ZipFile(self.mrpack_path, "r") as zf:
                for member in zf.infolist():
                    filename = member.filename
                    target_rel = None
                    if filename.startswith("overrides/") and len(filename) > len("overrides/"):
                        target_rel = filename[len("overrides/"):]
                    elif filename.startswith("client-overrides/") and len(filename) > len("client-overrides/"):
                        target_rel = filename[len("client-overrides/"):]

                    if target_rel and not member.is_dir():
                        target_file = temp_mc_dir / target_rel
                        target_file.parent.mkdir(parents=True, exist_ok=True)
                        with zf.open(member) as src, open(target_file, "wb") as dst:
                            shutil.copyfileobj(src, dst)

            if self.mode == "zip":
                self.progress.emit(90, "Creating ZIP package...")
                if not self.output_path:
                    self.output_path = self.mrpack_path.parent / f"{name.replace(' ', '_')}.zip"

                self.output_path.parent.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(self.output_path, "w", zipfile.ZIP_DEFLATED) as out_zip:
                    inst_meta = {
                        "name": name,
                        "loader": loader,
                        "version": mc_version
                    }
                    out_zip.writestr("instance.json", json.dumps(inst_meta, indent=2))
                    
                    for root, _, files in os.walk(temp_mc_dir):
                        for fname in files:
                            fpath = Path(root) / fname
                            arcname = Path(".minecraft") / fpath.relative_to(temp_mc_dir)
                            out_zip.write(fpath, arcname)

                self.progress.emit(100, "Done!")
                msg = f"Successfully converted Modrinth pack '{name}' to ZIP:\n{self.output_path}"
                self.logger.info(f"[MRPack] {msg}")
                self.finished.emit(True, msg)

            else:
                self.progress.emit(90, "Setting up working instance...")
                inst_name = self.instance_name or name
                if not self.instance_mgr:
                    raise RuntimeError("Instance Manager is not available.")

                folder_name = self.instance_mgr.create_instance(
                    name=inst_name,
                    version=mc_version,
                    loader=loader
                )
                target_inst_mc = self.instance_mgr.instances_dir / folder_name / ".minecraft"
                target_inst_mc.mkdir(parents=True, exist_ok=True)

                for item in temp_mc_dir.iterdir():
                    dest_item = target_inst_mc / item.name
                    if item.is_dir():
                        shutil.copytree(item, dest_item, dirs_exist_ok=True)
                    else:
                        shutil.copy2(item, dest_item)

                self.progress.emit(100, "Done!")
                msg = f"Successfully created working instance '{inst_name}' ({loader} {mc_version})!"
                self.logger.info(f"[MRPack] {msg}")
                self.finished.emit(True, msg)

        except Exception as e:
            err = f"MRPack conversion failed: {e}"
            self.logger.error(f"[MRPack Error] {err}")
            self.finished.emit(False, err)
        finally:
            if temp_dir and temp_dir.exists():
                try:
                    shutil.rmtree(temp_dir)
                except Exception:
                    pass
