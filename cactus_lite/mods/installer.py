"""Installing, listing and removing mods in the game's mods folder."""

import os
import re
import shutil
import subprocess
import tempfile
import uuid

from cactus_lite.core.net import download
from cactus_lite.core.paths import MC_DIR
from cactus_lite.core.platform_utils import junction, no_window_flags, temp_dir
from cactus_lite.mods import catalog

MOD_EXTENSIONS = (".jar", ".zip")


def mods_dir(version, loader, mc_dir=MC_DIR):
    """Forge/NeoForge on 1.13+ read mods from the per-version folder."""
    if loader in ("forge", "neoforge") and version:
        m = re.match(r"(\d+)\.(\d+)", version)
        if m and (int(m.group(1)) > 1 or int(m.group(2)) >= 13):
            return os.path.join(mc_dir, "versions", version, "mods")
    return os.path.join(mc_dir, "mods")


def list_mods(directory):
    try:
        return sorted((f for f in os.listdir(directory)
                       if os.path.isfile(os.path.join(directory, f))
                       and f.lower().endswith(MOD_EXTENSIONS)), key=str.lower)
    except OSError:
        return []


def remove_mod(directory, name):
    os.remove(os.path.join(directory, name))


def copy_local_mod(src, directory):
    """Copy a user-provided jar into the mods folder. Returns the destination."""
    os.makedirs(directory, exist_ok=True)
    dst = os.path.join(directory, os.path.basename(src))
    shutil.copy2(src, dst)
    return dst


def target_path(mod_id, info, directory):
    """OptiFine installs as a patched *_MOD.jar; everything else keeps its name."""
    if mod_id == "optifine":
        edition = info["filename"][len("OptiFine_"):-len(".jar")]
        return os.path.join(directory, f"OptiFine_{edition}_MOD.jar")
    return os.path.join(directory, info["filename"])


def install_from_catalog(mod_id, series, info, dst, java=None, on_progress=None,
                         on_stage=None, mc_dir=MC_DIR):
    """Download (and for OptiFine, patch) a catalog mod into place."""
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if mod_id == "optifine":
        _install_optifine(series, info, dst, java, on_progress, on_stage, mc_dir)
        return dst
    tmp = os.path.join(os.path.dirname(dst), f".download_{uuid.uuid4().hex[:8]}.part")
    try:
        download(info["url"], tmp, total=info.get("size"), on_progress=on_progress)
        os.replace(tmp, dst)
    finally:
        _quiet_remove(tmp)
    return dst


def _quiet_remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _install_optifine(series, info, dst, java, on_progress, on_stage, mc_dir):
    direct_url = catalog.resolve_optifine_download(info["url"])
    installer = os.path.join(temp_dir(mc_dir), f"of_{uuid.uuid4().hex[:8]}.jar")
    try:
        download(direct_url, installer, on_progress=on_progress)
        if on_stage:
            on_stage("УСТАНОВКА")
        _run_optifine_installer(series, info, installer, dst, java, mc_dir)
    finally:
        _quiet_remove(installer)


def _run_optifine_installer(series, info, installer_jar, dst, java, mc_dir):
    """Run OptiFine's own installer in a sandbox, then extract the patched jar.

    The installer insists on a real .minecraft directory and writes
    launcher_profiles.json, so it gets a temporary APPDATA with a junction to the
    real game folder, and the profiles file is restored afterwards.
    """
    if not java:
        raise RuntimeError("Не найдена Java для установщика OptiFine")
    base_jar = os.path.join(mc_dir, "versions", series, f"{series}.jar")
    if not os.path.isfile(base_jar):
        raise RuntimeError(f"Сначала установите и запустите версию {series}")

    edition = info["filename"][len("OptiFine_"):-len(".jar")]
    profiles = os.path.join(mc_dir, "launcher_profiles.json")
    created = not os.path.isfile(profiles)
    backup = None
    if created:
        with open(profiles, "w", encoding="utf-8") as f:
            f.write('{"profiles":{}}')
    else:
        backup = profiles + ".bak"
        try:
            shutil.copy2(profiles, backup)
        except OSError:
            backup = None

    sandbox = tempfile.mkdtemp(prefix="of_")
    link = os.path.join(sandbox, ".minecraft")
    try:
        junction(link, mc_dir)
        env = dict(os.environ)
        env["APPDATA"] = sandbox
        result = subprocess.run([java, "-cp", installer_jar, "optifine.Installer"],
                                env=env, capture_output=True, text=True, timeout=300,
                                **no_window_flags())
        patched = os.path.join(mc_dir, "libraries", "optifine", "OptiFine", edition,
                               f"OptiFine-{edition}.jar")
        if not os.path.isfile(patched):
            raise RuntimeError(f"Установщик OptiFine не сработал (код {result.returncode})")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(patched, dst)
        edition_short = "_".join(edition.split("_")[1:])
        for junk in (os.path.join(mc_dir, "versions", f"{series}-OptiFine_{edition_short}"),
                     os.path.join(mc_dir, "libraries", "optifine")):
            shutil.rmtree(junk, ignore_errors=True)
    finally:
        try:
            os.rmdir(link)
        except OSError:
            pass
        shutil.rmtree(sandbox, ignore_errors=True)
        if backup and os.path.isfile(backup):
            try:
                shutil.copy2(backup, profiles)
                os.remove(backup)
            except OSError:
                pass
        elif created:
            _quiet_remove(profiles)


def install_from_search(mod, version, directory, on_progress=None):
    """Resolve the best file for `version` from Modrinth and download it."""
    versions = catalog.fetch_modrinth_project_versions(mod["project"])
    series = catalog.series_of(version)
    info = versions.get(series)
    if not info:
        keys = sorted(versions, key=catalog.version_sort_key, reverse=True)
        info = versions.get(keys[0]) if keys else None
    if not info:
        raise RuntimeError("Нет подходящей версии для этого мода.")
    os.makedirs(directory, exist_ok=True)
    dst = os.path.join(directory, info["filename"])
    tmp = os.path.join(directory, f".download_{uuid.uuid4().hex[:8]}.part")
    try:
        download(info["url"], tmp, total=info.get("size"), on_progress=on_progress)
        os.replace(tmp, dst)
    finally:
        _quiet_remove(tmp)
    return dst
