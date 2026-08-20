"""Main page: account, nickname, version, RAM and the play button."""

import re

import wx

from cactus_lite.auth.accounts import OFFLINE_ID
from cactus_lite.minecraft import skins
from cactus_lite.minecraft.versions import supports_skin
from cactus_lite.ui import messages
from cactus_lite.ui import ram as ram_options
from cactus_lite.ui import theme
from cactus_lite.ui.dialogs.account import AccountDialog
from cactus_lite.ui.dialogs.install_version import InstallVersionDialog
from cactus_lite.ui.pages.base import Page
from cactus_lite.ui.theme import BG3, FG, MUTED
from cactus_lite.ui.widgets import Console

NICK_RE = re.compile(r"[A-Za-z0-9_]{1,16}")
RAM_TICK_MS = 5000
PAD = 20
SKIN_WILDCARD = ("Изображения (*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.gif)"
                 "|*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.gif|Все файлы (*.*)|*.*")


class HomePage(Page):
    name = "home"

    def build(self):
        app = self.app
        self.console_shown = False
        self._account_ids = [OFFLINE_ID]
        self._ram_values = [2]
        self._ram_selectable = {2}
        self._ram_recommended = 2
        self._last_ram_label = ""

        box = self.sizer
        box.AddSpacer(20)

        box.Add(theme.section_label(self, "АККАУНТ"), 0, wx.LEFT | wx.RIGHT, PAD)
        box.AddSpacer(5)
        account_row = wx.BoxSizer(wx.HORIZONTAL)
        self.account_cb = theme.dropdown(self, on_select=self._on_account_selected, size=11)
        account_row.Add(self.account_cb, 1, wx.ALIGN_CENTER_VERTICAL)
        account_row.AddSpacer(8)
        account_row.Add(theme.ghost_button(self, "Ely.by", self._open_account_dialog, size=9),
                        0, wx.ALIGN_CENTER_VERTICAL)
        account_row.AddSpacer(6)
        self.account_logout_btn = theme.ghost_button(self, "Выйти", self._logout, size=9,
                                                     fg=MUTED, active_fg=FG)
        account_row.Add(self.account_logout_btn, 0, wx.ALIGN_CENTER_VERTICAL)
        box.Add(account_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, PAD)

        box.AddSpacer(14)
        self.nick_label = theme.section_label(self, "НИКНЕЙМ")
        box.Add(self.nick_label, 0, wx.LEFT | wx.RIGHT, PAD)
        box.AddSpacer(5)
        self.nick_row = wx.BoxSizer(wx.HORIZONTAL)
        self.nick_field = theme.entry(self, app.settings["nick"], on_enter=app.launch)
        self.nick_row.Add(self.nick_field, 1, wx.ALIGN_CENTER_VERTICAL)
        self.nick_row.AddSpacer(8)
        self.skin_btn = theme.ghost_button(self, "Скин", self._pick_skin, size=9, min_width=64)
        self.nick_row.Add(self.skin_btn, 0, wx.ALIGN_CENTER_VERTICAL)
        box.Add(self.nick_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, PAD)
        # The whole block — leading spacer, caption, gap, row — hides together.
        self._nick_slots = tuple(range(box.GetItemCount() - 4, box.GetItemCount()))

        box.AddSpacer(14)
        box.Add(theme.section_label(self, "ВЕРСИЯ"), 0, wx.LEFT | wx.RIGHT, PAD)
        box.AddSpacer(5)
        version_row = wx.BoxSizer(wx.HORIZONTAL)
        self.version_cb = theme.dropdown(self, on_select=self._on_version_selected)
        version_row.Add(self.version_cb, 1, wx.ALIGN_CENTER_VERTICAL)
        version_row.AddSpacer(8)
        add_btn = theme.ghost_button(self, "+", self._open_install_dialog, bg=BG3,
                                     size=14, min_width=44, padding=(10, 6))
        add_btn.SetFont(theme.font(14, "bold"))
        version_row.Add(add_btn, 0, wx.ALIGN_CENTER_VERTICAL)
        box.Add(version_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, PAD)

        box.AddSpacer(14)
        box.Add(theme.section_label(self, "ПАМЯТЬ (GB)"), 0, wx.LEFT | wx.RIGHT, PAD)
        box.AddSpacer(5)
        self.ram_cb = theme.dropdown(self, on_select=self._on_ram_selected, min_width=200)
        box.Add(self.ram_cb, 0, wx.LEFT | wx.RIGHT, PAD)

        box.AddSpacer(18)
        self.launch_btn = theme.primary_button(self, "ИГРАТЬ", app.launch, size=14,
                                               padding=(18, 13))
        box.Add(self.launch_btn, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, PAD)

        box.AddSpacer(14)
        self.progress = theme.progress_bar(self)
        box.Add(self.progress, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, PAD)
        self._progress_slot = box.GetItemCount() - 1
        box.Show(self._progress_slot, False)

        box.AddSpacer(12)
        self.status_label = theme.label(self, "", size=9, fg=MUTED, wrap=theme.AUTO_WRAP)
        box.Add(self.status_label, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, PAD)

        box.AddSpacer(8)
        self.console = Console(self)
        box.Add(self.console, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, PAD)
        self._console_slot = box.GetItemCount() - 1
        box.Show(self._console_slot, False)

        box.AddSpacer(8)
        self.log_btn = theme.link_button(self, "журнал", self.toggle_console, size=8)
        box.Add(self.log_btn, 0, wx.LEFT | wx.RIGHT, PAD)
        box.AddSpacer(12)

        self.refresh_ram()
        self.refresh_accounts()
        self._ram_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._tick_ram, self._ram_timer)
        self._ram_timer.Start(RAM_TICK_MS)

    # --- text fields --------------------------------------------------------

    def nick(self):
        return self.nick_field.GetValue().strip()

    def set_nick(self, value):
        self.nick_field.SetValue(value or "")

    def set_status(self, text):
        self.status_label.set_text(text)
        self.Layout()

    # --- accounts -----------------------------------------------------------

    def refresh_accounts(self):
        items = self.app.accounts.labels()
        self._account_ids = [account_id for account_id, _label in items]
        selected = self.app.accounts.selected
        if selected not in self._account_ids:
            selected = OFFLINE_ID
        self.account_cb.set_items([label for _id, label in items],
                                  selection=self._account_ids.index(selected))
        offline = selected == OFFLINE_ID
        self.account_logout_btn.Enable(not offline)
        self._set_nick_visible(offline)
        self.update_skin_button()

    def _set_nick_visible(self, visible):
        for slot in self._nick_slots:
            self.sizer.Show(slot, visible)
        self.Layout()

    def _on_account_selected(self, index):
        if 0 <= index < len(self._account_ids):
            self.app.select_account(self._account_ids[index])

    def _open_account_dialog(self):
        AccountDialog(self.app).show()

    def _logout(self):
        account = self.app.accounts.selected_account()
        if not account:
            return
        if not messages.ask_yes_no(f"Выйти из аккаунта «{account['username']}»?"):
            return
        self.app.logout_account(account)

    # --- version ------------------------------------------------------------

    def set_versions(self, labels, value):
        self.version_cb.set_items(labels)
        self.version_cb.set_value(value)

    def version_label(self):
        return self.version_cb.get_value()

    def _on_version_selected(self, index):
        self.app.select_version_by_index(index)
        self.update_skin_button()

    def _open_install_dialog(self):
        InstallVersionDialog(self.app).show()

    def update_skin_button(self):
        version = self.app.current_version()
        offline = self.app.accounts.selected == OFFLINE_ID
        self.skin_btn.Show(bool(offline and version and supports_skin(version)))
        self.Layout()

    def _pick_skin(self):
        paths = messages.open_file("Выберите скин", SKIN_WILDCARD)
        if not paths:
            return
        try:
            skins.save_skin(paths[0])
        except Exception as e:
            messages.error(f"Не удалось обработать изображение:\n{e}")
            return
        self.app.status("Скин выбран — будет подставлен в игру.")

    # --- RAM ----------------------------------------------------------------

    def refresh_ram(self):
        labels, values, selectable, recommended = ram_options.options()
        self._ram_values = values
        self._ram_selectable = selectable
        current = ram_options.parse(self.ram_cb.get_value(), values)
        saved = self.app.settings["ram"]
        if current is None and saved in selectable:
            current = saved
        if current is None or current == self._ram_recommended or current not in selectable:
            current = recommended
        label = ram_options.label_for(current, recommended, selectable)
        if labels != self.ram_cb.get_items():
            self.ram_cb.set_items(labels, value=label)
        else:
            self.ram_cb.set_value(label)
        self._ram_recommended = recommended
        self._last_ram_label = label

    def ram_gb(self):
        value = ram_options.parse(self.ram_cb.get_value(), self._ram_values)
        if value is not None:
            return value
        return self._ram_values[0] if self._ram_values else 2

    def _on_ram_selected(self, _index):
        value = self.ram_gb()
        if value not in self._ram_selectable:
            self.ram_cb.set_value(self._last_ram_label)
            self.app.status(f"{value} ГБ сейчас заняты системой — выбрать нельзя.")
        else:
            self._last_ram_label = self.ram_cb.get_value()

    def _tick_ram(self, _event):
        try:
            self.refresh_ram()
        except Exception:
            pass

    # --- launch button / progress / log -------------------------------------

    def set_running(self, running):
        if running:
            self.launch_btn.set_label("ЗАПУСК...")
            self.launch_btn.Enable(False)
        else:
            self.launch_btn.set_command(self.app.launch)
            self.launch_btn.set_label("ИГРАТЬ")
            self.launch_btn.Enable(True)

    def set_close_mode(self):
        self.launch_btn.set_command(self.app.close_game)
        self.launch_btn.set_label("Закрыть")
        self.launch_btn.Enable(True)

    def set_progress(self, value):
        self.progress.set_value(value)

    def show_progress(self, show):
        self.progress.set_value(0)
        self.sizer.Show(self._progress_slot, bool(show))
        self.Layout()

    def log(self, line):
        self.console.append(line)

    def toggle_console(self):
        self.console_shown = not self.console_shown
        self.sizer.Show(self._console_slot, self.console_shown)
        self.Layout()

    def validate_nick(self):
        """Return a valid nickname, or None after showing a warning."""
        nick = self.nick() or "Steve"
        if not NICK_RE.fullmatch(nick):
            messages.warning("Ник: латиница, цифры, «_», до 16 символов.")
            return None
        return nick
