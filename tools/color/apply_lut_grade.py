# -*- coding: utf-8 -*-
"""apply_lut_grade.py — батчевый накат 3D-LUT на клипы таймлайна Resolve.

Запускается ВНУТРИ Resolve (через skills/davinci-resolve-workbench/scripts/resolve_bridge.py).
План — JSON:

    {
      "dry_run": false,
      "items": [
        {"track": 1, "start": 90175, "name": "C0127.mp4", "lut": "C:/.../C0127.MP4.cube"},
        ...
      ]
    }

Пути через переменные окружения (мост не передаёт аргументы):
    ZOVOD_LUT_PLAN   — путь к плану (обязательно)
    ZOVOD_LUT_OUT    — куда положить отчёт (по умолчанию plan + ".report.json")
    ZOVOD_LUT_BATCH  — размер батча (по умолчанию 10)
    ZOVOD_LUT_LUTDIR — папка LUT Resolve (по умолчанию берётся из env_paths)
    ZOVOD_LUT_PREFIX — префикс ASCII-имён при установке (по умолчанию MU2_lut_)

Что уже учтено (проверено на 21.1.1):
  * мутации отбиваются, если впереди Project Manager — делаем OpenPage("edit");
  * инъектированный `project` протухает после перезапуска Resolve — берём
    resolve.GetCurrentProject();
  * переход может иметь тот же стартовый кадр, что и клип — клип ищем по имени;
  * у перехода GetNodeGraph() возвращает None — это не ошибка, а «не клип»;
  * SetLUT работает только с путём ВНУТРИ папки LUT Resolve — копируем туда
    с ASCII-именем (кириллица в путях к API небезопасна);
  * перечитывание изменённого .cube требует SetLUT(1, "") перед новым SetLUT;
  * флаг «True» ничего не значит — проверяем GetLUT() и GetToolsInNode().
"""
import json
import os
import shutil
import sys
import traceback

# скрипт исполняется внутри Resolve — __file__ там может отсутствовать
try:
    _HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _HERE = os.getcwd()
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..")))

REPORT_MARK = "LUT_JSON:"


def env(name, default=None):
    return os.environ.get(name) or default


def norm(n):
    n = (n or "").lower().replace("_", " ")
    return " ".join(n.split())


def install_lut(src, lut_dir, prefix):
    """Копирует .cube в папку LUT Resolve под устойчивым ASCII-именем.

    Имя выводится из хэша пути, а не из порядка в плане: иначе повторный прогон
    с другой сортировкой переименует файлы и перепривяжет клипы на другие LUT.
    """
    import hashlib
    os.makedirs(lut_dir, exist_ok=True)
    digest = hashlib.sha1(os.path.abspath(src).encode("utf-8")).hexdigest()[:8]
    name = "%s%s.cube" % (prefix, digest)
    dst = os.path.join(lut_dir, name)
    shutil.copy2(src, dst)
    return dst


def pick_clip(tl, track, start, name):
    """Клип по (трек, старт) + имя. Переходы отсеиваются по отсутствию графа."""
    items = [it for it in tl.GetItemListInTrack("video", track)
             if int(it.GetStart()) == start]
    if not items:
        return None, "клип не найден по (трек=%s, старт=%s)" % (track, start)
    want = norm(name)
    items.sort(key=lambda it: 0 if norm(it.GetName()) == want else 1)
    it = items[0]
    g = it.GetNodeGraph()
    if g is None:
        return None, "объект «%s» без графа — это переход, а не клип" % it.GetName()
    return (it, g), None


def main():
    plan_path = env("ZOVOD_LUT_PLAN")
    if not plan_path:
        print(REPORT_MARK + json.dumps({"ok": False, "error": "нет ZOVOD_LUT_PLAN"},
                                        ensure_ascii=False))
        return 1
    plan = json.load(open(plan_path, encoding="utf-8"))
    out_path = env("ZOVOD_LUT_OUT", plan_path + ".report.json")
    batch_size = int(env("ZOVOD_LUT_BATCH", "10"))
    prefix = env("ZOVOD_LUT_PREFIX", "MU2_lut_")
    dry_run = bool(plan.get("dry_run"))

    lut_dir = env("ZOVOD_LUT_LUTDIR")
    if not lut_dir:
        try:
            from env_paths import lut_dir as detect_lut_dir
            lut_dir = detect_lut_dir()
        except Exception:
            lut_dir = os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"),
                                   r"Blackmagic Design\DaVinci Resolve\Support\LUT")
    lut_dir = lut_dir or os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"),
                                      r"Blackmagic Design\DaVinci Resolve\Support\LUT")

    resolve = globals().get("resolve")
    if resolve is None:
        print(REPORT_MARK + json.dumps({"ok": False, "error": "нет resolve"}, ensure_ascii=False))
        return 1

    R = {"ok": True, "dry_run": dry_run, "page": None, "timeline": None,
         "lut_dir": lut_dir, "results": [], "summary": {}}

    try:
        page = resolve.GetCurrentPage()
        if page != "edit":
            resolve.OpenPage("edit")
            import time
            time.sleep(1)
        R["page"] = resolve.GetCurrentPage()
    except Exception as e:
        R["page_error"] = repr(e)

    project = resolve.GetCurrentProject()
    if project is None:
        R["ok"] = False
        R["error"] = "нет текущего проекта"
        print(REPORT_MARK + json.dumps(R, ensure_ascii=False, default=str))
        return 1
    pm = resolve.GetProjectManager()
    tl = project.GetCurrentTimeline()
    R["project"] = project.GetName()
    R["timeline"] = tl.GetName() if tl else None

    try:
        project.RefreshLUTList()
    except Exception as e:
        R["refresh_error"] = repr(e)

    # Фаза 1: установить все .cube в папку LUT Resolve.
    # Порядок важен: RefreshLUTList() должен идти ПОСЛЕ копирования, иначе
    # Resolve не знает о новых файлах и SetLUT возвращает False.
    # ZOVOD_LUT_NO_INSTALL=1 - использовать пути из плана как есть (LUT уже
    # установлена): нужно, когда имена важны (например, при восстановлении
    # проекта из .drp/БД, где ноды ссылаются на конкретные имена файлов).
    no_install = str(env("ZOVOD_LUT_NO_INSTALL", "")).strip().lower() in ("1", "true", "yes")
    installed = {}
    if not dry_run and not no_install:
        for it in plan.get("items", []):
            src = it.get("lut")
            if not src or not os.path.exists(src) or src in installed:
                continue
            try:
                installed[src] = install_lut(src, lut_dir, prefix)
            except Exception as e:
                R.setdefault("install_errors", []).append("%s: %s" % (src, e))
        try:
            project.RefreshLUTList()
            R["refresh_after_install"] = True
        except Exception as e:
            R["refresh_error_after_install"] = repr(e)
    R["no_install"] = no_install

    ok_n = fail_n = 0
    for i, it in enumerate(plan.get("items", [])):
        rec = {"track": it.get("track"), "start": it.get("start"),
               "name": it.get("name"), "lut": it.get("lut"), "ok": False}
        try:
            src = it["lut"]
            if not os.path.exists(src):
                rec["error"] = "нет файла LUT"
                R["results"].append(rec)
                fail_n += 1
                continue
            dst = src if dry_run else (src if no_install else installed.get(src))
            if not dst:
                rec["error"] = "LUT не установлен"
                R["results"].append(rec)
                fail_n += 1
                continue
            rec["installed"] = dst

            found, err = pick_clip(tl, it["track"], int(it["start"]), it.get("name"))
            if not found:
                rec["error"] = err
                R["results"].append(rec)
                fail_n += 1
                continue
            clip, g = found
            rec["picked"] = clip.GetName()
            n_nodes = g.GetNumNodes()
            rec["nodes_before"] = n_nodes
            tools = [str(x) for x in (g.GetToolsInNode(1) or [])] if n_nodes >= 1 else []
            rec["tools_before"] = tools

            if dry_run:
                rec["ok"] = True
                rec["dry"] = True
                ok_n += 1
                R["results"].append(rec)
                continue

            stale = n_nodes > 1 or any(not t.startswith("LUT:") for t in tools)
            if stale:
                rec["reset"] = bool(g.ResetAllGrades())
            try:
                g.SetLUT(1, "")            # сброс кэша LUT — иначе файл не перечитается
            except Exception:
                pass
            rec["set"] = bool(g.SetLUT(1, dst))
            rec["get"] = g.GetLUT(1)
            rec["tools_after"] = [str(x) for x in (g.GetToolsInNode(1) or [])]
            rec["nodes_after"] = g.GetNumNodes()
            rec["ok"] = bool(rec["set"]) and bool(rec["get"]) and \
                all(t.startswith("LUT:") for t in rec["tools_after"])
            if not rec["ok"]:
                rec["error"] = "не подтверждено чтением обратно"
        except Exception as e:
            rec["error"] = "%s: %s" % (type(e).__name__, e)
            rec["trace"] = traceback.format_exc()[-300:]
        ok_n += 1 if rec["ok"] else 0
        fail_n += 0 if rec["ok"] else 1
        R["results"].append(rec)

        if not dry_run and (len(R["results"]) % batch_size == 0):
            try:
                pm.SaveProject()
            except Exception as e:
                R.setdefault("save_errors", []).append(repr(e))

    if not dry_run:
        try:
            R["save"] = bool(pm.SaveProject())
        except Exception as e:
            R["save_error"] = repr(e)

    R["summary"] = {"total": len(R["results"]), "ok": ok_n, "fail": fail_n,
                    "installed": len(installed)}
    try:
        json.dump(R, open(out_path, "w", encoding="utf-8"), ensure_ascii=False,
                  indent=1, default=str)
        R["report"] = out_path
    except Exception as e:
        R["report_error"] = repr(e)

    print(REPORT_MARK + json.dumps(R["summary"], ensure_ascii=False))
    for r in R["results"]:
        if not r.get("ok"):
            print("FAIL %s@%s %s -> %s" % (r.get("track"), r.get("start"),
                                          (r.get("name") or "")[:28], r.get("error")))
    return 0


try:
    # внутри Resolve скрипт исполняется как exec: __name__ может быть любым,
    # а sys.exit() проглатывает вывод — поэтому вызываем main() напрямую
    main()
except Exception:
    import traceback
    print("LUT_ERROR:" + traceback.format_exc()[-600:])
    raise
