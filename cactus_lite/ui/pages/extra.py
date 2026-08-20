"""«Дополнительные»: game folder, resets and the mod loader selector."""

import wx

from cactus_lite.core.paths import APP_VERSION, MC_DIR
from cactus_lite.core.platform_utils import open_path
from cactus_lite.minecraft import skins
from cactus_lite.minecraft.versions import LOADER_NAMES, LOADER_UI_IDS, LOADER_UI_VALUES
from cactus_lite.ui import messages, theme
from cactus_lite.ui.pages.base import Page
from cactus_lite.ui.theme import FG, MUTED

LOADER_HINT = ("Не все версии совместимы со всеми подсистемами модов.\n"
               "Буквы рядом с версией: F — Forge, G — Fabric, N — NeoForge.\n"
               "С выбранной подсистемой несовместимые версии помечены «(недоступна)».")
RAM_HINT = ("ОЗУ определяется автоматически. Пометка «заняты» — этой памяти\n"
            "сейчас не хватает, её выбрать нельзя.")
PAD = 20


class ExtraPage(Page):
    name = "extra"

    def build(self):
        box = self.sizer
        box.AddSpacer(20)
        box.Add(theme.section_label(self, "НАСТРОЙКИ"), 0, wx.LEFT | wx.RIGHT, PAD)
        box.AddSpacer(10)

        box.Add(theme.section_label(self, "Папка игры:"), 0, wx.LEFT | wx.RIGHT, PAD)
        box.AddSpacer(4)
        box.Add(theme.label(self, MC_DIR, size=9, fg=FG, wrap=400), 0, wx.LEFT | wx.RIGHT, PAD)

        for text, command, fg in (
            ("Открыть папку игры", lambda: open_path(MC_DIR), FG),
            ("Сбросить настройки", self._reset_settings, MUTED),
            ("Сбросить скин", self._reset_skin, MUTED),
        ):
            box.AddSpacer(8)
            box.Add(theme.ghost_button(self, text, command, fg=fg, active_fg=FG), 0,
                    wx.LEFT | wx.RIGHT, PAD)

        box.AddSpacer(18)
        box.Add(theme.section_label(self, "ПОДСИСТЕМА МОДОВ"), 0, wx.LEFT | wx.RIGHT, PAD)
        box.AddSpacer(5)
        self.loader_cb = theme.dropdown(self, LOADER_UI_VALUES, self._on_loader_change,
                                        size=11, min_width=240)
        box.Add(self.loader_cb, 0, wx.LEFT | wx.RIGHT, PAD)
        self.sync_loader()

        box.AddSpacer(10)
        box.Add(theme.hint_label(self, LOADER_HINT), 0, wx.LEFT | wx.RIGHT, PAD)
        box.AddSpacer(16)
        box.Add(theme.hint_label(self, RAM_HINT), 0, wx.LEFT | wx.RIGHT, PAD)
        box.AddStretchSpacer()
        box.Add(theme.hint_label(self, f"by cactunus {APP_VERSION}", wrap=200), 0,
                wx.ALIGN_CENTER | wx.BOTTOM, 12)

    def sync_loader(self):
        loader = self.app.settings["loader"]
        index = LOADER_UI_IDS.index(loader) if loader in LOADER_UI_IDS else 0
        self.loader_cb.set_selection(index)

    def _on_loader_change(self, index):
        loader = LOADER_UI_IDS[index] if 0 <= index < len(LOADER_UI_IDS) else "none"
        self.app.set_loader(loader)
        if loader != "none":
            self.app.status(f"Подсистема: {LOADER_NAMES.get(loader, loader)}")

    def _reset_settings(self):
        if messages.ask_yes_no("Сбросить настройки?"):
            self.app.reset_settings()

    def _reset_skin(self):
        if not messages.ask_yes_no("Убрать скин?"):
            return
        skins.remove_skin()
        self.app.status("Скин убран.")
