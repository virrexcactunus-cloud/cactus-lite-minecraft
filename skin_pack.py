"""Ресурспак скина, работающий на всех версиях Minecraft 1.6+.

Форматы ресурспаков (pack_format) и пути к текстурам игрока по версиям:

    1.6.1 – 1.8.9      pack_format 1, скин 64x32 (legacy), textures/entity/steve.png (в 1.6 — char.png)
    1.9   – 1.10.2     pack_format 2
    1.11  – 1.12.2     pack_format 3
    1.13  – 1.14.4     pack_format 4
    1.15  – 1.16.1     pack_format 5
    1.16.2 – 1.16.5    pack_format 6
    1.17  – 1.17.1     pack_format 7
    1.18  – 1.18.2     pack_format 8
    1.19  – 1.19.2     pack_format 9
    1.19.3            pack_format 12
    1.19.4            pack_format 13
    1.20  – 1.20.1     pack_format 15
    1.20.2            pack_format 18
    1.20.3 – 1.20.4    pack_format 22
    1.20.5 – 1.20.6    pack_format 32
    1.21  – 1.21.1     pack_format 34
    1.21.2 – 1.21.3    pack_format 42
    1.21.4            pack_format 46
    1.21.5            pack_format 55
    1.21.6            pack_format 63
    1.21.7 – 1.21.8    pack_format 64
    1.21.9 – 1.21.10   pack_format 69 (в pack.mcmeta нужны поля min_format/max_format)
    1.21.11           pack_format 75
    26.1  – 26.1.2     pack_format 84
    26.2              pack_format 88

С 1.21.9 текстуры игрока лежат в textures/entity/player/{wide,slim}/ —
отдельные файлы для 9 дефолтных персонажей. Игрок без скина получает одного
из них, поэтому перекрываем все 18 файлов.
"""
import io
import json
import os
import re
import shutil

SKIN_PACK = "MC Lite Skin"

# Дефолтные персонажи с 1.21.9 (широкие и стройные варианты)
PLAYER_SKIN_NAMES = ("alex", "ari", "efe", "kai", "makena", "noor", "steve", "sunny", "zuri")

# Старые имена файлов скина игрока (1.6–1.21.8)
LEGACY_ENTITY_NAMES = ("steve.png", "alex.png", "char.png")

_VERSION_RE = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")


def _version_parts(version):
    m = _VERSION_RE.match(version or "")
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)


def pack_format_for(version):
    """Точный pack_format ресурспака для версии Minecraft."""
    parts = _version_parts(version)
    if not parts:
        return 88
    major, minor, patch = parts
    if major == 1:
        if minor <= 8:
            return 1
        if minor <= 10:
            return 2
        if minor <= 12:
            return 3
        if minor <= 14:
            return 4
        if minor == 15:
            return 5
        if minor == 16:
            return 6
        if minor == 17:
            return 7
        if minor == 18:
            return 8
        if minor == 19:
            return 9 if patch <= 2 else (12 if patch == 3 else 13)
        if minor == 20:
            if patch <= 1:
                return 15
            if patch == 2:
                return 18
            if patch <= 4:
                return 22
            return 32
        if minor == 21:
            if patch <= 1:
                return 34
            if patch <= 3:
                return 42
            if patch == 4:
                return 46
            if patch == 5:
                return 55
            if patch == 6:
                return 63
            if patch <= 8:
                return 64
            if patch <= 10:
                return 69
            return 75
        return 88
    if major == 26:
        return 84 if minor <= 1 else 88
    return 88


def version_supports_skin(version):
    """Ресурспак скина существует с 1.6.1; мод-сборки с иными id игнорируем."""
    v = (version or "").lower()
    if v.startswith(("a", "b", "c")) or not re.match(r"\d+\.\d+", v):
        return False
    major, minor = int(v.split(".")[0]), int(v.split(".")[1])
    if major == 1:
        return minor >= 6
    return major >= 2


def _needs_legacy_skin(version):
    """1.6–1.7 понимают только скин 64x32, современный 64x64 там ломается."""
    parts = _version_parts(version)
    return bool(parts) and parts[0] == 1 and parts[1] <= 7


def _needs_new_player_paths(version):
    """С 1.21.9 текстуры игрока лежат в player/{wide,slim}/."""
    parts = _version_parts(version)
    if not parts:
        return False
    major, minor, patch = parts
    return major > 1 or (major == 1 and (minor > 21 or (minor == 21 and patch >= 9)))


def _legacy_skin_bytes(skin_png):
    """Конвертирует любой скин в классический 64x32: верхняя половина 64x64
    лежит в старых версиях на тех же местах (проверено по стоковым текстурам),
    левые рука и нога дорисовываются игрой зеркально из правых."""
    from PIL import Image
    im = Image.open(skin_png).convert("RGBA").resize((64, 64), Image.LANCZOS)
    legacy = Image.new("RGBA", (64, 32), (0, 0, 0, 0))
    legacy.paste(im.crop((0, 0, 64, 32)), (0, 0))
    buf = io.BytesIO()
    legacy.save(buf, "PNG")
    return buf.getvalue()


def _pack_mcmeta(version):
    meta = {
        "pack": {
            "description": "MC Lite Skin",
            "pack_format": pack_format_for(version),
        }
    }
    if _needs_new_player_paths(version):
        fmt = meta["pack"]["pack_format"]
        meta["pack"]["min_format"] = fmt
        meta["pack"]["max_format"] = fmt
    return meta


def write_skin_pack(game_dir, version, skin_png):
    """Пишет (или обновляет) ресурспак скина в папке игры и включает его."""
    pack = os.path.join(game_dir, "resourcepacks", SKIN_PACK)
    os.makedirs(pack, exist_ok=True)
    with open(os.path.join(pack, "pack.mcmeta"), "w", encoding="utf-8") as f:
        json.dump(_pack_mcmeta(version), f)

    if _needs_new_player_paths(version):
        base = os.path.join(pack, "assets", "minecraft", "textures", "entity", "player")
        for sub in ("wide", "slim"):
            folder = os.path.join(base, sub)
            os.makedirs(folder, exist_ok=True)
            for name in PLAYER_SKIN_NAMES:
                shutil.copyfile(skin_png, os.path.join(folder, name + ".png"))
        return _enable_skin_pack(game_dir)

    folder = os.path.join(pack, "assets", "minecraft", "textures", "entity")
    os.makedirs(folder, exist_ok=True)
    if _needs_legacy_skin(version):
        try:
            data = _legacy_skin_bytes(skin_png)
        except Exception:
            data = None
        if data is not None:
            for name in LEGACY_ENTITY_NAMES:
                with open(os.path.join(folder, name), "wb") as f:
                    f.write(data)
            return _enable_skin_pack(game_dir)
    for name in LEGACY_ENTITY_NAMES:
        shutil.copyfile(skin_png, os.path.join(folder, name))
    return _enable_skin_pack(game_dir)


def remove_skin_pack(game_dir):
    """Удаляет ресурспак скина (папка остаётся в options.txt — это безвредно)."""
    try:
        shutil.rmtree(os.path.join(game_dir, "resourcepacks", SKIN_PACK))
    except Exception:
        pass


def _enable_skin_pack(game_dir):
    """Дописывает пак в resourcePacks списка options.txt, не трогая остальное."""
    opts = os.path.join(game_dir, "options.txt")
    lines = []
    names = []
    if os.path.isfile(opts):
        with open(opts, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
        for line in lines:
            if line.startswith("resourcePacks:"):
                names = re.findall(r'"([^"]*)"', line)
    if SKIN_PACK not in names:
        names.append(SKIN_PACK)
    packed = json.dumps(names)
    found = False
    for i, line in enumerate(lines):
        if line.startswith("resourcePacks:"):
            lines[i] = "resourcePacks:" + packed
            found = True
    if not found:
        lines.append("resourcePacks:" + packed)
    with open(opts, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
