"""Shared page base class."""

import wx

from cactus_lite.ui.theme import BG


class Page(wx.Panel):
    """A sidebar page. `app` is the controller (cactus_lite.ui.app.App)."""

    name = ""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.SetBackgroundColour(wx.Colour(BG))
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(self.sizer)
        self.build()
        self.Layout()

    def build(self):
        raise NotImplementedError

    def on_show(self):
        """Called every time the page becomes visible."""
