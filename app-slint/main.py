#!/usr/bin/env python3
"""Cactus Lite Minecraft v1.3 — интерфейс на Slint (Python) в стиле WinUI 3.

Логика лаунчера переиспользуется из соседних модулей проекта, здесь только
новый интерфейс: NavigationView, карточки и типографика WinUI 3 поверх
текущей тёмной палитры Cactus Lite.
"""
import base64
import hashlib
import io
import json
import os
import subprocess
import sys
import threading
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import slint
from slint import slint as slint_native

try:
    import crash_handler
except Exception:
    crash_handler = None


def on_ui_thread(callable_):
    """Выполняет действие в потоке интерфейса Slint (из фоновых потоков нельзя)."""
    slint_native.invoke_from_event_loop(callable_)

try:
    from PIL import Image as PILImage
except Exception:
    PILImage = None

try:
    import minecraft_launcher_lib as mll
except Exception:
    mll = None

try:
    import mod_catalog
except Exception:
    mod_catalog = None

try:
    import skin_pack
except Exception:
    skin_pack = None

APP_NAME = "Cactus Lite Minecraft"
APP_VERSION = "v1.3"
MC_DIR = os.path.join(os.path.expanduser("~"), ".mcl")
SETTINGS_PATH = os.path.join(MC_DIR, "settings.json")
SKIN_DIR = os.path.join(MC_DIR, "skins")
PLAYTIME_PATH = os.path.join(MC_DIR, "playtime.json")
ICON_PNG = os.path.join(ROOT, "icon.png")
ICONS_JSON = os.path.join(ROOT, "icons.json")
UI_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui", "app.slint")
CACHE_DIR = os.path.join(MC_DIR, "ui_cache")
INSTANCES_DIR = os.path.join(MC_DIR, "instances")
LEGACY_INSTANCE_ID = "__legacy__"

LOADER_UI_VALUES = ["Нет (ваниль)", "Forge", "Fabric", "NeoForge"]
LOADER_UI_IDS = ["none", "forge", "fabric", "neoforge"]
LOADER_NAMES = {"forge": "Forge", "fabric": "Fabric", "neoforge": "NeoForge"}
# эти моды показываем в каталоге всегда, даже если выбран другой загрузчик
ALWAYS_SHOWN = ("sodium", "zoomify", "voxy")

AUTO_RAM = "Авто (умный выбор)"
# Сколько версий показываем в окне установки за раз: список из сотен строк
# Slint раскладывает целиком и падает в отрисовке текста на macOS.
VERSION_LIST_LIMIT = 40
GB = 1024 ** 3


def base_mc_version(version_id):
    """Чистый номер версии из id вроде 1.20.1-forge-47.2.0 или fabric-loader-0.15-1.20.1."""
    import re
    found = re.findall(r"1\.\d+(?:\.\d+)?", str(version_id))
    if not found:
        return ""
    return found[0] if str(version_id)[:1].isdigit() else found[-1]


def ram_info():
    """(всего, свободно) ОЗУ в ГБ. Работает на Windows, macOS и Linux."""
    total = 0.0
    free = 0.0
    try:
        if sys.platform.startswith("win"):
            import ctypes

            class _MemStatus(ctypes.Structure):
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

            st = _MemStatus()
            st.dwLength = ctypes.sizeof(_MemStatus)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
            total = st.ullTotalPhys / GB
            free = st.ullAvailPhys / GB
        elif sys.platform == "darwin":
            total = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"]).strip()) / GB
            page = 4096
            pages = 0
            out = subprocess.check_output(["vm_stat"]).decode("utf-8", "ignore")
            for line in out.splitlines():
                if "page size of" in line:
                    digits = "".join(c for c in line if c.isdigit())
                    if digits:
                        page = int(digits)
                for key in ("Pages free:", "Pages inactive:", "Pages speculative:"):
                    if line.startswith(key):
                        pages += int(line.split(":")[1].strip().rstrip("."))
            free = pages * page / GB
        else:
            info = {}
            with open("/proc/meminfo", "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    name, _, rest = line.partition(":")
                    info[name.strip()] = rest.strip()
            total = int(info.get("MemTotal", "0").split()[0]) * 1024 / GB
            avail = info.get("MemAvailable") or info.get("MemFree") or "0 kB"
            free = int(avail.split()[0]) * 1024 / GB
    except Exception:
        pass
    if total <= 0:
        total = 8.0
    if free <= 0 or free > total:
        free = total / 2
    return total, free


def recommended_ram(version, loader_id="none"):
    """Рекомендуемая память: старым версиям меньше, новым и сборкам с модами больше."""
    base_version = base_mc_version(version) or str(version)
    try:
        minor = int("".join(c for c in base_version.split(".")[1] if c.isdigit()))
    except Exception:
        minor = 20
    if minor <= 12:
        need = 2.0
    elif minor <= 19:
        need = 3.0
    else:
        need = 4.0
    if loader_id and loader_id != "none":
        need += 2.0
    return need


def auto_ram(version, loader_id="none"):
    """Умный автоподбор: рекомендуемое для версии с оглядкой на свободную память."""
    total, free = ram_info()
    value = min(recommended_ram(version, loader_id), free - 1.0, total - 2.0)
    if value < 1:
        value = 1.0
    return int(round(value))


def read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass


def fmt_playtime(seconds):
    seconds = int(seconds or 0)
    hours, rest = divmod(seconds, 3600)
    minutes = rest // 60
    if hours:
        return f"Время в игре: {hours} ч {minutes} мин"
    return f"Время в игре: {minutes} мин"


import gc

# --- кроссплатформенность -------------------------------------------------
IS_WINDOWS = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
IS_LINUX = not IS_WINDOWS and not IS_MAC

# Объекты Slint нельзя трогать из чужих потоков, а сборщик мусора Python
# запускается в том потоке, который перешагнул порог, и роняет приложение
# (abort в PyStruct.__clear__). Отключаем автосборку: подсчёт ссылок работает.
gc.disable()
gc.set_threshold(0, 0, 0)
# Сторонние библиотеки могут снова включить сборку или вызвать collect()
# из рабочего потока — закрываем оба пути. Память держится на подсчёте ссылок.
gc.enable = lambda: None
gc.collect = lambda *a, **k: 0
try:
    gc.freeze()
except Exception:
    pass


def popen_kwargs():
    """На Windows прячем чёрное окно консоли у дочернего процесса."""
    if IS_WINDOWS:
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    return {}


def open_in_explorer(path):
    """Открыть папку: проводник Windows, Finder на macOS, xdg-open на Linux."""
    try:
        os.makedirs(path, exist_ok=True)
        if IS_WINDOWS:
            os.startfile(path)  # noqa: S606
        elif IS_MAC:
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


def cached_image(name, data):
    """Slint грузит картинки с диска, поэтому байты кладём во временный файл."""
    if not data:
        return None
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        path = os.path.join(CACHE_DIR, name)
        with open(path, "wb") as f:
            f.write(data)
        return slint.Image.load_from_path(path)
    except Exception:
        return None


# Прозрачный PNG 1x1 на случай, если PIL недоступен
BLANK_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="


def blank_image():
    """Заглушка для icon: в структуре ModTile это поле обязано быть картинкой."""
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        path = os.path.join(CACHE_DIR, "blank.png")
        if not os.path.isfile(path):
            if PILImage is not None:
                PILImage.new("RGBA", (1, 1), (0, 0, 0, 0)).save(path)
            else:
                with open(path, "wb") as f:
                    f.write(base64.b64decode(BLANK_PNG_B64))
        return slint.Image.load_from_path(path)
    except Exception:
        return None


def render_skin_front():
    """Собирает 2D-фигуру скина лицом к игроку (как в текущей версии)."""
    src = os.path.join(SKIN_DIR, "skin.png")
    if PILImage is None or not os.path.isfile(src):
        return None
    try:
        skin = PILImage.open(src).convert("RGBA")
        wide = skin.height >= 64
        fig = PILImage.new("RGBA", (16, 32), (0, 0, 0, 0))

        def part(box, pos, mirror=False):
            piece = skin.crop(box)
            if mirror:
                piece = piece.transpose(PILImage.FLIP_LEFT_RIGHT)
            fig.alpha_composite(piece, pos)

        part((8, 8, 16, 16), (4, 0))
        part((20, 20, 28, 32), (4, 8))
        part((44, 20, 48, 32), (0, 8))
        part((4, 20, 8, 32), (4, 20))
        if wide:
            part((36, 52, 40, 64), (12, 8))
            part((20, 52, 24, 64), (8, 20))
        else:
            part((44, 20, 48, 32), (12, 8), mirror=True)
            part((4, 20, 8, 32), (8, 20), mirror=True)
        part((40, 8, 48, 16), (4, 0))
        if wide:
            part((20, 36, 28, 48), (4, 8))
            part((44, 36, 48, 48), (0, 8))
            part((52, 52, 56, 64), (12, 8))
            part((4, 36, 8, 48), (4, 20))
            part((4, 52, 8, 64), (8, 20))

        big = fig.resize((fig.width * 6, fig.height * 6), PILImage.NEAREST)
        buf = io.BytesIO()
        big.save(buf, format="PNG")
        return cached_image("skin_preview.png", buf.getvalue())
    except Exception:
        return None


def changelog_lines():
    try:
        import launcher_changelog  # необязательный отдельный модуль
        data = launcher_changelog.CHANGELOG
    except Exception:
        data = None
    if data is None:
        data = read_json(os.path.join(ROOT, "changelog.json"), None)
    if data is None:
        return ["История версий появится после обновления лаунчера."]
    lines = []
    for entry in data:
        lines.append(entry.get("version", ""))
        for fix in entry.get("fixes", []):
            lines.append("• Исправлено: " + fix)
        for feat in entry.get("features", []):
            lines.append("• Новое: " + feat)
        lines.append("")
    return lines


class Launcher:
    def __init__(self):
        os.makedirs(MC_DIR, exist_ok=True)
        self.settings = read_json(SETTINGS_PATH, {})
        self.playtime = read_json(PLAYTIME_PATH, {}).get("total", 0)
        self.process = None
        self.icons = read_json(ICONS_JSON, {})

        component = slint.load_file(UI_FILE)
        self.win = component.AppWindow()

        # icon в ModTile — обязательное поле image, без него Slint падает
        self.blank_icon = blank_image()
        self.win.app_version = APP_VERSION
        self.win.game_dir = MC_DIR
        self.win.nick = self.settings.get("nick", "")
        total_ram, _free_ram = ram_info()
        max_ram = max(2, min(32, int(total_ram) - 1))
        self.win.rams = slint.ListModel([AUTO_RAM] + [str(g) for g in range(1, max_ram + 1)])
        self.win.ram = str(self.settings.get("ram", AUTO_RAM))
        self.win.loaders = slint.ListModel(LOADER_UI_VALUES)
        loader_id = self.settings.get("loader", "none")
        self.win.loader = LOADER_UI_VALUES[LOADER_UI_IDS.index(loader_id)] if loader_id in LOADER_UI_IDS else LOADER_UI_VALUES[0]
        self.win.playtime = fmt_playtime(self.playtime)
        self.win.changelog = slint.ListModel(changelog_lines())
        self.win.status = ""
        self.win.mods_status = ""
        self.win.mod_install_busy = False
        self.win.mod_install_progress = 0.0
        self.win.mod_install_indeterminate = False
        self.win.mod_install_name = ""
        self.mod_install_busy = False
        self.win.installed_instances = slint.ListModel([])
        self.win.installed_mods = slint.ListModel([])
        self.win.selected_installed_instance = ""
        self.win.catalog = slint.ListModel([])
        self.win.found = slint.ListModel([])
        self.win.all_versions = slint.ListModel([])
        self.win.add_status = ""
        self.win.version_filter = ""
        self.all_version_pairs = []

        logo = slint.Image.load_from_path(ICON_PNG) if os.path.isfile(ICON_PNG) else None
        if logo is not None:
            self.win.logo = logo
        skin = render_skin_front()
        if skin is not None:
            self.win.skin_preview = skin

        self.win.launch = self.on_launch
        self.win.add_version = self.on_add_version
        self.win.only_release_changed = self.on_only_release_changed
        self.win.version_filter_changed = self.on_version_filter_changed
        self.win.install_version = self.on_install_version
        self.win.version_changed = self.on_version_changed
        self.win.ram_changed = self.on_ram_changed
        self.win.loader_changed = self.on_loader_changed
        self.win.pick_skin = self.on_pick_skin
        self.win.reset_skin = self.on_reset_skin
        self.win.reset_settings = self.on_reset_settings
        self.win.open_game_dir = lambda: open_in_explorer(MC_DIR)
        self.win.open_mods_dir = self.on_open_mods_dir
        self.win.pick_mod_file = self.on_pick_mod_file
        self.win.search_mods = self.on_search_mods
        self.win.install_mod = self.on_install_mod
        self.win.install_found = self.on_install_found
        self.win.installed_instance_changed = self.on_installed_instance_changed
        self.win.remove_mod = self.on_remove_mod
        self.win.toggle_console = lambda: open_in_explorer(os.path.join(MC_DIR, "logs"))
        self.win.repair_deps_on_launch = bool(self.settings.get("repair_deps", True))
        self.win.repair_deps_changed = self.on_repair_deps_changed

        self.refresh_versions()
        self.refresh_installed()
        self.load_catalog_async()

    # --- данные -------------------------------------------------------
    def loader_id(self):
        try:
            return LOADER_UI_IDS[LOADER_UI_VALUES.index(str(self.win.loader))]
        except Exception:
            return "none"

    def mods_dir(self, instance_id=LEGACY_INSTANCE_ID):
        """Папка модов инстанса; старый общий каталог остаётся доступен без миграции."""
        if not instance_id or instance_id == LEGACY_INSTANCE_ID:
            return os.path.join(MC_DIR, "mods")
        return os.path.join(self.instance_dir(instance_id), "mods")

    def instance_dir(self, instance_id):
        """Стабильная безопасная папка для точного id установленной версии."""
        text = str(instance_id)
        safe = "".join(ch if ch.isalnum() or ch in ".-_" else "_" for ch in text).strip("._")
        safe = safe[:64] or "minecraft"
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:10]
        return os.path.join(INSTANCES_DIR, f"{safe}-{digest}")

    @staticmethod
    def instance_loader(instance_id):
        low = str(instance_id).lower()
        if "neoforge" in low:
            return "neoforge"
        if "fabric" in low:
            return "fabric"
        if "forge" in low:
            return "forge"
        return "none"

    def installed_instances(self):
        if mll is None:
            return []
        try:
            return [str(v["id"]) for v in mll.utils.get_installed_versions(MC_DIR)]
        except Exception:
            return []

    def refresh_versions(self):
        versions = []
        if mll is not None:
            try:
                versions = [v["id"] for v in mll.utils.get_installed_versions(MC_DIR)]
            except Exception:
                versions = []
        self.win.versions = slint.ListModel(versions)
        saved = self.settings.get("version", "")
        if saved in versions:
            self.win.version = saved
        elif versions:
            self.win.version = versions[0]

    def refresh_installed(self, preferred_id=""):
        """Обновляет ComboBox инстансов и карточки только выбранной папки mods."""
        candidates = [(LEGACY_INSTANCE_ID, "Общие моды (старый формат)")]
        for instance_id in self.installed_instances():
            loader_name = LOADER_NAMES.get(self.instance_loader(instance_id), "Ваниль")
            candidates.append((instance_id, f"{instance_id} • {loader_name}"))

        current_label = str(self.win.selected_installed_instance)
        current_id = preferred_id or getattr(self, "installed_instance_ids", {}).get(current_label, "")
        ids = {label: instance_id for instance_id, label in candidates}
        if current_id not in {item[0] for item in candidates}:
            game_instance = str(self.win.version)
            current_id = game_instance if game_instance in {item[0] for item in candidates} else candidates[0][0]
        selected_label = next(label for instance_id, label in candidates if instance_id == current_id)

        self.installed_instance_ids = ids
        self.win.installed_instances = slint.ListModel([label for _instance_id, label in candidates])
        self.win.selected_installed_instance = selected_label
        self.refresh_installed_mods(current_id)

    def refresh_installed_mods(self, instance_id):
        """Создаёт для выбранного инстанса плитки в стиле каталога."""
        try:
            names = sorted(n for n in os.listdir(self.mods_dir(instance_id))
                           if n.lower().endswith(".jar"))
        except Exception:
            names = []
        tiles = []
        for filename in names:
            stem = os.path.splitext(filename)[0]
            icon = self.icon_for(stem.lower())
            tiles.append(self.tile(filename, stem, f"Файл: {filename}", icon,
                                   action="Удалить", version=instance_id))
        self.win.installed_mods = slint.ListModel(tiles)

    def on_installed_instance_changed(self, label):
        instance_id = getattr(self, "installed_instance_ids", {}).get(str(label), "")
        if instance_id:
            self.refresh_installed_mods(instance_id)

    def tile(self, mod_id, name, note, icon, action="Установить", busy=False,
             versions=None, version=""):
        vlist = [str(v) for v in (versions or [])]
        data = {"id": mod_id, "name": name, "note": note, "action": action, "busy": busy,
                "progress": 0.0, "indeterminate": False,
                "versions": slint.ListModel(vlist),
                "version": version or (vlist[0] if vlist else "")}
        if icon is None:
            icon = getattr(self, "blank_icon", None)
        if icon is not None:
            data["icon"] = icon
        return data

    def mod_version_choices(self, supported):
        """Точные id установленных инстансов, совместимых с версиями проекта."""
        supported_bases = {str(v) for v in (supported or [])}
        result = []
        for instance_id in self.installed_instances():
            base = base_mc_version(instance_id) or instance_id
            if not supported_bases or base in supported_bases:
                result.append(instance_id)
        try:
            result.sort(key=lambda value: mod_catalog.version_sort_key(base_mc_version(value) or value),
                        reverse=True)
        except Exception:
            result.sort(reverse=True)
        return result[:40]

    def default_choice(self, choices):
        """По умолчанию — выбранный инстанс, иначе самый новый подходящий."""
        current = str(self.win.version)
        return current if current in choices else (choices[0] if choices else "")

    def icon_for(self, mod_id):
        b64 = self.icons.get(mod_id)
        if not b64:
            return None
        try:
            return cached_image(f"mod_{mod_id}.png", base64.b64decode(b64))
        except Exception:
            return None

    def catalog_versions(self):
        """Версии модов: сперва кэш, затем сеть. Вызывать из фонового потока."""
        try:
            data = mod_catalog.load_cache(MC_DIR)
            if data is None:
                data = mod_catalog.fetch_catalog()
                mod_catalog.save_cache(MC_DIR, data)
            return data or {}
        except Exception:
            return {}

    def load_catalog_async(self):
        # Свойства окна Slint можно читать только в главном потоке
        loader = self.loader_id()

        def job():
            raw = []
            if mod_catalog is not None:
                versions_by_mod = self.catalog_versions()
                for mod in mod_catalog.CATALOG:
                    mid = mod.get("id", "")
                    loaders = mod.get("loaders") or []
                    fits = loader == "none" or loader in loaders or mid in ALWAYS_SHOWN
                    if mid == "optifine" and loader in ("forge", "none"):
                        fits = True
                    if not fits:
                        continue
                    note = mod.get("desc", "") or mod.get("note", "")
                    count = len(versions_by_mod.get(mid) or {})
                    if count:
                        note = f"{note} • версий: {count}"
                    raw.append((mid, mod.get("name", ""), note,
                                list((versions_by_mod.get(mid) or {}).keys())))

            def apply_catalog():
                # slint.Image можно создавать только в потоке интерфейса
                mods = []
                for mid, name, note, supported in raw:
                    choices = self.mod_version_choices(supported)
                    mods.append(self.tile(mid, name, note, self.icon_for(mid),
                                          versions=choices,
                                          version=self.default_choice(choices)))
                self.win.catalog = slint.ListModel(mods)

            on_ui_thread(apply_catalog)

        threading.Thread(target=job, daemon=True).start()

    # --- действия -----------------------------------------------------
    def status(self, text):
        on_ui_thread(lambda: setattr(self.win, "status", text))

    def mods_status(self, text):
        on_ui_thread(lambda: setattr(self.win, "mods_status", text))

    def save_settings(self):
        write_json(SETTINGS_PATH, {
            "version": str(self.win.version),
            "nick": str(self.win.nick),
            "ram": str(self.win.ram),
            "loader": self.loader_id(),
        })

    def on_version_changed(self, value):
        self.settings["version"] = str(value)
        self.save_settings()

    def on_ram_changed(self, value):
        self.settings["ram"] = str(value)
        self.save_settings()

    def resolve_ram(self, value, version):
        """«Авто» превращаем в число гигабайт, обычный пункт берём как есть."""
        digits = "".join(ch for ch in str(value or "") if ch.isdigit())
        if digits:
            return digits
        return str(auto_ram(version, self.loader_id()))

    def on_loader_changed(self, value):
        self.settings["loader"] = self.loader_id()
        self.save_settings()
        self.load_catalog_async()

    def on_repair_deps_changed(self, value):
        self.settings["repair_deps"] = bool(value)
        write_json(SETTINGS_PATH, self.settings)

    def on_add_version(self):
        """Кнопка «+»: окно со списком всех версий Minecraft для установки."""
        if mll is None:
            self.status("Не установлен minecraft-launcher-lib.")
            return
        self.win.add_open = True
        self.win.add_status = "Загружаю список версий..."
        if self.all_version_pairs:
            self.apply_version_filter()
            return

        def job():
            try:
                data = mll.utils.get_version_list()
                pairs = {(v["id"], v.get("type", "release")) for v in data}
                try:
                    latest = mll.utils.get_latest_version()
                    for k in ("release", "snapshot"):
                        if latest.get(k):
                            pairs.add((latest[k], k))
                except Exception:
                    pass
                found = list(pairs)

                def apply():
                    self.all_version_pairs = found
                    self.apply_version_filter()

                on_ui_thread(apply)
            except Exception as e:
                on_ui_thread(lambda: setattr(self.win, "add_status", f"Ошибка загрузки: {e}"))

        threading.Thread(target=job, daemon=True).start()

    def apply_version_filter(self):
        """Фильтр «только релизы» плюс поиск по названию, список режем по лимиту."""
        only_release = bool(self.win.only_release)
        needle = str(self.win.version_filter).strip().lower()
        ids = [vid for vid, vtype in self.all_version_pairs
               if (not only_release or vtype == "release")
               and (not needle or needle in str(vid).lower())]
        try:
            ids.sort(key=mod_catalog.version_sort_key, reverse=True)
        except Exception:
            ids.sort(reverse=True)
        total = len(ids)
        shown = ids[:VERSION_LIST_LIMIT]
        self.win.all_versions = slint.ListModel(shown)
        current = str(self.win.new_version)
        if not shown:
            self.win.new_version = ""
        elif current not in shown:
            self.win.new_version = shown[0]
        if total > len(shown):
            self.win.add_status = f"Найдено версий: {total}, показаны первые {len(shown)} — уточните фильтр"
        else:
            self.win.add_status = f"Доступно версий: {total}"

    def on_version_filter_changed(self, value):
        if self.all_version_pairs:
            self.apply_version_filter()

    def on_only_release_changed(self, value):
        if self.all_version_pairs:
            self.apply_version_filter()

    def on_install_version(self, version):
        version = str(version).strip()
        if not version or mll is None:
            return
        loader_id = self.loader_id()

        def start():
            # закрывать окно и менять свойства прямо внутри обработчика клика нельзя:
            # Slint как раз выполняет колбэк этого окна. Делаем это следующим тиком.
            self.win.add_open = False
            self.win.busy = True
            self.win.status = f"Устанавливаю {version}..."
            threading.Thread(target=self.version_install_worker,
                             args=(version, loader_id), daemon=True).start()

        on_ui_thread(start)

    def install_progress(self):
        """Колбэки minecraft-launcher-lib: шаг, прогресс и максимум для полосы."""
        state = {"max": 0, "shown": -1}

        def set_status(text):
            self.status(str(text))

        def set_max(value):
            state["max"] = int(value or 0)
            state["shown"] = -1

        def set_progress(value):
            total = state["max"]
            if total <= 0:
                return
            percent = int(int(value or 0) * 100 / total)
            if percent < 0:
                percent = 0
            elif percent > 100:
                percent = 100
            if percent == state["shown"]:
                return
            state["shown"] = percent
            on_ui_thread(lambda: setattr(self.win, "progress", float(percent)))

        return {"setStatus": set_status, "setProgress": set_progress, "setMax": set_max}

    def set_progress(self, percent):
        on_ui_thread(lambda: setattr(self.win, "progress", float(percent)))

    def version_install_worker(self, version, loader_id="none"):
        callback = self.install_progress()
        try:
            self.set_progress(0)
            self.status(f"Скачиваю {version}...")
            mll.install.install_minecraft_version(version, MC_DIR, callback=callback)
            if loader_id != "none":
                self.status(f"Ставлю {LOADER_NAMES[loader_id]} для {version}...")
                loader = mll.mod_loader.get_mod_loader(loader_id)
                loader_versions = loader.get_loader_versions(version, stable_only=True)
                if not loader_versions:
                    raise RuntimeError(f"{LOADER_NAMES[loader_id]} не поддерживает версию {version}")
                lv = loader_versions[0]
                installed = {v["id"] for v in mll.utils.get_installed_versions(MC_DIR)}
                if loader.get_installed_version(version, lv) not in installed:
                    self.set_progress(0)
                    loader.install(version, MC_DIR, loader_version=lv, callback=callback)
            self.set_progress(100)
            self.status(f"{version} установлена.")

            def done():
                self.refresh_versions()
                self.win.version = version
                self.settings["version"] = version
                self.save_settings()

            on_ui_thread(done)
        except Exception as e:
            self.status(f"Ошибка установки: {e}")
        finally:
            on_ui_thread(lambda: setattr(self.win, "busy", False))

    def on_launch(self):
        if mll is None:
            self.status("Не установлен minecraft-launcher-lib.")
            return
        version = str(self.win.version)
        nick = str(self.win.nick).strip() or "Player"
        ram_choice = str(self.win.ram)
        ram = self.resolve_ram(ram_choice, version)
        if not version:
            self.status("Сначала выберите версию.")
            return
        if not "".join(ch for ch in ram_choice if ch.isdigit()):
            self.status(f"Авто-память: {ram} ГБ")
        self.save_settings()
        self.win.busy = True
        threading.Thread(target=self.launch_worker, args=(version, nick, ram, self.loader_id()), daemon=True).start()

    def launch_worker(self, version, nick, ram, loader_id):
        try:
            self.status("Проверка файлов...")
            self.set_progress(0)
            mll.install.install_minecraft_version(version, MC_DIR, callback=self.install_progress())
            launch_version = version
            if loader_id != "none":
                self.status(f"Установка {LOADER_NAMES[loader_id]}...")
                loader = mll.mod_loader.get_mod_loader(loader_id)
                loader_versions = loader.get_loader_versions(version, stable_only=True)
                if not loader_versions:
                    raise RuntimeError(f"{LOADER_NAMES[loader_id]} не поддерживает версию {version}")
                lv = loader_versions[0]
                launch_version = loader.get_installed_version(version, lv)
                installed = {v["id"] for v in mll.utils.get_installed_versions(MC_DIR)}
                if launch_version not in installed:
                    loader.install(version, MC_DIR, loader_version=lv)
                # доскачиваем недостающие зависимости уже установленных модов
                if self.settings.get("repair_deps", True):
                    missing = self.repair_mod_dependencies(launch_version)
                    if missing:
                        self.status(f"Докачано зависимостей: {missing}.")
            options = {
                "username": nick,
                "uuid": str(uuid.uuid4()),
                "token": "",
                "gameDirectory": self.instance_dir(launch_version),
                "jvmArguments": [f"-Xmx{ram}G", f"-Xms{ram}G", "-Dfile.encoding=UTF-8"],
                "launcherName": APP_NAME,
            }
            os.makedirs(options["gameDirectory"], exist_ok=True)
            if skin_pack is not None:
                skin_png = os.path.join(SKIN_DIR, "skin.png")
                if os.path.isfile(skin_png) and skin_pack.version_supports_skin(version):
                    self.status("Применяю скин...")
                    skin_pack.write_skin_pack(options["gameDirectory"], version, skin_png)
            command = mll.command.get_minecraft_command(launch_version, MC_DIR, options)
            self.status("Запуск игры...")
            self.process = subprocess.Popen(command, cwd=MC_DIR, **popen_kwargs())
            self.process.wait()
            self.process = None
            self.status("Игра закрыта.")
        except Exception as e:
            self.status(f"Ошибка запуска: {e}")
        finally:
            on_ui_thread(lambda: setattr(self.win, "busy", False))

    def on_pick_skin(self):
        self.status("Положите skin.png в папку " + SKIN_DIR)
        open_in_explorer(SKIN_DIR)

    def on_reset_skin(self):
        try:
            os.remove(os.path.join(SKIN_DIR, "skin.png"))
        except Exception:
            pass
        if skin_pack is not None:
            skin_pack.remove_skin_pack(MC_DIR)
            try:
                for entry in os.listdir(INSTANCES_DIR):
                    skin_pack.remove_skin_pack(os.path.join(INSTANCES_DIR, entry))
            except Exception:
                pass
        self.status("Скин сброшен.")

    def on_reset_settings(self):
        self.settings = {}
        write_json(SETTINGS_PATH, {})
        self.status("Настройки сброшены.")

    def on_open_mods_dir(self):
        label = str(self.win.selected_installed_instance)
        instance_id = getattr(self, "installed_instance_ids", {}).get(label, LEGACY_INSTANCE_ID)
        open_in_explorer(self.mods_dir(instance_id))

    def on_pick_mod_file(self):
        instance_id = str(self.win.version)
        if not instance_id:
            self.mods_status("Сначала выберите установленный инстанс на главной.")
            return
        open_in_explorer(self.mods_dir(instance_id))
        self.mods_status(f"Скопируйте .jar в папку mods инстанса {instance_id}.")
        self.refresh_installed()

    def on_search_mods(self):
        query = str(self.win.query).strip()
        if mod_catalog is None:
            return
        if not query:
            # пустой запрос: чистим прошлые результаты, чтобы не висели на странице
            self.win.found = slint.ListModel([])
            self.win.mods_status = ""
            return
        loader = self.loader_id()
        target = str(self.win.version)
        self.mods_status("Ищу на Modrinth...")

        def job():
            try:
                import urllib.request
                series = mod_catalog.series_of(target) or None
                results = mod_catalog.search_modrinth_mods(
                    query, loader=None if loader == "none" else loader, series=series)
                raw = []
                for r in results:
                    icon_data = None
                    ext = ".png"
                    url = str(r.get("icon_url") or "")
                    if url:
                        ext = ".svg" if url.lower().endswith(".svg") else ".png"
                        try:
                            req = urllib.request.Request(url, headers={"User-Agent": mod_catalog.UA})
                            with urllib.request.urlopen(req, timeout=15) as resp:
                                icon_data = resp.read()
                        except Exception:
                            icon_data = None
                    raw.append((r.get("id") or "", r.get("name") or "", r.get("note") or "",
                                list(r.get("versions") or []), icon_data, ext))

                def apply_found():
                    # карточки и картинки собираем только в потоке интерфейса
                    tiles = []
                    for mid, name, note, supported, icon_data, ext in raw:
                        icon = None
                        if icon_data:
                            try:
                                icon = cached_image(f"search_{mid}{ext}", icon_data)
                            except Exception:
                                icon = None
                        choices = self.mod_version_choices(supported)
                        tiles.append(self.tile(mid, name, note, icon,
                                               versions=choices,
                                               version=self.default_choice(choices)))
                    self.win.found = slint.ListModel(tiles)

                on_ui_thread(apply_found)
                self.mods_status(f"Найдено: {len(raw)}")
            except Exception as e:
                self.mods_status(f"Поиск не удался: {e}")

        threading.Thread(target=job, daemon=True).start()

    def on_install_mod(self, mod_id, instance_id=""):
        self.install_worker(str(mod_id), str(instance_id or ""))

    def on_install_found(self, mod_id, instance_id=""):
        self.install_worker(str(mod_id), str(instance_id or ""))

    def mod_install_ui(self, *, status=None, progress=None, indeterminate=None,
                       busy=None, name=None):
        """Единая безопасная точка обновления индикатора установки модов."""
        def apply():
            if status is not None:
                self.win.mods_status = status
            if progress is not None:
                self.win.mod_install_progress = float(progress)
            if indeterminate is not None:
                self.win.mod_install_indeterminate = bool(indeterminate)
            if busy is not None:
                self.win.mod_install_busy = bool(busy)
            if name is not None:
                self.win.mod_install_name = name

        on_ui_thread(apply)

    def mod_tile_ui(self, mod_id, *, progress=None, indeterminate=None, busy=None):
        """Обновляет плитку мода (каталог или поиск) прямо на месте кнопки."""
        def apply():
            def patch(data):
                tile = dict(data)
                if progress is not None:
                    tile["progress"] = float(progress)
                if indeterminate is not None:
                    tile["indeterminate"] = bool(indeterminate)
                if busy is not None:
                    tile["busy"] = bool(busy)
                return tile

            for model in (self.win.catalog, self.win.found):
                for row in range(model.row_count()):
                    data = model.row_data(row)
                    if data and str(data.get("id", "")) == str(mod_id):
                        model.set_row_data(row, patch(data))
                        return

        on_ui_thread(apply)

    def pick_version(self, versions, target, loader):
        """versions — словарь {версия Minecraft: {filename, url, loaders}}."""
        if not versions:
            return None
        series = mod_catalog.series_of(target) if target else ""

        def fits(info):
            info_loaders = info.get("loaders") or []
            return loader == "none" or not info_loaders or loader in info_loaders

        if target in versions and fits(versions[target]):
            return versions[target]
        keys = sorted(versions.keys(), key=mod_catalog.version_sort_key, reverse=True)
        for mc in keys:
            if series and not mod_catalog.matches_series(mc, series):
                continue
            if fits(versions[mc]):
                return versions[mc]
        for mc in keys:
            if fits(versions[mc]):
                return versions[mc]
        return None

    def download_file(self, url, dst):
        """Скачивает файл без прогресса — используется для зависимостей мода."""
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": mod_catalog.UA})
        with urllib.request.urlopen(req, timeout=mod_catalog.TIMEOUT) as resp, open(dst, "wb") as f:
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                f.write(chunk)

    def install_required_dependencies(self, info, mc_version, loader, folder, visited=None):
        """Скачивает обязательные зависимости мода (рекурсивно, без падений).

        Пропускает уже установленные файлы и циклы; ошибка при зависимости
        не ломает установку основного мода.
        """
        if visited is None:
            visited = set()
        installed = 0
        for dep in info.get("dependencies") or []:
            if dep.get("type") != "required":
                continue
            project_id = dep.get("project_id")
            if not project_id or project_id in visited:
                continue
            visited.add(project_id)
            dep_info = None
            try:
                version_id = dep.get("version_id")
                if version_id:
                    dep_info = mod_catalog.fetch_modrinth_version(version_id)
                if not dep_info:
                    versions = mod_catalog.fetch_modrinth_project_versions(project_id) or {}
                    dep_info = self.pick_version(versions, mc_version, loader)
            except Exception:
                dep_info = None
            if not dep_info:
                continue
            name = dep_info.get("filename") or f"{project_id}.jar"
            dst = os.path.join(folder, name)
            if os.path.isfile(dst):
                continue
            try:
                self.mods_status(f"Зависимость {project_id}: скачиваю {name}...")
                self.download_file(dep_info["url"], dst)
                installed += 1
                installed += self.install_required_dependencies(
                    dep_info, mc_version, loader, folder, visited)
            except Exception:
                try:
                    os.remove(dst)
                except OSError:
                    pass
                continue
        return installed

    @staticmethod
    def deps_word(count):
        count %= 100
        if 11 <= count <= 14:
            return "зависимостей"
        r = count % 10
        if r == 1:
            return "зависимость"
        if 2 <= r <= 4:
            return "зависимости"
        return "зависимостей"

    def repair_mod_dependencies(self, instance_id):
        """Лучший-effort: доскачивает недостающие зависимости модов, уже лежащих в папке."""
        if mod_catalog is None:
            return 0
        loader = self.instance_loader(instance_id)
        mc_version = base_mc_version(instance_id) or instance_id
        folder = self.mods_dir(instance_id)
        try:
            names = set(os.listdir(folder))
        except OSError:
            return 0
        installed = 0
        for mod in mod_catalog.CATALOG:
            mid = mod.get("id")
            if not mid:
                continue
            try:
                versions = mod_catalog.fetch_modrinth_project_versions(mod.get("project") or mid) or {}
                pick = versions.get(mc_version) or self.pick_version(versions, mc_version, loader)
                if not pick or pick.get("filename") not in names:
                    continue
                installed += self.install_required_dependencies(pick, mc_version, loader, folder, {mid})
            except Exception:
                continue
        return installed

    def install_worker(self, slug, instance_id=""):
        if mod_catalog is None:
            return
        if self.mod_install_busy:
            self.mods_status("Дождитесь завершения текущей установки мода.")
            return
        if slug == "optifine":
            self.mods_status("OptiFine ставится с optifine.net — на Modrinth его нет.")
            return
        instance_id = str(instance_id).strip()
        if not instance_id or instance_id not in self.installed_instances():
            self.mods_status("Выберите установленный Minecraft-инстанс.")
            return

        # Флаг ставим до запуска потока, чтобы двойной клик не создал две загрузки.
        self.mod_install_busy = True
        mc_version = base_mc_version(instance_id) or instance_id
        loader = self.instance_loader(instance_id)
        self.mod_install_ui(status=f"Подбираю версию {slug} для {instance_id}...",
                            progress=0, indeterminate=True, busy=True, name=slug)
        self.mod_tile_ui(slug, progress=0, indeterminate=True, busy=True)

        def job():
            dst = ""
            try:
                versions = mod_catalog.fetch_modrinth_project_versions(slug) or {}
                pick = versions.get(mc_version)
                if pick:
                    loaders = pick.get("loaders") or []
                    if loader != "none" and loaders and loader not in loaders:
                        pick = None
                if not pick:
                    pick = self.pick_version(versions, mc_version, loader)
                if not pick:
                    raise RuntimeError("подходящая версия мода не найдена")

                filename = pick.get("filename") or f"{slug}.jar"
                folder = self.mods_dir(instance_id)
                os.makedirs(folder, exist_ok=True)
                dst = os.path.join(folder, filename)
                self.mod_install_ui(status=f"Скачиваю {filename}...", indeterminate=True)
                self.mod_tile_ui(slug, indeterminate=True)

                import urllib.request
                req = urllib.request.Request(pick["url"], headers={"User-Agent": mod_catalog.UA})
                with urllib.request.urlopen(req, timeout=mod_catalog.TIMEOUT) as resp, open(dst, "wb") as f:
                    try:
                        total = int(resp.headers.get("Content-Length") or 0)
                    except (TypeError, ValueError):
                        total = 0
                    self.mod_install_ui(indeterminate=total <= 0, progress=0)
                    self.mod_tile_ui(slug, indeterminate=total <= 0, progress=0)
                    downloaded = 0
                    while True:
                        chunk = resp.read(64 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            percent = min(99.0, downloaded * 100.0 / total)
                            self.mod_install_ui(progress=percent)
                            self.mod_tile_ui(slug, progress=percent)

                deps_done = self.install_required_dependencies(pick, mc_version, loader, folder, {slug})
                deps_text = f" (+{deps_done} {self.deps_word(deps_done)})" if deps_done else ""
                self.mod_install_ui(
                    status=f"Установлен {filename} в {instance_id}{deps_text}",
                    progress=100, indeterminate=False)
                self.mod_tile_ui(slug, progress=100, indeterminate=False)
                on_ui_thread(lambda: self.refresh_installed(instance_id))
                # Оставляем завершённую полосу видимой на короткое время.
                import time
                time.sleep(0.7)
            except Exception as e:
                if dst:
                    try:
                        os.remove(dst)
                    except OSError:
                        pass
                self.mod_install_ui(status=f"Не удалось установить {slug}: {e}",
                                    progress=0, indeterminate=False)
                self.mod_tile_ui(slug, progress=0, indeterminate=False)
            finally:
                self.mod_install_busy = False
                self.mod_install_ui(busy=False, progress=0,
                                    indeterminate=False, name="")
                self.mod_tile_ui(slug, busy=False, progress=0, indeterminate=False)

        threading.Thread(target=job, daemon=True).start()

    def on_remove_mod(self, instance_id, name):
        try:
            folder = self.mods_dir(str(instance_id))
            path = os.path.abspath(os.path.join(folder, str(name)))
            if os.path.dirname(path) != os.path.abspath(folder):
                raise ValueError("некорректное имя файла")
            os.remove(path)
            self.mods_status(f"Удалён {name} из {instance_id}")
        except Exception as e:
            self.mods_status(f"Не удалось удалить: {e}")
        self.refresh_installed(str(instance_id))

    def run(self):
        self.win.run()


def main():
    # Cactus Crash Handler: лог падения в ~/.mcl/crashes + уведомление
    if crash_handler is not None:
        crash_handler.install(APP_VERSION)
    Launcher().run()


if __name__ == "__main__":
    main()
