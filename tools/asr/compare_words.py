# -*- coding: utf-8 -*-
"""compare_words.py — честное сопоставление речи оригинала и пересобранного файла.

Сравнение по мультимножеству слов даёт ложные «потери»: whisper по-разному
сегментирует и распознаёт одни и те же слова на разных файлах («россии»/«россе»,
«уезжай»/«выезжай»). Здесь сравнение идёт ПО ВРЕМЕНИ:

  1. строится карта cut-время -> src-время по сегментам из плана;
  2. для каждого слова ОРИГИНАЛА определяется: попало ли оно в вырезанный
     интервал (тогда это ожидаемая потеря) или должно присутствовать в cut;
  3. для каждого слова CUT ищется исходное слово, отображающееся в него
     (новых слов быть не должно).

Запуск:
    python compare_words.py --plan <cut_plan.json> [--out <корень проекта>]
"""
import argparse
import json
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import env_paths  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

MODELS = ""
FIXED = ""
ROOT = ""
FF = env_paths.ffmpeg() or "ffmpeg"
SR, FPS = 48000, 25


def dec(path, ac=1, rate=16000):
    cmd = [FF, "-v", "error", "-i", path, "-ac", str(ac), "-ar", str(rate),
           "-f", "f32le", "-acodec", "pcm_f32le", "-"]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return np.frombuffer(p.stdout, dtype=np.float32).astype(np.float64)


def asr_words(path):
    from faster_whisper import WhisperModel
    a16 = dec(path, ac=1, rate=16000)
    model = WhisperModel("small", device="cpu", compute_type="int8", download_root=MODELS)
    segs, _ = model.transcribe(a16, language="ru", vad_filter=False,
                               condition_on_previous_text=False, beam_size=5,
                               word_timestamps=True)
    words = []
    for s in segs:
        for w in (s.words or []):
            words.append({"w": w.word.strip(), "t0": round(w.start, 2),
                          "t1": round(w.end, 2)})
    return words


def norm(s):
    return "".join(ch for ch in s.lower() if ch.isalnum())


def build_map(segs, fps=FPS):
    """[(cut_start_s, cut_end_s, src_start_s, src_end_s)] — карта cut->src."""
    out = []
    t = 0.0
    for a, b in segs:
        dur = (b - a) / float(fps)
        out.append((t, t + dur, a / float(fps), b / float(fps)))
        t += dur
    return out


def cut_to_src(mp, t):
    for c0, c1, s0, s1 in mp:
        if c0 <= t < c1:
            return s0 + (t - c0)
    if mp and t >= mp[-1][1]:
        return mp[-1][3]
    return None


def main(argv=None):
    global MODELS, FIXED, ROOT

    p = argparse.ArgumentParser(
        prog="compare_words.py",
        description="сопоставление речи оригинала и пересобранного файла по времени")
    p.add_argument("--plan", default="", help="план вырезов (cut_plan.json)")
    p.add_argument("--out", default="", help="корень проекта для результатов")
    p.add_argument("--models", default="", help="папка с моделями Whisper")
    a = p.parse_args(argv)

    project = env_paths.project_root()
    ROOT = os.path.abspath(a.out) if a.out else str(project)
    plan_path = os.path.abspath(a.plan) if a.plan else os.path.join(ROOT, "audio", "cut_plan.json")
    if not os.path.exists(plan_path):
        p.error("нет плана вырезов: %s" % plan_path)

    MODELS = os.path.abspath(a.models) if a.models else os.path.join(ROOT, "audio", "models")
    FIXED = os.path.join(ROOT, "audio", "proc_mux_fixed")

    with open(plan_path, encoding="utf-8") as f:
        plan = json.load(f)
    report = {}
    for clip in plan:
        print("=" * 74)
        print("СОПОСТАВЛЕНИЕ СЛОВ · %s" % clip)
        print("=" * 74)
        cut = os.path.join(FIXED, "%s_cut.mp4" % clip)
        cut_words = asr_words(cut)
        json.dump(cut_words, open(os.path.join(ROOT, "audio", "%s_cut_words.json" % clip),
                                  "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        orig_words = json.load(open(os.path.join(ROOT, "audio", "%s_words.json" % clip),
                                    encoding="utf-8"))
        rec = plan[clip]
        mp = build_map(rec["audio_segments"])
        gaps_src = [(g["from_s"], g["to_s"]) for g in rec["gaps"]]

        def in_gap(t):
            return any(a <= t < b for a, b in gaps_src)

        # 1) оригинальные слова: вырезанные / потерянные
        cut_ok, cut_expected = [], []
        lost = []
        for w in orig_words:
            mid = (w["t0"] + w["t1"]) / 2.0
            if in_gap(mid) or in_gap(w["t0"]) or in_gap(w["t1"]):
                cut_expected.append(w)
                continue
            # ищем в cut слово, отображающееся в это место
            cand = None
            for c in cut_words:
                src_t = cut_to_src(mp, (c["t0"] + c["t1"]) / 2.0)
                if src_t is None:
                    continue
                if abs(src_t - mid) <= 1.2:
                    cand = c
                    break
            if cand is None or norm(cand["w"]) != norm(w["w"]):
                lost.append({"word": w["w"], "t": round(mid, 2),
                             "near": cand["w"] if cand else None})
            else:
                cut_ok.append(w)
        # 2) новые слова в cut (нет соответствующего оригинального)
        orig_norm = set(norm(w["w"]) for w in orig_words)
        new_words = [c for c in cut_words if norm(c["w"]) not in orig_norm]
        print(" оригинал: %d слов, из них вырезано (ожидаемо) %d, должно звучать %d"
              % (len(orig_words), len(cut_expected), len(cut_ok) + len(lost)))
        print(" подтверждено в cut: %d" % len(cut_ok))
        print(" РАСХОЖДЕНИЯ (%d):" % len(lost))
        for x in lost[:40]:
            print("    «%s» в %.2f с → в cut: %s"
                  % (x["word"], x["t"], x["near"] if x["near"] else "—"))
        print(" новых слов в cut (%d): %s"
              % (len(new_words), [w["w"] for w in new_words][:25]))
        print(" вырезанные слова (ожидаемо): %s"
              % [w["w"] for w in cut_expected][:40])
        report[clip] = {
            "orig_words": len(orig_words), "cut_words": len(cut_words),
            "expected_cut": len(cut_expected),
            "confirmed": len(cut_ok), "mismatches": lost,
            "new_words": [{"w": c["w"], "t": c["t0"]} for c in new_words],
            "cut_words_sample": [c["w"] for c in cut_words],
        }
    out_report = os.path.join(ROOT, "audio", "cut_word_compare.json")
    with open(out_report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print("\nотчёт: %s" % out_report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
