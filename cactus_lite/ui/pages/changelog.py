"""«Изменения»: rendered version history."""

import wx

from cactus_lite.ui import theme
from cactus_lite.ui.changelog_data import CHANGELOG
from cactus_lite.ui.pages.base import Page
from cactus_lite.ui.theme import ACCENT, FG, MUTED
from cactus_lite.ui.widgets import ScrollFrame

PAD = 20


class ChangelogPage(Page):
    name = "changelog"

    def build(self):
        self.sizer.AddSpacer(20)
        self.sizer.Add(theme.section_label(self, "ИЗМЕНЕНИЯ"), 0, wx.LEFT | wx.RIGHT, PAD)
        self.sizer.AddSpacer(8)

        scroll = ScrollFrame(self)
        body = scroll.sizer
        for entry in CHANGELOG:
            body.Add(theme.label(scroll, entry["version"], size=12, weight="bold", fg=ACCENT),
                     0, wx.LEFT | wx.RIGHT | wx.TOP, PAD)
            for title, items in (("Исправления", entry["fixes"]),
                                 ("Добавлено", entry["features"])):
                if not items:
                    continue
                body.AddSpacer(4)
                body.Add(theme.label(scroll, title, size=9, weight="bold", fg=MUTED),
                         0, wx.LEFT | wx.RIGHT, PAD)
                for item in items:
                    body.AddSpacer(2)
                    body.Add(theme.label(scroll, "• " + item, size=9, fg=FG,
                                         wrap=theme.AUTO_WRAP),
                             0, wx.EXPAND | wx.LEFT | wx.RIGHT, PAD + 12)
            body.AddSpacer(12)
        scroll.relayout()
        self.sizer.Add(scroll, 1, wx.EXPAND | wx.BOTTOM, 16)
