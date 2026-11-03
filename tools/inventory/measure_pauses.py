# -*- coding: utf-8 -*-
"""measure_pauses.py — измерение «провалов» в звуке разговора.

Вопрос: это цифровой ноль (выпадение) или очень тихая запись?
И какой уровень реального фона вокруг — чтобы понимать, чем заполнять.

Рядом с каждым провалом снимаем «эталон тишины» — 0,60 с ДО и 0,60 с ПОСЛЕ
(там, где говорят, фон всё равно слышен) и ищем самый тихий момент файла
вне провалов — это и есть настоящий floor.

    python measure_pauses.py --wav <файл.wav> --pauses "18.84-20.72,38.72-40.20"
                             [--used-end 65.04] [--json out.json]
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
SR = 48000


def load(path):
    p = subprocess.run([FF, "-v", "error", "-i", path, "-f", "f32le", "-acodec",
                        "pcm_f32le", "-"], stdout=subprocess.PIPE, check=True)
    return np.frombuffer(p.stdout, dtype=np.float32).astype(np.float64)


def rms_db(x):
    if len(x) == 0:
        return -999.0
    r = float(np.sqrt((x ** 2).mean()))
    return 20 * np.log10(max(r, 1e-12))


def parse_pauses(spec):
    """'18.84-20.72,38.72-40.20' -> [('P1', 18.84, 20.72), ...]"""
    out = []
    for i, part in enumerate(spec.split(","), 1):
        part = part.strip()
        if not part:
            continue
        if "-" not in part:
            raise ValueError("неверный интервал: %s" % part)
        a, b = part.split("-", 1)
        out.append(("P%d" % i, float(a), float(b)))
    return out


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="measure_pauses.py",
        description="измерение провалов в звуке и уровня фона вне них")
    p.add_argument("--wav", required=True, help="файл для измерения")
    p.add_argument("--pauses", default="", help="интервалы провалов: 't0-t1,t0-t1'")
    p.add_argument("--used-end", type=float, default=0.0,
                   help="анализировать только первые N секунд (0 — весь файл)")
    p.add_argument("--json", default="", help="куда записать отчёт JSON")
    a = p.parse_args(argv)

    if not os.path.exists(a.wav):
        p.error("нет файла: %s" % a.wav)
    pauses = parse_pauses(a.pauses) if a.pauses else []

    audio = load(a.wav)
    n = int(a.used_end * SR) if a.used_end > 0 else len(audio)
    audio = audio[:n]
    report = {"wav": os.path.abspath(a.wav), "pauses": [], "used_end_s": round(n / SR, 3)}

    print("=== ПРОВАЛЫ: что внутри ===")
    for tag, t0, t1 in pauses:
        x = audio[int(t0 * SR):int(t1 * SR)]
        zeros = int(np.sum(np.abs(x) < 1e-6))
        peak = float(np.max(np.abs(x))) if len(x) else 0.0
        print("%s %6.2f-%6.2f с  RMS %7.2f dBFS  пик %8.5f (%.1f dBFS)  "
              "нулевых сэмплов %d из %d (%.1f%%)"
              % (tag, t0, t1, rms_db(x), peak,
                 20 * np.log10(max(peak, 1e-12)), zeros, len(x),
                 100.0 * zeros / max(1, len(x))))
        pre = audio[max(0, int((t0 - 0.60) * SR)):int(t0 * SR)]
        post = audio[int(t1 * SR):int((t1 + 0.60) * SR)]
        report["pauses"].append({"tag": tag, "t0": t0, "t1": t1,
                                 "rms_dbfs": round(rms_db(x), 2),
                                 "peak_dbfs": round(20 * np.log10(max(peak, 1e-12)), 2),
                                 "zero_samples": zeros,
                                 "zero_pct": round(100.0 * zeros / max(1, len(x)), 3),
                                 "pre_dbfs": round(rms_db(pre), 2),
                                 "post_dbfs": round(rms_db(post), 2)})

    print()
    print("=== ФОН РЯДОМ (0,60 с до / после каждого провала) ===")
    for row in report["pauses"]:
        print("%s  до %7.2f dBFS   после %7.2f dBFS"
              % (row["tag"], row["pre_dbfs"], row["post_dbfs"]))

    print()
    print("=== САМЫЙ ТИХИЙ МОМЕНТ ФАЙЛА ВНЕ ПРОВАЛОВ (floor) ===")
    W = int(0.05 * SR)
    env = np.array([rms_db(audio[i:i + W]) for i in range(0, max(1, n - W), W)])
    in_pause = np.zeros(len(env), dtype=bool)
    for tag, t0, t1 in pauses:
        in_pause[int(t0 / 0.05):int(t1 / 0.05)] = True
    free = np.where(~in_pause)[0]
    if free.size == 0:
        free = np.arange(len(env))
    quiet_idx = free[np.argsort(env[free])[:8]]
    print("  8 самых тихих окон по 0,05 с вне провалов: %s дБFS"
          % ", ".join("%.1f" % env[i] for i in quiet_idx))
    print("  медиана фона вне провалов: %.2f dBFS" % float(np.median(env[free])))
    p10 = float(np.percentile(env[free], 10))
    print("  10-й перцентиль фона вне провалов: %.2f dBFS" % p10)
    report["floor_median_dbfs"] = round(float(np.median(env[free])), 2)
    report["floor_p10_dbfs"] = round(p10, 2)
    report["quiet_windows_dbfs"] = [round(float(env[i]), 2) for i in quiet_idx]

    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        print("report:", a.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
