"""Application controller: window shell, navigation, and long-running actions."""

import threading
import time

import wx

from cactus_lite.auth import elyby
from cactus_lite.auth.accounts import AccountStore
from cactus_lite.core.paths import APP_NAME, APP_VERSION, ICON_PNG, ensure_mc_dir
from cactus_lite.core.settings import Settings
from cactus_lite.minecraft import launch
from cactus_lite.minecraft.java import find_java
from cactus_lite.minecraft.versions import LOADER_NAMES, VersionCatalog
from cactus_lite.ui import messages, theme
from cactus_lite.ui.controls import FlatButton
from cactus_lite.ui.images import ImageCache, app_bitmap, app_icon
from cactus_lite.ui.pages.changelog import ChangelogPage
from cactus_lite.ui.pages.extra import ExtraPage
from cactus_lite.ui.pages.home import HomePage
from cactus_lite.ui.pages.mods import ModsPage
from cactus_lite.ui.theme import ACCENT, BG, BG2, BG3, FG, MUTED

NAV_ITEMS = (("Главная", "\u2302", "home"),
             ("Дополнительные", "\u2699", "extra"),
             ("Моды", "\u25A3", "mods"))
SIDEBAR_WIDTH = 180
WINDOW_SIZE = (760, 660)
MIN_SIZE = (660, 600)
PROGRESS_THROTTLE = 0.05


class MainFrame(wx.Frame):
    """Top-level window; asks the controller before closing."""

    def __init__(self, app):
        super().__init__(None, title=APP_NAME, size=wx.Size(*WINDOW_SIZE))
        self.app = app
        self.SetMinSize(wx.Size(*MIN_SIZE))
        self.SetBackgroundColour(wx.Colour(BG))
        icon = app_icon(ICON_PNG)
        if icon is not None:
            self.SetIcon(icon)
        self.Bind(wx.EVT_CLOSE, self._on_close)

    def _on_close(self, event):
        if not self.app.confirm_close():
            event.Veto()
            return
        self.Destroy()


class App:
    def __init__(self, frame=None):
        ensure_mc_dir()
        self.settings = Settings()
        self.accounts = AccountStore()
        self.versions = VersionCatalog()
        self.images = ImageCache()
        self.session = launch.GameSession()
        self._current_version_id = self.settings["version"]
        self._status = ""

        self.frame = frame or MainFrame(self)
        self.frame.app = self
        self._build_shell()
        self.refresh_versions(select=self.settings["version"])
        self.frame.Centre()
        self.frame.Show()
        self.run_async(self._load_compat, self._compat_loaded)

    # --- window -------------------------------------------------------------

    def _build_shell(self):
        base = theme.panel(self.frame, BG)
        root = wx.BoxSizer(wx.HORIZONTAL)
        base.SetSizer(root)

        sidebar = theme.panel(base, BG2)
        sidebar.SetMinSize(wx.Size(SIDEBAR_WIDTH, -1))
        side = wx.BoxSizer(wx.VERTICAL)
        sidebar.SetSizer(side)

        logo = app_bitmap(ICON_PNG, size=48)
        if logo is not None:
            side.AddSpacer(12)
            side.Add(theme.bitmap_view(sidebar, logo, bg=BG2), 0, wx.ALIGN_CENTER)
            side.AddSpacer(6)
        else:
            side.AddSpacer(18)

        self.nav_buttons = []
        for label, icon, page in NAV_ITEMS:
            self._add_nav(sidebar, side, f"{icon}  {label}", page)
        side.AddStretchSpacer()
        self._add_nav(sidebar, side, "\u2261  Изменения", "changelog")
        side.AddSpacer(6)
        side.Add(theme.label(sidebar, f"by cactunus {APP_VERSION}", size=8, fg=MUTED, bg=BG2),
                 0, wx.ALIGN_CENTER | wx.BOTTOM, 10)

        container = theme.panel(base, BG)
        self._container_sizer = wx.BoxSizer(wx.VERTICAL)
        container.SetSizer(self._container_sizer)

        root.Add(sidebar, 0, wx.EXPAND)
        root.Add(container, 1, wx.EXPAND)

        frame_sizer = wx.BoxSizer(wx.VERTICAL)
        frame_sizer.Add(base, 1, wx.EXPAND)
        self.frame.SetSizer(frame_sizer)

        self.pages = {}
        for page_class in (HomePage, ExtraPage, ModsPage, ChangelogPage):
            page = page_class(container, self)
            self._container_sizer.Add(page, 1, wx.EXPAND)
            self.pages[page.name] = page
        self.home = self.pages["home"]
        self.show_page("home")

    def _add_nav(self, sidebar, sizer, text, page):
        button = FlatButton(sidebar, text, lambda p=page: self.show_page(p),
                            bg=BG2, fg=FG, hover_bg=BG3, hover_fg=FG, font=theme.font(10),
                            padding=(14, 11), align=wx.ALIGN_LEFT, radius=0)
        sizer.Add(button, 0, wx.EXPAND)
        self.nav_buttons.append((button, page))

    def show_page(self, name):
        for button, page in self.nav_buttons:
            button.set_colours(fg=ACCENT if page == name else FG,
                               hover_fg=ACCENT if page == name else FG)
        for page_name, page in self.pages.items():
            page.Show(page_name == name)
        self.pages[name].on_show()
        self._container_sizer.Layout()
        self.frame.Layout()

    # --- threading helpers --------------------------------------------------

    def ui(self, fn, *args):
        """Run fn(*args) on the GUI thread."""
        wx.CallAfter(self._safe_call, fn, args)

    @staticmethod
    def _safe_call(fn, args):
        try:
            fn(*args)
        except RuntimeError:
            pass  # the target window was destroyed while the job was in flight

    def run_async(self, work, done=None):
        """Run `work()` on a thread, then `done(result, error)` on the GUI thread."""
        def job():
            try:
                result, error = work(), None
            except Exception as e:
                result, error = None, e
            if done is not None:
                self.ui(done, result, error)

        threading.Thread(target=job, daemon=True).start()

    def status(self, text):
        self._status = str(text or "")
        if getattr(self, "home", None) is not None:
            self.ui(self.home.set_status, self._status)

    def log(self, line):
        self.ui(self.home.log, line)

    def show_progress(self, show):
        self.ui(self.home.show_progress, show)

    def progress_callback(self):
        """minecraft-launcher-lib progress callback bound to the UI."""
        last = [0.0]

        def set_progress(value):
            now = time.time()
            if now - last[0] < PROGRESS_THROTTLE:
                return
            last[0] = now
            self.ui(self.home.set_progress, int(value))

        return {"setStatus": lambda msg: self.status(str(msg)) if msg else None,
                "setProgress": set_progress,
                "setMax": lambda _m: None}

    # --- versions -----------------------------------------------------------

    def _load_compat(self):
        return self.versions.refresh_compat()

    def _compat_loaded(self, changed, _error):
        if changed:
            self.refresh_versions()

    def refresh_versions(self, select=None):
        ids = self.versions.installed_ids()
        loader = self.settings["loader"]
        current = select or self._current_version_id
        if current not in ids:
            current = ids[0] if ids else ""
        self._current_version_id = current
        label = self.versions.label(current, loader) if current in ids else current
        self.home.set_versions([self.versions.label(i, loader) for i in ids], label)
        if not ids and not self._status:
            self.status("Версий нет — нажмите «+»")
        self.home.update_skin_button()

    def current_version(self):
        if self._current_version_id:
            return self._current_version_id
        # `home` is missing while the pages are still being constructed.
        home = getattr(self, "home", None)
        return self.versions.id_from_label(home.version_label()) if home else ""

    def select_version_by_index(self, index):
        ids = self.versions.ids
        if 0 <= index < len(ids):
            self._current_version_id = ids[index]

    def install_version(self, version):
        self.status(f"Устанавливаю {version}...")
        self.show_progress(True)

        def work():
            launch.install_version(version, callback=self.progress_callback())

        def done(_result, error):
            self.show_progress(False)
            if error:
                self.status("Ошибка установки.")
                messages.error(f"Ошибка установки:\n{error}")
            else:
                self.status(f"{version} установлена.")
            self.refresh_versions(select=version)

        self.run_async(work, done)

    def java_path(self):
        return find_java()[0]

    # --- settings / accounts ------------------------------------------------

    def save_settings(self):
        self.settings.update(nick=self.home.nick(), version=self.current_version(),
                             ram=self.home.ram_gb())

    def set_loader(self, loader):
        self.settings["loader"] = loader
        self.save_settings()
        self.refresh_versions()
        if self.pages["mods"].IsShown():
            self.pages["mods"].on_show()

    def reset_settings(self):
        self.settings.reset()
        self.home.set_nick("")
        self.pages["extra"].sync_loader()
        self.home.refresh_ram()
        self.refresh_versions()
        self.status("Настройки сброшены.")

    def select_account(self, account_id):
        self.accounts.select(account_id)
        self.home.refresh_accounts()
        account = self.accounts.selected_account()
        self.status(f"Аккаунт: {account['username']}" if account else "Оффлайн-режим.")

    def add_account(self, profile):
        account = self.accounts.add(profile)
        self.home.refresh_accounts()
        self.status(f"Вход выполнен: {account['username']}")

    def logout_account(self, account):
        self.run_async(lambda: elyby.invalidate(account))
        self.accounts.remove(account["id"])
        self.home.refresh_accounts()
        self.status("Вы вышли из аккаунта Ely.by.")

    # --- launching ----------------------------------------------------------

    def launch(self):
        if self.session.running:
            return
        version = self.current_version()
        if not version:
            messages.info("Сначала установите версию (кнопка «+»).")
            return
        loader = self.settings["loader"]
        if not self.versions.supports(version, loader):
            messages.warning(
                f"{LOADER_NAMES[loader]} не поддерживает эту версию Minecraft.\n\n"
                "Выберите совместимую версию — несовместимые помечены «(недоступна)».")
            return

        stored = self.accounts.selected_account()
        nick = None
        if stored is None:
            nick = self.home.validate_nick()
            if nick is None:
                return
        self.save_settings()
        ram = self.home.ram_gb()
        self.home.set_running(True)
        note = f" | {LOADER_NAMES[loader]}" if loader != "none" else ""
        who = stored["username"] if stored else nick
        self.log(f"Запуск: {version} | {who} | RAM: {ram} GB{note}")
        self.run_async(lambda: self._launch_worker(version, loader, stored, nick, ram),
                       self._launch_finished)

    def _launch_worker(self, version, loader, stored, nick, ram):
        account, _ = launch.resolve_account(stored, nick)
        if stored is not None and account.get("access_token") != stored.get("access_token"):
            self.ui(self.accounts.update, account)
        self.show_progress(True)
        try:
            command = launch.prepare_command(
                version, loader, account, ram,
                callback=self.progress_callback(), on_status=self.status,
                on_progress=lambda done, total: None)
        finally:
            self.show_progress(False)
        self.status("Запуск игры...")
        self.log("» " + " ".join(command))
        self.session.start(command, on_line=self.log,
                           on_window=lambda: self.ui(self.home.set_close_mode))
        self.session.wait()
        self.status("Игра закрыта.")

    def _launch_finished(self, _result, error):
        self.show_progress(False)
        self.home.set_running(False)
        if error:
            self.status("Ошибка запуска.")
            messages.error(f"Ошибка запуска:\n{error}")

    def close_game(self):
        if not self.session.running:
            return
        if not messages.ask_yes_no("Закрыть игру?"):
            return
        self.status("Закрываю игру...")
        self.run_async(self.session.close)

    def confirm_close(self):
        """False vetoes the window close."""
        if self.session.running:
            return messages.ask_yes_no("Игра ещё запущена. Закрыть лаунчер?")
        return True

    def on_close(self):
        self.frame.Close()
