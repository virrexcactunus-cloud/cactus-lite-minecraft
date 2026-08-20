"""Pinned mod catalog plus Modrinth/OptiFine metadata lookups."""

import re

from cactus_lite.core.net import get_bytes, get_json, quote
from cactus_lite.core.paths import CATALOG_CACHE_PATH
from cactus_lite.core.storage import read_cache, write_cache

CACHE_TTL = 86400
MODRINTH_API = "https://api.modrinth.com/v2"
OPTIFINE_DOWNLOADS = "https://optifine.net/downloads"

RELEASE_VER = re.compile(r"^\d+\.\d+(\.\d+)?$")
_OPTIFINE_NAME = re.compile(r"adloadx\?f=(OptiFine_[^&\"']+)\.jar&x=([^&\"']+)")
_OPTIFINE_LINK = re.compile(r"downloadx\?f=([^\"'&]+)&x=([^\"'&]+)")

# Icons are stored in assets/mod_icons.json keyed by icon_key.
PINNED_MODS = [
    {
        "id": "embeddium",
        "name": "Embeddium",
        "icon_key": "embeddium",
        "color": "#10b981",
        "source": "modrinth",
        "project": "embeddium",
        "note": "Аналог Sodium (Forge / NeoForge)",
    },
    {
        "id": "zoomify",
        "name": "Zoomify",
        "icon_key": "zoomify",
        "color": "#8b5cf6",
        "source": "modrinth",
        "project": "zoomify",
        "note": "Зум с настройками (Fabric / Quilt)",
    },
    {
        "id": "distant-horizons",
        "name": "Distant Horizons",
        "icon_key": "distanthorizons",
        "color": "#06b6d4",
        "source": "modrinth",
        "project": "distant-horizons",
        "note": "Отрисовка дальних чанков (Forge / Fabric)",
    },
    {
        "id": "voxy",
        "name": "Voxy",
        "icon_key": "voxy",
        "color": "#f59e0b",
        "source": "modrinth",
        "project": "voxy",
        "note": "Быстрая LOD-генерация (Fabric)",
    },
    {
        "id": "sodium",
        "name": "Sodium",
        "icon_key": "sodium",
        "color": "#3b82f6",
        "source": "modrinth",
        "project": "sodium",
        "note": "Оптимизация рендера (Fabric)",
    },
    {
        "id": "optifine",
        "name": "OptiFine",
        "icon_key": "optifine",
        "color": "#e05d3f",
        "source": "optifine",
        "note": "Оптимизация и шейдеры (Forge / ваниль)",
    },
]


def version_sort_key(version):
    nums = [int(x) for x in re.findall(r"\d+", version or "")]
    return (nums + [0] * 4)[:4]


def series_of(version):
    m = re.match(r"(\d+)\.(\d+)", version or "")
    return f"{m.group(1)}.{m.group(2)}" if m else ""


def matches_series(version, series):
    return bool(series) and series_of(version) == series


def fetch_modrinth_project_versions(project_slug):
    """Best file per Minecraft release version: newest release beats a beta."""
    try:
        data = get_json(f"{MODRINTH_API}/project/{project_slug}/version")
    except Exception:
        return {}
    best = {}
    for entry in data:
        files = entry.get("files") or []
        if not files:
            continue
        file = next((f for f in files if f.get("primary")), files[0])
        if not file.get("url") or not file.get("filename"):
            continue
        rank = (entry.get("version_type") == "release", entry.get("date_published") or "")
        info = {
            "filename": file["filename"],
            "url": file["url"],
            "size": file.get("size"),
            "loaders": entry.get("loaders") or [],
        }
        for mc in entry.get("game_versions") or []:
            if not RELEASE_VER.match(mc):
                continue
            current = best.get(mc)
            if current is None or rank > current[1]:
                best[mc] = (info, rank)
    return {mc: info for mc, (info, _rank) in best.items()}


def search_modrinth_mods(query, limit=12, index="relevance", loader=None):
    facets = ['["project_type:mod"]']
    if loader and loader != "all":
        facets.append(f'["categories:{loader}"]')
    facets_str = quote("[" + ",".join(facets) + "]")
    url = (f"{MODRINTH_API}/search?query={quote((query or '').strip())}"
           f"&facets={facets_str}&limit={limit}&index={index}")
    try:
        data = get_json(url)
    except Exception:
        return []
    results = []
    for hit in data.get("hits") or []:
        mod_id = hit.get("slug") or hit.get("project_id")
        if not mod_id:
            continue
        description = hit.get("description") or ""
        results.append({
            "id": mod_id,
            "name": hit.get("title") or mod_id,
            "color": "#6366f1",
            "source": "modrinth",
            "project": mod_id,
            "note": description[:65] + ("..." if len(description) > 65 else ""),
            "full_desc": description,
            "icon_url": hit.get("icon_url") or "",
            "categories": hit.get("categories") or [],
            "pinned": False,
        })
    return results


def fetch_optifine():
    html = get_bytes(OPTIFINE_DOWNLOADS).decode("iso-8859-1", "replace")
    out = {}
    for match in _OPTIFINE_NAME.finditer(html):
        name, token = match.group(1), match.group(2)
        parts = name.split("_")
        if len(parts) < 3 or not RELEASE_VER.match(parts[1]):
            continue
        mc = parts[1]
        if mc in out:
            continue
        out[mc] = {
            "filename": name + ".jar",
            "size": None,
            "url": f"https://optifine.net/adloadx?f={name}.jar&x={token}",
            "loaders": ["forge", "vanilla"],
        }
    return out


def resolve_optifine_download(page_url):
    """OptiFine hides the real file behind an ad page; pull the direct link out."""
    page = get_bytes(page_url).decode("iso-8859-1", "replace")
    match = _OPTIFINE_LINK.search(page)
    if not match:
        raise RuntimeError("Не удалось получить ссылку на скачивание OptiFine")
    return f"https://optifine.net/downloadx?f={match.group(1)}&x={match.group(2)}"


def fetch_catalog():
    out = {}
    for mod in PINNED_MODS:
        if mod["source"] == "modrinth":
            out[mod["id"]] = fetch_modrinth_project_versions(mod["project"])
        elif mod["source"] == "optifine":
            out[mod["id"]] = fetch_optifine()
    return out


def load_cache():
    cached = read_cache(CATALOG_CACHE_PATH, CACHE_TTL, key="catalog")
    return cached if isinstance(cached, dict) else None


def save_cache(catalog):
    return write_cache(CATALOG_CACHE_PATH, catalog, key="catalog")
