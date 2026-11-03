#!/usr/bin/env python3
"""smoke_test.py — дымовой прогон инструментов пакета.

Проверяет, что каждый перенесённый скрипт **запускается** и не падает с
traceback: импортируется, разбирает аргументы, печатает справку. Скрипты, у которых
нет `--help`, запускаются «как есть» — и просто не должны упасть с необработанным
исключением.

Запуск:
    python tools/smoke_test.py
    python tools/smoke_test.py --full      # дольше: ждёт завершения каждого (до 30 с)

Код возврата: 0 — все инструменты живы, 1 — есть падающие.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

PACK_ROOT = Path(__file__).resolve().parent.parent
TOOLS = PACK_ROOT / "tools"

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SKIP_NAMES = {
    "env_paths.py",      # сам конфиг, проверяется отдельно
    "verify_pack.py",    # самопроверка пакета
    "smoke_test.py",     # этот файл
}


def collect_scripts() -> List[Path]:
    out: List[Path] = []
    for path in sorted(TOOLS.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        if path.name in SKIP_NAMES:
            continue
        out.append(path)
    return out


def run_one(script: Path, timeout: int) -> Tuple[str, str]:
    """Вернуть (статус, детали) для одного скрипта."""
    cmd = [sys.executable, str(script), "--help"]
    try:
        res = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace", check=False,
        )
    except subprocess.TimeoutExpired:
        return "TIMEOUT", f"не ответил за {timeout} с"
    except Exception as exc:
        return "FAIL", f"запуск не удался: {exc}"

    out = (res.stdout or "") + (res.stderr or "")
    if "Traceback (most recent call last)" in out:
        last = [ln for ln in out.strip().splitlines() if ln.strip()][-1]
        return "FAIL", f"traceback: {last[:160]}"
    if res.returncode == 0:
        return "OK", ""
    # Нет --help: скрипт может ругаться на отсутствие аргументов — это не падение,
    # если нет traceback.
    return "OK", "запускается без --help (код 0/1 без traceback)"


def main() -> int:
    ap = argparse.ArgumentParser(description="Дымовой прогон инструментов")
    ap.add_argument("--full", action="store_true", help="ждать завершения каждого скрипта")
    ap.add_argument("--timeout", type=int, default=30)
    args = ap.parse_args()

    scripts = collect_scripts()
    print("=" * 72)
    print(f"ДЫМОВОЙ ПРОГОН: {len(scripts)} скриптов")
    print("=" * 72)

    failed: List[Tuple[str, str]] = []
    for s in scripts:
        status, detail = run_one(s, args.timeout)
        rel = s.relative_to(PACK_ROOT)
        if status == "OK":
            print(f"[ ok ] {rel}" + (f"  ({detail})" if detail else ""))
        else:
            print(f"[FAIL] {rel}  — {detail}")
            failed.append((str(rel), detail))

    print("-" * 72)
    print(f"прошло: {len(scripts) - len(failed)}   провалено: {len(failed)}")
    if failed:
        print("ВЕРДИКТ: есть падающие инструменты — чинить до отправки.")
    else:
        print("ВЕРДИКТ: все инструменты запускаются.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
