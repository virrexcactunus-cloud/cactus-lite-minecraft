"""Filesystem locations and application-wide constants."""

import os
import sys

APP_NAME = "Cactus Lite Minecraft"
APP_VERSION = "v1.3"
USER_AGENT = f"CactusLiteMinecraft/{APP_VERSION.lstrip('v')} (cactunus)"

if getattr(sys, "frozen", False):
    APP_DIR = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
else:
    # .../cactus_lite/core/paths.py -> project root
    APP_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ASSETS_DIR = os.path.join(APP_DIR, "assets")
ICON_ICO = os.path.join(ASSETS_DIR, "icon.ico")
ICON_PNG = os.path.join(ASSETS_DIR, "icon.png")
MOD_ICONS_PATH = os.path.join(ASSETS_DIR, "mod_icons.json")

MC_DIR = os.path.join(os.path.expanduser("~"), ".mcl")
SETTINGS_PATH = os.path.join(MC_DIR, "settings.json")
ACCOUNTS_PATH = os.path.join(MC_DIR, "accounts.json")
COMPAT_CACHE_PATH = os.path.join(MC_DIR, "loader_compat.json")
CATALOG_CACHE_PATH = os.path.join(MC_DIR, "mod_catalog_v13.json")
SKIN_DIR = os.path.join(MC_DIR, "skins")
LIB_DIR = os.path.join(MC_DIR, "cactus")
SKIN_PACK = "MC Lite Skin"


def ensure_mc_dir():
    os.makedirs(MC_DIR, exist_ok=True)
    return MC_DIR
