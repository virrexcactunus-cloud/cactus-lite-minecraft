"""Local skin support: converts an image and injects it as a resource pack.

Only used for offline play. Ely.by accounts get their skin from the auth server
via authlib-injector, so no resource pack is written for them.
"""

import json
import os
import re
import shutil

from cactus_lite.core.paths import MC_DIR, SKIN_DIR, SKIN_PACK

SKIN_PATH = os.path.join(SKIN_DIR, "skin.png")
_ENTITY_TEXTURES = ("steve.png", "alex.png", "char.png")
# (max minor version, pack_format) for 1.x releases.
_PACK_FORMATS = ((8, 1), (12, 3), (14, 4), (15, 5), (16, 6), (17, 7), (18, 8))


def pack_format_for(version):
    m = re.match(r"(\d+)\.(\d+)(?:\.(\d+))?", version or "")
    if not m:
        return 15
    major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
    if major != 1:
        return 55
    for max_minor, fmt in _PACK_FORMATS:
        if minor <= max_minor:
            return fmt
    if minor == 19:
        return 9 if patch <= 2 else (12 if patch == 3 else 13)
    if minor == 20:
        if patch <= 1:
            return 15
        if patch == 2:
            return 18
        return 22 if patch <= 4 else 32
    if minor == 21:
        if patch <= 1:
            return 34
        if patch <= 3:
            return 42
        return 46 if patch == 4 else 55
    return 55


def has_skin():
    return os.path.isfile(SKIN_PATH)


def save_skin(src):
    """Convert any supported image to a 64x64 PNG skin. Raises on failure."""
    os.makedirs(SKIN_DIR, exist_ok=True)
    try:
        from PIL import Image
    except Exception:
        Image = None
    if Image is not None:
        Image.open(src).convert("RGBA").resize((64, 64), Image.LANCZOS).save(SKIN_PATH, "PNG")
        return SKIN_PATH
    import wx
    image = wx.Image(src)
    if not image.IsOk():
        raise RuntimeError("Не удалось прочитать изображение")
    image.Rescale(64, 64, wx.IMAGE_QUALITY_HIGH).SaveFile(SKIN_PATH, wx.BITMAP_TYPE_PNG)
    return SKIN_PATH


def remove_skin(mc_dir=MC_DIR):
    for path in (SKIN_PATH,):
        try:
            os.remove(path)
        except OSError:
            pass
    shutil.rmtree(os.path.join(mc_dir, "resourcepacks", SKIN_PACK), ignore_errors=True)


def write_skin_pack(version, mc_dir=MC_DIR, skin_png=SKIN_PATH):
    pack = os.path.join(mc_dir, "resourcepacks", SKIN_PACK)
    entity = os.path.join(pack, "assets", "minecraft", "textures", "entity")
    os.makedirs(entity, exist_ok=True)
    with open(os.path.join(pack, "pack.mcmeta"), "w", encoding="utf-8") as f:
        json.dump({"pack": {"pack_format": pack_format_for(version), "description": SKIN_PACK}}, f)
    for name in _ENTITY_TEXTURES:
        shutil.copyfile(skin_png, os.path.join(entity, name))
    enable_skin_pack(mc_dir)


def enable_skin_pack(mc_dir=MC_DIR):
    """Add the skin pack to options.txt so the player does not have to enable it."""
    options = os.path.join(mc_dir, "options.txt")
    lines, names = [], []
    if os.path.isfile(options):
        with open(options, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
        for line in lines:
            if line.startswith("resourcePacks:"):
                names = re.findall(r'"([^"]*)"', line)
    if SKIN_PACK not in names:
        names.append(SKIN_PACK)
    packed = "resourcePacks:" + json.dumps(names)
    for i, line in enumerate(lines):
        if line.startswith("resourcePacks:"):
            lines[i] = packed
            break
    else:
        lines.append(packed)
    with open(options, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
