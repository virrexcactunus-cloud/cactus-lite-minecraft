"""Owner-drawn base controls.

wxWidgets does not honour custom background colours on native buttons, choices
and gauges (notably on macOS), so the dark theme is painted by hand here.
Everything in this module is purely visual and knows nothing about the launcher.
"""

import wx

RADIUS = 6


def blend(a, b, t):
    """Mix two colours; t=0 returns `a`, t=1 returns `b`."""
    a, b = wx.Colour(a), wx.Colour(b)
    return wx.Colour(*(int(round(x + (y - x) * t))
                       for x, y in ((a.Red(), b.Red()), (a.Green(), b.Green()),
                                    (a.Blue(), b.Blue()))))


def parent_bg(window):
    parent = window.GetParent()
    return parent.GetBackgroundColour() if parent else wx.Colour("#000000")


class Canvas(wx.Window):
    """A flicker-free window that paints itself in `draw(dc, width, height)`."""

    def __init__(self, parent, size=wx.DefaultSize):
        super().__init__(parent, size=size, style=wx.BORDER_NONE | wx.TRANSPARENT_WINDOW)
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetBackgroundColour(parent_bg(self))
        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_SIZE, lambda e: (self.Refresh(), e.Skip()))

    def _on_paint(self, _event):
        # GCDC needs a concrete DC type; wx.AutoBufferedPaintDC is not accepted.
        # Cocoa/GTK already double-buffer, so only MSW needs an explicit buffer.
        dc = wx.BufferedPaintDC(self) if wx.Platform == "__WXMSW__" else wx.PaintDC(self)
        dc.SetBackground(wx.Brush(self.GetBackgroundColour()))
        dc.Clear()
        width, height = self.GetClientSize()
        if width > 0 and height > 0:
            self.draw(wx.GCDC(dc), width, height)

    def draw(self, dc, width, height):
        """Override me."""


class FlatButton(Canvas):
    """Rounded, flat, fully themed button with hover and disabled states."""

    def __init__(self, parent, label, on_click=None, *, bg, fg, hover_bg=None, hover_fg=None,
                 font=None, padding=(16, 9), min_width=0, align=wx.ALIGN_CENTER, radius=RADIUS):
        super().__init__(parent)
        self._label = label
        self._on_click = on_click
        self._bg = wx.Colour(bg)
        self._fg = wx.Colour(fg)
        self._hover_bg = wx.Colour(hover_bg) if hover_bg else self._bg
        self._hover_fg = wx.Colour(hover_fg) if hover_fg else self._fg
        self._padding = padding
        self._min_width = min_width
        self._align = align
        self._radius = radius
        self._hover = False
        self._pressed = False
        if font is not None:
            self.SetFont(font)
        self.SetCursor(wx.Cursor(wx.CURSOR_HAND))
        self.Bind(wx.EVT_ENTER_WINDOW, self._on_enter)
        self.Bind(wx.EVT_LEAVE_WINDOW, self._on_leave)
        self.Bind(wx.EVT_LEFT_DOWN, self._on_down)
        self.Bind(wx.EVT_LEFT_UP, self._on_up)
        self.InvalidateBestSize()

    # --- public API ---------------------------------------------------------

    def set_label(self, label):
        if label != self._label:
            self._label = label
            self.InvalidateBestSize()
            self.Refresh()

    def get_label(self):
        return self._label

    def set_command(self, on_click):
        self._on_click = on_click

    def set_colours(self, bg=None, fg=None, hover_bg=None, hover_fg=None):
        if bg is not None:
            self._bg = wx.Colour(bg)
        if fg is not None:
            self._fg = wx.Colour(fg)
        if hover_bg is not None:
            self._hover_bg = wx.Colour(hover_bg)
        if hover_fg is not None:
            self._hover_fg = wx.Colour(hover_fg)
        self.Refresh()

    def Enable(self, enable=True):  # noqa: N802 - wx naming
        changed = super().Enable(enable)
        self._hover = False
        self.SetCursor(wx.Cursor(wx.CURSOR_HAND if enable else wx.CURSOR_ARROW))
        self.Refresh()
        return changed

    # --- painting ----------------------------------------------------------

    def DoGetBestSize(self):  # noqa: N802 - wx naming
        dc = wx.ClientDC(self)
        dc.SetFont(self.GetFont())
        text_w, text_h = dc.GetTextExtent(self._label or " ")
        pad_x, pad_y = self._padding
        return wx.Size(max(text_w + pad_x * 2, self._min_width), text_h + pad_y * 2)

    def draw(self, dc, width, height):
        enabled = self.IsEnabled()
        base = self.GetBackgroundColour()
        bg = self._hover_bg if (self._hover and enabled) else self._bg
        fg = self._hover_fg if (self._hover and enabled) else self._fg
        if not enabled:
            bg, fg = blend(bg, base, 0.55), blend(fg, base, 0.5)
        if self._pressed and enabled:
            bg = blend(bg, wx.Colour("#000000"), 0.12)

        if bg != base:
            dc.SetPen(wx.Pen(bg))
            dc.SetBrush(wx.Brush(bg))
            dc.DrawRoundedRectangle(0, 0, width, height, self._radius)

        dc.SetFont(self.GetFont())
        dc.SetTextForeground(fg)
        text_w, text_h = dc.GetTextExtent(self._label or "")
        x = (width - text_w) // 2
        if self._align == wx.ALIGN_LEFT:
            x = self._padding[0]
        dc.DrawText(self._label or "", x, (height - text_h) // 2)

    # --- events ------------------------------------------------------------

    def _on_enter(self, _event):
        if self.IsEnabled():
            self._hover = True
            self.Refresh()

    def _on_leave(self, _event):
        self._hover = self._pressed = False
        self.Refresh()

    def _on_down(self, _event):
        if self.IsEnabled():
            self._pressed = True
            self.Refresh()

    def _on_up(self, _event):
        pressed, self._pressed = self._pressed, False
        self.Refresh()
        if pressed and self.IsEnabled() and self._on_click is not None:
            self._on_click()


class _ListPopup(wx.PopupTransientWindow):
    """Owner-drawn dropdown list; only visible rows are painted.

    The owning Dropdown opens this on mouse-UP, so the click that opened the list
    is already finished and the list stays up until the next click.
    """

    ROW = 26
    MAX_HEIGHT = 320

    def __init__(self, owner, items, selection, on_pick, *, bg, fg, accent, border, font):
        super().__init__(owner, wx.BORDER_NONE)
        self._items = list(items)
        self._selection = selection
        self._on_pick = on_pick
        self._bg, self._fg = wx.Colour(bg), wx.Colour(fg)
        self._accent, self._border = wx.Colour(accent), wx.Colour(border)
        self._hover = -1
        self._offset = 0
        self.SetFont(font)
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetBackgroundColour(self._bg)
        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_MOTION, self._on_motion)
        self.Bind(wx.EVT_LEFT_UP, self._on_click)
        self.Bind(wx.EVT_MOUSEWHEEL, self._on_wheel)
        self.Bind(wx.EVT_LEAVE_WINDOW, self._on_leave)

    def popup_at(self, screen_pos, width):
        rows = max(len(self._items), 1)
        height = min(rows * self.ROW + 8, self.MAX_HEIGHT)
        self.SetSize(wx.Size(width, height))
        visible = max((height - 8) // self.ROW, 1)
        self._offset = max(0, min(self._selection - visible // 2, rows - visible))
        display = wx.Display(max(wx.Display.GetFromPoint(screen_pos), 0)).GetClientArea()
        x = min(max(screen_pos.x, display.x), display.x + display.width - width)
        y = screen_pos.y
        if y + height > display.y + display.height:
            y = max(display.y, y - height - self.GetParent().GetSize().height)
        self.Position(wx.Point(x, y), (0, 0))
        self.Popup()

    def _visible_rows(self):
        _, height = self.GetClientSize()
        return max((height - 8) // self.ROW, 1)

    def _row_at(self, y):
        index = (y - 4) // self.ROW + self._offset
        return index if 0 <= index < len(self._items) and y >= 4 else -1

    def _on_paint(self, _event):
        dc = wx.BufferedPaintDC(self) if wx.Platform == "__WXMSW__" else wx.PaintDC(self)
        width, height = self.GetClientSize()
        dc.SetBackground(wx.Brush(self._bg))
        dc.Clear()
        gc = wx.GCDC(dc)
        gc.SetPen(wx.Pen(self._border))
        gc.SetBrush(wx.Brush(self._bg))
        gc.DrawRoundedRectangle(0, 0, width - 1, height - 1, RADIUS)
        gc.SetFont(self.GetFont())

        for row in range(self._offset, min(self._offset + self._visible_rows(), len(self._items))):
            y = 4 + (row - self._offset) * self.ROW
            if row == self._hover:
                highlight = blend(self._bg, self._fg, 0.12)
                gc.SetPen(wx.Pen(highlight))
                gc.SetBrush(wx.Brush(highlight))
                gc.DrawRoundedRectangle(4, y, width - 9, self.ROW - 2, 4)
            gc.SetTextForeground(self._accent if row == self._selection else self._fg)
            text = self._items[row]
            _, text_h = gc.GetTextExtent(text)
            gc.DrawText(text, 10, y + (self.ROW - text_h) // 2 - 1)

        if len(self._items) > self._visible_rows():
            track = height - 8
            thumb = max(int(track * self._visible_rows() / len(self._items)), 16)
            top = 4 + int((track - thumb) * self._offset /
                          max(len(self._items) - self._visible_rows(), 1))
            gc.SetPen(wx.Pen(self._border))
            gc.SetBrush(wx.Brush(blend(self._bg, self._fg, 0.25)))
            gc.DrawRoundedRectangle(width - 6, top, 3, thumb, 1)

    def _on_motion(self, event):
        row = self._row_at(event.GetY())
        if row != self._hover:
            self._hover = row
            self.Refresh()

    def _on_leave(self, _event):
        if self._hover != -1:
            self._hover = -1
            self.Refresh()

    def _on_wheel(self, event):
        step = -1 if event.GetWheelRotation() > 0 else 1
        limit = max(len(self._items) - self._visible_rows(), 0)
        offset = max(0, min(self._offset + step * 3, limit))
        if offset != self._offset:
            self._offset = offset
            self.Refresh()

    def _on_click(self, event):
        row = self._row_at(event.GetY())
        self.Dismiss()
        if row >= 0:
            self._on_pick(row)


class Dropdown(Canvas):
    """Read-only combobox: a painted field plus an owner-drawn popup list."""

    def __init__(self, parent, items=(), on_select=None, *, bg, fg, border, accent, muted,
                 font=None, min_width=0, height=None):
        super().__init__(parent)
        self._items = list(items)
        self._selection = 0 if self._items else -1
        self._text = self._items[0] if self._items else ""
        self._on_select = on_select
        self._bg, self._fg = wx.Colour(bg), wx.Colour(fg)
        self._border, self._accent = wx.Colour(border), wx.Colour(accent)
        self._muted = wx.Colour(muted)
        self._min_width = min_width
        self._height = height
        self._hover = False
        self._open = False
        self._pressed = False
        self._popup = None
        if font is not None:
            self.SetFont(font)
        self.SetCursor(wx.Cursor(wx.CURSOR_HAND))
        # Open on mouse-UP, not down: wx.PopupTransientWindow dismisses itself on the
        # first mouse-up it sees, so opening on down made a plain click open and
        # instantly close the list — the user had to hold the button to keep it up.
        self.Bind(wx.EVT_LEFT_DOWN, lambda e: self._set_pressed(True))
        self.Bind(wx.EVT_LEFT_UP, self._on_left_up)
        self.Bind(wx.EVT_ENTER_WINDOW, lambda e: self._set_hover(True))
        self.Bind(wx.EVT_LEAVE_WINDOW, self._on_leave)

    # --- public API ---------------------------------------------------------

    def set_items(self, items, selection=None, value=None):
        self._items = list(items)
        if value is not None:
            self.set_value(value)
            return
        if selection is None:
            selection = self._selection
        self.set_selection(selection if 0 <= selection < len(self._items) else
                           (0 if self._items else -1))

    def get_items(self):
        return list(self._items)

    def get_selection(self):
        return self._selection

    def set_selection(self, index, notify=False):
        if 0 <= index < len(self._items):
            self._selection, self._text = index, self._items[index]
        else:
            self._selection, self._text = -1, ""
        self.Refresh()
        if notify and self._on_select is not None:
            self._on_select(self._selection)

    def get_value(self):
        return self._text

    def set_value(self, text):
        """Select the matching item, or just display `text` when it is not listed."""
        text = text or ""
        if text in self._items:
            self.set_selection(self._items.index(text))
        else:
            self._selection, self._text = -1, text
            self.Refresh()

    def Enable(self, enable=True):  # noqa: N802 - wx naming
        changed = super().Enable(enable)
        self.SetCursor(wx.Cursor(wx.CURSOR_HAND if enable else wx.CURSOR_ARROW))
        self.Refresh()
        return changed

    # --- painting ----------------------------------------------------------

    def DoGetBestSize(self):  # noqa: N802 - wx naming
        dc = wx.ClientDC(self)
        dc.SetFont(self.GetFont())
        _, text_h = dc.GetTextExtent("Wg")
        return wx.Size(max(self._min_width, 120), self._height or text_h + 16)

    def draw(self, dc, width, height):
        enabled = self.IsEnabled()
        bg = self._bg if enabled else blend(self._bg, self.GetBackgroundColour(), 0.5)
        border = self._accent if (self._open or self._hover) and enabled else self._border
        dc.SetPen(wx.Pen(border))
        dc.SetBrush(wx.Brush(bg))
        dc.DrawRoundedRectangle(0, 0, width - 1, height - 1, RADIUS)

        dc.SetFont(self.GetFont())
        dc.SetTextForeground(self._fg if enabled else self._muted)
        text = self._text or ""
        text_w, text_h = dc.GetTextExtent(text)
        limit = width - 34
        while text and text_w > limit:
            text = text[:-1]
            text_w, text_h = dc.GetTextExtent(text + "…")
        dc.DrawText(text + ("…" if text != (self._text or "") else ""),
                    10, (height - text_h) // 2)

        cx, cy = width - 16, height // 2
        dc.SetPen(wx.Pen(self._muted))
        dc.SetBrush(wx.Brush(self._muted))
        dc.DrawPolygon([wx.Point(cx - 4, cy - 2), wx.Point(cx + 4, cy - 2), wx.Point(cx, cy + 3)])

    # --- popup -------------------------------------------------------------

    def _set_hover(self, hover):
        if self.IsEnabled():
            self._hover = hover
            self.Refresh()

    def _set_pressed(self, pressed):
        if self.IsEnabled():
            self._pressed = pressed

    def _on_leave(self, _event):
        self._pressed = False
        self._set_hover(False)

    def _on_left_up(self, _event):
        """Toggle the list on release, so a normal click opens it and it stays open."""
        pressed, self._pressed = self._pressed, False
        if not pressed or not self.IsEnabled():
            return
        if self._open:
            self._close_popup()
        else:
            self._show_popup()

    def _show_popup(self):
        if not self.IsEnabled() or not self._items or self._open:
            return
        popup = _ListPopup(self, self._items, self._selection, self._pick,
                           bg=self._bg, fg=self._fg, accent=self._accent,
                           border=self._border, font=self.GetFont())
        popup.Bind(wx.EVT_SHOW, self._on_popup_show)
        self._popup = popup
        self._open = True
        self.Refresh()
        width, height = self.GetSize()
        popup.popup_at(self.ClientToScreen(wx.Point(0, height + 2)), width)

    def _close_popup(self):
        popup, self._popup = getattr(self, "_popup", None), None
        self._open = False
        self.Refresh()
        if popup:
            popup.Dismiss()

    def _on_popup_show(self, event):
        if not event.IsShown():
            self._popup = None
            self._open = False
            self.Refresh()
        event.Skip()

    def _pick(self, index):
        if index != self._selection:
            self.set_selection(index, notify=True)
        else:
            self.set_selection(index)


class ProgressBar(Canvas):
    """Slim determinate progress bar (0..100)."""

    def __init__(self, parent, *, trough, fill, height=8):
        super().__init__(parent, size=wx.Size(-1, height))
        self._trough, self._fill = wx.Colour(trough), wx.Colour(fill)
        self._value = 0
        self.SetMinSize(wx.Size(-1, height))

    def set_value(self, value):
        value = max(0, min(int(value), 100))
        if value != self._value:
            self._value = value
            self.Refresh()

    def draw(self, dc, width, height):
        radius = height / 2
        dc.SetPen(wx.Pen(self._trough))
        dc.SetBrush(wx.Brush(self._trough))
        dc.DrawRoundedRectangle(0, 0, width, height, radius)
        filled = int(width * self._value / 100)
        if filled > 1:
            dc.SetPen(wx.Pen(self._fill))
            dc.SetBrush(wx.Brush(self._fill))
            dc.DrawRoundedRectangle(0, 0, filled, height, radius)


class WrapText(wx.StaticText):
    """StaticText that keeps its raw text and re-wraps on demand.

    `wrap=WrapText.AUTO` re-wraps to the width the sizer hands the label, so long
    status lines and hints follow the window instead of a fixed pixel budget. In
    AUTO mode the label reports a 1px minimum width, otherwise its unwrapped text
    extent would drive the whole page's minimum size.
    """

    AUTO = -1

    def __init__(self, parent, text="", wrap=400, **kwargs):
        super().__init__(parent, label="", **kwargs)
        self._wrap = wrap
        self._text = ""
        self._wrapped_at = 0
        self._wrapping = False
        if wrap == self.AUTO:
            self.Bind(wx.EVT_SIZE, self._on_size)
        self.set_text(text)

    def set_text(self, text):
        self._text = text or ""
        self._rewrap(self._wrapped_at if self._wrap == self.AUTO else self._wrap)

    def get_text(self):
        return self._text

    def set_wrap(self, wrap):
        self._wrap = wrap
        self._rewrap(0 if wrap == self.AUTO else wrap)

    def _rewrap(self, limit):
        """Re-wrap to `limit` px. Guarded: Wrap() resizes us and re-enters EVT_SIZE."""
        if self._wrapping:
            return
        self._wrapping = True
        try:
            self._wrapped_at = limit
            self.SetLabel(self._text)
            if limit > 0:
                self.Wrap(limit)
            if self._wrap == self.AUTO:
                # Height must follow the new line count; width must not pin the page.
                self.SetMinSize(wx.Size(1, -1))
                self.InvalidateBestSize()
                self.SetMinSize(wx.Size(1, self.GetBestSize().height))
        finally:
            self._wrapping = False

    def _on_size(self, event):
        event.Skip()
        if self._wrapping:
            return
        width = event.GetSize().width
        if width > 20 and width != self._wrapped_at:
            self._rewrap(width)
            parent = self.GetParent()
            if parent is not None:
                parent.Layout()
