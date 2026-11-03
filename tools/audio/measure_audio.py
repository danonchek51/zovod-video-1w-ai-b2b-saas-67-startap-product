# -*- coding: utf-8 -*-
"""measure_audio.py — измерение звука по всем клипам из inventory.json.

Для каждого клипа:
  peak_dbfs, rms_dbfs, LUFS (интегрированная громкость, ebur128),
  клиппинг (доля сэмплов |x| >= 0.999), DC offset,
  «пол» (шум в паузах) и SNR относительно пола,
  доля речи (кадры с энергией выше порога), число пауз.

Пишет: <out>/audio_report.json + <out>/audio_summary.txt
"""
import argparse
import json
import os
import re
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import env_paths  # noqa: E402

FF = env_paths.ffmpeg() or "ffmpeg"
FFP = env_paths.ffprobe() or "ffprobe"
SR = 48000


def decode(path):
    cmd = [FF, "-v", "error", "-i", path, "-ac", "1", "-ar", str(SR),
           "-f", "f32le", "-"]
    p = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, timeout=1800)
    return np.frombuffer(p.stdout, dtype=np.float32)


def ebur128(path):
    """Интегрированная громкость и true peak через ffmpeg ebur128."""
    cmd = [FF, "-nostats", "-v", "info", "-i", path, "-af",
           "ebur128=peak=true", "-f", "null", "-"]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=1800)
    txt = p.stdout.decode("utf-8", "replace")
    i = txt.rfind("Integrated loudness")
    lufs = None
    if i >= 0:
        m = re.search(r"I:\s*(-?[\d.]+)\s*LUFS", txt[i:i + 400])
        if m:
            lufs = float(m.group(1))
    tp = None
    j = txt.rfind("True peak")
    if j >= 0:
        m = re.search(r"Peak:\s*(-?[\d.]+)\s*dBFS", txt[j:j + 200])
        if m:
            tp = float(m.group(1))
    return lufs, tp


def frame_stats(x, win_ms=40):
    w = int(SR * win_ms / 1000)
    n = len(x) // w
    if n == 0:
        return None
    fr = x[: n * w].reshape(n, w)
    rms = np.sqrt((fr ** 2).mean(axis=1))
    db = 20 * np.log10(np.maximum(rms, 1e-10))
    return db


def analyze(path):
    x = decode(path)
    if len(x) == 0:
        return None
    peak = float(np.max(np.abs(x)))
    rms = float(np.sqrt((x ** 2).mean()))
    clip = float((np.abs(x) >= 0.999).mean() * 100)
    dc = float(x.mean())
    db = frame_stats(x)
    # порог речи: -45 dBFS по 40-мс окнам
    thr = -45.0
    speech = db > thr
    speech_ratio = float(speech.mean())
    # паузы: окна ниже порога
    floor_db = float(np.percentile(db, 10)) if len(db) else -90.0
    active_db = float(np.median(db[db > thr])) if (db > thr).any() else -90.0
    snr = active_db - floor_db if active_db > -90 else 0.0
    # число пауз > 0.4 с
    runs = 0
    prev = False
    gap = 0
    for s in speech:
        if not s:
            gap += 1
            if not prev and gap * 40 >= 400:
                runs += 1
        prev = s
    lufs, tp = ebur128(path)
    return {
        "duration_s": round(len(x) / SR, 2),
        "peak_dbfs": round(20 * np.log10(max(peak, 1e-10)), 2),
        "rms_dbfs": round(20 * np.log10(max(rms, 1e-10)), 2),
        "lufs": lufs, "true_peak_dbfs": tp,
        "clip_pct": round(clip, 3),
        "dc_offset": round(dc, 5),
        "floor_dbfs": round(floor_db, 1),
        "active_dbfs": round(active_db, 1),
        "snr_db": round(snr, 1),
        "speech_ratio": round(speech_ratio, 3),
        "pauses": runs,
    }


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="measure_audio.py",
        description="измерение звука по всем клипам из inventory.json")
    p.add_argument("--inventory", default="", help="inventory.json (список клипов)")
    p.add_argument("--out", default="", help="куда писать отчёты (корень проекта)")
    a = p.parse_args(argv)

    project = env_paths.project_root()
    root = os.path.abspath(a.out) if a.out else str(project)
    inv_path = os.path.abspath(a.inventory) if a.inventory else os.path.join(root, "inventory.json")
    out_json = os.path.join(root, "audio_report.json")
    out_txt = os.path.join(root, "audio_summary.txt")
    if not os.path.exists(inv_path):
        p.error("нет инвентаризации: %s" % inv_path)

    with open(inv_path, encoding="utf-8") as f:
        inv = json.load(f)
    clips = inv["clips"]
    out = {}
    lines = []
    for i, c in enumerate(clips, 1):
        name = os.path.splitext(c["file"])[0]
        r = analyze(c["path"])
        if r is None:
            out[name] = {"error": "decode failed"}
            continue
        r["folder"] = c["folder"]
        r["path"] = c["path"]
        out[name] = r
        print("[%d/%d] %s peak=%.1f rms=%.1f lufs=%s clip=%.2f%% snr=%.1f speech=%.0f%%"
              % (i, len(clips), name, r["peak_dbfs"], r["rms_dbfs"],
                 ("%.1f" % r["lufs"]) if r["lufs"] is not None else " n/a ",
                 r["clip_pct"], r["snr_db"], r["speech_ratio"] * 100), flush=True)
        lines.append("%s  dur=%6.1fs peak=%6.1f rms=%7.1f lufs=%7s tp=%7s clip=%6.2f%% "
                     "floor=%6.1f act=%6.1f snr=%5.1f speech=%3.0f%% pauses=%d  | %s"
                     % (name, r["duration_s"], r["peak_dbfs"], r["rms_dbfs"],
                        ("%.1f" % r["lufs"]) if r["lufs"] is not None else "n/a",
                        ("%.1f" % r["true_peak_dbfs"]) if r["true_peak_dbfs"] is not None else "n/a",
                        r["clip_pct"], r["floor_dbfs"], r["active_dbfs"], r["snr_db"],
                        r["speech_ratio"] * 100, r["pauses"], c["folder"][:40]))

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    with open(out_txt, "w", encoding="utf-8") as f:
        f.write("=== ЗВУК: peak/rms в dBFS, LUFS (ebur128), clip % сэмплов >= 0.999 ===\n")
        f.write("=== floor = шум в паузах, act = медиана активных окон, snr = act-floor ===\n\n")
        f.write("\n".join(lines))
    print("DONE", len(out), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
