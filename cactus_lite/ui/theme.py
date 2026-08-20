"""Colors, fonts and widget factories — the whole visual language lives here."""

import wx

from cactus_lite.core.platform_utils import IS_MACOS, IS_WINDOWS
from cactus_lite.ui.controls import Dropdown, FlatButton, ProgressBar, WrapText

BG = "#0f1215"
BG2 = "#1a1f25"
BG3 = "#232a31"
FG = "#e8edf2"
MUTED = "#8b949e"
ACCENT = "#22c55e"
ACCENT_DARK = "#16a34a"
ON_ACCENT = "#06130b"
DANGER = "#f2b8b3"
DANGER_ACTIVE = "#ff6b61"
CONSOLE_BG = "#0a0c0e"
CONSOLE_FG = "#9fb3c8"

AUTO_WRAP = WrapText.AUTO  # wrap to whatever width the sizer hands the label

if IS_WINDOWS:
    FONT = "Segoe UI"
    MONO = "Consolas"
    _SCALE = 1.0
elif IS_MACOS:
    FONT = "Helvetica Neue"
    MONO = "Menlo"
    # Tk point sizes read small on macOS; wx uses real points.
    _SCALE = 1.15
else:
    FONT = "DejaVu Sans"
    MONO = "DejaVu Sans Mono"
    _SCALE = 1.0

_FONT_CACHE = {}


def font(size=10, weight=None, face=None, underline=False):
    """Cached wx.Font in the launcher's type scale. `weight` accepts "bold"."""
    key = (size, weight, face, underline)
    cached = _FONT_CACHE.get(key)
    if cached is None:
        cached = wx.Font(wx.FontInfo(max(int(round(size * _SCALE)), 6))
                         .FaceName(face or FONT)
                         .Bold(weight == "bold")
                         .Underlined(underline))
        _FONT_CACHE[key] = cached
    return cached


def mono_font(size=8):
    return font(size, face=MONO)


def apply_dark(window, bg=BG, fg=FG):
    window.SetBackgroundColour(wx.Colour(bg))
    window.SetForegroundColour(wx.Colour(fg))
    return window


def panel(parent, bg=BG):
    """A plain container panel in the dark palette."""
    return apply_dark(wx.Panel(parent), bg)


def label(parent, text, *, size=9, weight=None, fg=MUTED, bg=None, wrap=0):
    if wrap:
        widget = WrapText(parent, text, wrap=wrap)
    else:
        widget = wx.StaticText(parent, label=text)
    widget.SetFont(font(size, weight))
    widget.SetForegroundColour(wx.Colour(fg))
    if bg is not None:
        widget.SetBackgroundColour(wx.Colour(bg))
    return widget


def section_label(parent, text, bg=None, size=9, weight=None, fg=MUTED):
    return label(parent, text, size=size, weight=weight, fg=fg, bg=bg)


def hint_label(parent, text, bg=None, size=8, wrap=400, fg=MUTED, **_kwargs):
    return label(parent, text, size=size, fg=fg, bg=bg, wrap=wrap)


def primary_button(parent, text, command, size=12, min_width=0, padding=(18, 9)):
    return FlatButton(parent, text, command, bg=ACCENT, fg=ON_ACCENT, hover_bg=ACCENT_DARK,
                      hover_fg=ON_ACCENT, font=font(size, "bold"), padding=padding,
                      min_width=min_width)


def ghost_button(parent, text, command, bg=BG3, size=10, fg=FG, active_fg=ACCENT, min_width=0,
                 padding=(14, 7)):
    return FlatButton(parent, text, command, bg=bg, fg=fg, hover_bg=BG2, hover_fg=active_fg,
                      font=font(size), padding=padding, min_width=min_width)


def link_button(parent, text, command, size=8, fg=MUTED, active_fg=FG, bg=None):
    return FlatButton(parent, text, command, bg=bg or BG, fg=fg, hover_bg=bg or BG,
                      hover_fg=active_fg, font=font(size), padding=(2, 4))


def entry(parent, value="", size=12, bg=BG2, password=False, on_enter=None):
    style = wx.BORDER_NONE | (wx.TE_PASSWORD if password else 0)
    if on_enter is not None:
        style |= wx.TE_PROCESS_ENTER
    field = wx.TextCtrl(parent, value=value or "", style=style)
    field.SetFont(font(size))
    field.SetBackgroundColour(wx.Colour(bg))
    field.SetForegroundColour(wx.Colour(FG))
    field.SetMinSize(wx.Size(-1, field.GetBestSize().height + 10))
    if on_enter is not None:
        field.Bind(wx.EVT_TEXT_ENTER, lambda e: on_enter())
    return field


def dropdown(parent, items=(), on_select=None, size=12, min_width=0, height=None):
    return Dropdown(parent, items, on_select, bg=BG2, fg=FG, border=BG3, accent=ACCENT,
                    muted=MUTED, font=font(size), min_width=min_width, height=height)


def progress_bar(parent):
    return ProgressBar(parent, trough=BG2, fill=ACCENT)


def bitmap_view(parent, bitmap, bg=BG):
    view = wx.StaticBitmap(parent, bitmap=bitmap)
    view.SetBackgroundColour(wx.Colour(bg))
    return view
