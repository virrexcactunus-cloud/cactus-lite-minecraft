import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import urllib.request
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import minecraft_launcher_lib as mll
import mod_catalog
import skin_pack

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_AVAILABLE = True
except Exception:
    DND_AVAILABLE = False

if getattr(sys, "frozen", False):
    APP_DIR = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_ICO = os.path.join(APP_DIR, "icon.ico")
ICON_PNG = os.path.join(APP_DIR, "icon.png")
APP_NAME = "Cactus Lite Minecraft"
APP_VERSION = "v1.3"
MC_DIR = os.path.join(os.path.expanduser("~"), ".mcl")
SETTINGS_PATH = os.path.join(MC_DIR, "settings.json")
SKIN_DIR = os.path.join(MC_DIR, "skins")
PLAYTIME_PATH = os.path.join(MC_DIR, "playtime.json")
SKIN_PACK = skin_pack.SKIN_PACK

CHANGELOG = [
    {
        "version": "v1.3",
        "fixes": [
            "Поиск модов теперь действительно виден и работает — страница «Моды» показывала его только после выбора подсистемы",
            "Страница «Моды» прокручивается колесом мыши даже над плитками",
            "Скин: ресурспак теперь работает на всех версиях — 1.6–1.7 получают скин 64×32, на 1.21.9+ скин подставляется во все текстуры игроков",
            "Скин на 1.21.11 больше не пропадает — исправлены pack.mcmeta и пути к текстурам",
            "Старые версии (1.7–1.16) запускаются на подходящей Java, а не на самой новой",
        ],
        "features": [
            "Большие плитки каталога во всю ширину страницы",
            "Каталог показывает только моды, совместимые с выбранной подсистемой",
            "Поиск Modrinth: фильтр по Forge / Fabric / NeoForge и сортировка совместимых с выбранной версией",
            "Счётчик времени в игре на главной",
            "Предпросмотр скина в «Дополнительных»",
        ],
    },
    {
        "version": "v1.2",
        "fixes": [],
        "features": [
            "Подсистемы модов: Forge, Fabric и NeoForge — выбор в «Дополнительных»",
            "Буквы у версий (F — Forge, G — Fabric, N — NeoForge)",
            "Несовместимые с подсистемой версии помечаются «(недоступна)»",
            "Кнопка «Играть» становится «Закрыть», когда игра открыта — можно закрыть игру прямо из лаунчера",
            "Страница «Моды»: перетаскивание файлов или кнопка «Загрузить вручную» — мод копируется в папку mods",
            "Каталог модов: Sodium и OptiFine — плитки с выбором версии и прогрессом скачивания",
            "Список установленных модов с удалением прямо из лаунчера",
        ],
    },
    {
        "version": "v1.1",
        "fixes": [
            "Починил переключение страниц в боковом меню — раньше пункты не реагировали на клики",
        ],
        "features": [
            "Новое название — Cactus Lite Minecraft",
            "Боковое меню: Главная, Дополнительные, Моды",
            "Умная память: список от 1 ГБ до всего объёма, метки «занято» и «рекомендовано», обновление в реальном времени",
            "Выбор скина прямо из лаунчера — скин сам подставляется в игру",
            "Страница «Изменения» с историей версий",
        ],
    },
    {
        "version": "v1",
        "fixes": [],
        "features": [
            "Создание лаунчера, добавление базовых функций",
        ],
    },
]

BG = "#0f1215"
BG2 = "#1a1f25"
BG3 = "#232a31"
FG = "#e8edf2"
MUTED = "#8b949e"
ACCENT = "#22c55e"
ACCENT_DARK = "#16a34a"
FONT = "Segoe UI"

LOADER_IDS = ("forge", "fabric", "neoforge")
LOADER_LETTERS = {"forge": "F", "fabric": "G", "neoforge": "N"}
LOADER_NAMES = {"forge": "Forge", "fabric": "Fabric", "neoforge": "NeoForge"}
LOADER_UI_VALUES = ("Нет (ваниль)", "Forge", "Fabric", "NeoForge")
LOADER_UI_IDS = ("none", "forge", "fabric", "neoforge")
COMPAT_CACHE_PATH = os.path.join(MC_DIR, "loader_compat.json")
_RELEASE_RE = re.compile(r"^\d+\.\d+(?:\.\d+)?$")


def is_loader_version_id(vid):
    v = (vid or "").lower()
    return ("-forge-" in v or v.startswith("forge-") or "fabric-loader" in v
            or v.startswith("neoforge-") or "quilt" in v or "optifine" in v)


def heuristic_compat(vid):
    if not _RELEASE_RE.match(vid or ""):
        return set()
    major, minor = (int(x) for x in vid.split(".")[:2])
    out = set()
    if major == 1 and 1 <= minor <= 20:
        out.add("forge")
    if (major == 1 and minor >= 14) or major >= 2:
        out.add("fabric")
    if (major == 1 and minor >= 20) or major >= 2:
        out.add("neoforge")
    return out


def load_compat_cache():
    try:
        with open(COMPAT_CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if time.time() - data.get("ts", 0) < 86400:
            return {k: set(v) for k, v in data.get("compat", {}).items()}
    except Exception:
        pass
    return None


def save_compat_cache(compat):
    try:
        os.makedirs(MC_DIR, exist_ok=True)
        with open(COMPAT_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump({"ts": time.time(), "compat": {k: sorted(v) for k, v in compat.items()}},
                      f, ensure_ascii=False)
    except Exception:
        pass


def fetch_loader_compat():
    compat = {}
    for lid in LOADER_IDS:
        loader = mll.mod_loader.get_mod_loader(lid)
        for v in loader.get_minecraft_versions(stable_only=True):
            compat.setdefault(v, set()).add(lid)
    return compat


def version_sort_key(v):
    nums = [int(x) for x in re.findall(r"\d+", v)]
    return (nums + [0] * 4)[:4]


def parse_java_version(out_text):
    m = re.search(r'version\s+"?(\d+)', out_text or "")
    if not m:
        m = re.match(r"(\d+)", out_text or "")
    if not m:
        return None
    v = int(m.group(1))
    return 8 if v == 1 else v


def system_ram_gb():
    try:
        mem = ctypes.c_ulonglong()
        if ctypes.windll.kernel32.GetPhysicallyInstalledSystemMemory(ctypes.byref(mem)):
            return mem.value // (1024 * 1024)
    except Exception:
        pass
    return 4


def system_ram_info():
    try:
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]
        m = MemoryStatus()
        m.dwLength = ctypes.sizeof(MemoryStatus)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
            return m.ullTotalPhys // (1024 ** 3), m.ullAvailPhys // (1024 ** 3)
    except Exception:
        pass
    total = system_ram_gb()
    return total, total


def hide_console():
    try:
        import ctypes
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    except Exception:
        pass


def version_supports_skin(version):
    return skin_pack.version_supports_skin(version)


def pack_format_for(version):
    return skin_pack.pack_format_for(version)


def find_java_candidates():
    cands = []
    try:
        for info in mll.java_utils.find_system_java_versions_information():
            p = info.get("javaw_path") or info.get("path") or info.get("java_path")
            if p and os.path.isfile(p):
                cands.append((p, parse_java_version(info.get("version"))))
    except Exception:
        pass

    if not cands:
        seen, manual = set(), []

        def add(p):
            if p and os.path.isfile(p) and p not in seen:
                seen.add(p)
                manual.append(p)

        jh = os.environ.get("JAVA_HOME")
        if jh:
            add(os.path.join(jh, "bin", "javaw.exe"))
            add(os.path.join(jh, "bin", "java.exe"))
        for d in os.environ.get("PATH", "").split(os.pathsep):
            if d:
                add(os.path.join(d, "javaw.exe"))
                add(os.path.join(d, "java.exe"))
        for base in (os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", "")):
            if base:
                for pattern in ("Java/*/bin/javaw.exe", "Eclipse Adoptium/*/bin/javaw.exe",
                                "Microsoft/*/bin/javaw.exe"):
                    try:
                        for p in Path(base).glob(pattern):
                            add(str(p))
                    except OSError:
                        pass
                for pattern in ("Java/*/bin/java.exe", "Eclipse Adoptium/*/bin/java.exe",
                                "Microsoft/*/bin/java.exe"):
                    try:
                        for p in Path(base).glob(pattern):
                            add(str(p))
                    except OSError:
                        pass
        for c in manual:
            v = None
            try:
                out = subprocess.run([c, "-version"], capture_output=True, text=True, timeout=10)
                v = parse_java_version((out.stderr or "") + (out.stdout or ""))
            except Exception:
                pass
            cands.append((c, v))
    return cands


def find_java():
    best = None
    for c, v in find_java_candidates():
        if best is None or (best[1] or 0) < (v or 0):
            best = (c, v)
    return best


class App:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME)
        self.root.configure(bg=BG)
        self.root.geometry("680x560")
        self.root.minsize(580, 520)
        try:
            self.root.iconbitmap(ICON_ICO)
            self._icon_photo = tk.PhotoImage(file=ICON_PNG)
            self.root.iconphoto(True, self._icon_photo)
        except Exception:
            pass
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.process = None
        self.console_shown = False
        self._last_progress = 0.0
        self._game_window_open = False
        self._ram_vals = [2]
        self._ram_selectable = {2}
        self._ram_filling = False
        self._last_ram_label = ""
        os.makedirs(MC_DIR, exist_ok=True)
        self.settings = self._load_settings()
        self._playtime_total = self._load_playtime()
        self._session_start = None
        self._loader_compat = load_compat_cache() or {}
        self._version_ids = []
        self._cur_version_id = self.settings.get("version", "")
        self._install_ids = []

        self._setup_style()

        self.nick_var = tk.StringVar(value=self.settings.get("nick", ""))
        self.ram_var = tk.StringVar()
        self.version_var = tk.StringVar(value=self.settings.get("version", ""))
        self.status_var = tk.StringVar(value="")
        self.progress_var = tk.DoubleVar(value=0)

        self._build_ui()
        self._refresh_ram_options()
        self.ram_var.trace_add("write", self._on_ram_change)
        self.root.after(5000, self._tick_ram)
        self._center()
        self.refresh_versions(select=self.settings.get("version"))
        self._update_skin_btn()
        threading.Thread(target=self._compat_worker, daemon=True).start()

    def _compat_worker(self):
        cached = load_compat_cache()
        if cached is not None:
            self._loader_compat = cached
            self.root.after(0, self.refresh_versions)
            return
        try:
            compat = fetch_loader_compat()
        except Exception:
            return
        save_compat_cache(compat)
        self._loader_compat = compat
        self.root.after(0, self.refresh_versions)

    def _setup_style(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TCombobox", fieldbackground=BG2, background=BG2, foreground=FG,
                        arrowcolor=MUTED, bordercolor=BG3, lightcolor=BG3, darkcolor=BG3, padding=5)
        style.map("TCombobox", fieldbackground=[("readonly", BG2)], foreground=[("readonly", FG)],
                  selectbackground=[("readonly", BG2)], selectforeground=[("readonly", FG)])
        style.configure("TProgressbar", troughcolor=BG2, background=ACCENT, bordercolor=BG,
                        lightcolor=ACCENT, darkcolor=ACCENT)
        style.configure("Mods.Vertical.TScrollbar", troughcolor=BG, background=BG3,
                        bordercolor=BG, arrowcolor=MUTED, lightcolor=BG3, darkcolor=BG3,
                        relief="flat", borderwidth=0, arrowsize=12, width=10)
        style.map("Mods.Vertical.TScrollbar",
                  background=[("active", MUTED), ("pressed", MUTED)],
                  arrowcolor=[("active", FG)])

    def _build_ui(self):
        base = tk.Frame(self.root, bg=BG)
        base.pack(fill="both", expand=True)

        self.sidebar = tk.Frame(base, bg=BG2, width=170)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        self.nav_buttons = []
        try:
            self._logo_photo = tk.PhotoImage(file=ICON_PNG)
            logo = self._logo_photo.subsample(4, 4)
            tk.Label(self.sidebar, image=logo, bg=BG2).pack(pady=(12, 6))
        except Exception:
            pass
        for label, icon, page in (("Главная", "\u2302", "home"),
                                  ("Дополнительные", "\u2699", "extra"),
                                  ("Моды", "\u25A3", "mods")):
            btn = tk.Button(self.sidebar, text=f"{icon}  {label}", anchor="w", padx=14, pady=11,
                            bg=BG2, fg=FG, activebackground=BG3, activeforeground=FG,
                            relief="flat", bd=0, font=(FONT, 10), cursor="hand2",
                            command=lambda p=page: self._show_page(p))
            btn.pack(fill="x")
            self.nav_buttons.append((btn, page))

        tk.Frame(self.sidebar, bg=BG2).pack(fill="both", expand=True)

        self.changelog_btn = tk.Button(self.sidebar, text="≡  Изменения", anchor="w", padx=14, pady=9,
                                       bg=BG2, fg=FG, activebackground=BG3, activeforeground=FG,
                                       relief="flat", bd=0, font=(FONT, 10), cursor="hand2",
                                       command=lambda: self._show_page("changelog"))
        self.changelog_btn.pack(fill="x")
        self.nav_buttons.append((self.changelog_btn, "changelog"))


        tk.Label(self.sidebar, text=f"by cactunus {APP_VERSION}", font=(FONT, 8), fg=MUTED, bg=BG2)\
            .pack(fill="x", pady=(6, 10))

        self.container = tk.Frame(base, bg=BG)
        self.container.pack(side="left", fill="both", expand=True)
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        self.pages = {
            "home": self._build_home_page(self.container),
            "extra": self._build_extra_page(self.container),
            "mods": self._build_mods_page(self.container),
            "changelog": self._build_changelog_page(self.container),
        }
        for p in self.pages.values():
            p.grid(row=0, column=0, sticky="nsew")
        self._show_page("home")

    def _show_page(self, page):
        for btn, p in self.nav_buttons:
            btn.config(fg=ACCENT if p == page else FG)
        if page == "mods":
            self._refresh_mods_page()
        if page == "extra":
            self._render_skin_preview()
        self.pages[page].tkraise()

    def _build_home_page(self, parent):
        body = tk.Frame(parent, bg=BG)

        tk.Label(body, text="НИКНЕЙМ", font=(FONT, 9), fg=MUTED, bg=BG).pack(anchor="w", padx=20, pady=(20, 5))
        nickrow = tk.Frame(body, bg=BG)
        nickrow.pack(fill="x", padx=20)
        nick = tk.Entry(nickrow, textvariable=self.nick_var, font=(FONT, 12), bg=BG2, fg=FG,
                        insertbackground=FG, relief="flat", highlightthickness=1,
                        highlightbackground=BG3, highlightcolor=ACCENT)
        nick.pack(side="left", fill="x", expand=True, ipady=7)
        nick.bind("<Return>", lambda e: self.launch())
        self.skin_btn = tk.Button(nickrow, text="Скин", font=(FONT, 9, "bold"), fg=FG, bg=BG3,
                                  activebackground=BG2, activeforeground=ACCENT, relief="flat", bd=0,
                                  width=6, cursor="hand2", command=self._pick_skin)
        self.skin_btn.pack(side="left", padx=(8, 0), ipady=8)

        tk.Label(body, text="ВЕРСИЯ", font=(FONT, 9), fg=MUTED, bg=BG).pack(anchor="w", padx=20, pady=(14, 5))
        vrow = tk.Frame(body, bg=BG)
        vrow.pack(fill="x", padx=20)
        self.version_cb = ttk.Combobox(vrow, textvariable=self.version_var, state="readonly",
                                       font=(FONT, 12))
        self.version_cb.pack(side="left", fill="x", expand=True, ipady=4)
        self.version_cb.bind("<<ComboboxSelected>>", self._on_version_selected)
        add = tk.Button(vrow, text="+", font=(FONT, 14, "bold"), fg=FG, bg=BG3, activebackground=BG2,
                        activeforeground=ACCENT, relief="flat", bd=0, width=3, cursor="hand2",
                        command=self.open_install_dialog)
        add.pack(side="left", padx=(8, 0), ipady=2)

        tk.Label(body, text="ПАМЯТЬ (GB)", font=(FONT, 9), fg=MUTED, bg=BG).pack(anchor="w", padx=20, pady=(14, 5))
        self.ram_cb = ttk.Combobox(body, textvariable=self.ram_var, state="readonly",
                                   font=(FONT, 12), width=18)
        self.ram_cb.pack(anchor="w", padx=20, ipady=4)

        self.launch_btn = tk.Button(body, text="ИГРАТЬ", font=(FONT, 14, "bold"), fg="#06130b", bg=ACCENT,
                                    activebackground=ACCENT_DARK, activeforeground="#06130b",
                                    relief="flat", bd=0, cursor="hand2", command=self.launch)
        self.launch_btn.pack(fill="x", padx=20, ipady=10, pady=(22, 0))

        self.progress = ttk.Progressbar(body, variable=self.progress_var, maximum=100)

        self.status_label = tk.Label(body, textvariable=self.status_var, font=(FONT, 9), fg=MUTED, bg=BG,
                                     anchor="w", justify="left", wraplength=420)
        self.status_label.pack(fill="x", padx=20, pady=(12, 0))

        self.playtime_var = tk.StringVar(value=self._fmt_playtime(self._playtime_total))
        tk.Label(body, textvariable=self.playtime_var, font=(FONT, 9), fg=ACCENT, bg=BG,
                 anchor="w").pack(fill="x", padx=20, pady=(6, 0))

        self.log_btn = tk.Button(body, text="журнал", font=(FONT, 8), fg=MUTED, bg=BG3,
                                 activebackground=BG2, activeforeground=FG, relief="flat", bd=0,
                                 cursor="hand2", command=self.toggle_console)
        self.log_btn.pack(anchor="w", padx=20, pady=(8, 0))

        self.console = tk.Text(body, font=("Consolas", 8), bg="#0a0c0e", fg="#9fb3c8",
                               relief="flat", height=8, state="disabled")
        return body

    def _build_extra_page(self, parent):
        page = tk.Frame(parent, bg=BG)

        tk.Label(page, text="НАСТРОЙКИ", font=(FONT, 9), fg=MUTED, bg=BG).pack(anchor="w", padx=20, pady=(20, 10))

        tk.Label(page, text="Папка игры:", font=(FONT, 9), fg=MUTED, bg=BG).pack(anchor="w", padx=20)
        tk.Label(page, text=MC_DIR, font=(FONT, 9), fg=FG, bg=BG, justify="left",
                 wraplength=400).pack(anchor="w", padx=20, pady=(4, 0))

        open_btn = tk.Button(page, text="Открыть папку игры", font=(FONT, 10), fg=FG, bg=BG3,
                             activebackground=BG2, activeforeground=ACCENT, relief="flat", bd=0,
                             cursor="hand2", command=lambda: os.startfile(MC_DIR))
        open_btn.pack(anchor="w", padx=20, ipadx=10, ipady=5, pady=(12, 0))

        reset_btn = tk.Button(page, text="Сбросить настройки", font=(FONT, 10), fg=MUTED, bg=BG3,
                              activebackground=BG2, activeforeground=FG, relief="flat", bd=0,
                              cursor="hand2", command=self._reset_settings)
        reset_btn.pack(anchor="w", padx=20, ipadx=10, ipady=5, pady=(8, 0))

        skin_btn = tk.Button(page, text="Сбросить скин", font=(FONT, 10), fg=MUTED, bg=BG3,
                             activebackground=BG2, activeforeground=FG, relief="flat", bd=0,
                             cursor="hand2", command=self._reset_skin)
        skin_btn.pack(anchor="w", padx=20, ipadx=10, ipady=5, pady=(8, 0))

        tk.Label(page, text="ПРЕДПРОСМОТР СКИНА", font=(FONT, 9), fg=MUTED, bg=BG)\
            .pack(anchor="w", padx=20, pady=(18, 4))
        self.skin_preview = tk.Canvas(page, width=112, height=168, bg=BG2,
                                      highlightthickness=1, highlightbackground=BG3)
        self.skin_preview.pack(anchor="w", padx=20, pady=(0, 4))
        self._render_skin_preview()

        tk.Label(page, text="ПОДСИСТЕМА МОДОВ", font=(FONT, 9), fg=MUTED, bg=BG)\
            .pack(anchor="w", padx=20, pady=(18, 5))
        self.loader_cb = ttk.Combobox(page, values=LOADER_UI_VALUES, state="readonly", font=(FONT, 11))
        self.loader_cb.pack(anchor="w", padx=20, ipady=4)
        saved_loader = self.settings.get("loader", "none")
        self.loader_cb.current(LOADER_UI_IDS.index(saved_loader) if saved_loader in LOADER_UI_IDS else 0)
        self.loader_cb.bind("<<ComboboxSelected>>", self._on_loader_change)

        tk.Label(page, text="Не все версии совместимы со всеми подсистемами модов.\n"
                            "Буквы рядом с версией: F — Forge, G — Fabric, N — NeoForge.\n"
                            "С выбранной подсистемой несовместимые версии помечены «(недоступна)».",
                 font=(FONT, 8), fg=MUTED, bg=BG, justify="left", wraplength=400)\
            .pack(anchor="w", padx=20, pady=(10, 0))

        tk.Label(page, text="ОЗУ определяется автоматически. Пометка «заняты» — этой памяти\nсейчас не хватает, её выбрать нельзя.",
                 font=(FONT, 8), fg=MUTED, bg=BG, justify="left", wraplength=400)\
            .pack(anchor="w", padx=20, pady=(16, 0))

        tk.Label(page, text=f"by cactunus {APP_VERSION}", font=(FONT, 8), fg=MUTED, bg=BG)\
            .pack(side="bottom", pady=12)
        return page

    def _build_mods_page(self, parent):
        page = tk.Frame(parent, bg=BG)

        tk.Label(page, text="МОДЫ", font=(FONT, 9), fg=MUTED, bg=BG).pack(anchor="w", padx=20, pady=(20, 10))

        self._mods_empty = tk.Frame(page, bg=BG)
        tk.Label(self._mods_empty, text="Нет подсистемы модов", font=(FONT, 13, "bold"), fg=FG, bg=BG)\
            .pack(pady=(90, 6))
        tk.Label(self._mods_empty,
                 text="Выберите Forge, Fabric или NeoForge в «Дополнительных»,\nчтобы устанавливать моды.",
                 font=(FONT, 9), fg=MUTED, bg=BG, justify="center").pack()
        tk.Button(self._mods_empty, text="Открыть «Дополнительные»", font=(FONT, 10), fg=FG, bg=BG3,
                  activebackground=BG2, activeforeground=ACCENT, relief="flat", bd=0, cursor="hand2",
                  command=lambda: self._show_page("extra")).pack(pady=(16, 0), ipadx=10, ipady=5)

        self._mods_center = tk.Frame(page, bg=BG)
        canvas = tk.Canvas(self._mods_center, bg=BG, highlightthickness=0)
        sb = ttk.Scrollbar(self._mods_center, orient="vertical", command=canvas.yview,
                           style="Mods.Vertical.TScrollbar")
        inner = tk.Frame(canvas, bg=BG)
        self._mods_inner = inner
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        self._mods_canvas = canvas
        self._mods_window = win
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        self._last_catalog_cols = 0
        canvas.bind("<Configure>", self._on_mods_canvas_resize)
        self._bind_mods_wheel(canvas)

        self._mods_status_var = tk.StringVar(value="")
        self._mods_block = tk.Frame(inner, bg=BG2, highlightthickness=2, highlightbackground=BG3)
        self._mods_block.pack(fill="x", padx=20, pady=(14, 0))

        icon = tk.Canvas(self._mods_block, width=64, height=78, bg=BG2, highlightthickness=0)
        icon.pack(pady=(22, 6))
        icon.create_rectangle(14, 8, 50, 66, fill=BG3, outline=FG, width=2)
        icon.create_polygon(32, 8, 50, 8, 50, 26, fill=BG3, outline=FG, width=2)
        icon.create_line(20, 38, 44, 38, fill=MUTED, width=2)
        icon.create_line(20, 46, 44, 46, fill=MUTED, width=2)
        icon.create_line(20, 54, 36, 54, fill=MUTED, width=2)

        tk.Label(self._mods_block, text="Здесь вы можете загрузить свои файлы", font=(FONT, 12), fg=FG, bg=BG2)\
            .pack(pady=(8, 4))
        self._mods_hint_var = tk.StringVar()
        tk.Label(self._mods_block, textvariable=self._mods_hint_var, font=(FONT, 9), fg=MUTED, bg=BG2)\
            .pack(pady=(0, 18))
        tk.Label(self._mods_block, textvariable=self._mods_status_var, font=(FONT, 9), fg=ACCENT, bg=BG2)\
            .pack(pady=(0, 12))
        tk.Button(self._mods_block, text="ЗАГРУЗИТЬ ВРУЧНУЮ", font=(FONT, 9, "bold"), fg="#06130b",
                  bg=ACCENT, activebackground=ACCENT_DARK, activeforeground="#06130b", relief="flat",
                  bd=0, cursor="hand2", command=self._pick_mod).pack(pady=(0, 16), ipadx=12, ipady=5)

        tk.Label(inner, text="ПОИСК МОДОВ НА MODRINTH", font=(FONT, 9, "bold"), fg=FG, bg=BG)\
            .pack(anchor="w", padx=20, pady=(16, 2))
        search_row = tk.Frame(inner, bg=BG)
        search_row.pack(fill="x", padx=20, pady=(2, 0))
        self._search_var = tk.StringVar()
        search_entry = tk.Entry(search_row, textvariable=self._search_var, font=(FONT, 9),
                                 bg=BG3, fg=FG, insertbackground=FG, relief="flat")
        search_entry.pack(side="left", fill="x", expand=True, ipady=7, ipadx=8)
        search_entry.bind("<Return>", lambda e: self._search_mods())
        tk.Button(search_row, text="НАЙТИ", font=(FONT, 9, "bold"), fg="#06130b",
                  bg=ACCENT, activebackground=ACCENT_DARK, activeforeground="#06130b",
                  relief="flat", bd=0, cursor="hand2",
                  command=self._search_mods).pack(side="left", padx=(8, 0), ipadx=10, ipady=5)
        filter_row = tk.Frame(inner, bg=BG)
        filter_row.pack(fill="x", padx=20, pady=(4, 0))
        tk.Label(filter_row, text="Подсистема:", font=(FONT, 8), fg=MUTED, bg=BG)\
            .pack(side="left")
        saved_loader = self.settings.get("loader", "none")
        search_loader_vals = ["Все", "Forge", "Fabric", "NeoForge"]
        search_loader_ids = ["all", "forge", "fabric", "neoforge"]
        self._search_loader_var = tk.StringVar(
            value=search_loader_vals[search_loader_ids.index(saved_loader)] if saved_loader in search_loader_ids else "Все")
        sl = ttk.Combobox(filter_row, textvariable=self._search_loader_var, values=search_loader_vals,
                          state="readonly", font=(FONT, 8), width=9)
        sl.pack(side="left", padx=(6, 12))
        self._search_loader_ids = search_loader_ids
        self._search_loader_vals = search_loader_vals
        tk.Label(filter_row, text="Сортировка:", font=(FONT, 8), fg=MUTED, bg=BG).pack(side="left")
        self._search_sort_var = tk.StringVar(value="Популярные")
        ss = ttk.Combobox(filter_row, textvariable=self._search_sort_var,
                          values=["Популярные", "Совместимые", "Новые"],
                          state="readonly", font=(FONT, 8), width=12)
        ss.pack(side="left", padx=(6, 0))
        self._search_status_var = tk.StringVar(value="")
        tk.Label(inner, textvariable=self._search_status_var, font=(FONT, 8), fg=ACCENT, bg=BG)\
            .pack(anchor="w", padx=20, pady=(6, 0))
        self._search_grid = tk.Frame(inner, bg=BG)
        self._search_grid.pack(fill="x", padx=12, pady=(2, 0))
        self._search_tile_state = {}
        self._search_avatars = []

        tk.Label(inner,
                 text="Мы не ручаемся за ошибки при таком переносе, если мод не подойдёт\n"
                      "под подсистему модов или если он скачан не на ту версию.",
                 font=(FONT, 8), fg=MUTED, bg=BG, justify="center").pack(pady=(12, 0))

        self._mods_hint_var.set("Перетащите сюда файл мода (например, .jar)" if DND_AVAILABLE
                                else "Нажмите на блок или кнопку ниже, чтобы выбрать файл")
        if DND_AVAILABLE:
            targets = [self._mods_block, icon]
            targets += list(self._mods_block.winfo_children())
            for w in targets:
                try:
                    w.drop_target_register(DND_FILES)
                    w.dnd_bind("<<Drop>>", self._on_drop)
                    w.dnd_bind("<<DragEnter>>", self._on_drag_enter)
                    w.dnd_bind("<<DragLeave>>", self._on_drag_leave)
                except Exception:
                    pass

        def open_picker(e=None):
            self._pick_mod()

        for w in (self._mods_block, icon):
            w.config(cursor="hand2")
            w.bind("<Button-1>", open_picker)

        self._catalog_state_var = tk.StringVar(value="Каталог загружается...")
        tk.Label(inner, text="КАТАЛОГ МОДОВ", font=(FONT, 9, "bold"), fg=FG, bg=BG)\
            .pack(anchor="w", padx=20, pady=(20, 2))
        tk.Label(inner, text="Sodium — нужен Fabric. OptiFine — для Forge или ванили.\n"
                             "Скачанный мод автоматически попадёт в папку mods.",
                 font=(FONT, 8), fg=MUTED, bg=BG, justify="left").pack(anchor="w", padx=20)
        tk.Label(inner, textvariable=self._catalog_state_var, font=(FONT, 8), fg=ACCENT, bg=BG)\
            .pack(anchor="w", padx=20, pady=(6, 0))
        self._catalog_grid = tk.Frame(inner, bg=BG)
        self._catalog_grid.pack(fill="x", padx=12, pady=(2, 0))
        self._tile_state = {}
        self._catalog_data = {}


        self._installed_header_var = tk.StringVar(value="УСТАНОВЛЕННЫЕ МОДЫ")
        tk.Label(inner, textvariable=self._installed_header_var, font=(FONT, 9, "bold"), fg=FG, bg=BG)\
            .pack(anchor="w", padx=20, pady=(16, 4))
        self._installed_list = tk.Frame(inner, bg=BG)
        self._installed_list.pack(fill="x", padx=20)
        tk.Button(inner, text="Открыть папку mods", font=(FONT, 9), fg=FG, bg=BG3,
                  activebackground=BG2, activeforeground=ACCENT, relief="flat", bd=0, cursor="hand2",
                  command=self._open_mods_dir).pack(anchor="w", padx=20, pady=(10, 0), ipadx=8, ipady=4)
        tk.Label(inner, text=f"by cactunus {APP_VERSION}", font=(FONT, 8), fg=MUTED, bg=BG)\
            .pack(pady=(12, 12))
        return page

    def _bind_wheel_recursive(self, widget, canvas):
        # Колесо мыши обрабатывается одним глобальным обработчиком (_bind_mods_wheel),
        # поэтому отдельные привязки к каждому виджету больше не нужны.
        return

    def _bind_mods_wheel(self, canvas):
        def on_wheel(e):
            try:
                root_path = str(self._mods_center)
                widget_path = str(e.widget)
            except Exception:
                return None
            if widget_path != root_path and not widget_path.startswith(root_path + "."):
                return None
            try:
                if not canvas.winfo_exists():
                    return None
                first, last = canvas.yview()
            except Exception:
                return None
            if first <= 0.0 and last >= 1.0:
                return "break"
            num = getattr(e, "num", 0)
            if num == 4:
                step = -3
            elif num == 5:
                step = 3
            else:
                delta = getattr(e, "delta", 0) or 0
                if delta == 0:
                    return "break"
                if abs(delta) >= 120:
                    step = -int(delta / 120) * 3
                else:
                    step = -int(delta) * 3
                    if step == 0:
                        step = -1 if delta > 0 else 1
            try:
                canvas.yview_scroll(step, "units")
            except Exception:
                pass
            return "break"

        self._mods_wheel_handler = on_wheel
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            try:
                self.root.bind_all(seq, on_wheel, add="+")
            except Exception:
                pass

    def _on_mods_canvas_resize(self, e=None):
        win = getattr(self, "_mods_window", None)
        if e is not None and win is not None:
            try:
                self._mods_canvas.itemconfigure(win, width=e.width)
            except Exception:
                pass
        cols = self._flow_columns()
        if cols != getattr(self, "_last_catalog_cols", 0):
            self._last_catalog_cols = cols
            if getattr(self, "_catalog_data", None):
                self._rebuild_catalog()

    def _refresh_mods_page(self):
        if not hasattr(self, "_mods_center"):
            return
        self._mods_empty.pack_forget()
        self._mods_center.pack(fill="both", expand=True)
        self._refresh_installed_mods()
        self._load_catalog_async()

    def _mods_dir(self):
        version = self._current_version()
        loader = self.settings.get("loader", "none")
        if loader in ("forge", "neoforge") and version:
            m = re.match(r"(\d+)\.(\d+)", version)
            if m and (int(m.group(1)) > 1 or int(m.group(2)) >= 13):
                return os.path.join(MC_DIR, "versions", version, "mods")
        return os.path.join(MC_DIR, "mods")

    def _drop_highlight(self, on):
        self._mods_block.config(highlightbackground=ACCENT if on else BG3)

    def _on_drag_enter(self, e=None):
        self._drop_highlight(True)

    def _on_drag_leave(self, e=None):
        self._drop_highlight(False)

    def _on_drop(self, event):
        self._drop_highlight(False)
        paths = self.root.tk.splitlist(event.data)
        if not paths:
            return
        path = paths[0]
        if os.path.isdir(path):
            messagebox.showinfo(APP_NAME, "Перетащите файл мода, а не папку.")
            return
        ext = os.path.splitext(path)[1].lower()
        if ext not in (".jar", ".zip"):
            messagebox.showwarning(APP_NAME, "Моды обычно бывают файлами .jar.\nВыберите файл .jar или .zip.")
            return
        self._install_mod(path)

    def _pick_mod(self):
        paths = filedialog.askopenfilenames(
            title="Выберите моды",
            filetypes=[("Файлы модов", "*.jar *.zip"), ("Все файлы", "*.*")])
        for p in paths:
            self._install_mod(p)

    def _install_mod(self, src):
        name = os.path.basename(src)
        dst_dir = self._mods_dir()
        try:
            os.makedirs(dst_dir, exist_ok=True)
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Не удалось создать папку модов:\n{e}")
            return
        dst = os.path.join(dst_dir, name)
        if os.path.isfile(dst) and not messagebox.askyesno(
                APP_NAME, f"«{name}» уже есть в папке модов.\nЗаменить его?"):
            return
        self._mods_status_var.set("Мод загружается в папку...")
        start = time.time()

        def job():
            try:
                shutil.copy2(src, dst)
                remain = 1.0 - (time.time() - start)
                if remain > 0:
                    time.sleep(remain)
                self.root.after(0, lambda: self._mods_status_var.set(f"Мод загружен: {name}"))
                self.root.after(0, self._status, f"Мод загружен: {name}")
            except Exception as e:
                self.root.after(0, lambda: self._mods_status_var.set("Ошибка загрузки мода."))
                self.root.after(0, messagebox.showerror, APP_NAME, f"Не удалось скопировать файл:\n{e}")

        threading.Thread(target=job, daemon=True).start()

    def _load_catalog_async(self):
        if getattr(self, "_catalog_loading", False):
            return
        cached = mod_catalog.load_cache(MC_DIR)
        if cached is not None:
            self._catalog_data = cached
            self._rebuild_catalog()
            return
        self._catalog_loading = True
        self._catalog_state_var.set("Каталог загружается...")
        threading.Thread(target=self._catalog_worker, daemon=True).start()

    def _catalog_worker(self):
        try:
            data = mod_catalog.fetch_catalog()
            mod_catalog.save_cache(MC_DIR, data)
        except Exception:
            self.root.after(0, lambda: self._catalog_state_var.set(
                "Не удалось загрузить каталог. Проверьте интернет."))
            self._catalog_loading = False
            return
        self._catalog_loading = False
        self._catalog_data = data
        self.root.after(0, self._rebuild_catalog)

    def _rebuild_catalog(self):
        for w in self._catalog_grid.winfo_children():
            w.destroy()
        self._tile_state = {}
        self._catalog_avatars = []
        data = self._catalog_data
        if not data:
            self._catalog_state_var.set("Каталог пуст или не загрузился.")
            return
        cur_series = mod_catalog.series_of(self._current_version())
        loader = self.settings.get("loader", "none")
        mods = [m for m in mod_catalog.CATALOG
                if loader == "none" or loader in (m.get("loaders") or [])
                or (m.get("id") == "optifine" and loader in ("forge", "none"))
                or m.get("id") in ("sodium", "zoomify", "voxy")]
        cols = self._flow_columns()
        for c in range(12):
            if c < cols:
                self._catalog_grid.grid_columnconfigure(c, weight=1, uniform="tile")
            else:
                self._catalog_grid.grid_columnconfigure(c, weight=0, uniform="")
        count = 0
        for mod in mods:
            versions = data.get(mod["id"]) or {}
            i = count
            count += 1
            tile = tk.Frame(self._catalog_grid, bg=BG2, highlightthickness=1,
                            highlightbackground=BG3, width=300, height=116)
            tile.grid(row=i // cols, column=i % cols, padx=8, pady=(10, 0), sticky="new")
            tile.grid_propagate(False)
            tile.pack_propagate(False)

            avatar = tk.Canvas(tile, width=48, height=48, bg=BG2, highlightthickness=0)
            avatar.pack(side="left", padx=(12, 10), pady=12)
            info = tk.Frame(tile, bg=BG2)
            info.pack(side="left", fill="both", expand=True, padx=(0, 12), pady=10)
            photo = self._mod_icon_photo(mod.get("icon_b64"))
            if photo is not None:
                avatar.create_image(24, 24, image=photo)
            else:
                avatar.create_rectangle(2, 2, 46, 46, fill=mod["color"], outline=mod["color"])
                avatar.create_text(24, 24, text=mod["name"][0], fill="#ffffff",
                                   font=(FONT, 16, "bold"))

            tk.Label(info, text=mod["name"], font=(FONT, 11, "bold"), fg=FG, bg=BG2,
                     anchor="w").pack(fill="x")
            tk.Label(info, text=mod["note"], font=(FONT, 8), fg=MUTED, bg=BG2,
                     wraplength=230, justify="left", anchor="w").pack(fill="x", pady=(1, 6))

            bottom = tk.Frame(info, bg=BG2)
            bottom.pack(fill="x", pady=(0, 2))
            series_keys = sorted(versions, key=mod_catalog.version_sort_key, reverse=True)
            labels = []
            for v in series_keys:
                loaders = (versions.get(v) or {}).get("loaders") or []
                if not loaders:
                    letters = " ".join(LOADER_LETTERS[l] for l in LOADER_IDS if l in self._compat_for(v))
                else:
                    letters = " ".join(LOADER_LETTERS.get(l, "") for l in loaders if l in LOADER_LETTERS)
                label = v + ((" " + letters.strip()) if letters.strip() else "")
                if mod_catalog.matches_series(v, cur_series):
                    label += " (рекомендовано)"
                labels.append(label)
            var = tk.StringVar()
            state = {"button": None, "var": var, "keys": series_keys,
                     "busy": False, "name": mod["name"]}
            self._tile_state[mod["id"]] = state
            cb = ttk.Combobox(bottom, textvariable=var, values=labels, state="readonly",
                              font=(FONT, 9), width=17, height=25)
            cb.pack(side="left")
            state["cb"] = cb
            state["labels"] = labels
            if labels:
                idx = next((k for k, v in enumerate(series_keys)
                            if mod_catalog.matches_series(v, cur_series)), 0)
                var.set(labels[idx])
            else:
                cb.config(state="disabled")
            btn = tk.Button(bottom, text="УСТАНОВИТЬ", font=(FONT, 8, "bold"), fg="#06130b",
                            bg=ACCENT, activebackground=ACCENT_DARK, activeforeground="#06130b",
                            relief="flat", bd=0, cursor="hand2", width=8,
                            command=lambda mid=mod["id"]: self._install_catalog_mod(mid))
            btn.pack(side="right")
            state["button"] = btn
        self._bind_wheel_recursive(self._catalog_grid, self._mods_canvas)
        if not count:
            self._catalog_state_var.set("Каталог пуст или не загрузился.")
            return
        self._catalog_state_var.set("")

    def _flow_columns(self):
        try:
            width = self._mods_canvas.winfo_width()
        except Exception:
            width = 0
        if width < 60:
            try:
                width = self._catalog_grid.winfo_width()
            except Exception:
                width = 0
        if width < 60:
            width = 660
        cols = max(1, (width - 24) // (320 + 16))
        return cols

    def _mod_icon_photo(self, b64):
        if not b64:
            return None
        try:
            import base64
            import io
            from PIL import Image, ImageTk
            img = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGBA")
            img = img.resize((46, 46), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
        except Exception:
            try:
                photo = tk.PhotoImage(data=b64)
            except Exception:
                return None
        self._catalog_avatars.append(photo)
        return photo

    def _install_catalog_mod(self, mod_id):
        state = self._tile_state.get(mod_id)
        if not state or state.get("busy"):
            return
        label = state["var"].get()
        if not label:
            messagebox.showinfo(APP_NAME, "Для этой версии мод недоступен.")
            return
        m = re.match(r"(\d+\.\d+(?:\.\d+)?)", label)
        if not m:
            return
        series = m.group(1)
        info = (self._catalog_data.get(mod_id) or {}).get(series)
        if not info:
            return
        dst = self._catalog_dst(mod_id, info, series)
        if os.path.isfile(dst) and not messagebox.askyesno(
                APP_NAME, f"«{os.path.basename(dst)}» уже есть в папке модов.\nЗаменить его?"):
            return
        state["busy"] = True
        state["button"].config(state="disabled", text="0.0 МБ")
        threading.Thread(target=self._catalog_install_worker,
                         args=(mod_id, series, info, state, dst), daemon=True).start()

    def _catalog_dst(self, mod_id, info, series):
        mods_dir = self._mods_dir()
        if mod_id == "optifine":
            ed = info["filename"][len("OptiFine_"):-len(".jar")]
            return os.path.join(mods_dir, "OptiFine_" + ed + "_MOD.jar")
        return os.path.join(mods_dir, info["filename"])

    def _catalog_install_worker(self, mod_id, series, info, state, dst):
        err = None
        tmp = os.path.join(os.path.dirname(dst), ".download_" + uuid.uuid4().hex[:8] + ".part")
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if mod_id == "optifine":
                err = self._install_optifine(series, info, dst, state)
            else:
                self._download_stream(info["url"], tmp, state, total=info.get("size"))
                os.replace(tmp, dst)
        except Exception as e:
            err = str(e)
        finally:
            try:
                os.remove(tmp)
            except Exception:
                pass
        self.root.after(0, lambda: self._tile_after_done(state, mod_id, err))

    def _download_stream(self, url, dst, state, total=None):
        req = urllib.request.Request(url, headers={"User-Agent": mod_catalog.UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            total = total or int(r.headers.get("Content-Length") or 0) or None
            done = 0
            last = [0.0]
            with open(dst, "wb") as f:
                while True:
                    chunk = r.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    now = time.time()
                    if now - last[0] >= 0.15:
                        last[0] = now
                        text = self._mb_text(done, total)
                        self.root.after(0, lambda t=text: state["button"].config(text=t))
        return done

    def _mb_text(self, done, total):
        if total:
            return f"{done / 1048576:.1f}/{total / 1048576:.1f} МБ"
        return f"{done / 1048576:.1f} МБ"

    def _install_optifine(self, series, info, dst, state):
        page = mod_catalog._get(info["url"]).decode("iso-8859-1", "replace")
        m = re.search(r"downloadx\?f=([^\"'&]+)&x=([^\"'&]+)", page)
        if not m:
            raise RuntimeError("Не удалось получить ссылку на скачивание OptiFine")
        dl = "https://optifine.net/downloadx?f=" + m.group(1) + "&x=" + m.group(2)
        installer_tmp = os.path.join(os.environ.get("TEMP", MC_DIR),
                                     "of_" + uuid.uuid4().hex[:8] + ".jar")
        try:
            self._download_stream(dl, installer_tmp, state, total=None)
            self.root.after(0, lambda: state["button"].config(text="УСТАНОВКА"))
            self._run_optifine_installer(series, info, installer_tmp, dst)
        finally:
            try:
                os.remove(installer_tmp)
            except Exception:
                pass
        return None

    def _run_optifine_installer(self, series, info, installer_jar, dst):
        base_jar = os.path.join(MC_DIR, "versions", series, series + ".jar")
        if not os.path.isfile(base_jar):
            raise RuntimeError(f"Сначала установите и запустите версию {series}")
        ed = info["filename"][len("OptiFine_"):-len(".jar")]
        lp = os.path.join(MC_DIR, "launcher_profiles.json")
        lp_created = not os.path.isfile(lp)
        lp_backup = None
        if not lp_created:
            lp_backup = lp + ".bak"
            try:
                shutil.copy2(lp, lp_backup)
            except Exception:
                lp_backup = None
        else:
            with open(lp, "w", encoding="utf-8") as f:
                f.write('{"profiles":{}}')
        base = tempfile.mkdtemp(prefix="of_")
        link = os.path.join(base, ".minecraft")
        try:
            java, _ver = find_java()
            if not java:
                raise RuntimeError("Не найдена Java для установщика OptiFine")
            res = subprocess.run(["cmd", "/c", "mklink", "/J", link, MC_DIR],
                                 capture_output=True)
            if res.returncode != 0:
                raise RuntimeError("Не удалось подготовить папку установки")
            env = dict(os.environ)
            env["APPDATA"] = base
            res = subprocess.run([java, "-cp", installer_jar, "optifine.Installer"],
                                 env=env, capture_output=True, text=True, timeout=300)
            patched = os.path.join(MC_DIR, "libraries", "optifine", "OptiFine", ed,
                                   "OptiFine-" + ed + ".jar")
            if not os.path.isfile(patched):
                raise RuntimeError("Установщик OptiFine не сработал (код " + str(res.returncode) + ")")
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(patched, dst)
            ed_short = "_".join(ed.split("_")[1:])
            for junk in (os.path.join(MC_DIR, "versions", series + "-OptiFine_" + ed_short),
                         os.path.join(MC_DIR, "libraries", "optifine")):
                try:
                    shutil.rmtree(junk, ignore_errors=True)
                except Exception:
                    pass
        finally:
            try:
                os.rmdir(link)
            except Exception:
                pass
            try:
                shutil.rmtree(base, ignore_errors=True)
            except Exception:
                pass
            if lp_backup and os.path.isfile(lp_backup):
                try:
                    shutil.copy2(lp_backup, lp)
                    os.remove(lp_backup)
                except Exception:
                    pass
            if lp_created:
                try:
                    os.remove(lp)
                except Exception:
                    pass

    def _tile_after_done(self, state, mod_id, err):
        btn = state["button"]
        state["busy"] = False
        if err:
            btn.config(state="normal", text="УСТАНОВИТЬ")
            messagebox.showerror(APP_NAME, f"Ошибка установки:\n{err}")
            return
        btn.config(state="normal", text="ГОТОВО", command=self._open_mods_dir)
        self._refresh_installed_mods()
        self._status(f"Мод установлен: {state['name']}")

    def _search_mods(self):
        query = self._search_var.get().strip()
        if not query:
            for w in self._search_grid.winfo_children():
                w.destroy()
            self._search_tile_state = {}
            self._search_avatars = []
            self._search_status_var.set("")
            return
        if getattr(self, "_search_loading", False):
            return
        self._search_loading = True
        self._search_status_var.set("Поиск...")
        sl_id = self._search_loader_var.get()
        loader = self._search_loader_ids[self._search_loader_vals.index(sl_id)] if sl_id in self._search_loader_vals else "all"
        sort = self._search_sort_var.get()
        index = "relevance"
        if sort == "Новые":
            index = "newest"
        elif sort == "Совместимые":
            index = "relevance"
        series = mod_catalog.series_of(self._current_version())
        if not series:
            series = None
        threading.Thread(target=self._search_worker,
                         args=(query, loader, index, series), daemon=True).start()

    def _search_worker(self, query, loader, index, series):
        try:
            results = mod_catalog.search_modrinth_mods(
                query, loader=loader, index=index, series=series)
        except Exception:
            results = []
        self._search_loading = False
        self.root.after(0, lambda: self._rebuild_search_results(results))

    def _rebuild_search_results(self, results):
        for w in self._search_grid.winfo_children():
            w.destroy()
        self._search_tile_state = {}
        self._search_avatars = []
        if not results:
            self._search_status_var.set("Ничего не найдено.")
            return
        self._search_status_var.set(f"Найдено: {len(results)}")
        cols = self._flow_columns()
        for c in range(12):
            if c < cols:
                self._search_grid.grid_columnconfigure(c, weight=1, uniform="stile")
            else:
                self._search_grid.grid_columnconfigure(c, weight=0, uniform="")
        cur_series = mod_catalog.series_of(self._current_version())
        for i, mod in enumerate(results):
            tile = tk.Frame(self._search_grid, bg=BG2, highlightthickness=1,
                            highlightbackground=BG3, width=300, height=116)
            tile.grid(row=i // cols, column=i % cols, padx=8, pady=(10, 0), sticky="new")
            tile.grid_propagate(False)
            tile.pack_propagate(False)

            avatar = tk.Canvas(tile, width=48, height=48, bg=BG2, highlightthickness=0)
            avatar.pack(side="left", padx=(12, 10), pady=12)
            info = tk.Frame(tile, bg=BG2)
            info.pack(side="left", fill="both", expand=True, padx=(0, 12), pady=10)
            photo = self._net_icon_photo(mod.get("icon_url"), self._search_avatars)
            if photo is not None:
                avatar.create_image(24, 24, image=photo)
            else:
                avatar.create_rectangle(2, 2, 46, 46, fill=mod["color"], outline=mod["color"])
                avatar.create_text(24, 24, text=(mod["name"][:1] or "?"), fill="#ffffff",
                                   font=(FONT, 16, "bold"))

            name = mod["name"]
            if mod.get("compatible"):
                name += " ✓"
            tk.Label(info, text=name[:26], font=(FONT, 11, "bold"), fg=FG, bg=BG2,
                     anchor="w").pack(fill="x")
            tk.Label(info, text=mod["note"] or " ", font=(FONT, 8), fg=MUTED, bg=BG2,
                     wraplength=230, justify="left", anchor="w").pack(fill="x", pady=(1, 6))

            bottom = tk.Frame(info, bg=BG2)
            bottom.pack(fill="x", pady=(0, 2))
            var = tk.StringVar()
            state = {"button": None, "var": var, "keys": [], "busy": False, "name": mod["name"],
                     "mod": mod}
            self._search_tile_state[mod["id"]] = state
            cb = ttk.Combobox(bottom, textvariable=var, values=["загрузка..."], state="readonly",
                              font=(FONT, 9), width=17, height=25)
            var.set("загрузка...")
            cb.config(state="disabled")
            cb.pack(side="left")
            state["cb"] = cb
            state["labels"] = []
            btn = tk.Button(bottom, text="УСТАНОВИТЬ", font=(FONT, 8, "bold"), fg="#06130b",
                            bg=ACCENT, activebackground=ACCENT_DARK, activeforeground="#06130b",
                            relief="flat", bd=0, cursor="hand2", width=8,
                            command=lambda mid=mod["id"], m=mod: self._install_search_mod(mid, m))
            btn.pack(side="right")
            state["button"] = btn
            threading.Thread(target=self._search_versions_worker,
                             args=(mod["id"], mod, cur_series), daemon=True).start()
        self._bind_wheel_recursive(self._search_grid, self._mods_canvas)

    def _search_versions_worker(self, mod_id, mod, cur_series):
        try:
            versions = mod_catalog.fetch_modrinth_project_versions(mod["project"])
        except Exception:
            versions = {}
        self.root.after(0, lambda: self._fill_search_versions(mod_id, versions, cur_series))

    def _fill_search_versions(self, mod_id, versions, cur_series):
        state = self._search_tile_state.get(mod_id)
        if not state:
            return
        cb = state.get("cb")
        try:
            if cb is None or not cb.winfo_exists():
                return
        except Exception:
            return
        keys = sorted(versions, key=mod_catalog.version_sort_key, reverse=True)
        labels = []
        for v in keys:
            loaders = (versions.get(v) or {}).get("loaders") or []
            letters = " ".join(LOADER_LETTERS.get(l, "") for l in loaders if l in LOADER_LETTERS)
            label = v + ((" " + letters.strip()) if letters.strip() else "")
            if mod_catalog.matches_series(v, cur_series):
                label += " (рекомендовано)"
            labels.append(label)
        state["keys"] = keys
        state["labels"] = labels
        if not labels:
            state["var"].set("нет версий")
            cb.config(values=[], state="disabled")
            return
        cb.config(values=labels, state="readonly")
        idx = next((k for k, v in enumerate(keys) if mod_catalog.matches_series(v, cur_series)), 0)
        state["var"].set(labels[idx])

    def _selected_series(self, state):
        keys = state.get("keys") or []
        labels = state.get("labels") or []
        try:
            return keys[labels.index(state["var"].get())]
        except Exception:
            return None

    def _net_icon_photo(self, icon_url, cache_list):
        if not icon_url:
            return None
        try:
            import base64
            import io
            from PIL import Image, ImageTk
            req = urllib.request.Request(icon_url, headers={"User-Agent": mod_catalog.UA})
            with urllib.request.urlopen(req, timeout=6) as r:
                raw = r.read()
            img = Image.open(io.BytesIO(raw)).convert("RGBA")
            img = img.resize((46, 46), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
        except Exception:
            return None
        cache_list.append(photo)
        return photo

    def _install_search_mod(self, mod_id, mod):
        state = self._search_tile_state.get(mod_id)
        if not state or state.get("busy"):
            return
        state["chosen"] = self._selected_series(state)
        state["busy"] = True
        btn = state["button"]
        btn.config(state="disabled", text="...")
        threading.Thread(target=self._install_search_mod_worker,
                         args=(mod_id, mod, state), daemon=True).start()

    def _install_search_mod_worker(self, mod_id, mod, state):
        err = None
        dst = None
        try:
            versions = mod_catalog.fetch_modrinth_project_versions(mod["project"])
            series = state.get("chosen") or mod_catalog.series_of(self._current_version())
            info = versions.get(series)
            if not info:
                keys = sorted(versions, key=mod_catalog.version_sort_key, reverse=True)
                info = versions.get(keys[0]) if keys else None
            if not info:
                raise RuntimeError("Нет подходящей версии для этого мода.")
            mods_dir = self._mods_dir()
            os.makedirs(mods_dir, exist_ok=True)
            dst = os.path.join(mods_dir, info["filename"])
            tmp = os.path.join(mods_dir, ".download_" + uuid.uuid4().hex[:8] + ".part")
            self._download_stream(info["url"], tmp, state, total=info.get("size"))
            os.replace(tmp, dst)
        except Exception as e:
            err = str(e)
        self.root.after(0, lambda: self._tile_after_done(state, mod_id, err))

    def _list_mods(self):
        d = self._mods_dir()
        try:
            return sorted([f for f in os.listdir(d)
                           if os.path.isfile(os.path.join(d, f))
                           and f.lower().endswith((".jar", ".zip"))], key=str.lower)
        except Exception:
            return []

    def _refresh_installed_mods(self):
        if not hasattr(self, "_installed_list"):
            return
        for w in self._installed_list.winfo_children():
            w.destroy()
        mods = self._list_mods()
        self._installed_header_var.set(f"УСТАНОВЛЕННЫЕ МОДЫ ({len(mods)})")
        if not mods:
            tk.Label(self._installed_list, text="Пока пусто — моды появятся здесь после установки.",
                     font=(FONT, 9), fg=MUTED, bg=BG, anchor="w").pack(fill="x", pady=(2, 0))
            return
        mods_dir = self._mods_dir()
        for name in mods:
            row = tk.Frame(self._installed_list, bg=BG)
            row.pack(fill="x", pady=3)
            path = os.path.join(mods_dir, name)
            size = self._fmt_size(os.path.getsize(path)) if os.path.isfile(path) else ""
            tk.Label(row, text=name + (f"  ({size})" if size else ""), font=(FONT, 9), fg=FG, bg=BG,
                     anchor="w").pack(side="left", fill="x", expand=True)
            tk.Button(row, text="Удалить", font=(FONT, 8), fg="#f2b8b3", bg=BG3, activebackground=BG2,
                      activeforeground="#ff6b61", relief="flat", bd=0, cursor="hand2",
                      command=lambda n=name: self._remove_installed_mod(n)).pack(side="right")

    def _remove_installed_mod(self, name):
        if not messagebox.askyesno(APP_NAME, f"Удалить мод «{name}»?"):
            return
        try:
            os.remove(os.path.join(self._mods_dir(), name))
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Не удалось удалить:\n{e}")
            return
        self._refresh_installed_mods()
        self._status(f"Мод удалён: {name}")

    def _open_mods_dir(self):
        d = self._mods_dir()
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            pass
        try:
            os.startfile(d)
        except Exception as e:
            messagebox.showerror(APP_NAME, str(e))

    @staticmethod
    def _fmt_size(n):
        if n is None:
            return ""
        if n >= 1024 * 1024:
            return f"{n / (1024 * 1024):.1f} МБ"
        return f"{n / 1024:.0f} КБ"

    def _build_changelog_page(self, parent):
        page = tk.Frame(parent, bg=BG)
        tk.Label(page, text="ИЗМЕНЕНИЯ", font=(FONT, 9), fg=MUTED, bg=BG).pack(anchor="w", padx=20, pady=(20, 8))

        wrap = tk.Frame(page, bg=BG)
        wrap.pack(fill="both", expand=True, padx=(20, 12), pady=(0, 16))
        text = tk.Text(wrap, bg=BG, fg=FG, font=(FONT, 9), relief="flat", bd=0, wrap="word",
                       state="disabled", cursor="arrow")
        sb = tk.Scrollbar(wrap, command=text.yview, bg=BG2, activebackground=BG3, troughcolor=BG)
        text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        text.pack(side="left", fill="both", expand=True)

        text.tag_configure("ver", foreground=ACCENT, font=(FONT, 12, "bold"))
        text.tag_configure("sub", foreground=MUTED, font=(FONT, 9, "bold"))
        text.tag_configure("item", foreground=FG, lmargin1=14, lmargin2=14)
        text.tag_configure("gap", font=(FONT, 4))

        text.config(state="normal")
        for entry in CHANGELOG:
            text.insert("end", entry["version"] + "\n", "ver")
            if entry["fixes"]:
                text.insert("end", "Исправления\n", "sub")
                for item in entry["fixes"]:
                    text.insert("end", "• " + item + "\n", "item")
            if entry["features"]:
                text.insert("end", "Добавлено\n", "sub")
                for item in entry["features"]:
                    text.insert("end", "• " + item + "\n", "item")
            text.insert("end", "\n", "gap")
        text.config(state="disabled")

        text.bind("<MouseWheel>", lambda e: text.yview_scroll(-1 * (e.delta // 120), "units"))
        return page

    def _reset_settings(self):
        if not messagebox.askyesno(APP_NAME, "Сбросить настройки?"):
            return
        try:
            os.remove(SETTINGS_PATH)
        except Exception:
            pass
        self.settings = {}
        self.settings["loader"] = "none"
        self.nick_var.set("")
        self.version_var.set("")
        self.ram_var.set("")
        self._last_recommended = None
        self.loader_cb.current(0)
        self._refresh_ram_options()
        self._refresh_mods_page()
        self.refresh_versions()
        self._status("Настройки сброшены.")

    def _refresh_ram_options(self):
        usable, avail = system_ram_info()
        total = max(system_ram_gb(), usable)
        if total < 1:
            total = 4
        vals = list(range(1, total + 1))
        recommended = min(total // 2, avail)
        if recommended < 1:
            recommended = 1
        selectable = [v for v in vals if v <= avail]
        if not selectable:
            selectable = [1]
        if recommended > selectable[-1]:
            recommended = selectable[-1]
        if recommended < selectable[0]:
            recommended = selectable[0]
        labels = []
        for v in vals:
            if v in selectable:
                note = " (рекомендовано)" if v == recommended else ""
            else:
                note = " (заняты)"
            labels.append(f"{v} ГБ{note}")
        if labels != list(self.ram_cb["values"]):
            self.ram_cb["values"] = labels
        self._ram_vals = vals
        self._ram_selectable = set(selectable)
        self._ram_filling = True
        cur = self._parse_ram()
        if cur is None:
            saved = self.settings.get("ram")
            if saved in self._ram_selectable:
                self.ram_var.set(f"{saved} ГБ")
            else:
                self.ram_var.set(f"{recommended} ГБ (рекомендовано)")
        elif cur == getattr(self, "_last_recommended", None):
            self.ram_var.set(f"{recommended} ГБ (рекомендовано)")
        elif cur in self._ram_selectable:
            self.ram_var.set(f"{cur} ГБ")
        else:
            self.ram_var.set(f"{recommended} ГБ (рекомендовано)")
        self._last_recommended = recommended
        self._last_ram_label = self.ram_var.get()
        self._ram_filling = False

    def _parse_ram(self):
        m = re.match(r"(\d+)", self.ram_var.get())
        if m:
            v = int(m.group(1))
            if v in self._ram_vals:
                return v
        return None

    def _tick_ram(self):
        try:
            self._refresh_ram_options()
        except Exception:
            pass
        self.root.after(5000, self._tick_ram)

    def _on_ram_change(self, *a):
        if getattr(self, "_ram_filling", False):
            return
        v = self._ram_gb()
        if v not in self._ram_selectable:
            self.ram_var.set(self._last_ram_label)
            self._status(f"{v} ГБ сейчас заняты системой — выбрать нельзя.")
        else:
            self._last_ram_label = self.ram_var.get()

    def _ram_gb(self):
        m = re.match(r"(\d+)", self.ram_var.get())
        if m:
            v = int(m.group(1))
            if v in self._ram_vals:
                return v
        return self._ram_vals[0] if self._ram_vals else 2

    def _update_skin_btn(self):
        version = self._current_version()
        show = bool(version) and version_supports_skin(version)
        if show:
            self.skin_btn.pack(side="left", padx=(8, 0), ipady=8)
        else:
            self.skin_btn.pack_forget()

    def _pick_skin(self):
        path = filedialog.askopenfilename(
            title="Выберите скин",
            filetypes=[("Изображения", "*.png *.jpg *.jpeg *.webp *.bmp *.gif"),
                       ("Все файлы", "*.*")])
        if not path:
            return
        os.makedirs(SKIN_DIR, exist_ok=True)
        dst = os.path.join(SKIN_DIR, "skin.png")
        try:
            self._convert_skin(path, dst)
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Не удалось обработать изображение:\n{e}")
            return
        self._status("Скин выбран — будет подставлен в игру.")
        self._render_skin_preview()

    def _convert_skin(self, src, dst):
        try:
            from PIL import Image
        except Exception:
            Image = None
        if Image is not None:
            im = Image.open(src)
            im = im.convert("RGBA")
            im = im.resize((64, 64), Image.LANCZOS)
            im.save(dst, "PNG")
            return
        if not src.lower().endswith(".png"):
            raise RuntimeError("Для этого формата нужна библиотека Pillow")
        photo = tk.PhotoImage(file=src)
        photo.write(dst, format="png")

    def _render_skin_preview(self):
        try:
            canvas = self.skin_preview
        except Exception:
            return
        canvas.delete("all")
        skin_png = os.path.join(SKIN_DIR, "skin.png")
        if not os.path.isfile(skin_png):
            canvas.create_rectangle(6, 6, 106, 162, fill=BG3, outline=BG3)
            canvas.create_text(56, 84, text="Скин не выбран", fill=MUTED,
                               font=(FONT, 9), justify="center")
            return
        try:
            from PIL import Image, ImageTk
            im = Image.open(skin_png).convert("RGBA")
        except Exception:
            canvas.create_text(56, 84, text="Не удалось открыть скин", fill=MUTED,
                               font=(FONT, 9), justify="center")
            return
        try:
            w, h = im.size
            if w != 64:
                im = im.resize((64, 32 if h * 2 <= w else 64), Image.NEAREST)
                w, h = im.size
            legacy = h <= 32

            def part(box):
                return im.crop(box)

            head = part((8, 8, 16, 16))
            hat = part((40, 8, 48, 16))
            body = part((20, 20, 28, 32))
            r_arm = part((44, 20, 48, 32))
            r_leg = part((4, 20, 8, 32))
            if legacy:
                l_arm = r_arm.transpose(Image.FLIP_LEFT_RIGHT)
                l_leg = r_leg.transpose(Image.FLIP_LEFT_RIGHT)
            else:
                l_arm = part((36, 52, 40, 64))
                l_leg = part((20, 52, 24, 64))
                if not l_arm.getbbox():
                    l_arm = r_arm.transpose(Image.FLIP_LEFT_RIGHT)
                if not l_leg.getbbox():
                    l_leg = r_leg.transpose(Image.FLIP_LEFT_RIGHT)

            front = Image.new("RGBA", (16, 32), (0, 0, 0, 0))
            front.paste(head, (4, 0))
            if hat.getbbox():
                front.alpha_composite(hat, (4, 0))
            front.paste(body, (4, 8))
            front.paste(r_arm, (0, 8))
            front.paste(l_arm, (12, 8))
            front.paste(r_leg, (4, 20))
            front.paste(l_leg, (8, 20))
            if not legacy:
                overlays = (((20, 36, 28, 48), (4, 8)),
                            ((44, 36, 48, 48), (0, 8)),
                            ((52, 52, 56, 64), (12, 8)),
                            ((4, 36, 8, 48), (4, 20)),
                            ((4, 52, 8, 64), (8, 20)))
                for box, pos in overlays:
                    layer = part(box)
                    if layer.getbbox():
                        front.alpha_composite(layer, pos)

            scale = 5
            front = front.resize((16 * scale, 32 * scale), Image.NEAREST)
            photo = ImageTk.PhotoImage(front)
        except Exception:
            canvas.create_text(56, 84, text="Не удалось собрать скин", fill=MUTED,
                               font=(FONT, 9), justify="center")
            return
        self._skin_preview_photo = photo
        canvas.create_image(56, 84, image=photo)

    def _reset_skin(self):
        if not messagebox.askyesno(APP_NAME, "Убрать скин?"):
            return
        try:
            os.remove(os.path.join(SKIN_DIR, "skin.png"))
        except Exception:
            pass
        skin_pack.remove_skin_pack(MC_DIR)
        self._status("Скин убран.")
        self._render_skin_preview()

    def _write_skin_pack(self, version, skin_png):
        skin_pack.write_skin_pack(MC_DIR, version, skin_png)

    def _center(self):
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() - self.root.winfo_width()) // 2
        y = (self.root.winfo_screenheight() - self.root.winfo_height()) // 2
        self.root.geometry(f"+{x}+{y}")

    def _compat_for(self, vid):
        if vid in self._loader_compat:
            return self._loader_compat[vid]
        return heuristic_compat(vid)

    def _version_label(self, vid):
        letters = " ".join(LOADER_LETTERS[l] for l in LOADER_IDS if l in self._compat_for(vid))
        label = vid + ((" " + letters) if letters else "")
        loader = self.settings.get("loader", "none")
        if loader != "none" and loader not in self._compat_for(vid):
            label += " (недоступна)"
        return label

    def _current_version(self):
        label = self.version_var.get()
        if label in self._version_ids:
            return label
        for i, v in zip(self._version_ids, self.version_cb["values"]):
            if v == label:
                return i
        if label:
            return label.split(" ")[0]
        return ""

    def _set_version(self, vid):
        self._cur_version_id = vid
        if vid in self._version_ids:
            self.version_var.set(self._version_label(vid))
        else:
            self.version_var.set(vid)

    def _on_version_selected(self, e=None):
        idx = self.version_cb.current()
        if 0 <= idx < len(self._version_ids):
            self._cur_version_id = self._version_ids[idx]
        self._update_skin_btn()

    def _on_loader_change(self, e=None):
        idx = self.loader_cb.current()
        loader = LOADER_UI_IDS[idx] if 0 <= idx < len(LOADER_UI_IDS) else "none"
        self.settings["loader"] = loader
        self._save_settings(self._current_version(),
                            self.nick_var.get().strip() or "Steve", self._ram_gb())
        self.refresh_versions()
        self._refresh_mods_page()
        if loader != "none":
            self._status(f"Подсистема: {LOADER_NAMES.get(loader, loader)}")

    def refresh_versions(self, select=None):
        try:
            versions = mll.utils.get_installed_versions(MC_DIR)
            ids = sorted({v["id"] for v in versions if not is_loader_version_id(v["id"])},
                         key=version_sort_key, reverse=True)
        except Exception:
            ids = []
        self._version_ids = ids
        self.version_cb["values"] = [self._version_label(i) for i in ids]
        cur = select or self._cur_version_id
        if cur not in ids:
            cur = ids[0] if ids else ""
        self._set_version(cur)
        if not ids and not self.status_var.get():
            self.status_var.set("Версий нет — нажмите «+»")
        self._update_skin_btn()

    def open_install_dialog(self):
        win = tk.Toplevel(self.root)
        win.title("Установка версии")
        win.configure(bg=BG)
        win.transient(self.root)
        win.resizable(False, False)
        win.geometry("420x330")
        win.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - 420) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - 330) // 2
        win.geometry(f"+{x}+{y}")

        tk.Label(win, text="Версия", font=(FONT, 9), fg=MUTED, bg=BG).pack(anchor="w", padx=18, pady=(18, 5))
        var = tk.StringVar()
        cb = ttk.Combobox(win, textvariable=var, state="readonly", font=(FONT, 12))
        cb.pack(fill="x", padx=18, ipady=4)

        only_rel = tk.BooleanVar(value=True)
        chk = tk.Checkbutton(win, text="только стабильные релизы", variable=only_rel, bg=BG, fg=FG,
                             activebackground=BG, activeforeground=FG, selectcolor=BG2,
                             font=(FONT, 9), cursor="hand2")
        chk.pack(anchor="w", padx=18, pady=(10, 0))

        info = tk.Label(win, text="Загружаю список версий...", font=(FONT, 9), fg=MUTED, bg=BG, anchor="w")
        info.pack(fill="x", padx=18, pady=(10, 0))

        install = tk.Button(win, text="УСТАНОВИТЬ", font=(FONT, 12, "bold"), fg="#06130b", bg=ACCENT,
                            activebackground=ACCENT_DARK, activeforeground="#06130b", relief="flat",
                            bd=0, cursor="hand2", state="disabled")
        install.pack(fill="x", padx=18, ipady=8, pady=(16, 0))

        all_ids = []

        def apply_filter():
            items = [(i, t) for i, t in all_ids if (not only_rel.get() or t == "release")]
            items.sort(key=lambda x: version_sort_key(x[0]), reverse=True)
            self._install_ids = [i for i, _ in items]
            values = [self._version_label(i) for i, _ in items]
            cb["values"] = values
            if values:
                var.set(values[0])

        def load():
            try:
                data = mll.utils.get_version_list()
                pairs = {(v["id"], v.get("type", "release")) for v in data}
                latest = mll.utils.get_latest_version()
                for k in ("release", "snapshot"):
                    if latest.get(k):
                        pairs.add((latest[k], k))
                nonlocal all_ids
                all_ids = list(pairs)
                self.root.after(0, apply_filter)
                self.root.after(0, lambda: info.config(text=f"Доступно версий: {len(all_ids)}"))
                self.root.after(0, lambda: install.config(state="normal"))
            except Exception as e:
                self.root.after(0, lambda: info.config(text=f"Ошибка загрузки: {e}"))

        threading.Thread(target=load, daemon=True).start()

        def on_install():
            label = var.get()
            if not label:
                return
            if label in self._install_ids:
                v = label
            else:
                v = label.split(" ")[0]
            win.destroy()
            self._status(f"Устанавливаю {v}...")
            self._show_progress(True)
            threading.Thread(target=self._install_worker, args=(v,), daemon=True).start()

        only_rel.trace_add("write", lambda *a: apply_filter())
        install.config(command=on_install)

    def _install_worker(self, version):
        try:
            mll.install.install_minecraft_version(version, MC_DIR, callback=self._cb())
            self._status(f"{version} установлена.")
        except Exception as e:
            self._status("Ошибка установки.")
            self.root.after(0, messagebox.showerror, APP_NAME, f"Ошибка установки:\n{e}")
        finally:
            self._show_progress(False)
            self.root.after(0, self.refresh_versions, version)

    def launch(self):
        if self.process is not None and self.process.poll() is None:
            return
        version = self._current_version()
        if not version:
            messagebox.showinfo(APP_NAME, "Сначала установите версию (кнопка «+»).")
            return
        loader = self.settings.get("loader", "none")
        if loader != "none" and loader not in self._compat_for(version):
            messagebox.showwarning(APP_NAME,
                                   LOADER_NAMES[loader] + " не поддерживает эту версию Minecraft.\n\n"
                                   "Выберите совместимую версию — несовместимые помечены «(недоступна)».")
            return
        nick = self.nick_var.get().strip() or "Steve"
        if not re.fullmatch(r"[A-Za-z0-9_]{1,16}", nick):
            messagebox.showwarning(APP_NAME, "Ник: латиница, цифры, «_», до 16 символов.")
            return
        ram = self._ram_gb()
        self._save_settings(version, nick, ram)
        self._game_window_open = False
        self._set_ui_running(True)
        note = f" | {LOADER_NAMES[loader]}" if loader != "none" else ""
        self._log(f"Запуск: {version} | RAM: {ram} GB{note}")
        threading.Thread(target=self._launch_worker, args=(version, nick, ram, loader), daemon=True).start()

    def _launch_worker(self, version, nick, ram, loader_id="none"):
        try:
            java = self._ensure_java(version)
            options = {
                "username": nick,
                "uuid": str(uuid.uuid4()),
                "token": "",
                "executablePath": java,
                "jvmArguments": [f"-Xmx{ram}G", f"-Xms{ram}G", "-Dfile.encoding=UTF-8"],
                "launcherName": APP_NAME,
            }
            self._status("Проверка файлов...")
            self._show_progress(True)
            mll.install.install_minecraft_version(version, MC_DIR, callback=self._cb())
            launch_version = version
            if loader_id != "none":
                self._status(f"Установка {LOADER_NAMES[loader_id]}...")
                loader = mll.mod_loader.get_mod_loader(loader_id)
                loader_versions = loader.get_loader_versions(version, stable_only=True)
                if not loader_versions:
                    raise RuntimeError(f"{LOADER_NAMES[loader_id]} не поддерживает версию {version}")
                lv = loader_versions[0]
                launch_version = loader.get_installed_version(version, lv)
                installed = {v["id"] for v in mll.utils.get_installed_versions(MC_DIR)}
                if launch_version not in installed:
                    loader.install(version, MC_DIR, callback=self._cb(), java=java, loader_version=lv)
            self._show_progress(False)
            skin_png = os.path.join(SKIN_DIR, "skin.png")
            if os.path.isfile(skin_png) and version_supports_skin(version):
                self._status("Применяю скин...")
                self._write_skin_pack(version, skin_png)
            command = mll.command.get_minecraft_command(launch_version, MC_DIR, options)
            self._status("Запуск игры...")
            self._log("» " + " ".join(command))
            self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                            text=True, encoding="utf-8", errors="replace",
                                            bufsize=1, cwd=MC_DIR, creationflags=subprocess.CREATE_NO_WINDOW)
            self._mark_session_start()
            threading.Thread(target=self._watch_game_window, args=(self.process,), daemon=True).start()
            threading.Thread(target=self._read_output, args=(self.process,), daemon=True).start()
            self.process.wait()
            self.process = None
            self._status("Игра закрыта.")
        except Exception as e:
            self._show_progress(False)
            self._status("Ошибка запуска.")
            self.root.after(0, messagebox.showerror, APP_NAME, f"Ошибка запуска:\n{e}")
        finally:
            self._mark_session_end()
            self.root.after(0, self._set_ui_running, False)

    def _ensure_java(self, version):
        required = self._required_java(version)
        # Старые версии (1.7–1.16 и Forge) падают на слишком новой Java:
        # берём самую старую подходящую, а не самую новую.
        low = None
        high = None
        for c, v in find_java_candidates():
            if v is None:
                continue
            if v >= required and (low is None or v < low[1]):
                low = (c, v)
            if high is None or v > high[1]:
                high = (c, v)
        if low is not None:
            return low[0]
        java = high[0] if high is not None else None
        ver = high[1] if high is not None else None
        if java and ver is not None and ver >= required:
            return java
        name = None
        try:
            info = mll.runtime.get_version_runtime_information(version, MC_DIR)
            if info:
                name = info.get("name")
        except Exception:
            pass
        if not name:
            name = "java-21" if required >= 21 else ("java-17" if required >= 17 else "java-runtime-delta")
        self._status(f"Нужна Java {required}+. Скачиваю встроенную...")
        try:
            installed = set()
            try:
                installed = set(mll.runtime.get_installed_jvm_runtimes(MC_DIR))
            except Exception:
                pass
            if name not in installed:
                self._show_progress(True)
                mll.runtime.install_jvm_runtime(name, MC_DIR, callback=self._cb())
                self._show_progress(False)
        except Exception:
            if java:
                return java
            raise
        path = mll.runtime.get_executable_path(name, MC_DIR)
        if path and os.path.isfile(path):
            return path
        raise RuntimeError("Не удалось получить подходящую Java.")

    def _required_java(self, version):
        try:
            info = mll.runtime.get_version_runtime_information(version, MC_DIR)
            if info:
                return int(info.get("javaMajorVersion") or 8)
        except Exception:
            pass
        m = re.match(r"1\.(\d+)", version)
        if m:
            minor = int(m.group(1))
            return 21 if minor >= 20 else (17 if minor >= 18 else 8)
        if re.match(r"\d+\.", version):
            return 21
        return 8

    def _read_output(self, proc):
        try:
            for line in iter(proc.stdout.readline, ""):
                if line:
                    self.root.after(0, self._log, line.rstrip("\r\n"))
        except Exception:
            pass

    def _log(self, line):
        self.console.config(state="normal")
        self.console.insert("end", line + "\n")
        self.console.see("end")
        self.console.config(state="disabled")

    def _cb(self):
        def set_status(msg):
            text = str(msg)
            if text:
                self._status(text)

        def set_progress(pct):
            now = time.time()
            if now - self._last_progress < 0.05:
                return
            self._last_progress = now
            self.root.after(0, lambda: self.progress_var.set(int(pct)))

        return {"setStatus": set_status, "setProgress": set_progress, "setMax": lambda m: None}

    def _status(self, text):
        self.root.after(0, lambda: self.status_var.set(text))

    def _load_playtime(self):
        try:
            with open(PLAYTIME_PATH, "r", encoding="utf-8") as f:
                return float(json.load(f).get("seconds", 0))
        except Exception:
            return 0.0

    def _save_playtime(self):
        try:
            os.makedirs(MC_DIR, exist_ok=True)
            with open(PLAYTIME_PATH, "w", encoding="utf-8") as f:
                json.dump({"seconds": self._playtime_total}, f)
        except Exception:
            pass

    @staticmethod
    def _fmt_playtime(seconds):
        total = int(seconds or 0)
        h, rem = divmod(total, 3600)
        m, s = divmod(rem, 60)
        parts = []
        if h:
            parts.append(f"{h} ч")
        if m or h:
            parts.append(f"{m} мин")
        if not parts:
            parts.append(f"{s} сек")
        return "Время в игре: " + " ".join(parts)

    def _refresh_playtime_label(self):
        if hasattr(self, "playtime_var"):
            self.playtime_var.set(self._fmt_playtime(self._playtime_total))

    def _mark_session_start(self):
        self._session_start = time.time()

    def _mark_session_end(self):
        if self._session_start is None:
            return
        self._playtime_total += max(0.0, time.time() - self._session_start)
        self._session_start = None
        self._save_playtime()
        self.root.after(0, self._refresh_playtime_label)

    def _show_progress(self, show):
        def job():
            self.progress_var.set(0)
            if show:
                self.progress.pack(fill="x", padx=20, pady=(14, 0), before=self.status_label)
            else:
                self.progress.pack_forget()
        self.root.after(0, job)

    def _set_ui_running(self, running):
        if running:
            self.launch_btn.config(state="disabled", text="ЗАПУСК...")
        else:
            self.launch_btn.config(state="normal", text="ИГРАТЬ", command=self.launch)

    def _find_game_window(self, pid):
        result = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def enum_cb(hwnd, lparam):
            if ctypes.windll.user32.IsWindowVisible(hwnd):
                tid = ctypes.c_ulong()
                ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(tid))
                if tid.value == pid and not result:
                    length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buf = ctypes.create_unicode_buffer(length + 1)
                        ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
                        if "minecraft" in buf.value.lower():
                            result.append(hwnd)
            return True

        ctypes.windll.user32.EnumWindows(enum_cb, 0)
        return result[0] if result else None

    def _watch_game_window(self, proc):
        while proc.poll() is None and not self._game_window_open:
            if self._find_game_window(proc.pid):
                self._game_window_open = True
                self.root.after(0, self._set_close_btn)
                return
            time.sleep(0.5)

    def _set_close_btn(self):
        self.launch_btn.config(state="normal", text="Закрыть", command=self._close_game)

    def _close_game(self):
        proc = self.process
        if proc is None or proc.poll() is not None:
            return
        if not messagebox.askyesno(APP_NAME, "Закрыть игру?"):
            return
        self._status("Закрываю игру...")
        hwnd = self._find_game_window(proc.pid)
        if hwnd:
            ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)
            try:
                proc.wait(timeout=5)
                return
            except Exception:
                pass
        proc.terminate()

    def toggle_console(self):
        if self.console_shown:
            self.console.pack_forget()
        else:
            self.console.pack(fill="both", expand=True, padx=20, pady=(10, 0), before=self.log_btn)
        self.console_shown = not self.console_shown

    def _load_settings(self):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_settings(self, version, nick, ram):
        try:
            with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump({"version": version, "nick": nick, "ram": ram,
                           "loader": self.settings.get("loader", "none")}, f)
        except Exception:
            pass

    def _on_close(self):
        if self.process is not None and self.process.poll() is None:
            if not messagebox.askyesno(APP_NAME, "Игра ещё запущена. Закрыть лаунчер?"):
                return
        self.root.destroy()


def main():
    hide_console()
    os.makedirs(MC_DIR, exist_ok=True)
    if DND_AVAILABLE:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
