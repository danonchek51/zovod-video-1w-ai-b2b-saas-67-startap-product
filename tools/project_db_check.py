# -*- coding: utf-8 -*-
"""project_db_check.py — проверка целостности базы проекта Resolve (Project.db).

Resolve хранит каждый проект в SQLite-базе. Если процесс упал во время
сохранения, база может быть в промежуточном состоянии. Скрипт открывает базу
**только на чтение** и проверяет:

- целостность (PRAGMA integrity_check);
- наличие основных таблиц;
- сколько таймлайнов и сколько в них айтемов (по таблице Timeline).

База ищется по стандартному пути библиотеки проектов Resolve для текущей ОС
(Windows: %APPDATA%, macOS: ~/Library/Application Support). Путь можно задать
явно через --db, имя проекта — через --project (по умолчанию "guest").

    python project_db_check.py --project <имя_проекта> [--db <путь к Project.db>]
                               [--json out.json]
"""
import argparse
import json
import os
import sqlite3
import sys


def resolve_projects_root():
    """Корень библиотеки проектов Resolve для текущей ОС."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~\\AppData\\Roaming")
        return os.path.join(base, "Blackmagic Design", "DaVinci Resolve",
                            "Support", "Resolve Project Library", "Resolve Projects",
                            "Users")
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
        return os.path.join(base, "Blackmagic Design", "DaVinci Resolve",
                            "Support", "Resolve Project Library", "Resolve Projects",
                            "Users")
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "Blackmagic Design", "DaVinci Resolve",
                        "Support", "Resolve Project Library", "Resolve Projects",
                        "Users")


def find_db(project, users_root):
    """Ищет Project.db по имени проекта (в т.ч. в подпапке пользователя)."""
    cands = []
    for user in ("guest",):
        base = os.path.join(users_root, user, "Projects", project)
        cands.append(os.path.join(base, "Project.db"))
    if os.path.isdir(users_root):
        for user in sorted(os.listdir(users_root)):
            cands.append(os.path.join(users_root, user, "Projects", project, "Project.db"))
    for c in cands:
        if os.path.exists(c):
            return c
    return cands[0] if cands else ""


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="project_db_check.py",
        description="проверка целостности Project.db (только чтение)")
    p.add_argument("--project", default="guest", help="имя проекта Resolve")
    p.add_argument("--db", default="", help="явный путь к Project.db")
    p.add_argument("--library", default="", help="корень библиотеки проектов Resolve")
    p.add_argument("--json", default="", help="куда записать отчёт JSON")
    a = p.parse_args(argv)

    users_root = os.path.abspath(a.library) if a.library else resolve_projects_root()
    db = os.path.abspath(a.db) if a.db else find_db(a.project, users_root)

    out = {"db": db, "project": a.project, "exists": os.path.exists(db)}
    if os.path.exists(db):
        out["size"] = os.path.getsize(db)
        out["mtime"] = os.path.getmtime(db)
        uri = "file:" + db.replace("\\", "/") + "?mode=ro&immutable=0"
        try:
            con = sqlite3.connect(uri, uri=True, timeout=5)
            cur = con.cursor()
            cur.execute("PRAGMA integrity_check")
            rows = cur.fetchall()
            out["integrity"] = [r[0] for r in rows][:10]
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            tables = [r[0] for r in cur.fetchall()]
            out["tables_count"] = len(tables)
            out["tables_sample"] = tables[:40]
            # таймлайны
            if "Timeline" in tables:
                cur.execute("SELECT * FROM Timeline LIMIT 50")
                cols = [d[0] for d in cur.description]
                tl = []
                for row in cur.fetchall():
                    d = dict(zip(cols, row))
                    tl.append({k: (str(v)[:120] if v is not None else None)
                               for k, v in d.items()})
                out["timelines"] = tl
            con.close()
        except Exception as e:
            out["error"] = "%s: %s" % (type(e).__name__, e)

    blob = json.dumps(out, ensure_ascii=False, indent=1, default=str)
    print(blob[:6000])
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1, default=str)
        print("report:", a.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
