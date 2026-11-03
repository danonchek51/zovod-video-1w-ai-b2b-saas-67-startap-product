# -*- coding: utf-8 -*-
"""extract_clip_frames.py — извлечение опорных кадров (960x540) для расчёта
посцензорного баланса.

По каждому клипу снимаются три кадра: 18 %, 50 % и 82 % длительности.

    python extract_clip_frames.py --src <папка с исходниками> [--out <корень проекта>]
                                  [--frames-dir <папка кадров>] [--jobs 4]

Исходники открываются ТОЛЬКО НА ЧТЕНИЕ.
"""
import argparse
import concurrent.futures as cf
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import env_paths  # noqa: E402

FFMPEG = env_paths.ffmpeg() or "ffmpeg"
FFPROBE = env_paths.ffprobe() or "ffprobe"
FR = ""
FRACTIONS = (0.18, 0.5, 0.82)


def source_files(src_root):
    """Все видео под src_root (рекурсивно), по имени файла."""
    files = []
    for root, dirs, names in os.walk(src_root):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fn in sorted(names):
            if os.path.splitext(fn)[1].lower() == ".mp4":
                files.append(os.path.join(root, fn))
    files.sort(key=lambda p: os.path.basename(p))
    return files


def duration(path):
    out = subprocess.run([FFPROBE, '-v', 'error', '-show_entries', 'format=duration',
                          '-of', 'default=nk=1:nw=1', path],
                         capture_output=True, text=True, check=True).stdout.strip()
    return float(out)


def grab(path, sec, out):
    if os.path.exists(out) and os.path.getsize(out) > 1000:
        return out
    cmd = [FFMPEG, '-hide_banner', '-loglevel', 'error', '-i', path, '-ss', str(sec),
           '-frames:v', '1', '-vf', 'scale=960:540', '-update', '1', '-y', out]
    subprocess.run(cmd, check=True)
    return out


def one(path):
    name = os.path.splitext(os.path.basename(path))[0]
    dur = duration(path)
    marks = []
    for frac in FRACTIONS:
        sec = round(dur * frac, 2)
        out = os.path.join(FR, '%s_%02d.png' % (name, int(frac * 100)))
        try:
            grab(path, sec, out)
            marks.append({'sec': sec, 'file': out})
        except Exception as exc:
            marks.append({'sec': sec, 'error': str(exc)})
    return {'clip': name, 'duration': round(dur, 2), 'frames': marks}


def main(argv=None):
    global FR

    p = argparse.ArgumentParser(
        prog="extract_clip_frames.py",
        description="извлечение опорных кадров 960x540 из клипов")
    p.add_argument("--src", default="", help="папка с исходниками (только чтение)")
    p.add_argument("--out", default="", help="корень проекта для результатов")
    p.add_argument("--frames-dir", default="", help="папка для кадров")
    p.add_argument("--jobs", type=int, default=4, help="потоков извлечения")
    a = p.parse_args(argv)

    project = env_paths.project_root()
    root = os.path.abspath(a.out) if a.out else str(project)
    src = os.path.abspath(a.src) if a.src else str(env_paths.src_root() or "")
    if not src or not os.path.isdir(src):
        p.error("нет папки с исходниками (укажи --src)")
    FR = os.path.abspath(a.frames_dir) if a.frames_dir else os.path.join(root, "resolve_check", "frames")
    os.makedirs(FR, exist_ok=True)

    files = source_files(src)
    if not files:
        p.error("под %s нет .mp4" % src)
    results = []
    with cf.ThreadPoolExecutor(max_workers=max(1, a.jobs)) as ex:
        for r in ex.map(one, files):
            results.append(r)
            print(r['clip'], r['duration'], flush=True)

    out_json = os.path.join(root, "resolve_check", "clip_frames.json")
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    with open(out_json, 'w', encoding='utf-8') as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2)
    print('DONE', len(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
