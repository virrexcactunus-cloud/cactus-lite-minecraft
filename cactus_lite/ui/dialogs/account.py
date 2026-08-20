"""Ely.by sign-in dialog.

The password is only held in the entry widget for the duration of the request:
Ely.by returns tokens, and only tokens are saved to disk.
"""

import webbrowser

import wx

from cactus_lite.auth import elyby
from cactus_lite.ui import theme
from cactus_lite.ui.dialogs.base import Dialog
from cactus_lite.ui.theme import ACCENT, DANGER, FG, MUTED

REGISTER_URL = "https://account.ely.by/register"
INTRO = ("Войдите в аккаунт Ely.by, чтобы играть с ником, скином и плащом "
         "на серверах с online-mode. Пароль не сохраняется — лаунчер хранит "
         "только токен доступа.")
PAD = 18


class AccountDialog(Dialog):
    title = "Вход через Ely.by"
    size = (440, 470)

    def build(self):
        self._busy = False
        self._client_token = elyby.new_client_token()
        box = self.sizer

        box.AddSpacer(PAD)
        box.Add(theme.section_label(self, "ELY.BY"), 0, wx.LEFT | wx.RIGHT, PAD)
        box.AddSpacer(4)
        box.Add(theme.hint_label(self, INTRO, wrap=380), 0, wx.LEFT | wx.RIGHT, PAD)

        box.AddSpacer(14)
        box.Add(theme.section_label(self, "E-mail или ник"), 0, wx.LEFT | wx.RIGHT, PAD)
        box.AddSpacer(4)
        self.login_field = theme.entry(self, size=11, on_enter=self._submit)
        box.Add(self.login_field, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, PAD)

        box.AddSpacer(10)
        box.Add(theme.section_label(self, "Пароль"), 0, wx.LEFT | wx.RIGHT, PAD)
        box.AddSpacer(4)
        self.password_field = theme.entry(self, size=11, password=True, on_enter=self._submit)
        box.Add(self.password_field, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, PAD)

        box.AddSpacer(10)
        self.totp_label = theme.section_label(self, "Код двухфакторной аутентификации")
        box.Add(self.totp_label, 0, wx.LEFT | wx.RIGHT, PAD)
        box.AddSpacer(4)
        self.totp_field = theme.entry(self, size=11, on_enter=self._submit)
        box.Add(self.totp_field, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, PAD)
        self._totp_slots = tuple(range(box.GetItemCount() - 4, box.GetItemCount()))
        for slot in self._totp_slots:
            box.Show(slot, False)

        box.AddSpacer(10)
        self.status = theme.label(self, "", size=9, fg=ACCENT, wrap=380)
        box.Add(self.status, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, PAD)

        box.AddSpacer(10)
        self.submit_btn = theme.primary_button(self, "ВОЙТИ", self._submit, padding=(18, 11))
        box.Add(self.submit_btn, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, PAD)
        box.AddSpacer(10)
        box.Add(theme.ghost_button(self, "Создать аккаунт на ely.by",
                                   lambda: webbrowser.open(REGISTER_URL), size=9,
                                   fg=MUTED, active_fg=FG), 0, wx.LEFT | wx.RIGHT, PAD)
        box.AddSpacer(PAD)

        self.login_field.SetFocus()

    def _show_totp(self):
        for slot in self._totp_slots:
            self.sizer.Show(slot, True)
        self.Layout()
        self.totp_field.SetFocus()

    def _set_status(self, text, colour=ACCENT):
        self.status.SetForegroundColour(wx.Colour(colour))
        self.status.set_text(text)
        self.Layout()

    def _set_busy(self, busy, message=""):
        self._busy = busy
        self.submit_btn.set_label("ВХОД..." if busy else "ВОЙТИ")
        self.submit_btn.Enable(not busy)
        self._set_status(message)

    def _submit(self):
        if self._busy:
            return
        login = self.login_field.GetValue().strip()
        password = self.password_field.GetValue()
        totp = self.totp_field.GetValue().strip()
        if not login or not password:
            self._set_status("Введите логин и пароль.", DANGER)
            return
        self._set_busy(True, "Проверяю данные...")

        def work():
            return elyby.authenticate(login, password, totp=totp or None,
                                      client_token=self._client_token)

        self.app.run_async(work, self._done)

    def _done(self, profile, error):
        if not self.alive():
            return
        if isinstance(error, elyby.TwoFactorRequired):
            self._set_busy(False)
            self._set_status("Введите код из приложения аутентификации.", FG)
            self._show_totp()
            return
        if error:
            self._set_busy(False)
            self._set_status(str(error), DANGER)
            return
        self.password_field.SetValue("")
        self.close()
        self.app.add_account(profile)
