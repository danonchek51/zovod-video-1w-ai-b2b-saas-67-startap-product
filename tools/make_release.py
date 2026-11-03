#!/usr/bin/env python3
"""make_release.py — собрать готовые к отправке архивы пакета.

Запуск:
    python tools/make_release.py              # собрать оба архива в ../dist
    python tools/make_release.py --out D:\\out

Что делает
----------
Собирает **два** архива из одной и той же папки пакета:

  * ``ZOVod-Video-Env-Windows.zip`` — с ``ПЕРВЫЙ_ШАГ-WINDOWS.md`` наверху;
  * ``ZOVod-Video-Env-macOS.zip``   — с ``ПЕРВЫЙ_ШАГ-MACOS.md`` наверху.

Внутри архива — папка ``ZOVod-Video-Env/`` (имя без пробелов и скобок: так удобнее
распаковывать и запускать команды). Всё остальное содержимое пакета попадает в архив
без изменений.

Печатает для каждого архива: размер, число файлов и SHA-256 — чтобы передачу можно
было проверить, не распаковывая.

Исключаются: ``.git``, ``__pycache__``, ``node_modules`` (ставится на месте командой
``cd vendor && npm install``), локальный ``config/env.json``.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import zipfile
from pathlib import Path
from typing import List

PACK_ROOT = Path(__file__).resolve().parent.parent

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

EXCLUDE_DIRS = {".git", "__pycache__", ".pytest_cache"}
EXCLUDE_FILES = {"env.json", ".DS_Store"}

#: npm-зависимости (zstd-codec, fzstd). В архив для товарища они кладутся,
#: чтобы папка работала сразу и без сети. В git-репозиторий — нет:
#: там ставится командой `cd vendor && npm install`.
INCLUDE_VENDOR_NODE_MODULES = True

RELEASES = [
    {
        "zip": "ZOVod-Video-Env-Windows.zip",
        "quickstart": "platforms/windows/START_WINDOWS.md",
        "quickstart_name": "ПЕРВЫЙ_ШАГ-WINDOWS.md",
        "title": "Windows",
    },
    {
        "zip": "ZOVod-Video-Env-macOS.zip",
        "quickstart": "platforms/macos/START_MACOS.md",
        "quickstart_name": "ПЕРВЫЙ_ШАГ-MACOS.md",
        "title": "macOS",
    },
]

ROOT_NAME = "ZOVod-Video-Env"


def iter_pack_files() -> List[Path]:
    out: List[Path] = []
    for path in PACK_ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(PACK_ROOT).parts
        if any(part == "__pycache__" or part == ".git" for part in rel_parts):
            continue
        if "node_modules" in rel_parts:
            # npm-зависимости кладём только из vendor/ и только если разрешено
            if not (INCLUDE_VENDOR_NODE_MODULES and rel_parts[0] == "vendor"):
                continue
        if path.name in EXCLUDE_FILES:
            continue
        out.append(path)
    return out


def build(out_dir: Path, rel: dict) -> dict:
    files = iter_pack_files()
    target = out_dir / rel["zip"]
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for f in files:
            arc = f"{ROOT_NAME}/{f.relative_to(PACK_ROOT).as_posix()}"
            zf.write(f, arc)
        # платформенный быстрый старт наверх архива
        qs = PACK_ROOT / rel["quickstart"]
        if qs.is_file():
            zf.writestr(f"{ROOT_NAME}/{rel['quickstart_name']}", qs.read_text(encoding="utf-8"))
        else:
            print(f"[make_release] ВНИМАНИЕ: нет файла {qs}", file=sys.stderr)

    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    return {
        "zip": target,
        "files": len(files) + 1,
        "bytes": target.stat().st_size,
        "sha256": digest,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Собрать архивы пакета")
    ap.add_argument("--out", default=str(PACK_ROOT.parent / "dist"))
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print("СБОРКА АРХИВОВ")
    print("=" * 72)
    results = []
    for rel in RELEASES:
        res = build(out_dir, rel)
        results.append(res)
        print(f"[{rel['title']:>8}] {res['zip'].name}")
        print(f"            файлов: {res['files']}   размер: {res['bytes'] / 1048576:.2f} МБ")
        print(f"            sha256: {res['sha256']}")
    print("-" * 72)
    print(f"готово: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
