#!/usr/bin/env python3
"""doctor.py — проверить, что рабочая среда собрана, и сказать, чего не хватает.

Запуск:
    python tools/doctor.py            # полная проверка
    python tools/doctor.py --quiet    # только ошибки и предупреждения
    python tools/doctor.py --json     # машинный вывод

Что проверяется
---------------
  * Python и нужные модули (numpy, opencv, pillow, faster-whisper)
  * ffmpeg / ffprobe
  * DaVinci Resolve: установлен ли, запущен ли, доступен ли скриптовый API
  * папка LUT
  * Node (нужен для генерации DRX)
  * вендорные кодеки DRX/DRP и их npm-зависимости
  * свободное место на диске
  * ключ SFXMint (только факт наличия, значение никогда не печатается)

Код возврата: 0 — можно работать, 1 — есть блокирующие проблемы.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import env_paths  # noqa: E402

# Консоль Windows по умолчанию cp1251/cp866 и не умеет ни «→», ни «—».
# Переводим вывод в UTF-8 с заменой, чтобы отчёт не падал на ровном месте.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PACK_ROOT = env_paths.PACK_ROOT

OK = "OK"
WARN = "WARN"
FAIL = "FAIL"

results: List[Tuple[str, str, str]] = []


def record(status: str, name: str, detail: str = "") -> None:
    results.append((status, name, detail))


def check_python() -> None:
    ver = sys.version_info
    if ver >= (3, 9):
        record(OK, "python", f"{ver.major}.{ver.minor}.{ver.micro} ({sys.executable})")
    else:
        record(FAIL, "python", f"нужен 3.9+, стоит {ver.major}.{ver.minor}.{ver.micro}")

    optional = [
        ("numpy", "анализ кадров, огибающие"),
        ("cv2", "кадры, кропы, контроль"),
        ("PIL", "контактные листы, кадры"),
        ("faster_whisper", "транскрипция речи"),
    ]
    missing: List[str] = []
    for mod, why in optional:
        try:
            __import__(mod)
        except Exception:
            missing.append(f"{mod} ({why})")
    if missing:
        record(
            WARN,
            "python-модули",
            "не хватает: " + ", ".join(missing) + " → pip install numpy opencv-python pillow faster-whisper",
        )
    else:
        record(OK, "python-модули", "numpy, cv2, PIL, faster-whisper на месте")


def check_ffmpeg() -> None:
    ff = env_paths.ffmpeg()
    if not ff:
        record(FAIL, "ffmpeg", "не найден. macOS: brew install ffmpeg; Windows: winget install Gyan.FFmpeg")
        record(FAIL, "ffprobe", "не найден (ставится вместе с ffmpeg)")
        return
    ver = ""
    try:
        out = subprocess.run(
            [ff, "-version"], capture_output=True, text=True, timeout=20, check=False
        )
        ver = (out.stdout or "").splitlines()[0] if out.stdout else ""
    except Exception as exc:
        record(WARN, "ffmpeg", f"найден, но не запускается: {exc}")
        return
    record(OK, "ffmpeg", ver)
    fp = env_paths.ffprobe()
    if fp:
        record(OK, "ffprobe", fp)
    else:
        record(FAIL, "ffprobe", "не найден — нужен для замеров (ffprobe -show_streams)")


def _resolve_modules_dirs() -> List[Path]:
    dirs: List[Path] = []
    if sys.platform == "darwin":
        dirs.append(
            Path("/Library/Application Support/Blackmagic Design/DaVinci Resolve")
            / "Developer" / "Scripting" / "Modules"
        )
    elif os.name == "nt":
        dirs.append(
            Path("C:/ProgramData/Blackmagic Design/DaVinci Resolve")
            / "Support" / "Developer" / "Scripting" / "Modules"
        )
        dirs.append(
            Path(os.environ.get("APPDATA", ""))
            / "Blackmagic Design" / "DaVinci Resolve" / "Support" / "Developer"
            / "Scripting" / "Modules"
        )
    return [d for d in dirs if d.is_dir()]


def check_resolve() -> None:
    exe = env_paths.resolve_exe()
    if not exe:
        record(
            WARN,
            "resolve",
            "не найден. macOS: /Applications/DaVinci Resolve.app; Windows: Program Files/Blackmagic Design",
        )
    else:
        record(OK, "resolve", exe)

    running = False
    try:
        if os.name == "nt":
            out = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq Resolve.exe"],
                capture_output=True, text=True, timeout=20, check=False,
            )
            running = "Resolve.exe" in (out.stdout or "")
        else:
            out = subprocess.run(
                ["pgrep", "-f", "DaVinci Resolve"], capture_output=True, text=True, timeout=20, check=False
            )
            running = bool((out.stdout or "").strip())
    except Exception:
        running = False
    record(
        OK if running else WARN,
        "resolve-процесс",
        "запущен" if running else "не запущен — подними Resolve, иначе скриптовый API недоступен",
    )

    mods = _resolve_modules_dirs()
    if mods:
        found = []
        for d in mods:
            if list(d.glob("DaVinciResolveScript.py")):
                found.append(str(d))
        if found:
            record(OK, "resolve-scripting-api", found[0])
        else:
            record(WARN, "resolve-scripting-api", f"папка есть, но модуля нет: {mods[0]}")
    else:
        record(
            WARN,
            "resolve-scripting-api",
            "внешняя папка модулей не найдена — скрипты будут работать только внутри Resolve (MCP/bridge)",
        )


def check_lut() -> None:
    lut = env_paths.lut_dir()
    if lut and Path(lut).is_dir():
        count = len(list(Path(lut).rglob("*.cube")))
        record(OK, "lut-dir", f"{lut} ({count} .cube)")
    else:
        record(WARN, "lut-dir", "не найдена — LUT берём из локальной установки Resolve")


def check_node_and_vendor() -> None:
    node = env_paths.node()
    if not node:
        record(WARN, "node", "не найден — нужен для генерации DRX (nodejs.org)")
    else:
        record(OK, "node", node)

    vendor = PACK_ROOT / "vendor"
    drx = vendor / "resolve-mcp-advanced" / "resolve-advanced" / "vendor" / "drx-codec"
    if drx.is_dir():
        record(OK, "vendor-кодеки", f"drx-codec найден ({len(list(drx.glob('*.js')))} файлов)")
    else:
        record(WARN, "vendor-кодеки", "drx-codec не найден — генерация DRX невозможна")

    # npm-зависимости: zstd-codec и fzstd нужны кодеку.
    # Node ищет их вверх по дереву, поэтому годятся и vendor/node_modules, и корень пака.
    have: List[str] = []
    for base in (PACK_ROOT / "vendor" / "node_modules", PACK_ROOT / "node_modules"):
        for pkg in ("zstd-codec", "fzstd"):
            if (base / pkg).is_dir() and pkg not in have:
                have.append(pkg)
    if len(have) == 2:
        record(OK, "npm-зависимости", "zstd-codec, fzstd на месте")
    elif node:
        record(
            WARN,
            "npm-зависимости",
            "нет: " + ", ".join(p for p in ("zstd-codec", "fzstd") if p not in have)
            + f' -> cd "{PACK_ROOT / "vendor"}" && npm install',
        )
    else:
        record(WARN, "npm-зависимости", "нет node — зависимости не проверить")


def check_disk() -> None:
    try:
        usage = shutil.disk_usage(PACK_ROOT)
        free_gb = usage.free / (1024 ** 3)
        if free_gb < 5:
            record(WARN, "диск", f"свободно {free_gb:.1f} ГБ — для превью и рендеров нужно больше")
        else:
            record(OK, "диск", f"свободно {free_gb:.1f} ГБ")
    except Exception as exc:
        record(WARN, "диск", f"не определить: {exc}")


def check_sfxmint_key() -> None:
    has_key = bool(os.environ.get("SFXMINT_API_KEY", "").strip())
    record(
        OK if has_key else WARN,
        "sfxmint-ключ",
        "задан в окружении" if has_key else "не задан — доступна только библиотека CC0, генерация закрыта",
    )


def check_paths_config() -> None:
    cfg = env_paths.load_config()
    if not cfg:
        record(
            WARN,
            "config/env.json",
            "пусто — автодетект работает, но свои пути лучше зафиксировать: "
            "python tools/env_paths.py set src_root <папка>",
        )
    else:
        record(OK, "config/env.json", ", ".join(sorted(cfg)))
    src = env_paths.src_root()
    if src:
        record(OK, "src_root", str(src))
    else:
        record(WARN, "src_root", "не задан — исходники текущего проекта не подключены")


def main() -> int:
    ap = argparse.ArgumentParser(description="Проверка рабочей среды видеомонтажа")
    ap.add_argument("--quiet", action="store_true", help="только проблемы")
    ap.add_argument("--json", action="store_true", help="машинный вывод")
    args = ap.parse_args()

    check_python()
    check_ffmpeg()
    check_resolve()
    check_lut()
    check_node_and_vendor()
    check_disk()
    check_sfxmint_key()
    check_paths_config()

    failures = [r for r in results if r[0] == FAIL]
    warnings = [r for r in results if r[0] == WARN]

    if args.json:
        print(
            json.dumps(
                {
                    "checks": [{"status": s, "name": n, "detail": d} for s, n, d in results],
                    "failures": len(failures),
                    "warnings": len(warnings),
                    "ok": not failures,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1 if failures else 0

    icon = {OK: "[ ok ]", WARN: "[warn]", FAIL: "[FAIL]"}
    print("=" * 72)
    print("ПРОВЕРКА СРЕДЫ")
    print("=" * 72)
    for status, name, detail in results:
        if args.quiet and status == OK:
            continue
        print(f"{icon[status]} {name:<22} {detail}")
    print("-" * 72)
    print(f"провалов: {len(failures)}   предупреждений: {len(warnings)}")
    if failures:
        print("ВЕРДИКТ: работать нельзя — сначала чиним провалы.")
    elif warnings:
        print("ВЕРДИКТ: можно работать, но часть возможностей ограничена (см. warn).")
    else:
        print("ВЕРДИКТ: среда готова.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
