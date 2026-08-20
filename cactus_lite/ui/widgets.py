"""Reusable composite widgets: scroll area, mod tile, drop zone."""

import os

import wx

from cactus_lite.ui import theme
from cactus_lite.ui.controls import Canvas
from cactus_lite.ui.theme import ACCENT, BG, BG2, BG3, FG, MUTED

DND_AVAILABLE = True  # wxWidgets ships native file drag & drop on every platform.


class ScrollFrame(wx.ScrolledWindow):
    """A vertically scrollable container; children are added to `.sizer`."""

    def __init__(self, parent, bg=BG):
        super().__init__(parent, style=wx.VSCROLL | wx.BORDER_NONE)
        self.SetBackgroundColour(wx.Colour(bg))
        self.SetScrollRate(0, 14)
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(self.sizer)

    def relayout(self):
        """Recompute the virtual size after children were added or removed."""
        self.Layout()
        self.FitInside()


class Card(Canvas):
    """Rounded panel with a themed border; children go in `.sizer`."""

    def __init__(self, parent, bg=BG2, border=BG3, border_width=1, radius=8):
        super().__init__(parent)
        self._bg = wx.Colour(bg)
        self._border = wx.Colour(border)
        self._border_width = border_width
        self._radius = radius
        self.SetBackgroundColour(wx.Colour(parent.GetBackgroundColour()))
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(self.sizer)

    def set_border(self, colour):
        colour = wx.Colour(colour)
        if colour != self._border:
            self._border = colour
            self.Refresh()

    def inner_bg(self):
        return self._bg

    def draw(self, dc, width, height):
        dc.SetPen(wx.Pen(self._border, self._border_width))
        dc.SetBrush(wx.Brush(self._bg))
        inset = self._border_width
        dc.DrawRoundedRectangle(inset // 2, inset // 2, width - inset, height - inset,
                                self._radius)


class Avatar(Canvas):
    """Mod icon, or a coloured square with the first letter as a fallback."""

    def __init__(self, parent, bitmap, name, colour=ACCENT, size=44, bg=BG2):
        super().__init__(parent, size=wx.Size(size, size))
        self._bitmap = bitmap
        self._name = name or "?"
        self._colour = wx.Colour(colour)
        self._size = size
        self.SetBackgroundColour(wx.Colour(bg))
        self.SetMinSize(wx.Size(size, size))

    def draw(self, dc, width, height):
        if self._bitmap is not None:
            dc.DrawBitmap(self._bitmap, (width - self._bitmap.GetWidth()) // 2,
                          (height - self._bitmap.GetHeight()) // 2, True)
            return
        dc.SetPen(wx.Pen(self._colour))
        dc.SetBrush(wx.Brush(self._colour))
        dc.DrawRoundedRectangle(1, 1, width - 2, height - 2, 8)
        dc.SetFont(theme.font(16, "bold"))
        dc.SetTextForeground(wx.Colour("#ffffff"))
        letter = self._name[:1].upper()
        text_w, text_h = dc.GetTextExtent(letter)
        dc.DrawText(letter, (width - text_w) // 2, (height - text_h) // 2)


class ModTile(Card):
    """Catalog/search tile: avatar, name, note, version picker and action button."""

    WIDTH = 190
    HEIGHT = 186

    def __init__(self, parent, mod, bitmap, on_install, values=(), selected=None):
        super().__init__(parent, bg=BG2, border=BG3)
        self.mod = mod
        self.SetMinSize(wx.Size(self.WIDTH, self.HEIGHT))

        avatar = Avatar(self, bitmap, mod["name"], mod.get("color", ACCENT), bg=BG2)
        name = theme.label(self, mod["name"][:18], size=10, weight="bold", fg=FG, bg=BG2)
        note = theme.label(self, mod.get("note") or " ", size=7, fg=MUTED, bg=BG2, wrap=160)

        bottom = wx.BoxSizer(wx.HORIZONTAL)
        self.combo = theme.dropdown(self, values, size=8, min_width=86, height=26)
        self.combo.SetBackgroundColour(wx.Colour(BG2))
        if values:
            self.combo.set_value(selected or values[0])
        else:
            self.combo.Enable(False)
        self.button = theme.primary_button(self, "УСТАНОВИТЬ", on_install, size=8,
                                           min_width=82, padding=(6, 6))
        self.button.SetBackgroundColour(wx.Colour(BG2))
        bottom.Add(self.combo, 1, wx.ALIGN_CENTER_VERTICAL)
        bottom.AddSpacer(6)
        bottom.Add(self.button, 0, wx.ALIGN_CENTER_VERTICAL)

        self.sizer.AddSpacer(12)
        self.sizer.Add(avatar, 0, wx.ALIGN_CENTER)
        self.sizer.AddSpacer(6)
        self.sizer.Add(name, 0, wx.ALIGN_CENTER)
        self.sizer.AddSpacer(2)
        self.sizer.Add(note, 0, wx.ALIGN_CENTER | wx.LEFT | wx.RIGHT, 10)
        self.sizer.AddStretchSpacer()
        self.sizer.Add(bottom, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        self.Layout()

    def selected_label(self):
        return self.combo.get_value()

    def busy(self, text="..."):
        self.button.Enable(False)
        self.button.set_label(text)

    def progress(self, text):
        self.button.set_label(text)

    def done(self, command):
        self.button.set_command(command)
        self.button.set_label("ГОТОВО")
        self.button.Enable(True)

    def reset(self):
        self.button.set_label("УСТАНОВИТЬ")
        self.button.Enable(True)


class _FileDrop(wx.FileDropTarget):
    def __init__(self, zone):
        super().__init__()
        self.zone = zone

    def OnDragOver(self, x, y, default):  # noqa: N802 - wx naming
        self.zone.highlight(True)
        return default

    def OnLeave(self):  # noqa: N802 - wx naming
        self.zone.highlight(False)

    def OnDropFiles(self, _x, _y, filenames):  # noqa: N802 - wx naming
        self.zone.highlight(False)
        paths = [p for p in filenames if os.path.exists(p)]
        if paths:
            self.zone.on_files(paths)
        return bool(paths)


class _FileGlyph(Canvas):
    """The little document icon drawn inside the drop zone."""

    def __init__(self, parent, bg=BG2):
        super().__init__(parent, size=wx.Size(64, 78))
        self.SetBackgroundColour(wx.Colour(bg))
        self.SetMinSize(wx.Size(64, 78))

    def draw(self, dc, _width, _height):
        dc.SetPen(wx.Pen(wx.Colour(FG), 2))
        dc.SetBrush(wx.Brush(wx.Colour(BG3)))
        dc.DrawRoundedRectangle(14, 8, 36, 58, 4)
        dc.DrawPolygon([wx.Point(32, 8), wx.Point(50, 8), wx.Point(50, 26)])
        dc.SetPen(wx.Pen(wx.Colour(MUTED), 2))
        for y, x2 in ((38, 44), (46, 44), (54, 36)):
            dc.DrawLine(20, y, x2, y)


class DropZone(Card):
    """Click-or-drag target for adding mod files manually."""

    def __init__(self, parent, on_files):
        super().__init__(parent, bg=BG2, border=BG3, border_width=2)
        self.on_files = on_files

        glyph = _FileGlyph(self)
        title = theme.label(self, "Здесь вы можете загрузить свои файлы", size=12, fg=FG, bg=BG2)
        self.hint = theme.label(self, "Перетащите сюда файл мода (например, .jar)", size=9,
                                fg=MUTED, bg=BG2)
        self.status = theme.label(self, "", size=9, fg=ACCENT, bg=BG2)
        button = theme.primary_button(self, "ЗАГРУЗИТЬ ВРУЧНУЮ", lambda: on_files(None), size=9)
        button.SetBackgroundColour(wx.Colour(BG2))

        self.sizer.AddSpacer(22)
        self.sizer.Add(glyph, 0, wx.ALIGN_CENTER)
        self.sizer.AddSpacer(8)
        self.sizer.Add(title, 0, wx.ALIGN_CENTER)
        self.sizer.AddSpacer(4)
        self.sizer.Add(self.hint, 0, wx.ALIGN_CENTER)
        self.sizer.AddSpacer(10)
        self.sizer.Add(self.status, 0, wx.ALIGN_CENTER)
        self.sizer.AddSpacer(10)
        self.sizer.Add(button, 0, wx.ALIGN_CENTER)
        self.sizer.AddSpacer(18)

        for widget in (self, glyph, title, self.hint):
            widget.SetCursor(wx.Cursor(wx.CURSOR_HAND))
            widget.Bind(wx.EVT_LEFT_UP, lambda e: on_files(None))
        self.SetDropTarget(_FileDrop(self))

    def set_status(self, text):
        self.status.SetLabel(text or "")
        self.Layout()

    def set_hint(self, text):
        self.hint.SetLabel(text or "")
        self.Layout()

    def highlight(self, on):
        self.set_border(ACCENT if on else BG3)


class Console(wx.TextCtrl):
    """Read-only log view that keeps the newest line visible."""

    def __init__(self, parent, height=150):
        super().__init__(parent, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_DONTWRAP
                         | wx.BORDER_NONE)
        self.SetFont(theme.mono_font(8))
        self.SetBackgroundColour(wx.Colour(theme.CONSOLE_BG))
        self.SetForegroundColour(wx.Colour(theme.CONSOLE_FG))
        self.SetMinSize(wx.Size(-1, height))

    def append(self, line):
        self.AppendText(line + "\n")
