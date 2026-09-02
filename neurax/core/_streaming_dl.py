"""
Real, chunked, progress-emitting download helpers.

Why this exists: the launcher's install paths used ``requests.get(url)``
+ ``f.write(res.content)`` — that buffered every byte of every jar in
RAM before writing a single byte to disk, blocked the GUI thread for
seconds at a time on multi-megabyte downloads, and gave the user no
feedback beyond a frozen bar. It also had no progress callback, so
"what is downloading right now?" was invisible.

What this module provides:

* :func:`stream_download` — chunked streaming download with optional
  progress callback. Writes to a temp file and atomically renames
  into place so partial files never look "complete". 64 KB chunks by
  default.
* :func:`stream_download_to_dir` — same, but takes a directory and
  picks a filename from the URL or ``Content-Disposition``.

These helpers are intentionally synchronous (they block the worker
thread that called them) and fast — the launcher already runs them
inside ``LaunchWorker`` / ``CreateServerWorker`` (both ``QThread``s),
so the GUI stays responsive. The progress callback receives a dict
with ``url``, ``dest``, ``bytes_done``, ``bytes_total``, ``pct`` so
the caller can format it however they like.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import unquote, urlparse

import requests


_CHUNK_SIZE = 64 * 1024  # 64 KB


ProgressCallback = Optional[Callable[[dict], None]]


def _safe_filename_from_url(url: str) -> str:
    """Extract the last URL path component and return it sanitised.

    Falls back to ``download.bin`` if the URL has no usable filename.
    """
    try:
        path = urlparse(url).path
    except Exception:
        return "download.bin"
    name = unquote(os.path.basename(path)) if path else ""
    name = re.sub(r'[^A-Za-z0-9._-]', '_', name).strip("._")
    return name or "download.bin"


def _filename_from_content_disposition(headers: dict) -> Optional[str]:
    raw = headers.get("Content-Disposition") or headers.get("content-disposition")
    if not raw:
        return None
    m = re.search(r'filename\*?=(?:UTF-8\'\')?("?)([^";]+)\1', raw)
    if m:
        return unquote(m.group(2)).strip() or None
    return None


def stream_download(
    url: str,
    dest: Path,
    *,
    progress_cb: ProgressCallback = None,
    chunk_size: int = _CHUNK_SIZE,
    timeout: float = 60.0,
    headers: Optional[dict] = None,
    session: Optional[requests.Session] = None,
) -> bool:
    """Download ``url`` to ``dest`` in chunks, calling ``progress_cb`` per chunk.

    Writes to a temp file alongside ``dest`` first and atomically
    renames on success. Returns ``True`` on success, ``False`` on
    failure (the partial temp file is removed on failure).

    The progress callback receives:
      ``{"url", "dest", "bytes_done", "bytes_total", "pct", "phase"}``
    where ``phase`` is one of ``"start"``, ``"progress"``, ``"done"``,
    ``"error"``.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    req_headers = dict(headers or {})
    req_headers.setdefault("User-Agent", "NeuraX-Launcher/4.0.0")

    http = session or requests
    try:
        # Stream the response so we can read the body in chunks.
        resp = http.get(
            url,
            stream=True,
            timeout=timeout,
            allow_redirects=True,
            headers=req_headers,
        )
    except Exception as ex:
        if progress_cb:
            try:
                progress_cb({
                    "url": url, "dest": str(dest),
                    "bytes_done": 0, "bytes_total": 0, "pct": 0,
                    "phase": "error", "error": str(ex),
                })
            except Exception:
                pass
        return False

    if not (200 <= resp.status_code < 300):
        if progress_cb:
            try:
                progress_cb({
                    "url": url, "dest": str(dest),
                    "bytes_done": 0, "bytes_total": 0, "pct": 0,
                    "phase": "error",
                    "error": f"HTTP {resp.status_code}",
                })
            except Exception:
                pass
        return False

    # Some CDNs omit Content-Length on chunked transfers; treat
    # missing total as 0 and just report deltas.
    try:
        total = int(resp.headers.get("Content-Length") or 0)
    except (ValueError, TypeError):
        total = 0

    tmp_fd, tmp_path = tempfile.mkstemp(
        prefix=dest.name + ".", suffix=".part",
        dir=str(dest.parent),
    )
    try:
        # Notify "start" so callers can update their UI label before
        # the first byte arrives.
        if progress_cb:
            try:
                progress_cb({
                    "url": url, "dest": str(dest),
                    "bytes_done": 0, "bytes_total": total, "pct": 0,
                    "phase": "start",
                })
            except Exception:
                pass

        done = 0
        last_emit = -1
        with os.fdopen(tmp_fd, "wb") as f:
            try:
                for chunk in resp.iter_content(chunk_size=chunk_size):
                    if not chunk:
                        continue
                    f.write(chunk)
                    done += len(chunk)
                    # Throttle progress callback to ~every 1% so we
                    # don't flood the Qt event queue with millions of
                    # updates on large files.
                    if total > 0:
                        pct = int(done * 100 / total)
                        if pct != last_emit:
                            last_emit = pct
                            if progress_cb:
                                try:
                                    progress_cb({
                                        "url": url, "dest": str(dest),
                                        "bytes_done": done,
                                        "bytes_total": total,
                                        "pct": pct,
                                        "phase": "progress",
                                    })
                                except Exception:
                                    pass
                    else:
                        # Unknown total — still emit at most every 512 KB
                        # so the UI shows life.
                        if done - last_emit >= 512 * 1024 or last_emit < 0:
                            last_emit = done if last_emit < 0 else last_emit + 512 * 1024
                            if progress_cb:
                                try:
                                    progress_cb({
                                        "url": url, "dest": str(dest),
                                        "bytes_done": done,
                                        "bytes_total": 0,
                                        "pct": 0,
                                        "phase": "progress",
                                    })
                                except Exception:
                                    pass
            except Exception as ex:
                if progress_cb:
                    try:
                        progress_cb({
                            "url": url, "dest": str(dest),
                            "bytes_done": done, "bytes_total": total,
                            "pct": 0, "phase": "error",
                            "error": str(ex),
                        })
                    except Exception:
                        pass
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                return False

        # Atomic rename — on Windows, os.replace handles the case
        # where ``dest`` already exists and may be locked.
        try:
            if dest.exists():
                try:
                    dest.unlink()
                except OSError:
                    pass
            os.replace(tmp_path, dest)
        except OSError:
            # ``os.replace`` can fail across volumes or when dest is
            # locked; fall back to copy + delete.
            try:
                shutil.copyfile(tmp_path, dest)
                os.unlink(tmp_path)
            except Exception as ex:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                if progress_cb:
                    try:
                        progress_cb({
                            "url": url, "dest": str(dest),
                            "bytes_done": done, "bytes_total": total,
                            "pct": 0, "phase": "error",
                            "error": f"finalize: {ex}",
                        })
                    except Exception:
                        pass
                return False

    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        return False

    # Final progress event so the UI can move the bar to 100%.
    if progress_cb:
        try:
            progress_cb({
                "url": url, "dest": str(dest),
                "bytes_done": done, "bytes_total": total or done,
                "pct": 100 if total else 0, "phase": "done",
            })
        except Exception:
            pass

    return True


def stream_download_to_dir(
    url: str,
    dest_dir: Path,
    *,
    progress_cb: ProgressCallback = None,
    chunk_size: int = _CHUNK_SIZE,
    timeout: float = 60.0,
    headers: Optional[dict] = None,
    fallback_name: Optional[str] = None,
    session: Optional[requests.Session] = None,
) -> Optional[Path]:
    """Like :func:`stream_download` but picks the filename from the URL
    or the ``Content-Disposition`` header.

    Returns the destination path on success, ``None`` on failure.
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Probe the URL once (HEAD if the server supports it, otherwise a
    # tiny ranged GET) so we can read ``Content-Disposition`` cheaply.
    fname = fallback_name or _safe_filename_from_url(url)
    try:
        h = session.head(
            url, timeout=min(10.0, timeout), allow_redirects=True,
            headers=headers or {"User-Agent": "NeuraX-Launcher/4.0.0"},
        ) if session else requests.head(
            url, timeout=min(10.0, timeout), allow_redirects=True,
            headers=headers or {"User-Agent": "NeuraX-Launcher/4.0.0"},
        )
        cd_name = _filename_from_content_disposition(h.headers)
        if cd_name:
            fname = cd_name
    except Exception:
        pass

    dest = dest_dir / fname
    ok = stream_download(
        url, dest,
        progress_cb=progress_cb,
        chunk_size=chunk_size,
        timeout=timeout,
        headers=headers,
        session=session,
    )
    return dest if ok else None