# -*- coding: utf-8 -*-
"""compare_text.py — финальная честная проверка: не потеряна ли речь.

    python compare_text.py --plan <cut_plan.json> [--out <корень проекта>]
"""
import argparse
import difflib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import env_paths  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

FPS = 25
ROOT = ""


def norm(s):
    return "".join(ch for ch in s.lower() if ch.isalnum())


def main(argv=None):
    global ROOT

    p = argparse.ArgumentParser(
        prog="compare_text.py",
        description="финальная честная проверка: не потеряна ли речь")
    p.add_argument("--plan", default="", help="план вырезов (cut_plan.json)")
    p.add_argument("--out", default="", help="корень проекта для результатов")
    a = p.parse_args(argv)

    project = env_paths.project_root()
    ROOT = os.path.abspath(a.out) if a.out else str(project)
    plan_path = os.path.abspath(a.plan) if a.plan else os.path.join(ROOT, "audio", "cut_plan.json")
    if not os.path.exists(plan_path):
        p.error("нет плана вырезов: %s" % plan_path)

    with open(plan_path, encoding="utf-8") as f:
        plan = json.load(f)
    report = {}
    for clip, rec in plan.items():
        win0 = rec.get("audio_in", 0) / FPS
        win1 = rec.get("audio_out", 0) / FPS
        print("=" * 74)
        print("ТЕКСТОВОЕ СВЕРЕНИЕ · %s" % clip)
        print("=" * 74)
        ow = json.load(open(os.path.join(ROOT, "audio", "%s_words.json" % clip),
                            encoding="utf-8"))
        cw = json.load(open(os.path.join(ROOT, "audio", "%s_cut_words.json" % clip),
                            encoding="utf-8"))
        gaps = [(g["from_s"], g["to_s"]) for g in rec["gaps"]]

        def dropped(t0, t1):
            return any(t0 < b and t1 > a for a, b in gaps)

        expect = [w for w in ow
                  if w["t0"] >= win0 - 0.05 and w["t1"] <= win1 + 0.05
                  and not dropped(w["t0"], w["t1"])]
        cut_l = [norm(w["w"]) for w in cw]
        exp_l = [norm(w["w"]) for w in expect]
        print(" ожидается прозвучать: %d слов; в cut: %d слов"
              % (len(exp_l), len(cut_l)))
        sm = difflib.SequenceMatcher(a=exp_l, b=cut_l, autojunk=False)
        matched = 0
        missing = []
        extra = []
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                matched += i2 - i1
            elif tag in ("delete", "replace"):
                missing += [{"w": expect[k]["w"], "t": expect[k]["t0"]}
                            for k in range(i1, i2)]
                if tag == "replace":
                    extra += [{"w": cw[k]["w"], "t": cw[k]["t0"]}
                              for k in range(j1, j2)]
            elif tag == "insert":
                extra += [{"w": cw[k]["w"], "t": cw[k]["t0"]}
                          for k in range(j1, j2)]
        print(" совпало слов: %d (%.1f%%)" % (matched, 100.0 * matched / max(1, len(exp_l))))
        print(" НЕ НА МЕСТЕ (%d): %s" % (len(missing), [m["w"] for m in missing][:30]))
        for m in missing[:20]:
            print("     «%s» %.2f с" % (m["w"], m["t"]))
        print(" ЛИШНЕЕ в cut (%d): %s" % (len(extra), [e["w"] for e in extra][:30]))
        report[clip] = {"expected": len(exp_l), "cut": len(cut_l),
                        "matched": matched, "missing": missing, "extra": extra,
                        "matched_pct": round(100.0 * matched / max(1, len(exp_l)), 1),
                        "cut_text": " ".join(w["w"] for w in cw)}
    out_report = os.path.join(ROOT, "audio", "cut_text_compare.json")
    with open(out_report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print("\nотчёт: %s" % out_report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
