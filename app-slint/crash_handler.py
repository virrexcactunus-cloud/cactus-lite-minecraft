# -*- coding: utf-8 -*-
"""Cactus Crash Handler — служба слежения за падениями лаунчера.

Что делает:
  * пишет подробный лог краша в ~/.mcl/crashes;
  * показывает системное уведомление о том, что программа вылетела;
  * работает в двух режимах — встроенный перехватчик install() и
    служба-наблюдатель, которая запускает лаунчер дочерним процессом
    и ловит даже нативные падения (SIGABRT, SIGSEGV и подобные).

Запуск службой:  python3 crash_handler.py [команда...]
Без аргументов служба запускает main.py, лежащий рядом.
"""

import datetime
import faulthandler
import os
import platform
import subprocess
import sys
import threading
import traceback

SERVICE_NAME = "Cactus Crash Handler"
APP_NAME = "Cactus Lite Minecraft"
MC_DIR = os.path.join(os.path.expanduser("~"), ".mcl")
CRASH_DIR = os.path.join(MC_DIR, "crashes")
KEEP_LOGS = 20

IS_WINDOWS = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"


def crash_dir():
    os.makedirs(CRASH_DIR, exist_ok=True)
    return CRASH_DIR


def _trim_old_logs():
    """Держим только последние KEEP_LOGS отчётов."""
    try:
        files = sorted((f for f in os.listdir(CRASH_DIR) if f.startswith("crash-")), reverse=True)
        for name in files[KEEP_LOGS:]:
            os.remove(os.path.join(CRASH_DIR, name))
    except Exception:
        pass


def system_info(app_version=""):
    lines = [
        ("Приложение : " + APP_NAME + " " + str(app_version)).rstrip(),
        "Время      : " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Система    : " + platform.platform(),
        "Процессор  : " + platform.machine(),
        "Python     : " + sys.version.split()[0] + " (" + sys.executable + ")",
        "Папка игры : " + MC_DIR,
    ]
    try:
        import slint
        lines.append("Slint      : " + str(getattr(slint, "__version__", "неизвестно")))
    except Exception:
        pass
    return "\n".join(lines)


def write_crash_log(title, details, tail="", app_version=""):
    """Сохраняет отчёт о падении и возвращает путь к файлу."""
    crash_dir()
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = os.path.join(CRASH_DIR, "crash-" + stamp + ".log")
    parts = ["=== " + SERVICE_NAME + " ===", str(title), "", system_info(app_version), "", str(details)]
    if tail:
        parts += ["", "--- последние строки вывода ---", tail]
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(parts).rstrip() + "\n")
    except Exception:
        return ""
    _trim_old_logs()
    return path


def notify(message, title=None):
    """Системное уведомление на Windows, macOS и Linux."""
    title = title or (APP_NAME + " вылетел")
    try:
        if IS_MAC:
            text = str(message).replace('"', "'").replace("\n", " ")
            script = 'display notification "' + text + '" with title "' + title + '" sound name "Basso"'
            subprocess.run(["osascript", "-e", script], check=False, timeout=10)
        elif IS_WINDOWS:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, str(message), title, 0x10 | 0x1000)
        else:
            try:
                subprocess.run(["notify-send", "-u", "critical", title, str(message)], check=False, timeout=10)
            except FileNotFoundError:
                sys.stderr.write("[" + title + "] " + str(message) + "\n")
    except Exception:
        pass


def reveal(path):
    """Открыть папку с отчётами о падениях."""
    folder = os.path.dirname(path) or CRASH_DIR
    try:
        if IS_WINDOWS:
            os.startfile(folder)
        elif IS_MAC:
            subprocess.run(["open", "-R", path] if os.path.isfile(path) else ["open", folder], check=False)
        else:
            subprocess.run(["xdg-open", folder], check=False)
    except Exception:
        pass


_installed = False


def install(app_version="", on_crash=None):
    """Встроенный режим: ловим исключения Python в любом потоке."""
    global _installed
    if _installed:
        return
    _installed = True
    crash_dir()
    try:
        stream = open(os.path.join(CRASH_DIR, "faulthandler.log"), "a", encoding="utf-8", buffering=1)
        faulthandler.enable(file=stream, all_threads=True)
    except Exception:
        pass

    def report(exc_type, exc_value, exc_tb, where="главный поток"):
        details = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        path = write_crash_log("Необработанная ошибка (" + where + ")", details, app_version=app_version)
        short = exc_type.__name__ + ": " + str(exc_value)
        notify(short + (" | Лог: " + path if path else ""))
        if on_crash:
            try:
                on_crash(path)
            except Exception:
                pass
        try:
            sys.__stderr__.write(details)
        except Exception:
            pass

    def hook(exc_type, exc_value, exc_tb):
        report(exc_type, exc_value, exc_tb)

    def thread_hook(args):
        name = args.thread.name if args.thread is not None else "?"
        report(args.exc_type, args.exc_value, args.exc_traceback, where="поток " + name)

    sys.excepthook = hook
    threading.excepthook = thread_hook


def _tail(path, lines=200):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return "".join(f.readlines()[-lines:])
    except Exception:
        return ""


def _exit_reason(code):
    if code < 0:
        try:
            import signal
            return "аварийно завершён сигналом " + signal.Signals(-code).name + " (" + str(-code) + ")"
        except Exception:
            return "аварийно завершён сигналом " + str(-code)
    return "завершился с кодом " + str(code)


def _journal(text):
    """Короткая запись в общий журнал запусков (не только падений)."""
    try:
        crash_dir()
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(os.path.join(CRASH_DIR, "runs.log"), "a", encoding="utf-8") as f:
            f.write(stamp + "  " + text + "\n")
    except Exception:
        pass


def run_service(command=None, app_version=""):
    """Служба-наблюдатель: держит лаунчер под присмотром."""
    here = os.path.dirname(os.path.abspath(__file__))
    command = list(command) if command else [sys.executable, os.path.join(here, "main.py")]
    crash_dir()
    run_log = os.path.join(CRASH_DIR, "last-run.log")
    env = dict(os.environ)
    env["PYTHONFAULTHANDLER"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    started = datetime.datetime.now()
    _journal("старт: " + " ".join(command) + " (служба pid " + str(os.getpid()) + ")")
    try:
        with open(run_log, "w", encoding="utf-8") as log:
            proc = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, cwd=here, env=env)
            _journal("лаунчер запущен, pid " + str(proc.pid))
            try:
                import signal as _signal

                def _stop(signum, frame):
                    _journal("служба получила сигнал " + str(signum) + ", закрываю лаунчер")
                    try:
                        proc.terminate()
                    except Exception:
                        pass

                _signal.signal(_signal.SIGTERM, _stop)
                _signal.signal(_signal.SIGINT, _stop)
            except Exception:
                pass
            code = proc.wait()
    except Exception as e:
        path = write_crash_log("Не удалось запустить лаунчер", str(e), app_version=app_version)
        notify("Не удалось запустить лаунчер: " + str(e) + (" | Лог: " + path if path else ""))
        _journal("не удалось запустить: " + str(e))
        return 1
    uptime = int((datetime.datetime.now() - started).total_seconds())
    if code == 0:
        _journal("закрыт штатно, проработал " + str(uptime) + " c")
        return 0
    reason = _exit_reason(code)
    _journal(reason + ", проработал " + str(uptime) + " c")
    path = write_crash_log(
        APP_NAME + " " + reason,
        "Команда: " + " ".join(command) + "\nПроработал: " + str(uptime) + " c",
        _tail(run_log),
        app_version,
    )
    notify(APP_NAME + " " + reason + (" | Лог: " + path if path else ""))
    return code


if __name__ == "__main__":
    try:
        os.setsid()  # своя сессия: служба переживает закрытие терминала
    except Exception:
        pass
    sys.exit(run_service(sys.argv[1:] or None))
