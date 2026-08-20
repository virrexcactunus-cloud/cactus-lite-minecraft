"""Modal dialog base: centered, transient, dark themed."""

import wx

from cactus_lite.ui.theme import BG


class Dialog(wx.Dialog):
    """Base for the launcher's own dialogs. Subclasses implement `build`."""

    title = ""
    size = (420, 330)

    def __init__(self, app):
        super().__init__(app.frame, title=self.title, size=wx.Size(*self.size),
                        style=wx.DEFAULT_DIALOG_STYLE)
        self.app = app
        self._alive = True
        self.SetBackgroundColour(wx.Colour(BG))
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(self.sizer)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char)
        self.Bind(wx.EVT_CLOSE, lambda e: self.close())

    def show(self):
        self.build()
        self.Layout()
        self.CentreOnParent()
        self.Show()
        return self

    def build(self):
        raise NotImplementedError

    def close(self):
        if self._alive:
            self._alive = False
            self.Destroy()

    def alive(self):
        return self._alive and bool(self)

    def _on_char(self, event):
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.close()
            return
        event.Skip()
