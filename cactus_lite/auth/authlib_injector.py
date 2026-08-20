"""authlib-injector: makes the game talk to Ely.by instead of Mojang.

The jar is fetched once into ~/.mcl/cactus and reused; the SHA-256 published in
the release metadata is verified before the file is accepted.
"""

import hashlib
import os

from cactus_lite.core.net import download, get_json
from cactus_lite.core.paths import LIB_DIR

LATEST_URL = "https://authlib-injector.yushi.moe/artifact/latest.json"
ELY_API = "ely.by"


def _jar_path(version):
    return os.path.join(LIB_DIR, f"authlib-injector-{version}.jar")


def _existing_jar():
    try:
        jars = sorted(f for f in os.listdir(LIB_DIR)
                      if f.startswith("authlib-injector-") and f.endswith(".jar"))
    except OSError:
        return None
    return os.path.join(LIB_DIR, jars[-1]) if jars else None


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_jar(on_progress=None):
    """Return a local path to authlib-injector.jar, downloading it if needed."""
    os.makedirs(LIB_DIR, exist_ok=True)
    try:
        meta = get_json(LATEST_URL, timeout=15)
    except Exception:
        jar = _existing_jar()
        if jar:
            return jar
        raise RuntimeError("Не удалось скачать authlib-injector — нет соединения.")

    version = meta.get("version") or "latest"
    url = meta.get("download_url")
    expected = ((meta.get("checksums") or {}).get("sha256") or "").lower()
    path = _jar_path(version)
    if os.path.isfile(path) and (not expected or _sha256(path) == expected):
        return path
    if not url:
        raise RuntimeError("Ответ authlib-injector не содержит ссылки на файл.")

    tmp = path + ".part"
    try:
        download(url, tmp, total=None, on_progress=on_progress)
        if expected and _sha256(tmp) != expected:
            raise RuntimeError("Контрольная сумма authlib-injector не совпала.")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    return path


def jvm_argument(jar_path):
    return f"-javaagent:{jar_path}={ELY_API}"
