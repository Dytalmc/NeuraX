import sys
import os
<<<<<<< HEAD
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# Detach from any inherited console *immediately*
# ---------------------------------------------------------------------------
# Even when built with PyInstaller `--noconsole`, the launcher may still
# inherit an invisible console handle from the parent shell (or from a
# previous relaunch via `cmd /c start`). Any child process spawned by
# Python then has a console to attach to, and Windows can briefly flash
# a terminal window when the child starts. We call FreeConsole() right
# at startup — once detached, no descendant process can ever inherit a
# console from us, which eliminates the flash at its source.
# ---------------------------------------------------------------------------
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.kernel32.FreeConsole()  # type: ignore[attr-defined]
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Silent-mode stdout/stderr redirect
# ---------------------------------------------------------------------------
# When this launcher is built with PyInstaller `--noconsole` (or
# Nuitka `--disable-console`, etc.) the C runtime still attaches the
# standard streams to invisible console handles — and any write to those
# handles can briefly flash a console window on Windows before the
# stream is closed. We make absolutely sure that nothing in the launcher
# (or any third-party library) ever writes a single byte to a real
# console: we replace sys.stdout / sys.stderr with a file in the
# neurax/logs folder so any stray print() or traceback lands in the log
# file instead of flashing a terminal to the user.
#
# IMPORTANT: this happens BEFORE anything else is imported so the redirect
# covers import-time prints from every dependency.
# ---------------------------------------------------------------------------
def _install_silent_streams(log_path: Path) -> None:
    """Open an append-mode file and point sys.stdout / sys.stderr at it.

    The returned file handle is kept alive on a module-level tuple so
    the OS doesn't close it underneath us (Python's GC would normally
    close sys.stdout, but we don't want the log file to be locked while
    the app is running)."""
    global _silent_stdout_file, _silent_stderr_file  # type: ignore
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        # Use line buffering so partial writes still get flushed regularly.
        f_out = open(log_path, "a", encoding="utf-8", buffering=1)
        f_err = open(log_path, "a", encoding="utf-8", buffering=1)
    except Exception:
        # If even the log file can't be opened (read-only disk etc.),
        # fall back to os.devnull so the streams are still silenced.
        try:
            devnull = open(os.devnull, "w", encoding="utf-8")
        except Exception:
            return
        f_out = devnull
        f_err = devnull
    sys.stdout = f_out
    sys.stderr = f_err
    # sys.stdin must also be detached so any child we spawn with
    # `stdin=subprocess.PIPE` (the local server console, for example)
    # doesn't accidentally inherit a console-attached stdin handle.
    try:
        sys.stdin = open(os.devnull, "r", encoding="utf-8")
    except Exception:
        pass
    _silent_stdout_file = f_out  # type: ignore
    _silent_stderr_file = f_err  # type: ignore


_silent_stdout_file = None  # type: ignore
_silent_stderr_file = None  # type: ignore


try:
    # neurax lives under %APPDATA%\neurax on Windows. We resolve it
    # inline (without importing neurax.*) so the redirect is active
    # before any third-party import has a chance to print.
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        neurax_root = Path(appdata) / "neurax" if appdata else Path.home() / "AppData" / "Roaming" / "neurax"
    elif sys.platform == "darwin":
        neurax_root = Path.home() / "Library" / "Application Support" / "neurax"
    else:
        xdg = os.environ.get("XDG_DATA_HOME")
        neurax_root = Path(xdg) / "neurax" if xdg else Path.home() / ".local" / "share" / "neurax"
    _silent_log_path = neurax_root / "logs" / "launcher-stdouterr.log"
    _install_silent_streams(_silent_log_path)
except Exception:
    # Last-resort: redirect to devnull so we never flash a console.
    try:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
        sys.stdin = open(os.devnull, "r", encoding="utf-8")
    except Exception:
        pass


=======

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
if sys.platform == "win32":
    try:
        import asyncio
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

from neurax.app import main

<<<<<<< HEAD

# ---------------------------------------------------------------------------
# Unhandled exception hook
# ---------------------------------------------------------------------------
# If the launcher ever crashes (an uncaught exception outside Qt's event
# loop), Python's default behaviour is to print the traceback to stderr
# — which on a --noconsole exe would flash a console window. We redirect
# the traceback into the same silent log so the user never sees a flash
# and we still have a record of what happened.
# ---------------------------------------------------------------------------
def _silent_excepthook(exc_type, exc_value, exc_tb):
    try:
        import traceback
        msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        sys.stderr.write(msg)
        try:
            sys.stderr.flush()
        except Exception:
            pass
    except Exception:
        pass


sys.excepthook = _silent_excepthook


=======
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
if __name__ == "__main__":
    sys.exit(main())
