#!/usr/bin/env python3
"""start_resolve.py — поднять DaVinci Resolve и дождаться готовности.

Запуск:
    python tools/start_resolve.py            # запустить, если не запущен
    python tools/start_resolve.py --wait 60  # ждать готовности 60 секунд
    python tools/start_resolve.py --status   # только проверить

Поддерживает:
  * обычную установку Windows и macOS;
  * портативные сборки Windows (Resolve.exe глубоко в ~/Downloads или ~/Tools) —
    для них ищется лаунчер ResolvePortable.exe рядом, он поднимает нужные службы;
  * запуск через `open -a` на macOS.

Что считается «готов»: процесс Resolve запущен. Скриптовый API может подняться чуть
позже — это проверяется отдельно (skills/.../resolve_doctor.py).
"""

from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import env_paths  # noqa: E402

# Вывод в UTF-8: консоль Windows по умолчанию не умеет «→» и «—».
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def is_running() -> bool:
    """Запущен ли Resolve прямо сейчас."""
    try:
        if os.name == "nt":
            out = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq Resolve.exe"],
                capture_output=True, text=True, timeout=20, check=False,
            )
            return "Resolve.exe" in (out.stdout or "")
        out = subprocess.run(
            ["pgrep", "-f", "DaVinci Resolve"], capture_output=True, text=True, timeout=20, check=False
        )
        return bool((out.stdout or "").strip())
    except Exception:
        return False


def _portable_launcher(exe: Path) -> Optional[Path]:
    """Рядом с Resolve.exe найти лаунчер портативной сборки."""
    names = ["ResolvePortable.exe", "Resolve.exe"]
    for parent in list(exe.parents)[:4]:
        for name in names:
            cand = parent / name
            if cand.is_file() and cand != exe:
                return cand
    return None


def launch(exe: Path) -> Optional[Path]:
    """Запустить Resolve. Возвращает исполняемый файл, которым запустили."""
    system = platform.system()

    if system == "Darwin":
        # /Applications/DaVinci Resolve.app/Contents/MacOS/Resolve -> .app
        app = None
        for parent in exe.parents:
            if parent.suffix == ".app":
                app = parent
                break
        cmd = ["open", "-a", str(app)] if app else [str(exe)]
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return exe
        except Exception as exc:
            print(f"[start_resolve] не удалось запустить: {exc}", file=sys.stderr)
            return None

    if os.name == "nt":
        launcher = _portable_launcher(exe)
        target = launcher or exe
        try:
            subprocess.Popen([str(target)], cwd=str(target.parent))
            return target
        except Exception as exc:
            print(f"[start_resolve] не удалось запустить: {exc}", file=sys.stderr)
            return None

    try:
        subprocess.Popen([str(exe)])
        return exe
    except Exception as exc:
        print(f"[start_resolve] не удалось запустить: {exc}", file=sys.stderr)
        return None


def wait_ready(timeout: int) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_running():
            # даём процессу поднять окно и API
            time.sleep(3)
            return True
        time.sleep(1)
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description="Запуск DaVinci Resolve")
    ap.add_argument("--status", action="store_true", help="только проверить, запущен ли")
    ap.add_argument("--wait", type=int, default=0, help="ждать готовности N секунд")
    ap.add_argument("--path", default="", help="явный путь к Resolve.exe / .app")
    args = ap.parse_args()

    exe_str = args.path or env_paths.resolve_exe()
    if not exe_str:
        print("[start_resolve] Resolve не найден.")
        print("  Укажи путь: python tools/start_resolve.py --path '<путь>'")
        print("  Или запиши в конфиг: python tools/env_paths.py set resolve_exe '<путь>'")
        return 1

    exe = Path(exe_str).expanduser()
    if not exe.exists():
        print(f"[start_resolve] путь не существует: {exe}")
        return 1

    running = is_running()
    print(f"[start_resolve] исполняемый файл: {exe}")
    print(f"[start_resolve] процесс: {'ЗАПУЩЕН' if running else 'не запущен'}")

    if args.status:
        return 0 if running else 1

    if not running:
        target = launch(exe)
        if target is None:
            return 1
        print(f"[start_resolve] запущен через {target}")
        if args.wait:
            ok = wait_ready(args.wait)
            print(f"[start_resolve] готовность: {'да' if ok else 'нет (таймаут)'}")
            return 0 if ok else 1
        else:
            print("[start_resolve] запущен. Проверь скриптовый API через resolve_doctor.py")
    else:
        print("[start_resolve] уже запущен — ничего не делаю")
        if args.wait:
            print("[start_resolve] готовность: да")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
