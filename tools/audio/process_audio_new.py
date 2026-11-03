# -*- coding: utf-8 -*-
"""process_audio_new.py — обработка звука для ВЫБРАННЫХ клипов.

Тот же рецепт, что для основной массы клипов:
  highpass=f=80 -> arnndn(m=std.rnnn) -> [volume + alimiter] -> WAV 48 кГц 24 бит
Мукс: видео копией + обработанный звук pcm_s16be -> MP4 (audio/proc_mux).

Отличие: добавлен -vn (только аудио) — раньше ffmpeg перекодировал и 4K-видео,
здесь этого делать не нужно.

Классификация «речь / атмосфера»:
  1) есть сегменты в расшифровке (файлы --transcripts);
  2) иначе — энергетика: окна 25 мс, пол = 10-й перцентиль RMS, речь = +9 дБ
     над полом, участки >= 0,5 с.
Речь -> нормализация к -16 LUFS (потолок true peak -1,5 dBTP);
атмосфера -> уровень не трогаем (иначе поднимем шум).

    python process_audio_new.py --inventory inventory.json --clips "<клип1>,<клип2>"
                                [--out <корень проекта>] [--models <папка с моделями>]
                                [--transcripts <transcripts/*.json>]

Пишет: <out>/audio/proc/<клип>.wav, <out>/audio/proc_mux/<клип>.MP4,
       <out>/audio/proc_report_new.json, <out>/audio/proc_summary_new.txt
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import env_paths  # noqa: E402

RNN = "std.rnnn"
TARGET_I = -16.0
TARGET_TP = -1.5
MAX_GAIN = 12.0
LIMIT = 0.841

FF = env_paths.ffmpeg() or "ffmpeg"


def ebur128(path):
    p = subprocess.run([FF, "-nostats", "-v", "info", "-i", path, "-af",
                        "ebur128=peak=true", "-f", "null", "-"],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=3600)
    txt = p.stdout.decode("utf-8", "replace")
    out = {"I": None, "TP": None, "LRA": None}
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


def has_speech_energy(path):
    """Есть ли речь по энергетике: окна 25 мс, пол = 10-й перцентиль, речь = +9 дБ."""
    p = subprocess.run([FF, "-v", "error", "-i", path, "-ac", "1", "-ar", "16000",
                        "-f", "s16le", "-"], stdout=subprocess.PIPE, check=True)
    a = np.frombuffer(p.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    if a.size == 0:
        return False, 0.0
    w = 400  # 25 мс при 16 кГц
    n = a.size // w
    if n < 4:
        return False, 0.0
    rms = np.sqrt((a[:n * w].reshape(n, w) ** 2).mean(axis=1) + 1e-12)
    floor = np.percentile(rms, 10)
    thr = floor * 10 ** (9.0 / 20.0)
    hit = rms >= thr
    # непрерывные участки >= 0,5 с (20 окон)
    best = cur = 0
    for h in hit:
        cur = cur + 1 if h else 0
        best = max(best, cur)
    return best >= 20, float((rms[hit].mean() if hit.any() else 0.0) -
                             (floor if floor > 0 else 1e-9))


def load_transcripts(paths):
    out = {}
    for path in paths:
        if not os.path.exists(path):
            continue
        for k, v in json.load(open(path, encoding="utf-8")).items():
            out[k] = v.get("segments", [])
    return out


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="process_audio_new.py",
        description="обработка звука для выбранных клипов")
    p.add_argument("--inventory", default="", help="inventory.json (список клипов)")
    p.add_argument("--clips", required=True,
                   help="список клипов через запятую (без расширения)")
    p.add_argument("--out", default="", help="корень проекта для результатов")
    p.add_argument("--models", default="", help="папка с моделью RNNoise (std.rnnn)")
    p.add_argument("--transcripts", default="",
                   help="файлы расшифровок (*.json) или папка с ними")
    a = p.parse_args(argv)

    project = env_paths.project_root()
    root = os.path.abspath(a.out) if a.out else str(project)
    inv_path = os.path.abspath(a.inventory) if a.inventory else os.path.join(root, "inventory.json")
    models = os.path.abspath(a.models) if a.models else os.path.join(root, "audio", "models")
    out_wav = os.path.join(root, "audio", "proc")
    out_mux = os.path.join(root, "audio", "proc_mux")
    tmp_dir = os.path.join(root, "audio", "_tmp")

    if not os.path.exists(inv_path):
        p.error("нет инвентаризации: %s" % inv_path)
    if not os.path.isdir(models):
        p.error("нет папки с моделями RNNoise: %s (укажи --models)" % models)

    if a.transcripts:
        tr_paths = []
        for part in a.transcripts.split(","):
            part = part.strip()
            if not part:
                continue
            if os.path.isdir(part):
                tr_paths.extend(sorted(glob.glob(os.path.join(part, "*.json"))))
            else:
                tr_paths.append(part)
    else:
        tr_paths = sorted(glob.glob(os.path.join(root, "transcripts", "*.json")))

    new_names = [x.strip() for x in a.clips.split(",") if x.strip()]
    if not new_names:
        p.error("--clips пуст")

    with open(inv_path, encoding="utf-8") as f:
        inv = json.load(f)
    by_name = {os.path.splitext(c["file"])[0]: c for c in inv["clips"]}
    tr = load_transcripts(tr_paths)
    os.makedirs(out_wav, exist_ok=True)
    os.makedirs(out_mux, exist_ok=True)
    os.makedirs(tmp_dir, exist_ok=True)

    report = {}
    lines = []
    for idx, name in enumerate(new_names, 1):
        c = by_name.get(name)
        if not c:
            print("[%d/%d] %s НЕТ В ИНВЕНТАРИЗАЦИИ" % (idx, len(new_names), name), flush=True)
            continue
        src = c["path"]
        tmp = os.path.join(tmp_dir, name + "_den.wav")
        wav = os.path.join(out_wav, name + ".wav")

        # -map 0:a:0 -ac 1: у части клипов ДВЕ аудиодорожки (aac + apple_apac 4ch),
        # RNNoise требует моно — без явного выбора денойз падает.
        r = subprocess.run([FF, "-v", "error", "-y", "-i", src, "-map", "0:a:0",
                            "-ac", "1", "-af",
                            "highpass=f=80,arnndn=m=%s" % RNN, "-c:a", "pcm_s24le", tmp],
                           cwd=models, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if r.returncode != 0 or not os.path.exists(tmp):
            print("[%d/%d] %s DENOISE FAILED" % (idx, len(new_names), name), flush=True)
            report[name] = {"error": "denoise failed"}
            continue
        d = ebur128(tmp)

        segs = tr.get(name) or []
        speech_by_asr = bool(segs)
        speech_by_energy, snr = has_speech_energy(tmp)
        # Нормализуем ТОЛЬКО то, что распознано как речь. Энергия без ASR —
        # это шум: поднимать его на +12 дБ нельзя.
        is_speech = speech_by_asr
        if speech_by_asr:
            stype = "ДИАЛОГ"
        elif speech_by_energy:
            stype = "ЭНЕРГИЯ(без ASR)"
        else:
            stype = "НЕТ РЕЧИ"

        gain = 0.0
        capped = False
        if is_speech and d["I"] is not None:
            gain = TARGET_I - d["I"]
            if d["TP"] is not None:
                gain = min(gain, TARGET_TP - d["TP"])
            gain = max(gain, -40.0)
            if gain > MAX_GAIN:
                gain = MAX_GAIN
                capped = True
        af = "volume=%+.2fdB,alimiter=limit=%.4f:level=disabled" % (gain, LIMIT)
        r = subprocess.run([FF, "-v", "error", "-y", "-i", tmp, "-af", af,
                            "-c:a", "pcm_s24le", wav],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if r.returncode != 0:
            print("[%d/%d] %s GAIN FAILED" % (idx, len(new_names), name), flush=True)
            report[name] = {"error": "gain failed"}
            continue
        fin = ebur128(wav)

        mux = os.path.join(out_mux, name + ".MP4")
        r = subprocess.run([FF, "-v", "error", "-y", "-i", src, "-i", wav,
                            "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
                            "-c:a", "pcm_s16be", mux],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        mux_ok = (r.returncode == 0 and os.path.exists(mux))

        report[name] = {
            "stype": stype, "speech": is_speech, "speech_by_asr": speech_by_asr,
            "speech_by_energy": speech_by_energy, "snr_db": round(snr, 1),
            "duration_s": c.get("duration_s"), "fps": c.get("fps"),
            "orig": ebur128(src), "denoised": d, "gain_db": round(gain, 2),
            "gain_capped": capped, "final": fin, "wav": wav,
            "mux": mux if mux_ok else None,
            "asr_text": " ".join(s["text"] for s in segs)[:400],
        }
        print("[%d/%d] %-10s %-14s gain=%+6.2f  I: %s -> %s -> %s  TP %s -> %s  mux=%s"
              % (idx, len(new_names), name, stype, gain, report[name]["orig"]["I"],
                 d["I"], fin["I"], report[name]["orig"]["TP"], fin["TP"],
                 "ok" if mux_ok else "FAIL"), flush=True)
        lines.append("%-10s %-14s dur=%6.1f  I: %7s -> %7s -> %7s  TP: %6s -> %6s  gain=%+6.2f%s"
                     % (name, stype, c.get("duration_s") or 0,
                        report[name]["orig"]["I"], d["I"], fin["I"],
                        report[name]["orig"]["TP"], fin["TP"], gain,
                        " (cap)" if capped else ""))
        try:
            os.remove(tmp)
        except OSError:
            pass

    with open(os.path.join(root, "audio", "proc_report_new.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    with open(os.path.join(root, "audio", "proc_summary_new.txt"), "w", encoding="utf-8") as f:
        f.write("=== ВЫБРАННЫЕ КЛИПЫ: обработка звука ===\n")
        f.write("=== цепочка: highpass 80 -> RNNoise(std) -> volume -> alimiter(-1.5 dBFS) ===\n")
        f.write("=== речь -> -16 LUFS; атмосфера -> уровень не трогаем ===\n\n")
        f.write("\n".join(lines))
    print("DONE", len(report))


if __name__ == "__main__":
    sys.exit(main())
