# -*- coding: utf-8 -*-
"""verify_cut_files.py — независимая проверка пересобранных клипов.

Проверяем каждый файл audio/proc_mux_fixed/<CLIP>_cut.mp4:
  1. ffprobe: видео/аудио дорожки, кадры, длительность;
  2. аудио: пик, клиппинг, окна абсолютной тишины (< -60 dBFS) — их быть не должно;
  3. ASR: все слова оригинала на месте? какие слова пропали (только ли вырезанные)?
  4. уровень речи не просел (RMS слов);
  5. нет лишних/искажённых слов.

Запуск:
    python verify_cut_files.py --src <папка с оригиналами> --plan <cut_plan.json>
                              [--out <корень проекта>]
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

FF = env_paths.ffmpeg() or "ffmpeg"
FP = env_paths.ffprobe() or "ffprobe"
SR, FPS = 48000, 25
SILENCE_DB = -60.0
SILENCE_WIN = 0.5

MODELS = ""
FIXED = ""
ORIG_DIR = ""
ROOT = ""


def run(cmd, **kw):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kw)


def dec(path, ac=2, rate=SR):
    cmd = [FF, "-v", "error", "-i", path]
    if ac:
        cmd += ["-ac", str(ac)]
    cmd += ["-ar", str(rate), "-f", "f32le", "-acodec", "pcm_f32le", "-"]
    p = run(cmd)
    a = np.frombuffer(p.stdout, dtype=np.float32).astype(np.float64)
    if a.size == 0:
        raise RuntimeError("пустое аудио: " + path)
    return a.reshape(-1, ac) if ac == 2 else a


def db(x):
    return -999.0 if x <= 0 else 20.0 * float(np.log10(max(x, 1e-12)))


def probe(path):
    p = run([FP, "-v", "error", "-print_format", "json",
             "-show_streams", "-show_format", path])
    j = json.loads(p.stdout.decode("utf-8", "replace"))
    out = {"streams": [], "duration": float(j["format"].get("duration", 0))}
    for s in j.get("streams", []):
        out["streams"].append({
            "type": s.get("codec_type"), "codec": s.get("codec_name"),
            "nb_frames": s.get("nb_frames"), "dur": s.get("duration"),
            "sr": s.get("sample_rate"), "ch": s.get("channels"),
            "w": s.get("width"), "h": s.get("height")})
    return out


def silence_windows(a):
    """Окна абсолютной тишины: RMS ниже SILENCE_DB длиннее SILENCE_WIN с."""
    m = a.mean(axis=1) if a.ndim == 2 else a
    w = int(SILENCE_WIN * SR)
    if len(m) < w:
        return []
    n = len(m) // w
    rms = np.sqrt((m[:n * w].reshape(n, w) ** 2).mean(axis=1))
    q = 20 * np.log10(np.maximum(rms, 1e-12)) < SILENCE_DB
    out, i = [], 0
    while i < n:
        if q[i]:
            j = i
            while j < n and q[j]:
                j += 1
            out.append({"from_s": round(i * SILENCE_WIN, 2),
                        "to_s": round(j * SILENCE_WIN, 2),
                        "dur_s": round((j - i) * SILENCE_WIN, 2)})
            i = j
        else:
            i += 1
    return out


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


def main(argv=None):
    global MODELS, FIXED, ORIG_DIR, ROOT

    p = argparse.ArgumentParser(
        prog="verify_cut_files.py",
        description="независимая проверка пересобранных клипов")
    p.add_argument("--src", default="", help="папка с оригиналами (только чтение)")
    p.add_argument("--plan", default="", help="план вырезов (cut_plan.json)")
    p.add_argument("--out", default="", help="корень проекта для результатов")
    p.add_argument("--models", default="", help="папка с моделями Whisper")
    a = p.parse_args(argv)

    project = env_paths.project_root()
    ROOT = os.path.abspath(a.out) if a.out else str(project)
    plan_path = os.path.abspath(a.plan) if a.plan else os.path.join(ROOT, "audio", "cut_plan.json")
    if not os.path.exists(plan_path):
        p.error("нет плана вырезов: %s" % plan_path)
    src = os.path.abspath(a.src) if a.src else str(env_paths.src_root() or "")
    if not src or not os.path.isdir(src):
        p.error("нет папки с оригиналами (укажи --src)")

    MODELS = os.path.abspath(a.models) if a.models else os.path.join(ROOT, "audio", "models")
    FIXED = os.path.join(ROOT, "audio", "proc_mux_fixed")
    ORIG_DIR = src

    with open(plan_path, encoding="utf-8") as f:
        plan = json.load(f)
    report = {}
    for clip in plan:
        cut = os.path.join(FIXED, "%s_cut.mp4" % clip)
        orig = os.path.join(ORIG_DIR, clip + ".MP4")
        print("=" * 74)
        print("ПРОВЕРКА %s" % clip)
        print("=" * 74)
        pr = probe(cut)
        print(" ffprobe: длительность %.3f с" % pr["duration"])
        for s in pr["streams"]:
            print("   %-5s %-10s кадров=%s dur=%s %sx%s %s Hz %s кан."
                  % (s["type"], s["codec"], s["nb_frames"], s["dur"], s["w"], s["h"],
                     s["sr"], s["ch"]))

        a = dec(cut, ac=2)
        peak = float(np.abs(a).max())
        clipn = int((np.abs(a) >= 0.999).sum())
        sil = silence_windows(a)
        print(" аудио: %.3f с, пик %.2f dBFS, клиппинг %.4f%% (%d)"
              % (len(a) / SR, db(peak), 100.0 * clipn / a.size, clipn))
        print(" окна абсолютной тишины (< %.0f dBFS, ≥ %.1f с): %d %s"
              % (SILENCE_DB, SILENCE_WIN, len(sil),
                 sil[:8] if sil else "—"))

        cut_words = asr_words(cut)
        json.dump(cut_words, open(os.path.join(ROOT, "audio", "%s_cut_words.json" % clip),
                                  "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        orig_words = json.load(open(os.path.join(ROOT, "audio", "%s_words.json" % clip),
                                    encoding="utf-8"))
        co = [norm(w["w"]) for w in cut_words]
        oo = [norm(w["w"]) for w in orig_words]
        gaps = plan[clip]["gaps"]
        lost = []
        from collections import Counter
        oc, cc = Counter(oo), Counter(co)
        for w, n in (oc - cc).items():
            lost.append({"word": w, "n": n})
        new = [{"word": w, "n": n} for w, n in (cc - oc).items()]
        print(" ASR: оригинал %d слов, в cut %d слов" % (len(oo), len(co)))
        print("   не хватает: %s" % (lost if lost else "—"))
        print("   лишние/новые: %s" % (new if new else "—"))
        # проверяем: каждое «потерянное» слово реально попало в вырезанный интервал
        unexplained = []
        for item in lost:
            w = item["word"]
            hits = [ow for ow in orig_words if norm(ow["w"]) == w]
            inside = False
            for ow in hits:
                for g in gaps:
                    if ow["t0"] < g["to_s"] and ow["t1"] > g["from_s"]:
                        inside = True
                        break
                if inside:
                    break
            if not inside:
                unexplained.append(item)
        print("   потеряно вне вырезанных интервалов: %s"
              % (unexplained if unexplained else "нет"))

        # уровень речи: RMS слов в cut vs оригинале
        m = a.mean(axis=1)
        def word_rms(words):
            vals = []
            for w in words:
                i0, i1 = int(w["t0"] * SR), int(w["t1"] * SR)
                if i1 <= i0:
                    continue
                seg = m[i0:i1]
                if seg.size:
                    vals.append(db(float(np.sqrt((seg ** 2).mean()))))
            return vals
        crms = word_rms(cut_words)
        orms = word_rms(orig_words)
        if crms:
            print(" RMS слов: оригинал медиана %.2f dBFS, cut медиана %.2f dBFS"
                  % (np.median(orms), np.median(crms)))
        report[clip] = {"probe": pr, "peak_dbfs": round(db(peak), 2),
                        "clip_samples": clipn, "silence_windows": sil,
                        "orig_words": len(oo), "cut_words": len(co),
                        "lost": lost, "new": new,
                        "lost_outside_gaps": unexplained,
                        "rms_words_orig": round(float(np.median(orms)), 2),
                        "rms_words_cut": round(float(np.median(crms)), 2) if crms else None,
                        "audio_duration_s": round(len(a) / SR, 3)}
    out_report = os.path.join(ROOT, "audio", "cut_verify.json")
    with open(out_report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print("\nотчёт: %s" % out_report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
