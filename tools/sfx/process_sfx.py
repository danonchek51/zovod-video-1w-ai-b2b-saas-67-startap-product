#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
process_sfx.py - обработка звуковых эффектов под стандарт проекта.

Стандарт: 48 кГц / стерео / pcm_s24le. Оригиналы SFXMint (44,1 кГц / s16)
остаются нетронутыми в папке orig/.

Рецепты (все — разрешённые SFXMint операции: фильтрация, ресемплинг, уровень):
  impact-thud-63  УДАР A (глухой): highpass 35, лимитер -1.5 dBTP
  car-crash-05    УДАР B (бампер):  highpass 35, lowpass 6000, лимитер -1.5 dBTP
  car-crash-04    УДАР C (сильный): highpass 35, lowpass 4000, лимитер -1.5 dBTP
  tinnitus-tone-09 ОГЛУШЕНИЕ:       highpass 80, лимитер -6 dBTP

Замеры после каждой обработки: true peak (ebur128 peak=true), RMS, LUFS,
клиппинг, спектральный центроид, длительность. Числа -> JSON-отчёт.

    python process_sfx.py --src <папка с оригиналами .wav> --out <папка результата>
                           [--report <out.json>]
"""
import argparse
import json
import math
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import env_paths  # noqa: E402


def _tool(name):
    """Путь к ffmpeg/ffprobe: env_paths -> PATH."""
    found = env_paths.ffmpeg() if name == "ffmpeg" else env_paths.ffprobe()
    return found or shutil.which(name) or name


FFMPEG = _tool("ffmpeg")
FFPROBE = _tool("ffprobe")

RECIPES = [
    {"slug": "impact-thud-63", "role": "УДАР A — глухой тяжёлый удар",
     "filters": "highpass=f=35", "target_tp_db": -1.5},
    {"slug": "car-crash-05", "role": "УДАР B — низкоскоростной бампер",
     "filters": "highpass=f=35,lowpass=f=6000", "target_tp_db": -1.5},
    {"slug": "car-crash-04", "role": "УДАР C — авария с разбитием стекла",
     "filters": "highpass=f=35,lowpass=f=4000", "target_tp_db": -1.5},
    {"slug": "tinnitus-tone-09", "role": "ОГЛУШЕНИЕ — звон в ушах",
     "filters": "highpass=f=80", "target_tp_db": -6.0},
]


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    return p.returncode, p.stdout, p.stderr


def measure(path):
    """true peak / RMS / LUFS через ebur128 + формат файла."""
    rc, out, err = run([FFMPEG, "-hide_banner", "-nostats", "-i", path,
                        "-af", "ebur128=peak=true", "-f", "null", "-"])
    text = out + err
    res = {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("I:") and " LUFS" in line:
            try:
                res["lufs"] = float(line.split()[1])
            except (ValueError, IndexError):
                pass
        if line.startswith("Peak:") and "dBFS" in line:
            try:
                res["true_peak_db"] = float(line.split()[1])
            except (ValueError, IndexError):
                pass
    rc, out, err = run([FFPROBE, "-hide_banner", "-v", "error",
                        "-show_entries", "stream=sample_rate,channels,duration",
                        "-of", "json", path])
    try:
        st = json.loads(out)["streams"][0]
        res["sample_rate"] = int(st.get("sample_rate", 0))
        res["channels"] = int(st.get("channels", 0))
        res["duration_s"] = float(st.get("duration", 0.0))
    except Exception:
        pass
    return res


def pcm_stats(path):
    """Клиппинг, RMS, спектральный центроид, хвост — через ffmpeg -> s16le -> numpy."""
    code = "\n".join([
        "import numpy as np, subprocess, json, sys, math",
        "cmd = [%s, '-v', 'error', '-i', sys.argv[1], '-f', 's16le'," % json.dumps(FFMPEG),
        "       '-acodec', 'pcm_s16le', '-ac', '2', '-ar', '48000', '-']",
        "p = subprocess.run(cmd, capture_output=True)",
        "a = np.frombuffer(p.stdout, dtype='<i2').astype(np.float32) / 32768.0",
        "if a.size % 2: a = a[:-1]",
        "m = a.reshape(-1, 2).mean(axis=1)",
        "clip = float((np.abs(a) >= 0.999).mean() * 100.0)",
        "rms = float(np.sqrt((m ** 2).mean())) if m.size else 0.0",
        "peak = float(np.abs(a).max()) if a.size else 0.0",
        "tail_n = int(0.2 * 48000)",
        "tail = float(np.sqrt((m[-tail_n:] ** 2).mean())) if m.size > tail_n else rms",
        "# активная часть: окна 40 мс с RMS выше (максимум - 35 дБ) и выше -70 dBFS",
        "w = 1920",
        "n = m.size // w",
        "wr = m[:n * w].reshape(n, w)",
        "wrms = np.sqrt((wr ** 2).mean(axis=1))",
        "thr = max(wrms.max() * 10 ** (-35 / 20.0), 3e-4)",
        "act = np.where(wrms >= thr)[0]",
        "if act.size:",
        "    seg = m[act[0] * w:(act[-1] + 1) * w]",
        "else:",
        "    seg = m",
        "ar = float(np.sqrt((seg ** 2).mean())) if seg.size else 0.0",
        "spec = np.abs(np.fft.rfft(seg * np.hanning(seg.size))) if seg.size > 1 else np.zeros(1)",
        "freqs = np.fft.rfftfreq(seg.size, 1 / 48000.0)",
        "cent = float((spec * freqs).sum() / spec.sum()) if spec.sum() > 0 else 0.0",
        "active_ms = int(seg.size / 48.0)",
        "print(json.dumps({'clip_pct': clip, 'rms_linear': rms,",
        "                  'tail_rms_linear': tail, 'centroid_hz': cent,",
        "                  'active_rms_db': (20 * math.log10(ar) if ar > 0 else None),",
        "                  'active_ms': active_ms,",
        "                  'peak_linear': peak, 'samples': int(a.size)}))",
    ])
    rc, out, err = run([sys.executable, "-c", code, path])
    try:
        return json.loads(out.strip().splitlines()[-1])
    except Exception:
        print("  ! pcm_stats не разобрал вывод:", (err or out)[-300:])
        return {}


def sha256(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def process(rec, orig_dir, proc_dir):
    src = os.path.join(orig_dir, rec["slug"] + ".wav")
    dst = os.path.join(proc_dir, rec["slug"] + ".wav")
    tmp = dst + ".tmp.wav"
    # замер ОРИГИНАЛА тем же кодом - чтобы "до/после" сравнивать в одной методике
    orig_meas = measure(src)
    orig_ps = pcm_stats(src)
    chain = ("aresample=48000:filter_size=64:phase_shift=10," + rec["filters"])
    gain = 0.0
    hist = []
    for attempt in range(4):
        parts = [chain]
        if gain != 0.0:
            parts.append("volume=%.3fdB" % gain)
        parts.append("alimiter=limit=0.891251:attack=5:release=50:level=disabled")
        af = ",".join(parts)
        rc, out, err = run([FFMPEG, "-hide_banner", "-nostats", "-y", "-i", src,
                            "-af", af, "-ar", "48000", "-ac", "2",
                            "-c:a", "pcm_s24le", tmp])
        if rc != 0:
            return {"error": err[-800:], "slug": rec["slug"]}
        m = measure(tmp)
        tp = m.get("true_peak_db")
        hist.append({"attempt": attempt + 1, "gain_db": round(gain, 2),
                     "true_peak_db": tp})
        if tp is None:
            break
        target = rec["target_tp_db"]
        if abs(tp - target) <= 0.05:
            break
        gain += (target - tp)          # тише — если выше цели, громче — если ниже
    run([FFMPEG, "-hide_banner", "-y", "-i", tmp, "-c:a", "copy", dst])
    try:
        os.remove(tmp)
    except OSError:
        pass
    m = measure(dst)
    ps = pcm_stats(dst)
    if ps:
        m["rms_db"] = 20 * math.log10(ps["rms_linear"]) if ps.get("rms_linear") else None
        m["tail_rms_db"] = (20 * math.log10(ps["tail_rms_linear"])
                            if ps.get("tail_rms_linear") else None)
        m["clip_pct"] = ps.get("clip_pct")
        m["centroid_hz"] = ps.get("centroid_hz")
        m["peak_linear"] = ps.get("peak_linear")
    m.update({key: val for key, val in ps.items() if key not in m})
    m["slug"] = rec["slug"]
    m["role"] = rec["role"]
    m["filters"] = rec["filters"]
    m["final_gain_db"] = round(gain, 2)
    m["target_tp_db"] = rec["target_tp_db"]
    m["iterations"] = hist
    m["out_file"] = dst
    m["sha256_out"] = sha256(dst)
    m["sha256_in"] = sha256(src)
    # "до/после" в одной методике
    m["orig_true_peak_db"] = orig_meas.get("true_peak_db")
    m["orig_centroid_hz"] = orig_ps.get("centroid_hz")
    m["orig_active_ms"] = orig_ps.get("active_ms")
    if m.get("centroid_hz") and m.get("orig_centroid_hz"):
        m["centroid_delta_hz"] = round(m["centroid_hz"] - m["orig_centroid_hz"], 1)
    if m.get("active_ms") and m.get("orig_active_ms"):
        m["active_ms_delta"] = m["active_ms"] - m["orig_active_ms"]
    return m


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="process_sfx.py",
        description="обработка SFX под стандарт проекта (48 кГц / стерео / pcm_s24le)")
    p.add_argument("--src", default="", help="папка с оригиналами .wav")
    p.add_argument("--out", default="", help="папка для обработанных .wav")
    p.add_argument("--report", default="", help="путь к JSON-отчёту")
    a = p.parse_args(argv)

    project = env_paths.project_root()
    orig_dir = os.path.abspath(a.src) if a.src else str(project / "sfx" / "orig")
    proc_dir = os.path.abspath(a.out) if a.out else str(project / "audio" / "sfx")
    if not os.path.isdir(orig_dir):
        p.error("нет папки с оригиналами: %s (укажи --src)" % orig_dir)
    os.makedirs(proc_dir, exist_ok=True)

    report = []
    for rec in RECIPES:
        r = process(rec, orig_dir, proc_dir)
        report.append(r)
        if "error" in r:
            print("%-20s ОШИБКА" % rec["slug"])
            print(r["error"])
        else:
            print("%-20s TP=%6.2f dBTP (цель %5.2f)  RMS=%6.2f dB  "
                  "LUFS=%7.2f  клиппинг=%.2f%%  центроид=%7.1f Гц  dur=%.2f с  gain=%.2f дБ"
                  % (rec["slug"], r.get("true_peak_db", 0), r["target_tp_db"],
                     r.get("rms_db", 0), r.get("lufs", 0), r.get("clip_pct", 0),
                     r.get("centroid_hz", 0), r.get("duration_s", 0),
                     r["final_gain_db"]))
    out = a.report or os.path.join(proc_dir, "sfx_report.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print("report:", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
