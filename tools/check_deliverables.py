# -*- coding: utf-8 -*-
"""check_deliverables.py — проверка целостности того, что отдаётся заказчику.

1. Все файлы, на которые ссылаются документы, существуют.
2. В таблицах с числами нет расхождений между документами и scene_map.json.
3. В audio/proc и audio/proc_mux — столько же файлов, сколько клипов в инвентаризации.

Проектные константы (список документов, «новые» клипы, число контрольных кадров,
файл отчёта verify_timeline) задаются аргументами командной строки — в коде их нет.

    python check_deliverables.py --out <корень проекта>
        --docs "КАК_НАЧАТЬ_НАРЕЗКУ.md,ХРОНОЛОГИЯ_СЦЕН.md"
        [--new-clips "<CLIP1>,<CLIP2>"] [--expect-ctrl-frames 6]
        [--verify-report <reports/stage<N>_verify.json>] [--job templates/verify_job.json]
        [--json <отчёт.json>]

Код возврата: 0 — расхождений нет, 1 — есть.
"""
import argparse
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROBLEMS = []
NOTES = []


def note(msg):
    NOTES.append(msg)


def problem(msg):
    PROBLEMS.append(msg)


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


# ---------- 1. ссылки на файлы ----------
REF_RE = re.compile(r"`([A-Za-z0-9А-Яа-яЁё_.\\/-]+\.(?:md|json|txt|py|jpg|wav|MP4|mp4|csv))`")


def check_refs(base, docs, search_dirs):
    for d in docs:
        p = os.path.join(base, d)
        if not os.path.exists(p):
            problem("нет документа %s" % d)
            continue
        txt = open(p, encoding="utf-8").read()
        for ref in sorted(set(REF_RE.findall(txt))):
            name = ref.replace("\\", os.sep).split(os.sep)[-1]
            if not any(os.path.exists(os.path.join(dd, name)) for dd in search_dirs):
                problem("%s: ссылка на несуществующий файл `%s`" % (d, ref))


# ---------- 2. числа против scene_map.json ----------
def check_scene_numbers(base, sm, guide_name, chrono_name):
    total = round(sum(c["duration_s"] for c in sm), 1)
    blocks = {}
    for c in sm:
        blocks.setdefault(c["block"], []).append(c)

    guide = open(os.path.join(base, guide_name), encoding="utf-8").read()
    chrono = open(os.path.join(base, chrono_name), encoding="utf-8").read()

    for b, clips in sorted(blocks.items(), key=lambda kv: int(kv[0])):
        sec = round(sum(c["duration_s"] for c in clips), 1)
        # в ХРОНОЛОГИЯ_СЦЕН.md десятичный разделитель — точка
        pat = r"Клипов: %d · суммарно %s с" % (len(clips), "%.1f" % sec)
        if not re.search(pat, chrono):
            problem("%s: для блока %s нет строки `%s`" % (chrono_name, b, pat))

    if ("Всего **%s с**" % ("%.1f" % total).replace(".", ",")) not in guide:
        problem("%s: нет строки про итог %.1f с" % (guide_name, total))

    # сумма блоков из таблицы инструкции
    tbl = re.findall(r"\| \d+ \| .*? \| (C[0-9–,\s C]+) \| ([\d,]+) с \|", guide)
    tbl_sum = 0.0
    for _rng, sec in tbl:
        tbl_sum += float(sec.replace(",", "."))
    if abs(tbl_sum - total) > 0.2:
        problem("%s: сумма блоков в таблице = %.1f с, а фактически %.1f с"
                % (guide_name, tbl_sum, total))
    else:
        note("сумма блоков в таблице инструкции сходится: %.1f с" % tbl_sum)
    return total


# ---------- 3. количество обработанных файлов ----------
def check_processed(base, want_clips, new_clips):
    for sub, ext in (("audio/proc", ".wav"), ("audio/proc_mux", ".MP4")):
        d = os.path.join(base, sub.replace("/", os.sep))
        got = len([f for f in os.listdir(d) if f.lower().endswith(ext.lower())]) \
            if os.path.isdir(d) else -1
        if got != want_clips:
            problem("%s: %d файлов %s вместо %d" % (sub, got, ext, want_clips))
        else:
            note("%s: %d файлов %s — OK" % (sub, got, ext))
    if not new_clips:
        return
    for sub, ext in (("audio/proc", ".wav"), ("audio/proc_mux", ".MP4")):
        d = os.path.join(base, sub.replace("/", os.sep))
        miss = [n for n in new_clips
                if not os.path.exists(os.path.join(d, n + ext))]
        if miss:
            problem("%s: нет файлов по новым клипам: %s" % (sub, miss))
        else:
            note("%s: все %d новых клипов на месте" % (sub, len(new_clips)))
    fixed = os.path.join(base, "audio", "proc_mux_fixed")
    if os.path.isdir(fixed):
        miss = [n for n in new_clips
                if not os.path.exists(os.path.join(fixed, n + ".MP4"))]
        if miss:
            problem("audio/proc_mux_fixed: нет исправленных муксов: %s" % miss)
        else:
            note("audio/proc_mux_fixed: исправленные муксы на месте (%d)" % len(new_clips))


# ---------- 3.1. контрольные кадры и отчёт verify_timeline ----------
def check_ctrl_frames(base, expect_ctrl):
    ctrl = os.path.join(base, "preview_new")
    n_ctrl = len([f for f in os.listdir(ctrl) if f.startswith("ctrl_")]) \
        if os.path.isdir(ctrl) else 0
    if expect_ctrl and n_ctrl < expect_ctrl:
        problem("preview_new: %d контрольных кадров вместо %d" % (n_ctrl, expect_ctrl))
    else:
        note("preview_new: %d контрольных кадров" % n_ctrl)


def check_verify_report(path, job_path):
    if not path:
        return
    if not os.path.exists(path):
        problem("нет отчёта verify_timeline: %s" % path)
        return
    vr = load_json(path, {})
    # два формата: verify_timeline.py (checks.duration_s) и его потомки (duration_check)
    d = vr.get("checks", {}).get("duration_s", {}) or vr.get("duration_check", {}) or {}
    want = None
    if job_path and os.path.exists(job_path):
        want = float(load_json(job_path, {}).get("expect_duration_s") or 0)
    if want is None:
        note("%s: отчёт прочитан, ожидание длительности не задано" % os.path.basename(path))
    elif not d.get("pass") or abs(float(d.get("actual") or 0) - want) > 0.05:
        problem("%s: длительность %s, ожидалось %.2f"
                % (os.path.basename(path), d.get("actual"), want))
    else:
        note("%s: длительность %.2f с, delta %.3f"
             % (os.path.basename(path), float(d.get("actual") or 0),
                float(d.get("delta_s") or 0)))
    ov = sum(len(t.get("overlaps") or []) for t in
             (vr.get("tracks", {}).get("video") or []) +
             (vr.get("tracks", {}).get("audio") or []))
    if ov:
        problem("%s: наложений %d" % (os.path.basename(path), ov))
    else:
        note("%s: наложений 0" % os.path.basename(path))


# ---------- 4. таблица тряски в инструкции против scene_map ----------
def check_shake_table(base, sm, guide_name):
    guide = open(os.path.join(base, guide_name), encoding="utf-8").read()
    shaky = [c for c in sm if c.get("shaky_start")]
    sec53 = guide.split("### 5.3.")[1].split("### 5.4.")[0] if "### 5.3." in guide else ""
    # основная таблица — до подзаголовка про «трясётся весь клип»
    main53 = sec53.split("**Трясётся не только начало")[0]
    rows53 = re.findall(r"^\| (C\d+) \| ([\d,]+) px \|", main53, re.M)
    tbl53 = {r[0]: float(r[1].replace(",", ".")) for r in rows53}
    map53 = {c["clip"]: round(float(c.get("shake_head_px_4k") or 0), 1) for c in shaky}
    if set(tbl53) != set(map53):
        problem("%s §5.3: состав таблицы не совпадает с картой "
                "(в карте нет: %s / лишние: %s)" % (
                    guide_name,
                    sorted(set(map53) - set(tbl53)) or "-",
                    sorted(set(tbl53) - set(map53)) or "-"))
    else:
        note("§5.3: %d клипов тряски — состав и амплитуды совпадают с картой" % len(map53))
    for k in tbl53:
        if k in map53 and abs(tbl53[k] - map53[k]) > 0.06:
            problem("§5.3: %s амплитуда %s != %s" % (k, tbl53[k], map53[k]))


# ---------- 5. таблица типов речи в сверке против scene_map ----------
def check_speech_types(base, sm, guide_name, sv_name):
    sv = open(os.path.join(base, sv_name), encoding="utf-8").read()
    guide = open(os.path.join(base, guide_name), encoding="utf-8").read()
    agg = {}
    for c in sm:
        a = agg.setdefault(c["speech_type"], [0, 0.0])
        a[0] += 1
        a[1] += c["duration_s"] or 0
    for stype, (n, secs) in agg.items():
        pat = r"\| %s \| %d \| ([\d,.]+) \|" % (re.escape(stype), n)
        m = re.search(pat, sv)
        if not m:
            problem("СВЕРКА: нет строки для типа речи %s (%d клипов)" % (stype, n))
            continue
        got = float(m.group(1).replace(",", "."))
        if abs(got - secs) > 0.15:
            problem("СВЕРКА: %s — %.1f с в таблице, %.1f с в scene_map.json"
                    % (stype, got, secs))
    # СПОРНО-список в инструкции
    m = re.search(r"`СПОРНО`.*?\(их (\d+)\)", guide, re.S)
    if m:
        want = agg.get("СПОРНО", [0, 0])[0]
        if int(m.group(1)) != want:
            problem("%s §5.1: СПОРНО указано %s, в карте %d"
                    % (guide_name, m.group(1), want))
    else:
        problem("%s §5.1: не найдено число СПОРНО" % guide_name)


# ---------- 6. точки отката ----------
def check_checkpoints(base):
    cp = os.path.join(base, "_checkpoints")
    if os.path.isdir(cp):
        marks = [(os.path.getmtime(os.path.join(cp, d)), d)
                 for d in os.listdir(cp) if d.startswith("stage")]
        marks.sort()
        note("точки отката (%d): %s" % (
            len(marks), ", ".join(d for _, d in marks[-4:])))
    else:
        problem("нет папки _checkpoints")


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="check_deliverables.py",
        description="проверка целостности выдачи")
    p.add_argument("--out", default="", help="корень проекта")
    p.add_argument("--docs", default="", help="документы для проверки ссылок (через запятую)")
    p.add_argument("--guide", default="КАК_НАЧАТЬ_НАРЕЗКУ.md", help="документ с таблицами")
    p.add_argument("--chrono", default="ХРОНОЛОГИЯ_СЦЕН.md", help="хронология сцен")
    p.add_argument("--verify-doc", default="СВЕРКА_СЦЕНАРИЯ_С_МАТЕРИАЛОМ.md",
                   help="документ со сводкой типов речи")
    p.add_argument("--new-clips", default="", help="список «новых» клипов через запятую")
    p.add_argument("--expect-ctrl-frames", type=int, default=0,
                   help="ожидаемое число контрольных кадров в preview_new")
    p.add_argument("--verify-report", default="", help="отчёт verify_timeline (.json)")
    p.add_argument("--job", default="", help="verify_job.json с ожиданием длительности")
    p.add_argument("--json", default="", help="куда записать отчёт JSON")
    a = p.parse_args(argv)

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    base = os.path.abspath(a.out) if a.out else project_root
    if not os.path.isdir(base):
        p.error("нет корня проекта: %s" % base)

    docs = [x.strip() for x in a.docs.split(",") if x.strip()]
    new_clips = [x.strip() for x in a.new_clips.split(",") if x.strip()]

    ws = os.path.dirname(base)
    search = [base,
              os.path.join(base, "audio", "proc_mux"),
              os.path.join(base, "audio", "proc_mux_fixed"),
              os.path.join(base, "audio", "proc"),
              os.path.join(base, "audio", "voice"),
              os.path.join(base, "audio", "sfx"),
              os.path.join(base, "audio"),
              os.path.join(base, "sfx", "orig"),
              os.path.join(base, "preview_new"),
              os.path.join(base, "transcripts"),
              ws,
              os.path.join(ws, "docs"),
              os.path.join(ws, "tools")]

    if docs:
        check_refs(base, docs, search)

    sm_path = os.path.join(base, "scene_map.json")
    sm = load_json(sm_path, None)
    if sm is None:
        problem("нет scene_map.json: %s" % sm_path)
        sm = []
    elif sm:
        if os.path.exists(os.path.join(base, a.guide)) and \
                os.path.exists(os.path.join(base, a.chrono)):
            check_scene_numbers(base, sm, a.guide, a.chrono)
        if os.path.exists(os.path.join(base, a.guide)):
            check_shake_table(base, sm, a.guide)
        if os.path.exists(os.path.join(base, a.verify_doc)):
            check_speech_types(base, sm, a.guide, a.verify_doc)

    inv = load_json(os.path.join(base, "inventory.json"), None)
    if inv is None:
        problem("нет inventory.json")
    else:
        check_processed(base, len(inv["clips"]), new_clips)

    check_ctrl_frames(base, a.expect_ctrl_frames)
    check_verify_report(os.path.abspath(a.verify_report) if a.verify_report else "",
                        os.path.abspath(a.job) if a.job else "")
    check_checkpoints(base)

    print("=== ПРОВЕРКА ВЫДАЧИ ===")
    for n in NOTES:
        print("  ok   " + n)
    if PROBLEMS:
        print("")
        for p_ in PROBLEMS:
            print("  FAIL " + p_)
        print("\nИТОГ: %d проблем" % len(PROBLEMS))
    else:
        print("\nИТОГ: расхождений нет")

    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"ok": not PROBLEMS, "notes": NOTES, "problems": PROBLEMS},
                      f, ensure_ascii=False, indent=2)
        print("report:", a.json)
    return 1 if PROBLEMS else 0


if __name__ == "__main__":
    sys.exit(main())
