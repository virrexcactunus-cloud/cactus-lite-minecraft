"""Cactus Lite Minecraft — launcher entry point.

The implementation lives in the `cactus_lite` package; this file stays so the
existing `python launcher.py` / PyInstaller workflow keeps working.
"""

from cactus_lite.__main__ import main

if __name__ == "__main__":
    main()
