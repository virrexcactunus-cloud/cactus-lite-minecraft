"""«Моды»: manual upload, pinned catalog, Modrinth search, installed list."""

import os

import wx

from cactus_lite.core.paths import APP_VERSION
from cactus_lite.core.platform_utils import open_path
from cactus_lite.mods import catalog, installer
from cactus_lite.ui import messages, theme
from cactus_lite.ui.pages.base import Page
from cactus_lite.ui.theme import ACCENT, BG, BG3, DANGER, DANGER_ACTIVE, FG, MUTED
from cactus_lite.ui.widgets import DropZone, ModTile, ScrollFrame

TILE_COLUMNS = 2
PAD = 20
CATALOG_HINT = ("Sodium — нужен Fabric. OptiFine — для Forge или ванили.\n"
                "Скачанный мод автоматически попадёт в папку mods.")
MANUAL_HINT = ("Мы не ручаемся за ошибки при таком переносе, если мод не подойдёт\n"
               "под подсистему модов или если он скачан не на ту версию.")
MOD_WILDCARD = "Файлы модов (*.jar;*.zip)|*.jar;*.zip|Все файлы (*.*)|*.*"


def _mb(done, total):
    if total:
        return f"{done / 1048576:.1f}/{total / 1048576:.1f} МБ"
    return f"{done / 1048576:.1f} МБ"


def _fmt_size(n):
    if not n:
        return ""
    if n >= 1024 * 1024:
        return f"{n / 1048576:.1f} МБ"
    return f"{n / 1024:.0f} КБ"


class ModsPage(Page):
    name = "mods"

    def build(self):
        self._catalog_data = {}
        self._catalog_loading = False
        self._search_loading = False
        self._catalog_tiles = {}
        self._search_tiles = {}

        self.sizer.AddSpacer(20)
        self.sizer.Add(theme.section_label(self, "МОДЫ"), 0, wx.LEFT | wx.RIGHT, PAD)
        self.sizer.AddSpacer(10)
        self._build_empty_state()
        self._build_content()
        self.sizer.Add(self.empty, 1, wx.EXPAND)
        self.sizer.Add(self.content, 1, wx.EXPAND)
        self._empty_slot = self.sizer.GetItemCount() - 2
        self._content_slot = self.sizer.GetItemCount() - 1

    # --- layout -------------------------------------------------------------

    def _build_empty_state(self):
        self.empty = theme.panel(self, BG)
        box = wx.BoxSizer(wx.VERTICAL)
        self.empty.SetSizer(box)
        box.AddSpacer(80)
        box.Add(theme.label(self.empty, "Нет подсистемы модов", size=13, weight="bold", fg=FG),
                0, wx.ALIGN_CENTER)
        box.AddSpacer(6)
        box.Add(theme.hint_label(self.empty,
                                 "Выберите Forge, Fabric или NeoForge в «Дополнительных»,\n"
                                 "чтобы устанавливать моды.", size=9), 0, wx.ALIGN_CENTER)
        box.AddSpacer(16)
        box.Add(theme.ghost_button(self.empty, "Открыть «Дополнительные»",
                                   lambda: self.app.show_page("extra")), 0, wx.ALIGN_CENTER)
        box.AddStretchSpacer()

    def _build_content(self):
        self.content = ScrollFrame(self)
        body = self.content.sizer
        host = self.content

        self.drop_zone = DropZone(host, self._add_local_mods)
        body.AddSpacer(14)
        body.Add(self.drop_zone, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, PAD)
        body.AddSpacer(12)
        body.Add(theme.hint_label(host, MANUAL_HINT), 0, wx.ALIGN_CENTER)

        body.AddSpacer(20)
        body.Add(theme.section_label(host, "КАТАЛОГ МОДОВ", fg=FG, weight="bold"), 0,
                 wx.LEFT | wx.RIGHT, PAD)
        body.AddSpacer(2)
        body.Add(theme.hint_label(host, CATALOG_HINT), 0, wx.LEFT | wx.RIGHT, PAD)
        body.AddSpacer(6)
        self.catalog_state = theme.label(host, "Каталог загружается...", size=8, fg=ACCENT)
        body.Add(self.catalog_state, 0, wx.LEFT | wx.RIGHT, PAD)
        body.AddSpacer(2)
        self.catalog_grid = wx.GridSizer(TILE_COLUMNS, 10, 10)
        body.Add(self.catalog_grid, 0, wx.LEFT | wx.RIGHT, PAD - 8)

        body.AddSpacer(20)
        body.Add(theme.section_label(host, "ПОИСК МОДОВ НА MODRINTH", fg=FG, weight="bold"), 0,
                 wx.LEFT | wx.RIGHT, PAD)
        body.AddSpacer(4)
        search_row = wx.BoxSizer(wx.HORIZONTAL)
        self.search_field = theme.entry(host, size=9, bg=BG3, on_enter=self._search)
        search_row.Add(self.search_field, 1, wx.ALIGN_CENTER_VERTICAL)
        search_row.AddSpacer(8)
        search_row.Add(theme.primary_button(host, "НАЙТИ", self._search, size=9), 0,
                       wx.ALIGN_CENTER_VERTICAL)
        body.Add(search_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, PAD)
        body.AddSpacer(6)
        self.search_state = theme.label(host, "", size=8, fg=ACCENT)
        body.Add(self.search_state, 0, wx.LEFT | wx.RIGHT, PAD)
        body.AddSpacer(2)
        self.search_grid = wx.GridSizer(TILE_COLUMNS, 10, 10)
        body.Add(self.search_grid, 0, wx.LEFT | wx.RIGHT, PAD - 8)

        body.AddSpacer(16)
        self.installed_header = theme.label(host, "УСТАНОВЛЕННЫЕ МОДЫ", size=9, weight="bold",
                                            fg=FG)
        body.Add(self.installed_header, 0, wx.LEFT | wx.RIGHT, PAD)
        body.AddSpacer(4)
        self.installed_sizer = wx.BoxSizer(wx.VERTICAL)
        body.Add(self.installed_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, PAD)
        body.AddSpacer(10)
        body.Add(theme.ghost_button(host, "Открыть папку mods", self._open_mods_dir, size=9), 0,
                 wx.LEFT | wx.RIGHT, PAD)
        body.AddSpacer(12)
        body.Add(theme.hint_label(host, f"by cactunus {APP_VERSION}"), 0, wx.ALIGN_CENTER)
        body.AddSpacer(12)

        self.drop_zone.set_hint("Перетащите сюда файл мода (например, .jar)")

    def on_show(self):
        loader_off = self.app.settings["loader"] == "none"
        self.sizer.Show(self._empty_slot, loader_off)
        self.sizer.Show(self._content_slot, not loader_off)
        self.Layout()
        if loader_off:
            return
        self.refresh_installed()
        self._load_catalog()

    def mods_dir(self):
        return installer.mods_dir(self.app.current_version(), self.app.settings["loader"])

    # --- manual upload ------------------------------------------------------

    def _add_local_mods(self, paths):
        if paths is None:
            paths = messages.open_file("Выберите моды", MOD_WILDCARD, multiple=True)
        for path in paths or []:
            self._add_local_mod(path)

    def _add_local_mod(self, src):
        name = os.path.basename(src)
        if os.path.isdir(src):
            messages.info("Перетащите файл мода, а не папку.")
            return
        if os.path.splitext(src)[1].lower() not in installer.MOD_EXTENSIONS:
            messages.warning("Моды обычно бывают файлами .jar.\nВыберите файл .jar или .zip.")
            return
        directory = self.mods_dir()
        if os.path.isfile(os.path.join(directory, name)) and not messages.ask_yes_no(
                f"«{name}» уже есть в папке модов.\nЗаменить его?"):
            return
        self.drop_zone.set_status("Мод загружается в папку...")

        def work():
            installer.copy_local_mod(src, directory)

        def done(_result, error):
            if error:
                self.drop_zone.set_status("Ошибка загрузки мода.")
                messages.error(f"Не удалось скопировать файл:\n{error}")
                return
            self.drop_zone.set_status(f"Мод загружен: {name}")
            self.app.status(f"Мод загружен: {name}")
            self.refresh_installed()

        self.app.run_async(work, done)

    # --- pinned catalog -----------------------------------------------------

    def _load_catalog(self):
        if self._catalog_loading:
            return
        cached = catalog.load_cache()
        if cached is not None:
            self._catalog_data = cached
            self._rebuild_catalog()
            return
        self._catalog_loading = True
        self._set_catalog_state("Каталог загружается...")

        def work():
            data = catalog.fetch_catalog()
            catalog.save_cache(data)
            return data

        def done(data, error):
            self._catalog_loading = False
            if error:
                self._set_catalog_state("Не удалось загрузить каталог. Проверьте интернет.")
                return
            self._catalog_data = data
            self._rebuild_catalog()

        self.app.run_async(work, done)

    def _set_catalog_state(self, text):
        self.catalog_state.SetLabel(text)
        self.content.relayout()

    def _rebuild_catalog(self):
        self.catalog_grid.Clear(delete_windows=True)
        self._catalog_tiles = {}
        current_series = catalog.series_of(self.app.current_version())
        shown = 0
        for mod in catalog.PINNED_MODS:
            versions = self._catalog_data.get(mod["id"]) or {}
            if not versions:
                continue
            keys = sorted(versions, key=catalog.version_sort_key, reverse=True)
            labels = [k + (" (рекомендовано)" if catalog.matches_series(k, current_series) else "")
                      for k in keys]
            selected = next((labels[i] for i, k in enumerate(keys)
                             if catalog.matches_series(k, current_series)), None)
            tile = ModTile(self.content, mod, self.app.images.mod_icon(mod.get("icon_key")),
                           lambda mid=mod["id"]: self._install_catalog_mod(mid),
                           values=labels, selected=selected)
            tile.keys = keys
            self.catalog_grid.Add(tile, 0, wx.ALIGN_TOP)
            self._catalog_tiles[mod["id"]] = tile
            shown += 1
        self._set_catalog_state("" if shown else "Каталог пуст или не загрузился.")

    def _install_catalog_mod(self, mod_id):
        tile = self._catalog_tiles.get(mod_id)
        if tile is None:
            return
        label = tile.selected_label()
        if not label:
            messages.info("Для этой версии мод недоступен.")
            return
        series = label.split(" (")[0]
        info = (self._catalog_data.get(mod_id) or {}).get(series)
        if not info:
            return
        dst = installer.target_path(mod_id, info, self.mods_dir())
        if os.path.isfile(dst) and not messages.ask_yes_no(
                f"«{os.path.basename(dst)}» уже есть в папке модов.\nЗаменить его?"):
            return
        tile.busy("0.0 МБ")

        def work():
            java = self.app.java_path() if mod_id == "optifine" else None
            return installer.install_from_catalog(
                mod_id, series, info, dst, java=java,
                on_progress=lambda done, total: self.app.ui(tile.progress, _mb(done, total)),
                on_stage=lambda text: self.app.ui(tile.progress, text))

        self.app.run_async(work, lambda result, error: self._tile_done(tile, error))

    # --- search -------------------------------------------------------------

    def _search(self):
        query = self.search_field.GetValue().strip()
        if not query or self._search_loading:
            return
        self._search_loading = True
        self._set_search_state("Поиск...")
        loader = self.app.settings["loader"]
        loader = loader if loader != "none" else None

        def work():
            return catalog.search_modrinth_mods(query, loader=loader)

        def done(results, error):
            self._search_loading = False
            self._rebuild_search([] if error else results)

        self.app.run_async(work, done)

    def _set_search_state(self, text):
        self.search_state.SetLabel(text)
        self.content.relayout()

    def _rebuild_search(self, results):
        self.search_grid.Clear(delete_windows=True)
        self._search_tiles = {}
        if not results:
            self._set_search_state("Ничего не найдено.")
            return
        for mod in results:
            tile = ModTile(self.content, mod,
                           self.app.images.remote_icon(mod.get("icon_url")),
                           lambda m=mod: self._install_search_mod(m))
            self.search_grid.Add(tile, 0, wx.ALIGN_TOP)
            self._search_tiles[mod["id"]] = tile
        self._set_search_state(f"Найдено: {len(results)}")

    def _install_search_mod(self, mod):
        tile = self._search_tiles.get(mod["id"])
        if tile is None:
            return
        tile.busy()
        directory = self.mods_dir()
        version = self.app.current_version()

        def work():
            return installer.install_from_search(
                mod, version, directory,
                on_progress=lambda done, total: self.app.ui(tile.progress, _mb(done, total)))

        self.app.run_async(work, lambda result, error: self._tile_done(tile, error))

    def _tile_done(self, tile, error):
        if error:
            tile.reset()
            messages.error(f"Ошибка установки:\n{error}")
            return
        tile.done(self._open_mods_dir)
        self.refresh_installed()
        self.app.status(f"Мод установлен: {tile.mod['name']}")

    # --- installed ----------------------------------------------------------

    def refresh_installed(self):
        self.installed_sizer.Clear(delete_windows=True)
        directory = self.mods_dir()
        mods = installer.list_mods(directory)
        self.installed_header.SetLabel(f"УСТАНОВЛЕННЫЕ МОДЫ ({len(mods)})")
        host = self.content
        if not mods:
            self.installed_sizer.Add(
                theme.label(host, "Пока пусто — моды появятся здесь после установки.",
                            size=9, fg=MUTED), 0, wx.TOP, 2)
            self.content.relayout()
            return
        for name in mods:
            path = os.path.join(directory, name)
            size = _fmt_size(os.path.getsize(path)) if os.path.isfile(path) else ""
            row = wx.BoxSizer(wx.HORIZONTAL)
            row.Add(theme.label(host, name + (f"  ({size})" if size else ""), size=9, fg=FG),
                    1, wx.ALIGN_CENTER_VERTICAL)
            row.Add(theme.link_button(host, "Удалить", lambda n=name: self._remove(n), size=8,
                                      fg=DANGER, active_fg=DANGER_ACTIVE), 0,
                    wx.ALIGN_CENTER_VERTICAL)
            self.installed_sizer.Add(row, 0, wx.EXPAND | wx.TOP | wx.BOTTOM, 3)
        self.content.relayout()

    def _remove(self, name):
        if not messages.ask_yes_no(f"Удалить мод «{name}»?"):
            return
        try:
            installer.remove_mod(self.mods_dir(), name)
        except Exception as e:
            messages.error(f"Не удалось удалить:\n{e}")
            return
        self.refresh_installed()
        self.app.status(f"Мод удалён: {name}")

    def _open_mods_dir(self):
        directory = self.mods_dir()
        try:
            os.makedirs(directory, exist_ok=True)
            open_path(directory)
        except Exception as e:
            messages.error(str(e))
