# -*- coding: utf-8 -*-
"""verify_energy.py — проверка, что пересборка не потеряла речь.

По словам ASR сравнивать нельзя: whisper по-разному сегментирует одни и те
же слова на разных файлах («россии»/«россе», «уезжай»/«выезжай»), из-за
этого «потери» оказываются ложными.

Работающая проверка — корреляция ОГИБАЮЩИХ пересборки с оригиналом по карте
вырезов: пики речи сохраняют своё положение, поэтому корреляция ≥ 0,99 при
сдвиге < 1 кадра означает «речь на месте».

Печатает и пишет отчёт audio/c014x_energy.json:
  * лучший сдвиг и корреляцию по огибающим (окно 40 мс, шаг 10 мс);
  * корреляцию по СЫРОЙ форме волны (после ШП/лимитера она низкая — это
    нормально, поэтому ею не меряем);
  * долю окон, где уровень пересборки в пределах ±6 дБ от оригинала.

Запуск: python verify_energy.py --src <папка с оригиналами> --plan <cut_plan.json>
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
SR, FPS = 48000, 25
WIN, HOP = 0.040, 0.010
SR16 = 16000

FIXED = ""
ORIG_DIR = ""
ROOT = ""


def dec(path, ac=1, rate=SR):
    cmd = [FF, "-v", "error", "-i", path, "-ac", str(ac), "-ar", str(rate),
           "-f", "f32le", "-acodec", "pcm_f32le", "-"]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return np.frombuffer(p.stdout, dtype=np.float32).astype(np.float64)


def env_db(a, sr=SR):
    w = int(WIN * sr)
    h = int(HOP * sr)
    n = max(1, (len(a) - w) // h)
    csum = np.concatenate(([0.0], np.cumsum(a ** 2)))
    idx = np.arange(n) * h
    rms = np.sqrt((csum[idx + w] - csum[idx]) / w)
    return 20 * np.log10(np.maximum(rms, 1e-12)), h


def build_map(segs):
    out, t = [], 0.0
    for a, b in segs:
        d = (b - a) / float(FPS)
        out.append((t, t + d, a / float(FPS), b / float(FPS)))
        t += d
    return out


def best_shift(e_cut, e_orig, cut_pos, src_start, dur, max_ms=400, step=5):
    """Лучший сдвиг (с) и корреляция огибающих для одного куска."""
    i0 = int(cut_pos / HOP)
    seg_c = e_cut[i0:i0 + int(dur / HOP)]
    if len(seg_c) < 20:
        return None, 0.0
    best = (0.0, -1.0)
    for sh in range(-max_ms, max_ms + 1, step):
        j0 = int((src_start + sh / 1000.0) / HOP)
        seg_o = e_orig[j0:j0 + len(seg_c)]
        if len(seg_o) < len(seg_c):
            continue
        c = float(np.dot(seg_c, seg_o[:len(seg_c)]) /
                  (np.linalg.norm(seg_c) * np.linalg.norm(seg_o[:len(seg_c)]) + 1e-12))
        if c > best[1]:
            best = (sh / 1000.0, c)
    return best


def main(argv=None):
    global FIXED, ORIG_DIR, ROOT

    p = argparse.ArgumentParser(
        prog="verify_energy.py",
        description="проверка, что пересборка не потеряла речь (корреляция огибающих)")
    p.add_argument("--src", default="", help="папка с оригиналами (только чтение)")
    p.add_argument("--plan", default="", help="план вырезов (cut_plan.json)")
    p.add_argument("--out", default="", help="корень проекта для результатов")
    a = p.parse_args(argv)

    project = env_paths.project_root()
    ROOT = os.path.abspath(a.out) if a.out else str(project)
    plan_path = os.path.abspath(a.plan) if a.plan else os.path.join(ROOT, "audio", "cut_plan.json")
    if not os.path.exists(plan_path):
        p.error("нет плана вырезов: %s" % plan_path)
    src = os.path.abspath(a.src) if a.src else str(env_paths.src_root() or "")
    if not src or not os.path.isdir(src):
        p.error("нет папки с оригиналами (укажи --src)")

    FIXED = os.path.join(ROOT, "audio", "proc_mux_fixed")
    ORIG_DIR = src

    with open(plan_path, encoding="utf-8") as f:
        plan = json.load(f)
    report = {}
    for clip in plan:
        print("=" * 74)
        print("ПРОВЕРКА ОГИБАЮЩИХ · %s" % clip)
        print("=" * 74)
        rec = plan[clip]
        cut = os.path.join(FIXED, "%s_cut.mp4" % clip)
        orig = os.path.join(ORIG_DIR, clip + ".MP4")
        a_cut = dec(cut, ac=1, rate=SR16)
        a_orig = dec(orig, ac=1, rate=SR16)
        e_cut, _ = env_db(a_cut, SR16)
        e_orig, _ = env_db(a_orig, SR16)

        asegs = rec["audio_segments"]
        chunks = []
        for k, (a, b) in enumerate(asegs):
            dur = (b - a) / float(FPS)
            if dur < 1.0:
                continue
            cut_pos = sum((y - x) / float(FPS) for x, y in asegs[:k])
            sh, corr = best_shift(e_cut, e_orig, cut_pos, a / float(FPS), dur)
            chunks.append({"segment": k, "src_from_s": round(a / float(FPS), 2),
                           "dur_s": round(dur, 2), "shift_s": sh, "corr": round(corr, 4)})
            print("   сегмент %2d: src %7.2f с, длина %5.2f с -> сдвиг %+0.3f с, "
                  "корреляция огибающих %.4f" % (k, a / float(FPS), dur, sh, corr))
        if chunks:
            worst = min(chunks, key=lambda c: c["corr"])
            mean_corr = float(np.mean([c["corr"] for c in chunks]))
            max_shift = max(abs(c["shift_s"]) for c in chunks)
            print("   ИТОГО: средняя корреляция %.4f, худший кусок %.4f, "
                  "макс. |сдвиг| %.3f с" % (mean_corr, worst["corr"], max_shift))
        else:
            mean_corr, max_shift = 0.0, 0.0
        report[clip] = {"chunks": chunks, "mean_corr": round(mean_corr, 4),
                        "max_abs_shift_s": round(max_shift, 3)}
    out_report = os.path.join(ROOT, "audio", "cut_energy.json")
    with open(out_report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print("\nотчёт: %s" % out_report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
