"""Persisted launcher settings."""

from cactus_lite.core.paths import SETTINGS_PATH
from cactus_lite.core.storage import read_json, write_json

DEFAULTS = {
    "nick": "",
    "version": "",
    "ram": None,
    "loader": "none",
}


class Settings:
    """Dict-backed settings with defaults and a single save path."""

    def __init__(self, path=SETTINGS_PATH):
        self.path = path
        self._data = dict(DEFAULTS)
        loaded = read_json(path)
        if isinstance(loaded, dict):
            self._data.update({k: v for k, v in loaded.items() if k in DEFAULTS})

    def get(self, key, default=None):
        value = self._data.get(key, DEFAULTS.get(key, default))
        return default if value is None and default is not None else value

    def __getitem__(self, key):
        return self._data.get(key, DEFAULTS.get(key))

    def __setitem__(self, key, value):
        self._data[key] = value

    def update(self, **values):
        self._data.update(values)
        return self.save()

    def save(self):
        return write_json(self.path, self._data)

    def reset(self):
        self._data = dict(DEFAULTS)
        return write_json(self.path, self._data)
