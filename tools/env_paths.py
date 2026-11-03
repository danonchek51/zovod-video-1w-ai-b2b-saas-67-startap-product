"""env_paths.py — единый источник правды о путях окружения.

Зачем этот модуль
-----------------
В пакете лежит много инструментов, и все они должны одинаково находить:
  * ffmpeg / ffprobe
  * DaVinci Resolve (и его LUT-папку)
  * папку с исходниками текущего проекта
  * папку для рабочих артефактов
  * Python / Node

На Windows пути выглядят иначе, чем на macOS, и у разных машин они разные.
Поэтому здесь ровно одно место, где живёт логика поиска, а остальные скрипты
берут пути отсюда и никогда не хардкодят их сами.

Приоритет (по убыванию)
------------------------
1. Переменная окружения:  ZOVOD_FFMPEG, ZOVOD_FFPROBE, ZOVOD_RESOLVE,
   ZOVOD_LUT_DIR, ZOVOD_SRC_ROOT, ZOVOD_PROJECT_ROOT, ZOVOD_WORK_ROOT,
   ZOVOD_ENV_FILE (путь к другому конфиг-файлу).
2. Файл конфига:  <PACK>/config/env.json   (правится руками, переживает перезапуск).
3. Автодетект:    PATH, стандартные места установки, портативные сборки.

Конфиг можно посмотреть и записать:
    python tools/env_paths.py show
    python tools/env_paths.py set src_root "D:/Shoot/raw"
    python tools/env_paths.py set ffmpeg "/opt/homebrew/bin/ffmpeg"

Только стандартная библиотека — чтобы работал на любой машине с Python 3.10+.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Консоль Windows по умолчанию cp1251/cp866: вывод в UTF-8, иначе отчёт падает
# на любом символе вне ASCII («→», «—», «≥»).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# --- геометрия пака ---------------------------------------------------------

PACK_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PACK_ROOT / "config"
CONFIG_FILE = CONFIG_DIR / "env.json"

#: Ключи, которые разрешено писать в конфиг.
CONFIG_KEYS = (
    "ffmpeg",
    "ffprobe",
    "resolve_exe",
    "lut_dir",
    "src_root",
    "project_root",
    "work_root",
    "python",
    "node",
)

_ENV_KEYS = {
    "ffmpeg": "ZOVOD_FFMPEG",
    "ffprobe": "ZOVOD_FFPROBE",
    "resolve_exe": "ZOVOD_RESOLVE",
    "lut_dir": "ZOVOD_LUT_DIR",
    "src_root": "ZOVOD_SRC_ROOT",
    "project_root": "ZOVOD_PROJECT_ROOT",
    "work_root": "ZOVOD_WORK_ROOT",
    "python": "ZOVOD_PYTHON",
    "node": "ZOVOD_NODE",
}


# --- конфиг -----------------------------------------------------------------

def config_path() -> Path:
    """Путь к файлу конфига (можно переопределить через ZOVOD_ENV_FILE)."""
    custom = os.environ.get("ZOVOD_ENV_FILE")
    if custom:
        return Path(custom).expanduser()
    return CONFIG_FILE


def load_config() -> Dict[str, Any]:
    """Прочитать config/env.json. Отсутствие файла — не ошибка."""
    path = config_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        print(f"[env_paths] config unreadable: {exc}", file=sys.stderr)
        return {}
    return data if isinstance(data, dict) else {}


def save_config(cfg: Dict[str, Any]) -> Path:
    """Записать конфиг, оставив только известные ключи."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    clean = {k: v for k, v in cfg.items() if k in CONFIG_KEYS and v}
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def get(key: str, default: Optional[str] = None) -> Optional[str]:
    """Значение параметра: env-переменная > конфиг > default."""
    env_name = _ENV_KEYS.get(key)
    if env_name:
        val = os.environ.get(env_name, "").strip()
        if val:
            return val
    val = load_config().get(key)
    if isinstance(val, str) and val.strip():
        return val.strip()
    return default


def set_value(key: str, value: str) -> Path:
    """Записать значение в конфиг (пустая строка = сброс)."""
    if key not in CONFIG_KEYS:
        raise KeyError(f"unknown key: {key}; allowed: {', '.join(CONFIG_KEYS)}")
    cfg = load_config()
    if value:
        cfg[key] = value
    else:
        cfg.pop(key, None)
    return save_config(cfg)


# --- автодетект -------------------------------------------------------------

def _first_existing(paths: List[Path]) -> Optional[Path]:
    for p in paths:
        if p and p.exists():
            return p
    return None


def _glob_first(patterns: List[str], max_depth: int = 4) -> Optional[Path]:
    """Найти первый файл по glob-паттернам (без рекурсии по всему диску)."""
    for pattern in patterns:
        try:
            hits = sorted(Path(p).glob(pattern))
        except (OSError, ValueError):
            continue
        if hits:
            return hits[0]
    return None


def detect_ffmpeg() -> Optional[str]:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    home = Path.home()
    local = os.environ.get("LOCALAPPDATA", "")
    candidates: List[Path] = []
    if sys.platform == "darwin":
        candidates += [
            Path("/opt/homebrew/bin/ffmpeg"),
            Path("/usr/local/bin/ffmpeg"),
            Path("/opt/local/bin/ffmpeg"),
            home / "bin" / "ffmpeg",
        ]
    elif os.name == "nt":
        if local:
            candidates.append(Path(local) / "Microsoft" / "WinGet" / "Links" / "ffmpeg.exe")
        candidates += [
            Path("C:/ffmpeg/bin/ffmpeg.exe"),
            Path("C:/Program Files/ffmpeg/bin/ffmpeg.exe"),
        ]
        # портативная раскладка: ~/Tools/ffmpeg/<версия>/bin/ffmpeg.exe
        candidates += sorted((home / "Tools" / "ffmpeg").glob("*/bin/ffmpeg.exe"))
    found = _first_existing(candidates)
    return str(found) if found else None


def detect_ffprobe() -> Optional[str]:
    exe = shutil.which("ffprobe")
    if exe:
        return exe
    ff = ffmpeg()
    if ff:
        sib = Path(ff).with_name("ffprobe" + (".exe" if os.name == "nt" else ""))
        if sib.exists():
            return str(sib)
    return None


def detect_resolve() -> Optional[str]:
    """Найти исполняемый файл DaVinci Resolve."""
    home = Path.home()
    candidates: List[Path] = []
    if sys.platform == "darwin":
        for app in ("DaVinci Resolve", "DaVinci Resolve Studio"):
            candidates += [
                Path("/Applications") / f"{app}.app" / "Contents" / "MacOS" / "Resolve",
                home / "Applications" / f"{app}.app" / "Contents" / "MacOS" / "Resolve",
            ]
    elif os.name == "nt":
        for env in ("ProgramFiles", "ProgramFiles(x86)"):
            base = os.environ.get(env)
            if base:
                candidates.append(
                    Path(base) / "Blackmagic Design" / "DaVinci Resolve" / "Resolve.exe"
                )
        # портативная сборка: Resolve.exe глубоко в ~/Downloads или ~/Tools
        for base in (home / "Downloads", home / "Tools", home / "Desktop"):
            candidates += sorted(base.glob("**/Resolve.exe"))[:1]
    found = _first_existing(candidates)
    return str(found) if found else None


def detect_lut_dir() -> Optional[str]:
    candidates: List[Path] = []
    if sys.platform == "darwin":
        candidates += [
            Path("/Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT"),
            Path.home() / "Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT",
        ]
    elif os.name == "nt":
        candidates += [
            Path("C:/ProgramData/Blackmagic Design/DaVinci Resolve/Support/LUT"),
            Path(os.environ.get("ProgramData", "C:/ProgramData"))
            / "Blackmagic Design" / "DaVinci Resolve" / "Support" / "LUT",
        ]
    found = _first_existing(candidates)
    return str(found) if found else None


def detect_node() -> Optional[str]:
    return shutil.which("node")


# --- публичные аксессоры ----------------------------------------------------

def ffmpeg() -> Optional[str]:
    return get("ffmpeg") or detect_ffmpeg()


def ffprobe() -> Optional[str]:
    return get("ffprobe") or detect_ffprobe()


def resolve_exe() -> Optional[str]:
    return get("resolve_exe") or detect_resolve()


def lut_dir() -> Optional[str]:
    return get("lut_dir") or detect_lut_dir()


def node() -> Optional[str]:
    return get("node") or detect_node()


def python_exe() -> str:
    return get("python") or sys.executable


def src_root() -> Optional[Path]:
    """Папка с исходниками текущего проекта (только чтение)."""
    val = get("src_root")
    return Path(val).expanduser() if val else None


def project_root() -> Path:
    """Корень текущего проекта (где лежит рабочий проект и его артефакты)."""
    val = get("project_root")
    return Path(val).expanduser() if val else (PACK_ROOT / "project")


def work_root() -> Path:
    """Куда складывать рабочие артефакты (кадры, отчёты, промежуточные файлы).

    Папку НЕ создаёт: путь — это адрес, а не действие. Создавай явно:
    env_paths.ensure_work_root()
    """
    val = get("work_root")
    return Path(val).expanduser() if val else (project_root() / "work")


def ensure_work_root() -> Path:
    """Создать рабочую папку (если ещё нет) и вернуть её."""
    root = work_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def describe() -> Dict[str, Any]:
    """Сводка окружения — её печатает doctor.py."""
    return {
        "pack_root": str(PACK_ROOT),
        "platform": f"{sys.platform} ({os.name})",
        "python": python_exe(),
        "python_version": sys.version.split()[0],
        "ffmpeg": ffmpeg(),
        "ffprobe": ffprobe(),
        "resolve_exe": resolve_exe(),
        "lut_dir": lut_dir(),
        "node": node(),
        "src_root": str(src_root()) if src_root() else None,
        "project_root": str(project_root()),
        "work_root": str(work_root()),
        "config_file": str(config_path()),
        "config_exists": config_path().is_file(),
    }


# --- CLI ---------------------------------------------------------------------

def _main(argv: List[str]) -> int:
    if not argv:
        print(json.dumps(describe(), ensure_ascii=False, indent=2))
        return 0
    cmd = argv[0]
    if cmd == "show":
        print(json.dumps(describe(), ensure_ascii=False, indent=2))
        return 0
    if cmd == "set":
        if len(argv) < 3:
            print("usage: env_paths.py set <key> <value>", file=sys.stderr)
            return 2
        path = set_value(argv[1], argv[2])
        print(f"записано в {path}: {argv[1]} = {argv[2]}")
        return 0
    if cmd == "unset":
        if len(argv) < 2:
            print("usage: env_paths.py unset <key>", file=sys.stderr)
            return 2
        path = set_value(argv[1], "")
        print(f"сброшено в {path}: {argv[1]}")
        return 0
    if cmd == "detect":
        print(json.dumps(describe(), ensure_ascii=False, indent=2))
        return 0
    print("usage: env_paths.py [show|detect|set <key> <value>|unset <key>]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
