import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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

if __name__ == "__main__":
    sys.exit(main())
