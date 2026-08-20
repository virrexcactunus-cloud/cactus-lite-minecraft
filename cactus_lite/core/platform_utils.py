"""Platform specific helpers.

Windows is the primary target; every helper degrades gracefully elsewhere so the
launcher can at least start and be developed on macOS/Linux.
"""

import ctypes
import os
import subprocess
import sys

IS_WINDOWS = sys.platform.startswith("win")
IS_MACOS = sys.platform == "darwin"

JAVA_EXECUTABLES = ("javaw.exe", "java.exe") if IS_WINDOWS else ("java",)


def _kernel32():
    if not IS_WINDOWS:
        return None
    return ctypes.windll.kernel32


def hide_console():
    if not IS_WINDOWS:
        return
    try:
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    except Exception:
        pass


def no_window_flags():
    """Popen flags that keep a console window from flashing up."""
    if IS_WINDOWS:
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    return {}


def open_path(path):
    """Open a folder or file in the system file manager."""
    if IS_WINDOWS:
        os.startfile(path)  # noqa: S606 - documented Windows API
        return
    if IS_MACOS:
        subprocess.Popen(["open", path])
        return
    subprocess.Popen(["xdg-open", path])


def total_ram_gb():
    k = _kernel32()
    if k is not None:
        try:
            mem = ctypes.c_ulonglong()
            if k.GetPhysicallyInstalledSystemMemory(ctypes.byref(mem)):
                return max(1, mem.value // (1024 * 1024))
        except Exception:
            pass
    try:
        return max(1, os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") // 1024 ** 3)
    except Exception:
        return 4


class _MemoryStatus(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def ram_info():
    """Return (total_gb, available_gb)."""
    k = _kernel32()
    if k is not None:
        try:
            m = _MemoryStatus()
            m.dwLength = ctypes.sizeof(_MemoryStatus)
            if k.GlobalMemoryStatusEx(ctypes.byref(m)):
                return m.ullTotalPhys // 1024 ** 3, m.ullAvailPhys // 1024 ** 3
        except Exception:
            pass
    total = total_ram_gb()
    try:
        avail = os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") // 1024 ** 3
    except Exception:
        avail = total
    return total, max(1, min(total, avail))


def temp_dir(fallback):
    return os.environ.get("TEMP") or os.environ.get("TMPDIR") or fallback


def junction(link, target):
    """Create a directory junction/symlink. Raises on failure."""
    if IS_WINDOWS:
        res = subprocess.run(["cmd", "/c", "mklink", "/J", link, target], capture_output=True)
        if res.returncode != 0:
            raise RuntimeError("Не удалось подготовить папку установки")
        return
    os.symlink(target, link)


def find_game_window(pid):
    """Handle of the visible Minecraft window owned by pid, or None."""
    if not IS_WINDOWS:
        return None
    result = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def enum_cb(hwnd, _lparam):
        if result or not ctypes.windll.user32.IsWindowVisible(hwnd):
            return True
        tid = ctypes.c_ulong()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(tid))
        if tid.value != pid:
            return True
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            if "minecraft" in buf.value.lower():
                result.append(hwnd)
        return True

    try:
        ctypes.windll.user32.EnumWindows(enum_cb, 0)
    except Exception:
        return None
    return result[0] if result else None


def close_window(hwnd):
    if IS_WINDOWS and hwnd:
        ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
