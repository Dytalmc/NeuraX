"""Encrypted on-disk device-lock file used by ``nx.py``.

When an admin disables a device via ``nx.py --lock``, the launcher must
honour that decision *even when offline*. So we persist a small encrypted
record under ``~/.neurax/cache/device_lock.bin``:

    {
      "version": 1,
      "locked": true,
      "locked_at": "2026-08-31T18:00:00Z",
      "locked_by": "admin@example",
      "message": "Account suspended",
      "nonce": "<base64>"
    }

The record is encrypted with Fernet (AES-128-CBC + HMAC-SHA256). The
launcher derives the Fernet key from a combination of:

  * The current user's SID, looked up via ``kernel32`` so the key is
    bound to the Windows user account.
  * A per-installation salt stored at ``~/.neurax/install.id`` so the
    same lock file does not decrypt under a different user/installation.

If the file is missing, malformed, or the key derivation fails, the
launcher behaves as **unlocked** — we never want a corrupt cache file
to brick the user's launcher. The :class:`DeviceLock` class also
provides :meth:`is_locked` and :meth:`apply_state` methods that the main
window can call on every state-change of the network monitor.

The accompanying CLI lives at ``nx.py`` in the repo root; it is the same
``nx.py`` you've been using, with two new subcommands:

    python nx.py --lock "message"      # writes an encrypted lock file
    python nx.py --unlock              # removes the lock file
    python nx.py --status              # prints current state

The encryption is deliberately simple — its purpose is not cryptographic
robustness against a determined attacker, but rather making it trivial for
a casual user to clear the lock. We rely on the Windows user SID for
binding so the file becomes useless outside the original account.
"""
from __future__ import annotations

import base64
import ctypes
import getpass
import hashlib
import json
import os
import socket
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Windows SID lookup. We use ctypes instead of pywin32 because the launcher
# otherwise only needs a small piece of Windows API.
# ---------------------------------------------------------------------------

def _windows_user_sid() -> bytes:
    """Return a stable identifier for the current Windows user.

    Uses ``kernel32.GetCurrentProcessToken`` + ``advapi32.GetTokenInformation``
    to read the user SID from the process token. If anything fails (non-Windows,
    permission errors) we fall back to the username + hostname so the key
    derivation at least has *something* stable per-machine.
    """
    try:
        if os.name != "nt":
            raise OSError("non-windows")
        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        class _TOKEN_USER(ctypes.Structure):
            _fields_ = [
                ("Sid", ctypes.c_void_p),
                ("Attributes", ctypes.c_ulong),
            ]

        advapi32.GetTokenInformation.restype = ctypes.c_bool
        advapi32.GetTokenInformation.argtypes = [
            ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p,
            ctypes.c_uint, ctypes.POINTER(ctypes.c_uint),
        ]
        ConvertStringSidToW = advapi32.ConvertStringSidToW
        ConvertStringSidToW.restype = ctypes.c_bool
        ConvertStringSidToW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_void_p)]

        token = kernel32.GetCurrentProcessToken() if hasattr(kernel32, "GetCurrentProcessToken") else None
        if token is None:
            # Fallback: OpenProcessToken on current process pseudo-handle.
            kernel32.OpenProcessToken.restype = ctypes.c_bool
            kernel32.OpenProcessToken.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p)]
            hToken = ctypes.c_void_p()
            ok = kernel32.OpenProcessToken(kernel32.GetCurrentProcess(), 0x0008, ctypes.byref(hToken))
            if not ok:
                raise OSError("OpenProcessToken failed")
            token = hToken.value

        needed = ctypes.c_uint(0)
        advapi32.GetTokenInformation(token, 1, None, 0, ctypes.byref(needed))
        buf = (ctypes.c_byte * needed.value)()
        ok = advapi32.GetTokenInformation(token, 1, buf, needed.value, ctypes.byref(needed))
        if not ok:
            raise OSError("GetTokenInformation failed")
        tu = _TOKEN_USER.from_buffer(buf)
        sid_ptr = ctypes.c_wchar_p()
        if not ConvertStringSidToW(tu.Sid, ctypes.byref(sid_ptr)):
            raise OSError("ConvertStringSidToW failed")
        return sid_ptr.value.encode("utf-8")
    except Exception:
        # Non-Windows fallback or permission error: bind to user@host so the
        # key still has some entropy.
        try:
            return f"{getpass.getuser()}@{socket.gethostname()}".encode("utf-8")
        except Exception:
            return b"neurax-default-salt"


def _load_install_salt(neurax_dir: Path) -> bytes:
    """Read or create ``install.id`` so the key is also bound to this install."""
    p = neurax_dir / "install.id"
    try:
        if p.exists():
            return p.read_bytes()
    except OSError:
        pass
    salt = os.urandom(32)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(salt)
    except OSError:
        pass
    return salt


def _derive_fernet_key(neurax_dir: Path) -> bytes:
    """Derive a 32-byte Fernet-compatible key from user SID + install salt."""
    sid = _windows_user_sid()
    salt = _load_install_salt(neurax_dir)
    digest = hashlib.sha256(sid + b"|" + salt).digest()
    return base64.urlsafe_b64encode(digest)


# ---------------------------------------------------------------------------
# Lock record
# ---------------------------------------------------------------------------

@dataclass
class LockRecord:
    locked: bool = False
    locked_at: str = ""
    locked_by: str = ""
    message: str = ""

    def is_active(self) -> bool:
        return bool(self.locked)


_LOCK_FILE_NAME = "device_lock.bin"
_FILE_VERSION = 1


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class DeviceLock:
    """Manages the encrypted lock file for this installation.

    The class is stateless aside from the on-disk file: every read parses
    the file from scratch, every write replaces the file. This keeps the
    code boring and predictable — there is no in-memory cache that could
    drift from disk.
    """

    def __init__(self, neurax_dir: Path):
        self.neurax_dir = Path(neurax_dir)
        self.path = self.neurax_dir / "cache" / _LOCK_FILE_NAME
        # NOTE: do NOT cache the Fernet instance. The key is derived from
        # ``install.id`` + the current Windows user SID, so if either of
        # those changes (e.g. an admin resets ``install.id`` to revoke a
        # stolen lock file) the next read/write must use the new key.
        # Re-derivation is cheap (one SHA-256 + a small file read) so the
        # safety win is worth the few extra microseconds.

    # --------------------------------------------------- low-level access
    def _get_fernet(self):
        try:
            from cryptography.fernet import Fernet
        except Exception:
            return None
        key = _derive_fernet_key(self.neurax_dir)
        try:
            return Fernet(key)
        except Exception:
            return None

    def read(self) -> LockRecord:
        """Return the current lock state, or an unlocked record on any error."""
        if not self.path.exists():
            return LockRecord()
        fernet = self._get_fernet()
        if fernet is None:
            return LockRecord()
        try:
            blob = self.path.read_bytes()
            plain = fernet.decrypt(blob)
            data = json.loads(plain.decode("utf-8"))
            if not isinstance(data, dict) or data.get("version") != _FILE_VERSION:
                return LockRecord()
            return LockRecord(
                locked=bool(data.get("locked", False)),
                locked_at=str(data.get("locked_at", "")),
                locked_by=str(data.get("locked_by", "")),
                message=str(data.get("message", "")),
            )
        except Exception:
            # Decryption failed = file was tampered with, key changed, or
            # a different user copied the file in. Treat as unlocked.
            return LockRecord()

    def write(self, record: LockRecord) -> bool:
        """Persist ``record`` encrypted. Returns True on success."""
        fernet = self._get_fernet()
        if fernet is None:
            return False
        try:
            payload = {
                "version": _FILE_VERSION,
                "locked": bool(record.locked),
                "locked_at": record.locked_at or _now_iso(),
                "locked_by": record.locked_by,
                "message": record.message,
            }
            blob = fernet.encrypt(json.dumps(payload).encode("utf-8"))
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_bytes(blob)
            os.replace(tmp, self.path)
            return True
        except Exception:
            try:
                if 'tmp' in locals() and tmp.exists():
                    tmp.unlink()
            except OSError:
                pass
            return False

    # ------------------------------------------------------ high-level
    def is_locked(self) -> bool:
        return self.read().is_active()

    def lock(self, *, message: str = "", locked_by: str = "nx.py") -> bool:
        rec = LockRecord(
            locked=True,
            locked_at=_now_iso(),
            locked_by=locked_by,
            message=message,
        )
        return self.write(rec)

    def unlock(self) -> bool:
        if not self.path.exists():
            return True
        try:
            self.path.unlink()
            return True
        except OSError:
            return False


# ---------------------------------------------------------------------------
# nx.py subcommand helpers — the CLI lives in nx.py at the repo root.
# ---------------------------------------------------------------------------

def cli_lock(neurax_dir: Path, message: str, locked_by: str) -> int:
    dl = DeviceLock(neurax_dir)
    ok = dl.lock(message=message, locked_by=locked_by)
    if ok:
        print(f"[nx] device locked: {message!r} (by {locked_by!r})")
        return 0
    print("[nx] could not write lock file. Is the cryptography package installed?")
    return 1


def cli_unlock(neurax_dir: Path) -> int:
    dl = DeviceLock(neurax_dir)
    if dl.unlock():
        print("[nx] device unlocked.")
        return 0
    print("[nx] could not remove lock file.")
    return 1


def cli_status(neurax_dir: Path) -> int:
    dl = DeviceLock(neurax_dir)
    rec = dl.read()
    if rec.is_active():
        print(f"[nx] LOCKED since {rec.locked_at} by {rec.locked_by!r}: {rec.message}")
        return 0
    print("[nx] unlocked.")
    return 0