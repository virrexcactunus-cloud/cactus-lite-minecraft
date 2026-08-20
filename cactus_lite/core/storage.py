"""Small JSON helpers used for settings, caches and account storage."""

import json
import os
import time


def read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, data):
    """Atomically write JSON. Returns True on success."""
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, path)
        return True
    except Exception:
        return False


def read_cache(path, ttl, key="data"):
    """Read a `{ts, <key>}` cache file, ignoring entries older than ttl seconds."""
    data = read_json(path)
    if not isinstance(data, dict):
        return None
    if time.time() - data.get("ts", 0) >= ttl:
        return None
    return data.get(key)


def write_cache(path, value, key="data"):
    return write_json(path, {"ts": time.time(), key: value})
