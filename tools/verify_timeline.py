# -*- coding: utf-8 -*-
"""verify_timeline.py — структурная проверка таймлайна после мутации.

Проверяет: длительность против ожидания, дыры и наложения на каждой дорожке,
нулевые/отрицательные длительности, выход за пределы таймлайна, маркеры,
имя таймлайна/fps/таймкод. Ничего не меняет.

Запуск внутри Resolve (run_script_unsafe):
    exec(compile(open(r'<ПАКЕТ>/tools/verify_timeline.py',
                      encoding='utf-8').read(), 'verify_timeline.py', 'exec'))

Запуск из консоли (прочитать тот же отчёт, но уже вне Resolve):
    python tools/verify_timeline.py --job templates/verify_job.json

Опциональный файл job (verify_job.json): путь можно задать флагом --job,
иначе он ищется сначала в текущем каталоге, затем рядом со скриптом;
каталог tools можно задать переменной ZOVOD_TOOLS_DIR:
    {"expect_duration_s": 150, "expect_fps": 25, "expect_timeline": "Grade_Test",
     "report_path": "<путь>/verify_report.json"}
"""
import argparse
import json
import os
import sys
import traceback

# В консоли Windows вывод по умолчанию cp1251/cp866 — переводим в UTF-8,
# иначе кириллица в отчёте превращается в мусор при перенаправлении в файл.
# Внутри Resolve stdout может быть и не текстовым потоком — тогда не трогаем.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _tools_dir():
    """Каталог tools: по __file__, иначе ZOVOD_TOOLS_DIR, иначе CWD/tools."""
    f = globals().get("__file__")
    if f:
        return os.path.dirname(os.path.abspath(f))
    env = os.environ.get("ZOVOD_TOOLS_DIR", "")
    if env:
        return os.path.abspath(env)
    cwd = os.getcwd()
    for cand in (os.path.join(cwd, "tools"), cwd):
        if os.path.isdir(cand):
            return cand
    return cwd


def _job_arg():
    """--job из командной строки. Внутри Resolve вызова нет — вернём пусто."""
    p = argparse.ArgumentParser(
        prog="verify_timeline.py",
        description="структурная проверка таймлайна (запускается внутри Resolve)")
    p.add_argument("--job", default="",
                   help="файл ожиданий (verify_job.json); по умолчанию — "
                        "verify_job.json в текущем каталоге, затем рядом со скриптом")
    try:
        argv = list(sys.argv[1:])
    except Exception:
        argv = []
    try:
        ns, _unknown = p.parse_known_args(argv)
    except SystemExit:
        return ""
    return ns.job


HERE = _tools_dir()
CWD = os.getcwd()
JOB = None
_explicit = _job_arg()
if _explicit:
    JOB = os.path.abspath(_explicit)
else:
    for _cand in (os.path.join(CWD, "verify_job.json"), os.path.join(HERE, "verify_job.json")):
        if os.path.exists(_cand):
            JOB = _cand
            break
    JOB = JOB or os.path.join(HERE, "verify_job.json")

job = {}
if os.path.exists(JOB):
    try:
        with open(JOB, "r", encoding="utf-8") as f:
            job = json.load(f)
    except Exception:
        job = {}

def _name(it):
    """В этой связке GetName бывает и методом, и строковым свойством — берём оба."""
    v = getattr(it, "GetName", None)
    if v is None:
        return "?"
    if callable(v):
        try:
            return str(v())
        except Exception:
            return "?"
    return str(v)


def _kind(it):
    """'transition' для кросс-фейдов/диссолвов, 'clip' для обычных айтемов.

    Переход (Cross Fade) лежит на таймлайне отдельным объектом и по уму
    перекрывает соседей — считать это наложением нельзя, иначе проверка
    ругается на нормальный монтаж.
    """
    try:
        t = it.GetType()
        if t:
            return str(t)
    except Exception:
        pass
    try:
        if it.GetMediaPoolItem() is None:
            return "transition"
    except Exception:
        pass
    n = _name(it).lower()
    if "cross fade" in n or "transition" in n or "dissolve" in n:
        return "transition"
    return "clip"


def _spans(items):
    spans = []
    for it in items:
        try:
            s = it.GetStart()
            e = it.GetEnd()
        except Exception:
            continue
        spans.append({"start": s, "end": e, "len": e - s, "name": _name(it),
                      "kind": _kind(it)})
    spans.sort(key=lambda x: x["start"])
    return spans


out = {"ok": False, "job": job}
try:
    resolve = globals().get("resolve")
    if resolve is None:
        # Вне Resolve таймлайн недоступен — это не ошибка, а нормальный режим
        # запуска из консоли (например, чтобы посмотреть справку).
        print("VERIFY_JSON:" + json.dumps(out, ensure_ascii=False, default=str))
        print(
            "verify_timeline.py читает ТАЙМЛАЙН — запускается внутри DaVinci Resolve:\n"
            "  run_script / skills/davinci-resolve-workbench/scripts/resolve_bridge.py\n"
            "В консоли он лишь разбирает аргументы и ищет файл ожиданий (--job)."
        )
        raise SystemExit(0)
    pm = resolve.GetProjectManager()
    proj = pm.GetCurrentProject()
    if proj is None:
        raise RuntimeError("нет текущего проекта")
    tl = proj.GetCurrentTimeline()
    if tl is None:
        raise RuntimeError("нет текущего таймлайна")

    fps = float(tl.GetSetting("timelineFrameRate") or 0) or 25.0
    start = tl.GetStartFrame()
    end = tl.GetEndFrame()
    dur_s = (end - start) / fps

    out["timeline"] = tl.GetName()
    out["project"] = proj.GetName()
    out["fps"] = fps
    out["start_frame"] = start
    out["end_frame"] = end
    out["duration_s"] = round(dur_s, 3)
    out["start_timecode"] = tl.GetStartTimecode()

    tracks = {}
    problems = []
    for ttype in ("video", "audio"):
        n = tl.GetTrackCount(ttype)
        tl_tracks = []
        for i in range(1, n + 1):
            items = tl.GetItemListInTrack(ttype, i) or []
            spans = _spans(items)
            # переходы (кросс-фейды) — отдельные объекты, они закономерно
            # перекрывают соседние клипы; в проверке дыр/наложений их не
            # участвуем, но считаем и показываем отдельно
            clips = [s for s in spans if s["kind"] != "transition"]
            trans = [s for s in spans if s["kind"] == "transition"]
            gaps, overlaps, zero = [], [], []
            for k in range(1, len(clips)):
                a, b = clips[k - 1], clips[k]
                if b["start"] > a["end"]:
                    gaps.append({"from": a["end"], "to": b["start"],
                                 "frames": b["start"] - a["end"]})
                elif b["start"] < a["end"]:
                    overlaps.append({"from": b["start"], "to": a["end"],
                                     "frames": a["end"] - b["start"]})
            for s in clips:
                if s["len"] <= 0:
                    zero.append(s)
                if s["start"] < start or s["end"] > end:
                    problems.append("item вне таймлайна: %s (%s)" % (s["name"], s))
            tl_tracks.append({
                "index": i,
                "name": tl.GetTrackName(ttype, i),
                "items": len(spans),
                "clips": len(clips),
                "transitions": len(trans),
                "transition_spans": trans,
                "coverage_s": round(sum(x["len"] for x in clips) / fps, 2),
                "gaps": gaps,
                "overlaps": overlaps,
                "zero_length": zero,
            })
            if gaps:
                problems.append("%s track %d: дыры %d" % (ttype, i, len(gaps)))
            if overlaps:
                problems.append("%s track %d: наложения %d" % (ttype, i, len(overlaps)))
        tracks[ttype] = tl_tracks
    out["tracks"] = tracks

    out["markers"] = {str(k): str(v) for k, v in (tl.GetMarkers() or {}).items()}

    # ожидания
    checks = {}
    if "expect_duration_s" in job:
        exp = float(job["expect_duration_s"])
        checks["duration_s"] = {"expected": exp, "actual": out["duration_s"],
                                "delta_s": round(out["duration_s"] - exp, 3),
                                "pass": abs(out["duration_s"] - exp) <= max(0.5, exp * 0.01)}
    if "expect_fps" in job:
        checks["fps"] = {"expected": job["expect_fps"], "actual": fps,
                         "pass": abs(fps - float(job["expect_fps"])) < 0.01}
    if "expect_timeline" in job:
        checks["timeline"] = {"expected": job["expect_timeline"], "actual": out["timeline"],
                              "pass": out["timeline"] == job["expect_timeline"]}
    out["checks"] = checks
    out["problems"] = problems
    out["pass"] = (not problems) and all(c.get("pass", True) for c in checks.values())
    out["ok"] = True
except Exception:
    out["error"] = traceback.format_exc()

txt = "VERIFY_JSON:" + json.dumps(out, ensure_ascii=False, default=str)
print(txt)
path = job.get("report_path")
if path:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2, default=str)
        print("report written:", path)
    except Exception as e:
        print("report write failed:", e)
