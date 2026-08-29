import uuid
import json
import time
import hashlib
import socket
import platform
import sys
import os
import requests
import threading
import base64
from pathlib import Path
from typing import Dict, Any, Tuple
import minecraft_launcher_lib
from neurax.core.config import ConfigManager
from neurax.core.logger import Logger

try:
    import keyring
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False


def java_uuid_hashcode(u: uuid.UUID) -> int:
    msb = u.int >> 64
    lsb = u.int & 0xffffffffffffffff
    bits = msb ^ lsb
    ans = (bits >> 32) ^ (bits & 0xffffffff)
    if ans >= 0x80000000:
        ans -= 0x100000000
    return ans


class AuthManager:
    """Handles Microsoft OAuth 2.0 via minecraft-launcher-lib, secure session
    persistence via keyring, and official Mojang skin and cape management.
    """

    CLIENT_ID = "00000000402b5328"
    REDIRECT_URL = "https://login.live.com/oauth20_desktop.srf"

    def __init__(self, config: ConfigManager):
        self.config = config
        self.logger = Logger.get_instance()

    def get_session(self) -> dict:
        return {
            "username": self.config.get("username", "NeuraPlayer"),
            "uuid": self.config.get("uuid", "00000000-0000-0000-0000-000000000000"),
            "access_token": self.config.get("access_token", "0"),
            "mode": self.config.get("auth_mode", "microsoft"),
            "skin_model": self.config.get("skin_model", "classic")
        }

    @property
    def client_id(self) -> str:
        cid = self.config.get("ms_client_id", "")
        if isinstance(cid, str):
            cid = cid.strip()
        return cid if cid else self.CLIENT_ID

    def get_secure_token(self, key: str) -> str:
        if KEYRING_AVAILABLE:
            try:
                val = keyring.get_password("neurax_launcher", key)
                if val:
                    return val
            except Exception:
                pass
        return self.config.get(key, "")

    def set_secure_token(self, key: str, value: str):
        if KEYRING_AVAILABLE:
            try:
                keyring.set_password("neurax_launcher", key, value)
                return
            except Exception:
                pass
        self.config.set(key, value)

    def delete_secure_token(self, key: str):
        if KEYRING_AVAILABLE:
            try:
                keyring.delete_password("neurax_launcher", key)
            except Exception:
                pass
        self.config.set(key, "")

    def get_login_url(self) -> str:
        cid = self.client_id
        return minecraft_launcher_lib.microsoft_account.get_login_url(cid, self.REDIRECT_URL)

    def complete_login_with_url(self, code_or_url: str) -> dict:
        self.logger.info("Completing Microsoft authentication...")
        code_or_url = code_or_url.strip()
        if not code_or_url:
            raise ValueError("Please provide a valid redirected URL or authorization code.")

        cid = self.client_id
        try:
            auth_code = minecraft_launcher_lib.microsoft_account.get_auth_code_from_url(code_or_url)
        except Exception:
            if "code=" in code_or_url:
                auth_code = code_or_url.split("code=")[1].split("&")[0]
            else:
                auth_code = code_or_url

        try:
            login_data = minecraft_launcher_lib.microsoft_account.complete_login(cid, None, self.REDIRECT_URL, auth_code)
        except Exception as e:
            raise RuntimeError(f"Microsoft authentication failed: {e}")

        username = login_data.get("name", "NeuraPlayer")
        uuid_str = login_data.get("id", str(uuid.uuid4()))
        mc_access = login_data.get("access_token", "")
        ms_refresh = login_data.get("refresh_token", "")

        skin_url, skin_model = self._cache_skin_mojang(uuid_str)

        self.config.set("username", username)
        self.config.set("uuid", uuid_str)
        self.config.set("access_token", mc_access)
        self.config.set("auth_mode", "microsoft")
        self.config.set("skin_model", skin_model)
        if ms_refresh:
            self.set_secure_token("refresh_token", ms_refresh)
        self.logger.info(f"Microsoft authentication complete. Player: {username} ({uuid_str})")
        return {
            "username": username,
            "uuid": uuid_str,
            "access_token": mc_access,
            "mode": "microsoft",
            "skin_model": skin_model,
            "refresh_token": ms_refresh
        }

    def silent_login(self) -> dict | None:
        """Attempts silent login using stored Microsoft refresh token from Windows Credentials / Keyring."""
        saved_refresh = self.get_secure_token("refresh_token")
        if not saved_refresh:
            return None
        try:
            return self.refresh_microsoft_token(saved_refresh)
        except Exception as e:
            self.logger.warning(f"Silent login failed: {e}")
            return None

    def refresh_microsoft_token(self, refresh_token: str) -> dict:
        self.logger.info("Refreshing Microsoft access token...")
        cid = self.client_id
        try:
            login_data = minecraft_launcher_lib.microsoft_account.complete_refresh(cid, None, self.REDIRECT_URL, refresh_token)
        except Exception as e:
            self.delete_secure_token("refresh_token")
            raise RuntimeError(f"Token Refresh Error: {e}")

        username = login_data.get("name", "NeuraPlayer")
        uuid_str = login_data.get("id", str(uuid.uuid4()))
        mc_access = login_data.get("access_token", "")
        ms_refresh = login_data.get("refresh_token", refresh_token)

        skin_url, skin_model = self._cache_skin_mojang(uuid_str)

        self.config.set("username", username)
        self.config.set("uuid", uuid_str)
        self.config.set("access_token", mc_access)
        self.config.set("auth_mode", "microsoft")
        self.config.set("skin_model", skin_model)
        if ms_refresh:
            self.set_secure_token("refresh_token", ms_refresh)

        return {
            "username": username,
            "uuid": uuid_str,
            "access_token": mc_access,
            "mode": "microsoft",
            "skin_model": skin_model,
            "refresh_token": ms_refresh
        }

    def _cache_skin_mojang(self, uuid_str: str) -> Tuple[str, str]:
        if not uuid_str:
            return "", "classic"
        try:
            uuid_clean = uuid_str.replace("-", "")
            url = f"https://sessionserver.mojang.com/session/minecraft/profile/{uuid_clean}"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                for prop in data.get("properties", []):
                    if prop.get("name") == "textures":
                        b64_val = prop.get("value", "")
                        decoded_bytes = base64.b64decode(b64_val)
                        decoded_json = json.loads(decoded_bytes.decode("utf-8"))
                        textures = decoded_json.get("textures", {})
                        
                        # Official Mojang Skin
                        skin_data = textures.get("SKIN", {})
                        skin_url = skin_data.get("url", "")
                        model = "classic"
                        metadata = skin_data.get("metadata", {})
                        if metadata.get("model") == "slim":
                            model = "slim"

                        skin_cache_path = self.config.neurax_dir / "cache" / "skins" / f"{uuid_clean}_skin.png"
                        skin_cache_path.parent.mkdir(parents=True, exist_ok=True)
                        if skin_url:
                            s_resp = requests.get(skin_url, timeout=10)
                            if s_resp.status_code == 200:
                                with open(skin_cache_path, "wb") as f:
                                    f.write(s_resp.content)

                        # Official Mojang Cape
                        cape_data = textures.get("CAPE", {})
                        cape_url = cape_data.get("url", "")
                        cape_cache_path = self.config.neurax_dir / "cache" / "capes" / f"{uuid_clean}_cape.png"
                        cape_cache_path.parent.mkdir(parents=True, exist_ok=True)
                        if cape_url:
                            c_resp = requests.get(cape_url, timeout=10)
                            if c_resp.status_code == 200:
                                with open(cape_cache_path, "wb") as f:
                                    f.write(c_resp.content)
                        else:
                            if cape_cache_path.exists():
                                try:
                                    cape_cache_path.unlink()
                                except Exception:
                                    pass

                        return skin_url, model
        except Exception as e:
            self.logger.warning(f"Failed to fetch/cache Mojang skin/cape for {uuid_str}: {e}")
        return "", "classic"

    def login_offline(self, username: str) -> dict:
        """Create a local offline session with deterministic offline UUID."""
        username = (username or "Player").strip()
        if not username:
            username = "Player"
        
        # Standard Minecraft offline UUID generation (v3 namespace DNS)
        offline_uuid = str(uuid.uuid3(uuid.NAMESPACE_DNS, f"OfflinePlayer:{username}"))
        
        self.config.set("username", username)
        self.config.set("uuid", offline_uuid)
        self.config.set("access_token", "0")
        self.config.set("auth_mode", "offline")
        self.config.set("skin_model", "classic")
        
        self.logger.info(f"Created offline profile: '{username}' ({offline_uuid})")
        return {
            "username": username,
            "uuid": offline_uuid,
            "access_token": "0",
            "mode": "offline",
            "skin_model": "classic",
            "refresh_token": ""
        }

    def upload_skin_to_mojang(self, custom_path: str, model: str = "classic"):
        mc_access = self.config.get("access_token")
        if not mc_access or mc_access == "0":
            raise RuntimeError("You must be logged into a Microsoft account to upload a skin.")

        url = "https://api.minecraftservices.com/minecraft/profile/skins"
        headers = {
            "Authorization": f"Bearer {mc_access}"
        }
        variant = "slim" if model.lower() == "slim" else "classic"

        with open(custom_path, "rb") as f:
            files = {
                "variant": (None, variant),
                "file": (os.path.basename(custom_path), f, "image/png")
            }
            resp = requests.post(url, headers=headers, files=files, timeout=15)

        if resp.status_code not in (200, 204):
            try:
                err_msg = resp.json().get("errorMessage", resp.text)
            except Exception:
                err_msg = resp.text
            raise RuntimeError(f"Mojang Skin Upload Failed: {err_msg}")

        self.config.set("skin_model", variant)
        uuid_str = self.config.get("uuid", "")
        if uuid_str:
            self._cache_skin_mojang(uuid_str)

    def reset_skin_mojang(self) -> bool:
        mc_access = self.config.get("access_token")
        if not mc_access or mc_access == "0":
            return False

        url = "https://api.minecraftservices.com/minecraft/profile/skins/active"
        headers = {
            "Authorization": f"Bearer {mc_access}"
        }
        resp = requests.delete(url, headers=headers, timeout=10)
        if resp.status_code in (200, 204):
            uuid_str = self.config.get("uuid", "")
            if uuid_str:
                self._cache_skin_mojang(uuid_str)
            return True
        return False
