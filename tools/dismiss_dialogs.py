#!/usr/bin/env python3
"""dismiss_dialogs.py — снять модальные окна, которые блокируют скриптовый API Resolve.

Запуск:
    python tools/dismiss_dialogs.py             # закрыть и, если надо, перезапустить
    python tools/dismiss_dialogs.py --dry-run   # только показать, что будет сделано
    python tools/dismiss_dialogs.py --no-relaunch

Что делает
----------
1. Нативные диалоги с кнопкой «Continue» / «Продолжить» — нажимает её программно
   (Windows: Win32 BM_CLICK; macOS: AppleScript System Events).
2. Окно краш-репортера («Отчёт о сбоях» / «Отчет о сбоях» / Crash Reporter) — оно
   рисуется на Qt, кнопки через Win32 не видны и не кликаются. Единственный надёжный
   выход — убить процесс и поднять Resolve заново. Проект при этом не теряется:
   Resolve автосохраняется, а база проекта остаётся целой.

Проверено на Windows 01.11.2026: краш в 16:10:49, последнее сохранение в 16:10:40,
Project.db цела, PRAGMA integrity_check = ok.
"""

from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import env_paths  # noqa: E402

# Вывод в UTF-8: консоль Windows по умолчанию не умеет «→» и «—».
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

CONTINUE_LABELS = ("Continue", "Продолжить", "Продолжить ", "OK", "Ok")
CRASH_TITLES = ("Отчет о сбоях", "Отчёт о сбоях", "Crash Reporter", "Crash Report")
BM_CLICK = 0x00F5


# --- Windows -----------------------------------------------------------------

def _win_processes() -> List[Tuple[int, str]]:
    """(pid, заголовок главного окна) для всех процессов Resolve."""
    out: List[Tuple[int, str]] = []
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return out

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    # найти pid процессов с именем Resolve.exe
    pids: List[int] = []
    try:
        res = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq Resolve.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=20, check=False,
        )
        for line in (res.stdout or "").splitlines():
            parts = [p.strip('" ') for p in line.split('","')]
            if len(parts) >= 2 and parts[0].isdigit():
                pids.append(int(parts[0]))
    except Exception:
        return out

    for pid in pids:
        title = ""
        hwnd = None
        EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def cb(h, l):  # noqa: ANN001
            nonlocal hwnd
            p = wintypes.DWORD()
            user32.GetWindowThreadProcessId(h, ctypes.byref(p))
            if p.value == pid and user32.IsWindowVisible(h):
                hwnd = h
                return False
            return True

        user32.EnumWindows(EnumWindowsProc(cb), 0)
        if hwnd:
            length = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value
        out.append((pid, title))
    return out


def _win_click_continue() -> List[str]:
    """Найти и нажать кнопки Continue в нативных диалогах Resolve."""
    clicked: List[str] = []
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return clicked

    user32 = ctypes.windll.user32
    EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def win_text(h) -> str:
        n = user32.GetWindowTextLengthW(h)
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(h, buf, n + 1)
        return buf.value

    def win_class(h) -> str:
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, buf, 256)
        return buf.value

    for pid, _title in _win_processes():
        tops: List[int] = []

        def top_cb(h, l):  # noqa: ANN001
            p = wintypes.DWORD()
            user32.GetWindowThreadProcessId(h, ctypes.byref(p))
            if p.value == pid:
                tops.append(h)
            return True

        user32.EnumWindows(EnumWindowsProc(top_cb), 0)
        for top in tops:
            kids: List[int] = []

            def kid_cb(h, l):  # noqa: ANN001
                kids.append(h)
                return True

            user32.EnumChildWindows(top, EnumWindowsProc(kid_cb), 0)
            for k in kids:
                if win_class(k) == "Button":
                    txt = win_text(k).strip()
                    if txt in CONTINUE_LABELS:
                        clicked.append(txt)
                        user32.SendMessageW(k, BM_CLICK, 0, 0)
                        time.sleep(0.4)
    return clicked


# --- macOS -------------------------------------------------------------------

def _mac_dialogs() -> List[str]:
    """Тексты кнопок диалогов Resolve (AppleScript)."""
    script = """
    tell application "System Events"
      if not (exists process "Resolve") then return ""
      set out to ""
      tell process "Resolve"
        repeat with w in windows
          try
            repeat with b in buttons of w
              set out to out & (name of b) & "\\n"
            end repeat
          end try
        end repeat
      end tell
      return out
    end tell
    """
    try:
        res = subprocess.run(
            ["osascript", "-e", script], capture_output=True, text=True, timeout=30, check=False
        )
    except Exception:
        return []
    return [line.strip() for line in (res.stdout or "").splitlines() if line.strip()]


def _mac_click(label: str) -> bool:
    script = f'''
    tell application "System Events"
      if not (exists process "Resolve") then return false
      tell process "Resolve"
        repeat with w in windows
          try
            repeat with b in buttons of w
              if (name of b) is "{label}" then
                click b
                return true
              end if
            end repeat
          end try
        end repeat
      end tell
      return false
    end tell
    '''
    try:
        res = subprocess.run(
            ["osascript", "-e", script], capture_output=True, text=True, timeout=30, check=False
        )
        return "true" in (res.stdout or "").lower()
    except Exception:
        return False


# --- общее -------------------------------------------------------------------

def _relaunch() -> None:
    exe = env_paths.resolve_exe()
    if not exe:
        print("[dismiss] Resolve не найден — перезапуск не выполнен")
        return
    exe_path = Path(exe)
    if platform.system() == "Darwin":
        app = None
        for parent in exe_path.parents:
            if parent.suffix == ".app":
                app = parent
                break
        cmd = ["open", "-a", str(app)] if app else [str(exe_path)]
    else:
        cmd = [str(exe_path)]
    try:
        subprocess.Popen(cmd, cwd=str(exe_path.parent) if platform.system() != "Darwin" else None)
        print(f"[dismiss] Resolve перезапущен: {cmd}")
    except Exception as exc:
        print(f"[dismiss] не удалось перезапустить: {exc}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Снять модальные окна DaVinci Resolve")
    ap.add_argument("--dry-run", action="store_true", help="ничего не менять, только показать")
    ap.add_argument("--no-relaunch", action="store_true", help="не перезапускать после краша")
    args = ap.parse_args()

    system = platform.system()
    action = "none"

    if system == "Darwin":
        buttons = _mac_dialogs()
        if not buttons:
            print("[dismiss] окна Resolve не найдены (или процесс не запущен)")
        for label in buttons:
            if label in CONTINUE_LABELS:
                print(f"[dismiss] нажимаю '{label}'")
                if not args.dry_run:
                    _mac_click(label)
                action = "continue-clicked"
                time.sleep(0.4)
    elif os.name == "nt":
        procs = _win_processes()
        if not procs:
            print("[dismiss] Resolve не запущен")
            if not args.no_relaunch and not args.dry_run:
                _relaunch()
            print(f"[dismiss] итог: relaunched")
            return 0
        for pid, title in procs:
            print(f"[dismiss] Resolve PID {pid}: '{title}'")
            if any(t.lower() in title.lower() for t in CRASH_TITLES):
                print("[dismiss] КРАШ-РЕПОРТЕР: UI на Qt, кнопки не кликаются — убиваю процесс")
                action = "crash-restarted"
                if not args.dry_run:
                    subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, timeout=30)
                    time.sleep(5)
                    if not args.no_relaunch:
                        _relaunch()
        clicked = [] if args.dry_run else _win_click_continue()
        for label in clicked:
            print(f"[dismiss] нажата кнопка '{label}'")
            action = "continue-clicked"
    else:
        print("[dismiss] платформа не поддерживается для этой операции")
        return 1

    print(f"[dismiss] итог: {action}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
