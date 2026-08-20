"""Message boxes and file pickers, themed titles and Russian button labels."""

import wx

from cactus_lite.core.paths import APP_NAME

_ICON = {"info": wx.ICON_INFORMATION, "warning": wx.ICON_WARNING, "error": wx.ICON_ERROR,
         "question": wx.ICON_QUESTION}


def _parent():
    top = wx.GetApp().GetTopWindow() if wx.GetApp() else None
    return top if top and top.IsShown() else None


def _show(message, kind, style):
    dialog = wx.MessageDialog(_parent(), str(message), APP_NAME, style | _ICON[kind])
    try:
        return dialog.ShowModal()
    finally:
        dialog.Destroy()


def info(message):
    _show(message, "info", wx.OK | wx.CENTRE)


def warning(message):
    _show(message, "warning", wx.OK | wx.CENTRE)


def error(message):
    _show(message, "error", wx.OK | wx.CENTRE)


def ask_yes_no(message):
    dialog = wx.MessageDialog(_parent(), str(message), APP_NAME,
                             wx.YES_NO | wx.NO_DEFAULT | wx.CENTRE | wx.ICON_QUESTION)
    dialog.SetYesNoLabels("Да", "Отмена")
    try:
        return dialog.ShowModal() == wx.ID_YES
    finally:
        dialog.Destroy()


def open_file(title, wildcard, multiple=False):
    """Return a list of chosen paths (possibly empty)."""
    style = wx.FD_OPEN | wx.FD_FILE_MUST_EXIST | (wx.FD_MULTIPLE if multiple else 0)
    dialog = wx.FileDialog(_parent(), title, wildcard=wildcard, style=style)
    try:
        if dialog.ShowModal() != wx.ID_OK:
            return []
        return list(dialog.GetPaths()) if multiple else [dialog.GetPath()]
    finally:
        dialog.Destroy()
