#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""transcribe_chunks.py — допрогон распознавания по КУСКАМ (обход mkl_malloc).

Длинные клипы без VAD роняют faster-whisper с «mkl_malloc: failed to allocate
memory». Здесь аудио режется на куски по 15 с (перекрытие 2 с), каждый
распознаётся отдельно — памяти хватает. Сегменты собираются обратно со
смещением времени.

Фильтр сегментов: avg_logprob >= -1.0 и no_speech_prob <= 0.5 — иначе в
«речь» попадает шум.

    python transcribe_chunks.py --clips <CLIP1>,<CLIP2> --src <папка>
"""
import argparse
import json
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import env_paths  # noqa: E402

FF = env_paths.ffmpeg() or "ffmpeg"
OUT = ""
SR = 16000
CHUNK = 15.0
OVERLAP = 2.0

# Нейтральная подсказка по умолчанию; доменный словарь задавайте --prompt.
PROMPT_DEFAULT = "Русский разговор. Неформальная речь, шум улицы и помещения."


def decode_pcm(path):
    p = subprocess.run([FF, "-v", "error", "-i", path, "-ac", "1",
                        "-ar", str(SR), "-f", "s16le", "-"],
                       check=True, stdout=subprocess.PIPE)
    return np.frombuffer(p.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def find_file(src_dir, name):
    for ext in (".MP4", ".mp4", ".MOV", ".mov", ".MKV", ".mkv"):
        p = os.path.join(src_dir, name + ext)
        if os.path.exists(p):
            return p
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="transcribe_chunks.py",
        description="распознавание по кускам (обход ошибки выделения памяти)")
    ap.add_argument("--clips", required=True, help="список клипов через запятую")
    ap.add_argument("--src", default="", help="папка с исходниками (только чтение)")
    ap.add_argument("--out", default="", help="куда писать расшифровки")
    ap.add_argument("--tag", default="chunks")
    ap.add_argument("--model", default="small")
    ap.add_argument("--prompt", default=PROMPT_DEFAULT, help="подсказка Whisper")
    args = ap.parse_args(argv)

    global OUT
    project = env_paths.project_root()
    root = os.path.abspath(args.out) if args.out else str(project)
    OUT = os.path.join(root, "transcripts")
    src = os.path.abspath(args.src) if args.src else str(env_paths.src_root() or "")
    if not src or not os.path.isdir(src):
        ap.error("нет папки с исходниками (укажи --src)")

    from faster_whisper import WhisperModel
    model = WhisperModel(args.model, device="cpu", compute_type="int8",
                         cpu_threads=max(1, (os.cpu_count() or 4) - 2))
    print("model ready", flush=True)

    out = {}
    for name in [x.strip() for x in args.clips.split(",") if x.strip()]:
        path = find_file(src, name)
        if not path:
            print("нет файла:", name, flush=True)
            continue
        audio = decode_pcm(path)
        total = len(audio) / SR
        step = CHUNK - OVERLAP
        segs_all = []
        t = 0.0
        while t < total:
            seg = audio[int(t * SR):int(min(t + CHUNK, total) * SR)]
            if len(seg) < 400:
                break
            segs, _ = model.transcribe(seg, language="ru", beam_size=5,
                                       vad_filter=False,
                                       condition_on_previous_text=False,
                                       initial_prompt=args.prompt,
                                       no_speech_threshold=0.6,
                                       log_prob_threshold=-2.0)
            for s in segs:
                if s.avg_logprob is not None and s.avg_logprob < -1.0:
                    continue
                if s.no_speech_prob is not None and s.no_speech_prob > 0.5:
                    continue
                txt = s.text.strip()
                if not txt:
                    continue
                segs_all.append({"start": round(s.start + t, 2),
                                 "end": round(s.end + t, 2), "text": txt,
                                 "avg_logprob": round(float(s.avg_logprob or 0), 3),
                                 "no_speech_prob": round(float(s.no_speech_prob or 0), 3)})
            t += step
        out[name] = {"file": os.path.basename(path), "dur_s": round(total, 2),
                     "segments": segs_all}
        print("[%s] %d сегментов: %s" % (name, len(segs_all),
              " ".join(s["text"] for s in segs_all)[:200]), flush=True)

    os.makedirs(OUT, exist_ok=True)
    path_out = os.path.join(OUT, "transcripts_%s.json" % args.tag)
    with open(path_out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("saved:", path_out)


if __name__ == "__main__":
    sys.exit(main())
