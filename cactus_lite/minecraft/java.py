"""Locating a usable Java runtime, falling back to Mojang's bundled JVMs."""

import os
import re
import subprocess
from pathlib import Path

import minecraft_launcher_lib as mll

from cactus_lite.core.paths import MC_DIR
from cactus_lite.core.platform_utils import IS_WINDOWS, JAVA_EXECUTABLES, no_window_flags
from cactus_lite.minecraft.versions import required_java


def parse_version(text):
    m = re.search(r'version\s+"?(\d+)', text or "") or re.match(r"(\d+)", text or "")
    if not m:
        return None
    major = int(m.group(1))
    return 8 if major == 1 else major


def _probe(path):
    try:
        out = subprocess.run([path, "-version"], capture_output=True, text=True, timeout=10,
                             **no_window_flags())
        return parse_version((out.stderr or "") + (out.stdout or ""))
    except Exception:
        return None


def _search_dirs():
    dirs = []
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        dirs.append(os.path.join(java_home, "bin"))
    dirs += [d for d in os.environ.get("PATH", "").split(os.pathsep) if d]
    if IS_WINDOWS:
        globs = ("Java/*/bin", "Eclipse Adoptium/*/bin", "Microsoft/*/bin")
        for base in (os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", "")):
            if not base:
                continue
            for pattern in globs:
                try:
                    dirs += [str(p) for p in Path(base).glob(pattern)]
                except OSError:
                    pass
    else:
        for base in ("/usr/lib/jvm", "/Library/Java/JavaVirtualMachines",
                     "/opt/homebrew/opt/openjdk/bin"):
            try:
                dirs += [str(p) for p in Path(base).glob("*/Contents/Home/bin")]
                dirs += [str(p) for p in Path(base).glob("*/bin")]
            except OSError:
                pass
    return dirs


def find_java():
    """Best (path, major_version) pair available on this machine, or (None, None)."""
    candidates = []
    try:
        for info in mll.java_utils.find_system_java_versions_information():
            path = info.get("javaw_path") or info.get("path") or info.get("java_path")
            if path and os.path.isfile(path):
                candidates.append((path, parse_version(info.get("version"))))
    except Exception:
        pass

    if not candidates:
        seen = set()
        for directory in _search_dirs():
            for exe in JAVA_EXECUTABLES:
                path = os.path.join(directory, exe)
                if path not in seen and os.path.isfile(path):
                    seen.add(path)
                    candidates.append((path, _probe(path)))

    best = (None, None)
    for path, version in candidates:
        if best[0] is None or (best[1] or 0) < (version or 0):
            best = (path, version)
    return best


def _runtime_name(version, minimum, mc_dir):
    try:
        info = mll.runtime.get_version_runtime_information(version, mc_dir)
        if info and info.get("name"):
            return info["name"]
    except Exception:
        pass
    if minimum >= 21:
        return "java-21"
    return "java-17" if minimum >= 17 else "java-runtime-delta"


def ensure_java(version, mc_dir=MC_DIR, callback=None, on_status=None):
    """Return a Java path suitable for `version`, downloading a JVM if needed."""
    minimum = required_java(version, mc_dir)
    path, found = find_java()
    if path and found is not None and found >= minimum:
        return path

    name = _runtime_name(version, minimum, mc_dir)
    if on_status:
        on_status(f"Нужна Java {minimum}+. Скачиваю встроенную...")
    try:
        installed = set()
        try:
            installed = set(mll.runtime.get_installed_jvm_runtimes(mc_dir))
        except Exception:
            pass
        if name not in installed:
            mll.runtime.install_jvm_runtime(name, mc_dir, callback=callback or {})
    except Exception:
        if path:
            return path
        raise

    runtime_path = mll.runtime.get_executable_path(name, mc_dir)
    if runtime_path and os.path.isfile(runtime_path):
        return runtime_path
    if path:
        return path
    raise RuntimeError("Не удалось получить подходящую Java.")
