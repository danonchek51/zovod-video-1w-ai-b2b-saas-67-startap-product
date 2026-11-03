#!/usr/bin/env python3
"""verify_pack.py — самопроверка пакета перед отправкой.

Запуск:
    python tools/verify_pack.py
    python tools/verify_pack.py --json

Что проверяет
-------------
1. **Синтаксис** — все .py компилируются (compileall).
2. **Утечки проекта** — в пакете не осталось названий конкретного проекта, клипов,
   людей и абсолютных путей чужой машины.
3. **Секреты** — ключи, токены, пароли. Значение ключа не печатается, только факт.
4. **Ссылки** — пути вида `tools/…`, `docs/…`, `skills/…` внутри markdown реально
   существуют (битые ссылки — самая частая поломка при переносе).
5. **Состав** — сколько файлов, сколько весит, нет ли гигантских файлов.

Код возврата: 0 — пакет готов к отправке, 1 — есть находки.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

PACK_ROOT = Path(__file__).resolve().parent.parent

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

#: Строки, которых не должно остаться в пакете.
FORBIDDEN = [
    "MissUIS2",
    "miss_uis2",
    "Мисс УИС",
    "C:\\ONEW",
    "C:\\Users\\user",
    "F:\\проект",
    "C0125",
    "C0140",
    "C0141",
    "Юля",
    "Алина",
]

#: Признаки секретов (значения не печатаются — только имя файла и находка).
SECRET_PATTERNS = [
    (r"sfx_live_[A-Za-z0-9]{8,}", "ключ SFXMint"),
    (r"ghp_[A-Za-z0-9]{20,}", "токен GitHub"),
    (r"github_pat_[A-Za-z0-9_]{20,}", "токен GitHub (fine-grained)"),
    (r"sk-[A-Za-z0-9]{20,}", "ключ API (openai-подобный)"),
    (r"AKIA[0-9A-Z]{16}", "ключ AWS"),
    (r"AIza[0-9A-Za-z_\-]{30,}", "ключ Google API"),
    (r"(?i)(api[_-]?key|secret|password|passwd)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}['\"]", "зашитый ключ"),
]

#: Пути-упоминания, которые должны существовать в пакете.
PATH_RE = re.compile(r"`((?:tools|docs|skills|vendor|templates|examples|config|platforms)/[A-Za-z0-9_./\-]+)`")
PATH_RE2 = re.compile(r"(?<![\w/])((?:tools|docs|skills|vendor|templates|examples|config|platforms)/[A-Za-z0-9_./\-]+\.(?:py|md|json|js|sh))")

SKIP_DIRS = {".git", "__pycache__", "node_modules"}

#: Пути, которые появляются в пакете только во время работы — их не существует
#: до первого запуска, и это нормально.
ALLOWED_MISSING = {
    "config/env.json",
    "vendor/drx-codec",
}


def iter_files(root: Path) -> List[Path]:
    out: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            out.append(Path(dirpath) / name)
    return out


def check_syntax() -> Dict[str, Any]:
    res = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", str(PACK_ROOT / "tools")],
        capture_output=True, text=True, timeout=300, check=False,
    )
    res2 = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", str(PACK_ROOT / "skills")],
        capture_output=True, text=True, timeout=300, check=False,
    )
    problems = (res.stdout + res.stderr + res2.stdout + res2.stderr).strip()
    return {"ok": (res.returncode == 0 and res2.returncode == 0), "detail": problems}


def check_forbidden(files: List[Path]) -> List[Dict[str, Any]]:
    hits: List[Dict[str, Any]] = []
    for f in files:
        if f.suffix.lower() not in {".py", ".md", ".json", ".js", ".txt", ".sh", ".example"}:
            continue
        # сам проверочный скрипт содержит искомые строки как образцы — себя не проверяем
        if f.name == Path(__file__).name:
            continue
        try:
            text = f.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
        for needle in FORBIDDEN:
            if needle in text:
                hits.append({"file": str(f.relative_to(PACK_ROOT)), "pattern": needle})
    return hits


def check_secrets(files: List[Path]) -> List[Dict[str, Any]]:
    hits: List[Dict[str, Any]] = []
    for f in files:
        if f.suffix.lower() not in {".py", ".md", ".json", ".js", ".txt", ".sh", ".example", ".env"}:
            continue
        try:
            text = f.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
        for pattern, label in SECRET_PATTERNS:
            for m in re.finditer(pattern, text):
                hits.append({"file": str(f.relative_to(PACK_ROOT)), "kind": label})
                break
    return hits


def check_links(files: List[Path]) -> List[Dict[str, Any]]:
    broken: List[Dict[str, Any]] = []
    for f in files:
        if f.suffix.lower() != ".md":
            continue
        # Вендор — чужой репозиторий: его внутренние ссылки ведут в его же
        # структуру, а не в наш пакет. Не считаем их битыми.
        rel_parts = f.relative_to(PACK_ROOT).parts
        if rel_parts and rel_parts[0] == "vendor":
            continue
        try:
            text = f.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
        refs = set(PATH_RE.findall(text)) | set(PATH_RE2.findall(text))
        for ref in refs:
            ref = ref.rstrip(".,;:)")
            if "<" in ref or ">" in ref:
                continue
            if ref in ALLOWED_MISSING:
                continue
            target = PACK_ROOT / ref
            if not target.exists():
                broken.append({"file": str(f.relative_to(PACK_ROOT)), "ref": ref})
    return broken


def check_composition(files: List[Path]) -> Dict[str, Any]:
    big = [
        {"file": str(f.relative_to(PACK_ROOT)), "mb": round(f.stat().st_size / 1048576, 2)}
        for f in files
        if f.stat().st_size > 5 * 1048576
    ]
    total = sum(f.stat().st_size for f in files)
    return {
        "files": len(files),
        "mb": round(total / 1048576, 2),
        "oversized": big,
        "by_ext": _by_ext(files),
    }


def _by_ext(files: List[Path]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for f in files:
        ext = f.suffix.lower() or "(без расширения)"
        out[ext] = out.get(ext, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def main() -> int:
    ap = argparse.ArgumentParser(description="Самопроверка пакета")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    files = iter_files(PACK_ROOT)
    syntax = check_syntax()
    forbidden = check_forbidden(files)
    secrets = check_secrets(files)
    broken = check_links(files)
    comp = check_composition(files)

    report = {
        "pack_root": str(PACK_ROOT),
        "syntax": syntax,
        "forbidden_hits": forbidden,
        "secret_hits": secrets,
        "broken_links": broken,
        "composition": comp,
        "ok": syntax["ok"] and not forbidden and not secrets and not broken,
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 1

    print("=" * 72)
    print("САМОПРОВЕРКА ПАКЕТА")
    print("=" * 72)
    print(f"[{'ok' if syntax['ok'] else 'FAIL'}] синтаксис Python"
          + ("" if syntax["ok"] else f" — {syntax['detail'][:400]}"))
    print(f"[{'ok' if not forbidden else 'FAIL'}] нет следов чужого проекта"
          f" — находок: {len(forbidden)}")
    for h in forbidden[:20]:
        print(f"      {h['file']}  <- {h['pattern']}")
    print(f"[{'ok' if not secrets else 'FAIL'}] нет секретов — находок: {len(secrets)}")
    for h in secrets[:20]:
        print(f"      {h['file']}  <- {h['kind']}")
    print(f"[{'ok' if not broken else 'WARN'}] битые ссылки — находок: {len(broken)}")
    for h in broken[:20]:
        print(f"      {h['file']}  ->  {h['ref']}")
    print("-" * 72)
    print(f"файлов: {comp['files']}   объём: {comp['mb']} МБ")
    print("расширения: " + ", ".join(f"{k}={v}" for k, v in list(comp['by_ext'].items())[:10]))
    if comp["oversized"]:
        print("крупные файлы: " + ", ".join(f"{o['file']} ({o['mb']} МБ)" for o in comp["oversized"]))
    print("-" * 72)
    print("ВЕРДИКТ: " + ("пакет готов к отправке" if report["ok"] else "есть находки — см. выше"))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
