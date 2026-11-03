# -*- coding: utf-8 -*-
"""transcribe.py — локальная транскрипция всех клипов через faster-whisper.

Зачем: исходники не смонтированы, дубы длинные и с шумом — по одной картине
не понять, что происходит в сцене. Текст даёт сюжет: кто говорит, о чём,
где смешно.

Модель грузится локально (ctranslate2 + faster-whisper уже установлены),
интернет нужен один раз — для скачивания весов.

    python transcribe.py --src <папка с исходниками> [--out <корень проекта>]
                         [--model small|medium] [--clips <CLIP1>,<CLIP2>...]
                         [--beam 5] [--prompt "<подсказка Whisper>"]

Результат: <out>/transcripts/<clip>.json, <out>/transcripts/<clip>.txt
и сводный <out>/TRANSCRIPTS.md.
"""
import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import env_paths  # noqa: E402

FF = env_paths.ffmpeg() or "ffmpeg"

# Нейтральная подсказка по умолчанию; для доменных словарей задавайте --prompt.
PROMPT_DEFAULT = "Русский разговор. Неформальная речь, шум улицы и помещения."


def clips(src_root):
    """Все видеофайлы под src_root (рекурсивно), по имени файла без расширения."""
    out = []
    for root, dirs, files in os.walk(src_root):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fn in sorted(files):
            if fn.lower().endswith((".mp4", ".mov", ".mkv")):
                out.append((os.path.splitext(fn)[0], os.path.join(root, fn)))
    return out


def ensure_audio(name, path, aud_dir):
    dst = os.path.join(aud_dir, name + ".mp3")
    if os.path.exists(dst) and os.path.getsize(dst) > 1000:
        return dst
    os.makedirs(aud_dir, exist_ok=True)
    subprocess.run([FF, "-v", "error", "-i", path, "-vn", "-ac", "1",
                    "-ar", "16000", "-b:a", "48k", "-y", dst], check=True)
    return dst


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="transcribe.py",
        description="локальная транскрипция клипов через faster-whisper")
    ap.add_argument("--model", default="small")
    ap.add_argument("--clips", default="", help="список клипов через запятую (пусто — все)")
    ap.add_argument("--beam", type=int, default=5)
    ap.add_argument("--src", default="", help="папка с исходниками (только чтение)")
    ap.add_argument("--out", default="", help="корень проекта для результатов")
    ap.add_argument("--prompt", default=PROMPT_DEFAULT, help="подсказка Whisper")
    args = ap.parse_args(argv)

    project = env_paths.project_root()
    root = os.path.abspath(args.out) if args.out else str(project)
    src = os.path.abspath(args.src) if args.src else str(env_paths.src_root() or "")
    if not src or not os.path.isdir(src):
        ap.error("нет папки с исходниками (укажи --src)")

    aud = os.path.join(root, "audio")
    out_dir = os.path.join(root, "transcripts")
    os.makedirs(out_dir, exist_ok=True)

    from faster_whisper import WhisperModel

    print("loading model:", args.model, flush=True)
    model = WhisperModel(args.model, device="cpu", compute_type="int8",
                         cpu_threads=max(1, (os.cpu_count() or 4) - 1))
    print("model ready", flush=True)

    wanted = set(x.strip() for x in args.clips.split(",") if x.strip())
    results = {}
    md = ["# Транскрипция исходников",
          "",
          "Модель faster-whisper `%s`, язык ru, VAD-фильтр. Текст — дословный," % args.model,
          "с исходных дубов, без монтажа; таймкоды — внутри клипа.",
          ""]

    for name, path in clips(src):
        if wanted and name not in wanted:
            continue
        ap_path = ensure_audio(name, path, aud)
        segs, info = model.transcribe(ap_path, language="ru", vad_filter=True,
                                      beam_size=args.beam, initial_prompt=args.prompt,
                                      condition_on_previous_text=False)
        parts = []
        for s in segs:
            txt = s.text.strip()
            if txt:
                parts.append({"start": round(s.start, 2), "end": round(s.end, 2),
                              "text": txt})
        results[name] = {"duration": round(info.duration, 2), "segments": parts}
        with open(os.path.join(out_dir, name + ".json"), "w", encoding="utf-8") as f:
            json.dump(results[name], f, ensure_ascii=False, indent=2)
        with open(os.path.join(out_dir, name + ".txt"), "w", encoding="utf-8") as f:
            for p in parts:
                f.write("[%.1f-%.1f] %s\n" % (p["start"], p["end"], p["text"]))
        print("== %s (%.1fs) %d seg" % (name, info.duration, len(parts)), flush=True)
        for p in parts:
            print("   [%.1f-%.1f] %s" % (p["start"], p["end"], p["text"]), flush=True)

    md.append("## Клипы\n")
    for name, r in results.items():
        md.append("### %s (%.1f s)\n" % (name, r["duration"]))
        if not r["segments"]:
            md.append("_речи не распознано_\n")
        for p in r["segments"]:
            md.append("- `[%.1f–%.1f]` %s" % (p["start"], p["end"], p["text"]))
        md.append("")
    md_path = os.path.join(root, "TRANSCRIPTS.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print("DONE -> %s" % md_path, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
