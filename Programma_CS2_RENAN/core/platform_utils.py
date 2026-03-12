"""Platform-specific utilities (drive detection, etc.)."""

import os
from typing import List

from kivy.utils import platform

from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.platform_utils")


def get_available_drives() -> List[str]:
    """Returns available drive roots.

    PU-02: Handles win, linux, macosx explicitly. Other platforms fall back to home dir.
    PU-01: All fallback paths are validated with os.path.isdir().
    """
    # PU-02: Explicit platform handling (Kivy platform strings)
    if platform == "win":
        return _get_windows_drives()
    if platform in ("linux", "macosx"):
        # Root is always valid on Unix-like systems
        return ["/"]
    # Android, iOS, or unknown — fall back to validated home dir
    home = os.path.expanduser("~")
    if os.path.isdir(home):
        return [home]
    logger.warning("PU-01: Home directory '%s' not accessible on platform '%s'", home, platform)
    return ["/"]


def _get_windows_drives() -> List[str]:
    """Windows drive detection with validated fallbacks."""
    import string

    try:
        from ctypes import windll

        drives = []
        bitmask = windll.kernel32.GetLogicalDrives()
        for letter in string.ascii_uppercase:
            if bitmask & 1:
                drive_path = letter + ":\\"
                # PU-01: Validate that the drive is actually accessible
                if os.path.isdir(drive_path):
                    drives.append(drive_path)
            bitmask >>= 1
        if drives:
            return drives
    except Exception as e:
        logger.debug("Win32 drive detection failed: %s", e)

    try:
        import psutil

        writable_drives = [
            p.mountpoint
            for p in psutil.disk_partitions()
            if "rw" in p.opts and os.path.isdir(p.mountpoint)
        ]
        if writable_drives:
            return writable_drives
    except Exception as e2:
        logger.debug("psutil drive detection failed: %s", e2)

    # PU-01: Final fallback — validate home dir exists
    home = os.path.expanduser("~")
    if os.path.isdir(home):
        return [home]
    return ["C:\\"]
