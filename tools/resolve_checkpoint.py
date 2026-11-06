# -*- coding: utf-8 -*-
"""resolve_checkpoint.py — точка отката состояния Resolve: .drp + копия Project.db.

tools/checkpoint.py архивирует рабочую папку проекта, но НЕ состояние Resolve.
А состояние Resolve живёт в двух местах:
  * Project.db в библиотеке проектов (живая база, пишется самим Resolve);
  * .drp — экспорт проекта (читается обратно через ImportProject).

Запас из одного .drp недостаточен: часть настроек таймлайна живёт только в БД.
Поэтому точка отката = .drp + копия Project.db.

Запуск ВНУТРИ Resolve (через skills/davinci-resolve-workbench/scripts/resolve_bridge.py).
Переменные окружения:
    ZOVOD_CKPT_DIR   — куда складывать (обязательно)
    ZOVOD_CKPT_LABEL — метка точки отката
    ZOVOD_CKPT_PRJ   — имя проекта (по умолчанию текущий)

Откат:
    1) закрыть проект в Resolve;
    2) скопировать Project.db на место живой базы;
    3) при необходимости — ImportProject(<.drp>) через pm.
"""
import datetime
import glob
import json
import os
import shutil
import time

MARK = "CKPT_JSON:"


def find_project_db(project_name):
    appdata = os.environ.get("APPDATA", "")
    root = os.path.join(appdata, "Blackmagic Design", "DaVinci Resolve", "Support",
                         "Resolve Project Library", "Resolve Projects")
    pat = os.path.join(root, "Users", "*", "Projects", project_name, "Project.db")
    hits = glob.glob(pat)
    return hits[0] if hits else None


def main():
    out_dir = os.environ.get("ZOVOD_CKPT_DIR")
    if not out_dir:
        print(MARK + json.dumps({"ok": False, "error": "нет ZOVOD_CKPT_DIR"}, ensure_ascii=False))
        return 1
    os.makedirs(out_dir, exist_ok=True)
    label = os.environ.get("ZOVOD_CKPT_LABEL", "checkpoint")

    resolve = globals().get("resolve")
    if resolve is None:
        print(MARK + json.dumps({"ok": False, "error": "нет resolve"}, ensure_ascii=False))
        return 1

    R = {"label": label, "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
    project = resolve.GetCurrentProject()
    if project is None:
        R["ok"] = False
        R["error"] = "нет текущего проекта"
        print(MARK + json.dumps(R, ensure_ascii=False))
        return 1
    pm = resolve.GetProjectManager()
    name = os.environ.get("ZOVOD_CKPT_PRJ") or project.GetName()
    R["project"] = name
    try:
        tl = project.GetCurrentTimeline()
        R["timeline"] = tl.GetName() if tl else None
    except Exception:
        pass

    stamp = time.strftime("%Y%m%d_%H%M%S")
    drp = os.path.join(out_dir, "%s_%s.drp" % (label, stamp))
    db_dst = os.path.join(out_dir, "Project_db_%s_%s.sqlite" % (label, stamp))

    try:
        R["save"] = bool(pm.SaveProject())
    except Exception as e:
        R["save_error"] = repr(e)
    time.sleep(2)
    try:
        R["export"] = bool(pm.ExportProject(name, drp))
    except Exception as e:
        R["export_error"] = repr(e)
    R["drp"] = drp
    R["drp_size"] = os.path.getsize(drp) if os.path.exists(drp) else None

    db_src = find_project_db(name)
    if db_src and os.path.exists(db_src):
        try:
            shutil.copy2(db_src, db_dst)
            R["db_src"] = db_src
            R["db"] = db_dst
            R["db_size"] = os.path.getsize(db_dst)
        except Exception as e:
            R["db_error"] = repr(e)
    else:
        R["db_error"] = "Project.db не найден для проекта «%s»" % name

    R["ok"] = bool(R.get("export")) and bool(R.get("db"))
    manifest = os.path.join(out_dir, "manifest_%s_%s.json" % (label, stamp))
    json.dump(R, open(manifest, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    R["manifest"] = manifest
    print(MARK + json.dumps({k: R.get(k) for k in
                              ("ok", "project", "timeline", "drp", "drp_size", "db", "db_size")},
                             ensure_ascii=False))
    return 0 if R["ok"] else 1


if __name__ in ("__main__", "__builtin__", None):
    # внутри Resolve скрипт исполняется как exec: sys.exit() проглатывает вывод
    main()
