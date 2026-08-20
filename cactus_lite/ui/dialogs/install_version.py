"""Version installation dialog."""

import wx

from cactus_lite.minecraft.versions import available_versions, sort_key
from cactus_lite.ui import theme
from cactus_lite.ui.dialogs.base import Dialog
from cactus_lite.ui.theme import BG, FG, MUTED

PAD = 18


class InstallVersionDialog(Dialog):
    title = "Установка версии"
    size = (430, 300)

    def build(self):
        self._all = []
        self._ids = []
        box = self.sizer

        box.AddSpacer(PAD)
        box.Add(theme.section_label(self, "Версия"), 0, wx.LEFT | wx.RIGHT, PAD)
        box.AddSpacer(5)
        self.combo = theme.dropdown(self)
        box.Add(self.combo, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, PAD)

        box.AddSpacer(12)
        self.only_release = wx.CheckBox(self, label="только стабильные релизы")
        self.only_release.SetValue(True)
        self.only_release.SetFont(theme.font(9))
        self.only_release.SetForegroundColour(wx.Colour(FG))
        self.only_release.SetBackgroundColour(wx.Colour(BG))
        self.only_release.Bind(wx.EVT_CHECKBOX, lambda e: self._apply_filter())
        box.Add(self.only_release, 0, wx.LEFT | wx.RIGHT, PAD)

        box.AddSpacer(10)
        self.info = theme.label(self, "Загружаю список версий...", size=9, fg=MUTED, wrap=380)
        box.Add(self.info, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, PAD)

        box.AddSpacer(16)
        self.install_btn = theme.primary_button(self, "УСТАНОВИТЬ", self._install,
                                                padding=(18, 11))
        self.install_btn.Enable(False)
        box.Add(self.install_btn, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, PAD)
        box.AddSpacer(PAD)

        self.app.run_async(available_versions, self._loaded)

    def _loaded(self, versions, error):
        if not self.alive():
            return
        if error:
            self.info.set_text(f"Ошибка загрузки: {error}")
            self.Layout()
            return
        self._all = versions
        self._apply_filter()
        self.info.set_text(f"Доступно версий: {len(versions)}")
        self.install_btn.Enable(True)
        self.Layout()

    def _apply_filter(self):
        if not self.alive():
            return
        items = [(i, t) for i, t in self._all
                 if not self.only_release.GetValue() or t == "release"]
        items.sort(key=lambda x: sort_key(x[0]), reverse=True)
        self._ids = [i for i, _t in items]
        labels = [self.app.versions.label(i, self.app.settings["loader"]) for i in self._ids]
        self.combo.set_items(labels, selection=0)

    def _install(self):
        label = self.combo.get_value()
        if not label:
            return
        index = self.combo.get_selection()
        version = self._ids[index] if 0 <= index < len(self._ids) else \
            self.app.versions.id_from_label(label)
        self.close()
        self.app.install_version(version)
