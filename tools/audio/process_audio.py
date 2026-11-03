# -*- coding: utf-8 -*-
"""process_audio.py — финальная обработка звука для всех клипов инвентаризации.

Цепочка:
  1. highpass=f=80        — убрать гул и низкочастотную тряску
  2. arnndn=m=std.rnnn    — RNNoise (xiph, BSD-2): шумоподавление,
                             обученное на речи; даёт −16…−30 дБ к полу
  3. volume + alimiter    — выравнивание громкости речи до −16 LUFS
                             (потолок true peak −1,5 dBTP) — только для
                             клипов с речью; «атмосфера» не трогается

Диэссер отклонён: RNNoise сам снимает шипящие на −7 дБ, а ffmpeg-деэссер
дополнительно режет речевой диапазон 300–3400 Гц.

    python process_audio.py --inventory inventory.json --scene-map scene_map.json
                            [--out <корень проекта>] [--models <папка с моделями RNNoise>]

Пишет:
  <out>/audio/proc/<клип>.wav      — обработанный звук 48 кГц 24 бит стерео
  <out>/audio/proc_mux/<клип>.MP4  — то же видео с обработанным звуком
  <out>/audio/proc_report.json     — замеры до/после по каждому клипу
  <out>/audio/proc_summary.txt     — таблица
"""
import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import env_paths  # noqa: E402

RNN = "std.rnnn"
SR = 48000
TARGET_I = -16.0
TARGET_TP = -1.5
MAX_GAIN = 12.0          # больше не поднимаем — иначе взлетит шум
LIMIT = 0.841            # alimiter, -1.5 dBFS по сэмплу

FF = env_paths.ffmpeg() or "ffmpeg"


def ebur128(path):
    p = subprocess.run([FF, "-nostats", "-v", "info", "-i", path, "-af",
                        "ebur128=peak=true", "-f", "null", "-"],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=1800)
    txt = p.stdout.decode("utf-8", "replace")
    out = {"I": None, "TP": None, "LRA": None, "thresh": None}
    i = txt.rfind("Integrated loudness")
    if i >= 0:
        m = re.search(r"I:\s*(-?[\d.]+)\s*LUFS", txt[i:i + 400])
        if m:
            out["I"] = float(m.group(1))
        m = re.search(r"LRA:\s*(-?[\d.]+)\s*LU", txt[i:i + 400])
        if m:
            out["LRA"] = float(m.group(1))
    j = txt.rfind("True peak")
    if j >= 0:
        m = re.search(r"Peak:\s*(-?[\d.]+)\s*dBFS", txt[j:j + 200])
        if m:
            out["TP"] = float(m.group(1))
    return out


def has_speech(name, smap):
    for r in smap:
        if r["clip"] == name:
            t = r.get("speech_type")
            return t in ("ДИАЛОГ", "ОЗВУЧКА", "СПОРНО", "ЗА КАДРОМ"), t
    return False, "?"


def run(cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, timeout=3600)


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="process_audio.py",
        description="финальная обработка звука (шумоподавление + нормализация речи)")
    p.add_argument("--inventory", default="", help="inventory.json (список клипов)")
    p.add_argument("--scene-map", default="", help="scene_map.json (тип речи по клипам)")
    p.add_argument("--out", default="", help="корень проекта для результатов")
    p.add_argument("--models", default="", help="папка с моделью RNNoise (std.rnnn)")
    a = p.parse_args(argv)

    project = env_paths.project_root()
    root = os.path.abspath(a.out) if a.out else str(project)
    inv_path = os.path.abspath(a.inventory) if a.inventory else os.path.join(root, "inventory.json")
    smap_path = os.path.abspath(a.scene_map) if a.scene_map else os.path.join(root, "scene_map.json")
    models = os.path.abspath(a.models) if a.models else os.path.join(root, "audio", "models")
    out_wav = os.path.join(root, "audio", "proc")
    out_mux = os.path.join(root, "audio", "proc_mux")
    tmp_dir = os.path.join(root, "audio", "_tmp")

    for path_ in (inv_path, smap_path):
        if not os.path.exists(path_):
            p.error("нет входного файла: %s" % path_)
    if not os.path.isdir(models):
        p.error("нет папки с моделями RNNoise: %s (укажи --models)" % models)

    with open(inv_path, encoding="utf-8") as f:
        inv = json.load(f)
    with open(smap_path, encoding="utf-8") as f:
        smap = json.load(f)

    os.makedirs(out_wav, exist_ok=True)
    os.makedirs(out_mux, exist_ok=True)
    os.makedirs(tmp_dir, exist_ok=True)

    report = {}
    lines = []
    clips = inv["clips"]
    total = len(clips)
    for idx, c in enumerate(clips, 1):
        name = os.path.splitext(c["file"])[0]
        src = c["path"]
        sp, stype = has_speech(name, smap)
        tmp = os.path.join(tmp_dir, name + "_den.wav")
        wav = os.path.join(out_wav, name + ".wav")

        # 1. шумоподавление
        r = run([FF, "-v", "error", "-y", "-i", src, "-af",
                 "highpass=f=80,arnndn=m=%s" % RNN, "-c:a", "pcm_s24le", tmp],
                cwd=models)
        if r.returncode != 0 or not os.path.exists(tmp):
            print("[%d/%d] %s DENOISE FAILED" % (idx, total, name), flush=True)
            report[name] = {"error": "denoise failed", "stype": stype}
            continue
        d = ebur128(tmp)

        # 2. выравнивание громкости (только для речи)
        gain = 0.0
        if sp and d["I"] is not None:
            gain = TARGET_I - d["I"]
            if d["TP"] is not None:
                gain = min(gain, TARGET_TP - d["TP"])
            gain = max(gain, -40.0)
            capped = False
            if gain > MAX_GAIN:
                gain = MAX_GAIN
                capped = True
        else:
            capped = False
        af = ("volume=%+.2fdB,alimiter=limit=%.4f:level=disabled" % (gain, LIMIT))
        r = run([FF, "-v", "error", "-y", "-i", tmp, "-af", af, "-c:a", "pcm_s24le", wav])
        if r.returncode != 0:
            print("[%d/%d] %s GAIN FAILED" % (idx, total, name), flush=True)
            report[name] = {"error": "gain failed", "stype": stype}
            continue
        fin = ebur128(wav)

        # 3. мукс: видео копией + обработанный звук
        mux = os.path.join(out_mux, name + ".MP4")
        r = run([FF, "-v", "error", "-y", "-i", src, "-i", wav,
                 "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
                 "-c:a", "pcm_s16be", mux])
        mux_ok = (r.returncode == 0 and os.path.exists(mux))

        report[name] = {
            "stype": stype, "speech": sp,
            "duration_s": c.get("duration_s"),
            "orig": ebur128(src),
            "denoised": d,
            "gain_db": round(gain, 2), "gain_capped": capped,
            "final": fin,
            "lufs_delta": round((fin["I"] or 0) - (d["I"] or 0), 2) if fin["I"] else None,
            "wav": wav, "mux": mux if mux_ok else None,
        }
        print("[%d/%d] %-6s %-10s gain=%+6.2f  I: %s -> %s -> %s  TP %s -> %s  mux=%s"
              % (idx, total, name, stype, gain,
                 report[name]["orig"]["I"], d["I"], fin["I"],
                 report[name]["orig"]["TP"], fin["TP"], "ok" if mux_ok else "FAIL"),
              flush=True)
        lines.append("%-6s %-10s dur=%6.1f  I: %7s -> %7s -> %7s  TP: %6s -> %6s  "
                     "gain=%+6.2f%s  LRA=%s"
                     % (name, stype, c.get("duration_s") or 0,
                        report[name]["orig"]["I"], d["I"], fin["I"],
                        report[name]["orig"]["TP"], fin["TP"], gain,
                        " (cap)" if capped else "", fin.get("LRA")))
        try:
            os.remove(tmp)
        except OSError:
            pass

    with open(os.path.join(root, "audio", "proc_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    with open(os.path.join(root, "audio", "proc_summary.txt"), "w", encoding="utf-8") as f:
        f.write("=== ОБРАБОТАННЫЙ ЗВУК: I — интегрированная громкость LUFS, "
                "TP — true peak dBFS ===\n")
        f.write("=== цепочка: highpass 80 -> RNNoise(std) -> volume -> alimiter(-1.5 dBFS) ===\n")
        f.write("=== речь нормализуется к -16 LUFS; «атмосфера» без изменения уровня ===\n\n")
        f.write("\n".join(lines))
    print("DONE", len(report))


if __name__ == "__main__":
    sys.exit(main())
