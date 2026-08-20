"""Entry point: `python launcher.py` or `python -m cactus_lite`."""

import wx

from cactus_lite.core.paths import APP_NAME, ensure_mc_dir
from cactus_lite.core.platform_utils import hide_console
from cactus_lite.ui.app import App


class LauncherApp(wx.App):
    def OnInit(self):  # noqa: N802 - wx naming
        self.SetAppName(APP_NAME)
        self.controller = App()
        self.SetTopWindow(self.controller.frame)
        return True


def main():
    hide_console()
    ensure_mc_dir()
    app = LauncherApp(False)
    app.MainLoop()


if __name__ == "__main__":
    main()
