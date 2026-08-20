"""Image loading for icons and mod avatars, with Pillow used when available."""

import base64
import io
import os

import wx

from cactus_lite.core.net import get_bytes
from cactus_lite.core.paths import MOD_ICONS_PATH
from cactus_lite.core.storage import read_json

ICON_SIZE = 44


def _load_icons():
    data = read_json(MOD_ICONS_PATH, default={})
    return data if isinstance(data, dict) else {}


def _scaled(image, size):
    if not image.IsOk():
        return None
    if image.GetWidth() != size or image.GetHeight() != size:
        image = image.Scale(size, size, wx.IMAGE_QUALITY_HIGH)
    return image.ConvertToBitmap()


def _decode(raw, size):
    """Bytes -> square wx.Bitmap. Pillow handles webp and odd formats."""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(raw)).convert("RGBA").resize((size, size), Image.LANCZOS)
        bitmap = wx.Bitmap.FromBufferRGBA(size, size, bytearray(img.tobytes()))
        return bitmap if bitmap.IsOk() else None
    except Exception:
        pass
    try:
        image = wx.Image(io.BytesIO(raw))
        return _scaled(image, size)
    except Exception:
        return None


class ImageCache:
    """Decoded bitmaps kept per (key, size) so tiles rebuild without re-decoding."""

    def __init__(self):
        self._icons = _load_icons()
        self._by_key = {}
        self._by_url = {}

    def clear(self):
        self._by_key.clear()
        self._by_url.clear()

    def mod_icon(self, icon_key, size=ICON_SIZE):
        if not icon_key:
            return None
        cache_key = (icon_key, size)
        if cache_key in self._by_key:
            return self._by_key[cache_key]
        b64 = self._icons.get(icon_key)
        bitmap = None
        if b64:
            try:
                bitmap = _decode(base64.b64decode(b64), size)
            except Exception:
                bitmap = None
        self._by_key[cache_key] = bitmap
        return bitmap

    def remote_icon(self, url, size=ICON_SIZE):
        if not url:
            return None
        cache_key = (url, size)
        if cache_key in self._by_url:
            return self._by_url[cache_key]
        try:
            bitmap = _decode(get_bytes(url, timeout=6), size)
        except Exception:
            bitmap = None
        self._by_url[cache_key] = bitmap
        return bitmap


def app_bitmap(path, size=None):
    """Load the window/logo icon as a wx.Bitmap, optionally resized."""
    if not path or not os.path.isfile(path):
        return None
    try:
        image = wx.Image(path)
        if not image.IsOk():
            return None
        if size:
            return _scaled(image, size)
        return image.ConvertToBitmap()
    except Exception:
        return None


def app_icon(path):
    """wx.Icon for the frame title bar / dock, or None."""
    bitmap = app_bitmap(path)
    if bitmap is None:
        return None
    icon = wx.Icon()
    icon.CopyFromBitmap(bitmap)
    return icon
