"""Minecraft version helpers: sorting, labels, mod-loader compatibility."""

import re

import minecraft_launcher_lib as mll

from cactus_lite.core.paths import COMPAT_CACHE_PATH, MC_DIR
from cactus_lite.core.storage import read_cache, write_cache

COMPAT_TTL = 86400

LOADER_IDS = ("forge", "fabric", "neoforge")
LOADER_LETTERS = {"forge": "F", "fabric": "G", "neoforge": "N"}
LOADER_NAMES = {"forge": "Forge", "fabric": "Fabric", "neoforge": "NeoForge"}
LOADER_UI_VALUES = ("Нет (ваниль)", "Forge", "Fabric", "NeoForge")
LOADER_UI_IDS = ("none", "forge", "fabric", "neoforge")

RELEASE_RE = re.compile(r"^\d+\.\d+(?:\.\d+)?$")
UNAVAILABLE_SUFFIX = " (недоступна)"


def sort_key(version):
    nums = [int(x) for x in re.findall(r"\d+", version or "")]
    return (nums + [0] * 4)[:4]


def series_of(version):
    m = re.match(r"(\d+)\.(\d+)", version or "")
    return f"{m.group(1)}.{m.group(2)}" if m else ""


def is_loader_version_id(version_id):
    v = (version_id or "").lower()
    return ("-forge-" in v or v.startswith("forge-") or "fabric-loader" in v
            or v.startswith("neoforge-") or "quilt" in v or "optifine" in v)


def supports_skin(version):
    v = (version or "").lower()
    if v.startswith(("a", "b", "c")) or not re.match(r"\d+\.\d+", v):
        return False
    major, minor = (int(x) for x in v.split(".")[:2])
    return minor >= 6 if major == 1 else major >= 2


def required_java(version, mc_dir=MC_DIR):
    try:
        info = mll.runtime.get_version_runtime_information(version, mc_dir)
        if info:
            return int(info.get("javaMajorVersion") or 8)
    except Exception:
        pass
    m = re.match(r"1\.(\d+)", version or "")
    if m:
        minor = int(m.group(1))
        return 21 if minor >= 20 else (17 if minor >= 18 else 8)
    return 21 if re.match(r"\d+\.", version or "") else 8


def heuristic_compat(version_id):
    """Loader support guess used before the online compatibility list arrives."""
    if not RELEASE_RE.match(version_id or ""):
        return set()
    major, minor = (int(x) for x in version_id.split(".")[:2])
    out = set()
    if major == 1 and 1 <= minor <= 20:
        out.add("forge")
    if (major == 1 and minor >= 14) or major >= 2:
        out.add("fabric")
    if (major == 1 and minor >= 20) or major >= 2:
        out.add("neoforge")
    return out


def fetch_loader_compat():
    compat = {}
    for loader_id in LOADER_IDS:
        loader = mll.mod_loader.get_mod_loader(loader_id)
        for version in loader.get_minecraft_versions(stable_only=True):
            compat.setdefault(version, set()).add(loader_id)
    return compat


def load_compat_cache():
    cached = read_cache(COMPAT_CACHE_PATH, COMPAT_TTL, key="compat")
    if not isinstance(cached, dict):
        return None
    return {k: set(v) for k, v in cached.items()}


def save_compat_cache(compat):
    return write_cache(COMPAT_CACHE_PATH, {k: sorted(v) for k, v in compat.items()}, key="compat")


class VersionCatalog:
    """Installed versions plus loader-compatibility aware labels."""

    def __init__(self, mc_dir=MC_DIR):
        self.mc_dir = mc_dir
        self.compat = load_compat_cache() or {}
        self.ids = []

    def refresh_compat(self):
        """Fetch and cache the online compatibility list. Returns True on change."""
        if load_compat_cache() is not None:
            self.compat = load_compat_cache()
            return True
        try:
            compat = fetch_loader_compat()
        except Exception:
            return False
        save_compat_cache(compat)
        self.compat = compat
        return True

    def installed_ids(self):
        try:
            versions = mll.utils.get_installed_versions(self.mc_dir)
            self.ids = sorted({v["id"] for v in versions if not is_loader_version_id(v["id"])},
                              key=sort_key, reverse=True)
        except Exception:
            self.ids = []
        return self.ids

    def loaders_for(self, version_id):
        return self.compat.get(version_id) or heuristic_compat(version_id)

    def supports(self, version_id, loader):
        return loader == "none" or loader in self.loaders_for(version_id)

    def label(self, version_id, loader="none"):
        letters = " ".join(LOADER_LETTERS[l] for l in LOADER_IDS
                           if l in self.loaders_for(version_id))
        label = version_id + ((" " + letters) if letters else "")
        if not self.supports(version_id, loader):
            label += UNAVAILABLE_SUFFIX
        return label

    @staticmethod
    def id_from_label(label):
        if not label:
            return ""
        return label.replace(UNAVAILABLE_SUFFIX, "").split(" ")[0]


def available_versions():
    """All downloadable versions as a list of (id, type)."""
    data = mll.utils.get_version_list()
    pairs = {(v["id"], v.get("type", "release")) for v in data}
    latest = mll.utils.get_latest_version()
    for key in ("release", "snapshot"):
        if latest.get(key):
            pairs.add((latest[key], key))
    return list(pairs)
