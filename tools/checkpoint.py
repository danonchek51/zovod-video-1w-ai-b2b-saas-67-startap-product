# -*- coding: utf-8 -*-
"""checkpoint.py — точки отката (универсальный).

Правило заказчика: любой этап = вывод + точка отката к состоянию ДО него.
Снимок делается ДО начала работы над этапом; откат — распаковка снимка.

    python tools\\checkpoint.py --root <проект> save <метка> "<что делаем>"
    python tools\\checkpoint.py --root <проект> list
    python tools\\checkpoint.py --root <проект> restore <метка>

Без --root берётся текущий каталог. Снимок: zip рабочей папки минус сам каталог
_checkpoints и тяжёлые временные файлы. Исходники (на других дисках) в снимок
не входят и не меняются.

Формат manifest.json совместим с прежним: label/note/timestamp/archive/files/size_mb.
"""
import argparse
import datetime
import json
import os
import zipfile

EXCLUDE_DIRS = {"_checkpoints", "__pycache__", "node_modules", ".git", "thumbs"}
EXCLUDE_EXT = {".mp4", ".mov", ".mkv", ".mxf", ".braw", ".r3d"}
MAX_FILE_MB = 6.0   # крупные промежуточные PNG не в снимок — они перегенерируются


def _excl(extra):
    d = set(EXCLUDE_DIRS)
    for e in (extra or []):
        e = e.strip()
        if e:
            d.add(e)
    return d


def _paths(root):
    ckp = os.path.join(root, "_checkpoints")
    return ckp, os.path.join(ckp, "manifest.json")


def _manifest(manifest):
    if os.path.exists(manifest):
        with open(manifest, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"checkpoints": []}


def _write_manifest(manifest, m):
    os.makedirs(os.path.dirname(manifest), exist_ok=True)
    with open(manifest, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)


def _iter_files(root, exclude=None):
    excl = _excl(exclude)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in excl]
        for fn in filenames:
            if os.path.splitext(fn)[1].lower() in EXCLUDE_EXT:
                continue
            full = os.path.join(dirpath, fn)
            try:
                if os.path.getsize(full) > MAX_FILE_MB * 1048576:
                    continue
            except OSError:
                continue
            yield full, os.path.relpath(full, root)


def save(root, label, note="", max_mb=MAX_FILE_MB, exclude=None):
    ckp, manifest = _paths(root)
    os.makedirs(ckp, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = "%s__%s" % (label.replace(" ", "_"), ts)
    zpath = os.path.join(ckp, slug + ".zip")
    n = 0
    limit = max_mb * 1048576
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for full, rel in _iter_files(root, exclude):
            try:
                if os.path.getsize(full) > limit:
                    continue
            except OSError:
                continue
            z.write(full, rel)
            n += 1
    m = _manifest(manifest)
    m["checkpoints"].append({
        "label": label,
        "note": note,
        "timestamp": ts,
        "archive": os.path.basename(zpath),
        "files": n,
        "size_mb": round(os.path.getsize(zpath) / 1048576.0, 2),
    })
    _write_manifest(manifest, m)
    print("SAVED  %s  (%d files, %.2f MB)  root=%s" %
          (slug, n, os.path.getsize(zpath) / 1048576.0, root))
    return slug


def list_ck(root):
    _, manifest = _paths(root)
    m = _manifest(manifest)
    if not m["checkpoints"]:
        print("(пусто)")
        return
    for i, c in enumerate(m["checkpoints"], 1):
        print("%2d. %-34s %s  %7.2f MB  %s" % (
            i, c["label"], c["timestamp"], c["size_mb"], c.get("note", "")))


def restore(root, label):
    _, manifest = _paths(root)
    m = _manifest(manifest)
    hit = None
    for c in m["checkpoints"]:
        if c["label"] == label or c["archive"].startswith(label + "__"):
            hit = c
            break
    if hit is None:
        raise SystemExit("точка отката не найдена: %s" % label)
    zpath = os.path.join(root, "_checkpoints", hit["archive"])
    with zipfile.ZipFile(zpath, "r") as z:
        z.extractall(root)
    print("RESTORED %s -> %s  (root=%s)" % (hit["label"], hit["archive"], root))


def main(argv=None):
    p = argparse.ArgumentParser(description="точки отката проекта")
    p.add_argument("--root", default=os.getcwd(), help="корень проекта (по умолчанию — текущий каталог)")
    p.add_argument("--max-mb", type=float, default=MAX_FILE_MB, help="порог размера файла для снимка")
    p.add_argument("--exclude", default="", help="папки через запятую, которые не включать в снимок")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("save"); s.add_argument("label"); s.add_argument("note", nargs="?", default="")
    sub.add_parser("list")
    r = sub.add_parser("restore"); r.add_argument("label")
    a = p.parse_args(argv)
    root = os.path.abspath(a.root)
    if a.cmd == "save":
        save(root, a.label, a.note, a.max_mb,
             [e for e in a.exclude.split(",") if e.strip()])
    elif a.cmd == "list":
        list_ck(root)
    elif a.cmd == "restore":
        restore(root, a.label)


if __name__ == "__main__":
    main()
