"""
Silent subprocess helpers.

Goal: launch child processes (Java for Minecraft, Java for a local
server, helper scripts, etc.) without ever flashing a console window on
Windows. The earlier version of the launcher passed
``subprocess.CREATE_NO_WINDOW`` to its Popen calls; that flag hides the
new child's window but does NOT detach the child from any console the
parent process may still hold. If the launcher is built as
``/SUBSYSTEM:CONSOLE`` (e.g. via a manual ``pyinstaller`` without
``--noconsole``) or if a stray ``print`` flushed a few bytes before
``sys.stdout`` was redirected, Windows can still allocate a console for
the child for a few milliseconds — exactly the "terminal flash" the user
reports.

Belt-and-suspenders fix used here:

* On Windows the child is started with
  ``CREATE_NO_WINDOW | DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP``.
  * ``CREATE_NO_WINDOW`` (0x08000000) — the new process has no window.
  * ``DETACHED_PROCESS`` (0x00000008) — the new process is not attached
    to the parent's console, so it cannot inherit or allocate a console.
  * ``CREATE_NEW_PROCESS_GROUP`` (0x00000200) — Ctrl-C events from the
    parent's console (if any) won't propagate to the child.
* ``stdin`` is forced to ``subprocess.DEVNULL`` unless the caller asked
  for a pipe (server console needs to send commands like ``stop``).
* The default ``stdout``/``stderr`` for the silent runner are also
  ``DEVNULL`` — these are short-lived installer / helper invocations
  where we don't want their output. The launcher still reads the
  Minecraft and server stdout through its own Popen call (see
  ``popen_no_window`` below) so the in-app log panels keep working.
"""
from __future__ import annotations

import os
import subprocess
import sys
from typing import Any, Mapping, Optional, Sequence


# Windows creation flag bits. They're not exposed on non-Windows, so we
# probe them lazily and default to 0 elsewhere.
if sys.platform == "win32":
    _CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    _DETACHED_PROCESS = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
    _CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
    SILENT_CREATIONFLAGS = _CREATE_NO_WINDOW | _DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP
else:
    SILENT_CREATIONFLAGS = 0


def _normalize_stdin(stdin: Any, *, allow_pipe: bool) -> Any:
    """Force stdin to a safe default unless the caller explicitly wants a pipe."""
    if allow_pipe:
        return stdin if stdin is not None else subprocess.DEVNULL
    if stdin is None:
        return subprocess.DEVNULL
    return stdin


def run_silent(
    cmd: Sequence[str],
    *,
    timeout: Optional[float] = None,
    cwd: Optional[str] = None,
    input: Optional[bytes] = None,
    env: Optional[Mapping[str, str]] = None,
    check: bool = False,
) -> subprocess.CompletedProcess:
    """Run a short helper process with no console window and no inherited stdio.

    stdout/stderr are routed to DEVNULL — the launcher logs them via its
    own ``logger.info`` calls. Use this for installer jars, wmic,
    taskkill, powershell, cmd /c, etc.
    """
    kwargs: dict[str, Any] = {
        "cwd": cwd,
        "stdin": subprocess.DEVNULL if input is None else subprocess.PIPE,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "creationflags": SILENT_CREATIONFLAGS,
    }
    if timeout is not None:
        kwargs["timeout"] = timeout
    if env is not None:
        kwargs["env"] = env
    if check:
        kwargs["check"] = True
    if input is not None:
        kwargs["input"] = input
    return subprocess.run(list(cmd), **kwargs)


def check_output_silent(
    cmd: Sequence[str],
    *,
    timeout: Optional[float] = None,
    cwd: Optional[str] = None,
    stderr_target: Any = subprocess.STDOUT,
    env: Optional[Mapping[str, str]] = None,
) -> bytes:
    """Drop-in for ``subprocess.check_output`` that never flashes a console.

    Used by helpers that need the child's output (Java version probe,
    Discord process probe, sysctl on macOS, …). Stdout is captured into
    a pipe; the caller's stderr_target controls where the child writes
    its own stderr (default STDOUT — most version probes go there).
    """
    return subprocess.check_output(
        list(cmd),
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=stderr_target,
        timeout=timeout,
        env=env,
        creationflags=SILENT_CREATIONFLAGS,
    )


def popen_no_window(
    cmd: Sequence[str],
    *,
    cwd: Optional[str] = None,
    stdin: Any = None,
    stdout: Any = None,
    stderr: Any = None,
    env: Optional[Mapping[str, str]] = None,
    allow_stdin_pipe: bool = False,
    text: bool = False,
    encoding: Optional[str] = None,
    errors: Optional[str] = None,
    bufsize: int = -1,
    **extra: Any,
) -> subprocess.Popen:
    """Drop-in replacement for ``subprocess.Popen`` that never flashes a console.

    The caller still gets the same ``Popen`` instance back with the same
    stdin/stdout/stderr pipes they asked for, so the in-launcher log
    readers (the per-game and per-server streaming threads) keep
    working unchanged. The only thing that changes is the Windows
    creation flags and the default stdin (DEVNULL unless explicitly
    requested as a pipe — needed for the server console).
    """
    stdin = _normalize_stdin(stdin, allow_pipe=allow_stdin_pipe)

    kwargs: dict[str, Any] = {
        "cwd": cwd,
        "stdin": stdin,
        "stdout": stdout,
        "stderr": stderr,
        "creationflags": SILENT_CREATIONFLAGS,
        "bufsize": bufsize,
    }
    if env is not None:
        kwargs["env"] = env
    if text:
        kwargs["text"] = True
    if encoding is not None:
        kwargs["encoding"] = encoding
    if errors is not None:
        kwargs["errors"] = errors
    kwargs.update(extra)
    return subprocess.Popen(list(cmd), **kwargs)


def detach_existing_console() -> None:
    """Best-effort: detach the current process from any inherited console.

    Call this from the entry script before the GUI starts so neither the
    launcher nor any future child can briefly allocate a console window.
    No-op on non-Windows.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        # FreeConsole returns non-zero on success. It only detaches if a
        # console is actually attached, so it's safe to call blindly.
        kernel32.FreeConsole()
    except Exception:
        pass