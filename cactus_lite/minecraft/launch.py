"""Installing versions/loaders and building the game launch command."""

import os
import subprocess
import threading
import time

import minecraft_launcher_lib as mll

from cactus_lite.auth import authlib_injector, elyby
from cactus_lite.auth.accounts import offline_account
from cactus_lite.core.paths import APP_NAME, APP_VERSION, MC_DIR
from cactus_lite.core.platform_utils import close_window, find_game_window, no_window_flags
from cactus_lite.minecraft import skins
from cactus_lite.minecraft.java import ensure_java
from cactus_lite.minecraft.versions import LOADER_NAMES, supports_skin


class LaunchError(RuntimeError):
    pass


def install_version(version, callback=None, mc_dir=MC_DIR):
    mll.install.install_minecraft_version(version, mc_dir, callback=callback or {})


def install_loader(loader_id, version, java, callback=None, mc_dir=MC_DIR):
    """Install a mod loader for `version` and return the version id to launch."""
    loader = mll.mod_loader.get_mod_loader(loader_id)
    loader_versions = loader.get_loader_versions(version, stable_only=True)
    if not loader_versions:
        raise LaunchError(f"{LOADER_NAMES[loader_id]} не поддерживает версию {version}")
    # Fabric/NeoForge list newest first; Forge lists oldest first.
    loader_version = loader_versions[-1] if loader_id == "forge" else loader_versions[0]
    launch_version = loader.get_installed_version(version, loader_version)
    installed = {v["id"] for v in mll.utils.get_installed_versions(mc_dir)}
    if launch_version not in installed:
        loader.install(version, mc_dir, callback=callback or {}, java=java,
                       loader_version=loader_version)
    return launch_version


def resolve_account(account, nick):
    """Return a game-ready account, refreshing an Ely.by session if needed."""
    if not account or account.get("kind") != "elyby":
        return offline_account(nick), None
    try:
        return elyby.ensure_session(account), None
    except elyby.AuthError as e:
        raise LaunchError(f"Сессия Ely.by недействительна: {e}\nВойдите в аккаунт заново.")


def build_options(account, java, ram, jvm_extra=()):
    return {
        "username": account["username"],
        "uuid": account["uuid"],
        "token": account.get("access_token") or "",
        "executablePath": java,
        "jvmArguments": [f"-Xmx{ram}G", f"-Xms{ram}G", "-Dfile.encoding=UTF-8", *jvm_extra],
        "launcherName": APP_NAME,
        "launcherVersion": APP_VERSION.lstrip("v"),
    }


class GameSession:
    """Owns the running game process and reports its lifecycle."""

    def __init__(self, mc_dir=MC_DIR):
        self.mc_dir = mc_dir
        self.process = None
        self.window_open = False

    @property
    def running(self):
        return self.process is not None and self.process.poll() is None

    def start(self, command, on_line=None, on_window=None):
        self.window_open = False
        self.process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding="utf-8", errors="replace", bufsize=1, cwd=self.mc_dir,
            **no_window_flags())
        if on_line:
            threading.Thread(target=self._pump_output, args=(on_line,), daemon=True).start()
        if on_window:
            threading.Thread(target=self._watch_window, args=(on_window,), daemon=True).start()
        return self.process

    def wait(self):
        if self.process is None:
            return None
        code = self.process.wait()
        self.process = None
        return code

    def close(self):
        """Ask the game to close, then terminate if it ignores the request."""
        proc = self.process
        if proc is None or proc.poll() is not None:
            return
        hwnd = find_game_window(proc.pid)
        if hwnd:
            close_window(hwnd)
            try:
                proc.wait(timeout=5)
                return
            except Exception:
                pass
        proc.terminate()

    def _pump_output(self, on_line):
        proc = self.process
        try:
            for line in iter(proc.stdout.readline, ""):
                if line:
                    on_line(line.rstrip("\r\n"))
        except Exception:
            pass

    def _watch_window(self, on_window):
        proc = self.process
        while proc is not None and proc.poll() is None and not self.window_open:
            if find_game_window(proc.pid):
                self.window_open = True
                on_window()
                return
            time.sleep(0.5)


def prepare_command(version, loader_id, account, ram, mc_dir=MC_DIR,
                    callback=None, on_status=None, on_progress=None):
    """Install everything needed and return the full launch command."""
    def status(text):
        if on_status:
            on_status(text)

    java = ensure_java(version, mc_dir, callback=callback, on_status=status)
    status("Проверка файлов...")
    install_version(version, callback=callback, mc_dir=mc_dir)

    launch_version = version
    if loader_id != "none":
        status(f"Установка {LOADER_NAMES[loader_id]}...")
        launch_version = install_loader(loader_id, version, java, callback=callback, mc_dir=mc_dir)

    jvm_extra = []
    if account.get("kind") == "elyby":
        status("Подключаю Ely.by...")
        jar = authlib_injector.ensure_jar(on_progress=on_progress)
        jvm_extra.append(authlib_injector.jvm_argument(jar))
    elif skins.has_skin() and supports_skin(version):
        status("Применяю скин...")
        skins.write_skin_pack(version, mc_dir)

    options = build_options(account, java, ram, jvm_extra)
    return mll.command.get_minecraft_command(launch_version, mc_dir, options)
