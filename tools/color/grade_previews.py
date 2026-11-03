# -*- coding: utf-8 -*-
"""grade_previews.py — варианты грейда на реальных кадрах исходника.

Строит сравнительный лист: опорные кадры (строки) × варианты обработки
(колонки). Варианты намеренно «чистые»: без блума, без вуали, без виньетки.

Исходники только читаются, результат пишется в <out>/grade_preview.

    python grade_previews.py --src <папка с исходниками> --out <корень проекта>
                             --frames "САЛОН|C0131.MP4|4.0,ДПС|C0138.MP4|7.0"
                             [--font <шрифт для подписей>]

Формат --frames: подпись|путь_к_клипу_относительно_src|секунда, через запятую.
"""
import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import env_paths  # noqa: E402

FF = env_paths.ffmpeg() or "ffmpeg"

# цепочки ffmpeg: без блума/виньетки/зерна-крупняка — только цвет и контраст
GRADES = [
    ("ORIG", None),
    ("A ОФИЦИАЛЬНЫЙ", (
        "eq=brightness=0.004:contrast=1.06:saturation=1.05:gamma=1.0,"
        "colorbalance=rs=0.012:bs=-0.012:rm=0.012:bm=-0.008:rh=0.010:bh=-0.010"
    )),
    ("B ТЁПЛЫЙ", (
        "eq=brightness=0.0:contrast=1.09:saturation=1.13:gamma=1.02,"
        "colorbalance=rs=0.022:bs=-0.022:rm=0.026:bm=-0.014:rh=0.020:bh=-0.020,"
        "noise=alls=3:allf=t"
    )),
    ("C ПЛОТНЫЙ", (
        "eq=brightness=-0.004:contrast=1.17:saturation=1.17:gamma=0.98,"
        "colorbalance=rs=0.006:bs=-0.032:rm=0.012:bm=-0.022:rh=0.010:bh=-0.028"
    )),
    ("D СТАЛЬНОЙ", (
        "eq=brightness=0.0:contrast=1.13:saturation=0.97:gamma=0.99,"
        "colorbalance=rs=-0.008:bs=0.024:rm=-0.006:bm=0.016:rh=-0.006:bh=0.016"
    )),
]

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\arialbd.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def find_font(explicit=""):
    """Шрифт для подписей: явный путь -> типовые системные -> None."""
    if explicit:
        return explicit if os.path.exists(explicit) else None
    for cand in FONT_CANDIDATES:
        if os.path.exists(cand):
            return cand
    return None


def run(args):
    subprocess.run(args, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def extract(path, t, dst):
    # -ss ПОСЛЕ -i: точный seek, иначе edit list сбивает выдачу кадра
    run([FF, "-v", "error", "-i", path, "-ss", str(t), "-frames:v", "1",
         "-update", "1", "-y", dst])


def apply_grade(src, dst, chain):
    vf = chain or "null"
    run([FF, "-v", "error", "-i", src, "-vf", vf + ",format=rgb24",
         "-update", "1", "-y", dst])


def label(src, dst, text, font_esc):
    # лейбл рисуется ПОСЛЕ масштабирования, иначе на плитке 470px он нечитаем
    if font_esc:
        vf = ("scale=470:-2,drawtext=fontfile='%s':text='%s':fontcolor=white:fontsize=26:"
              "box=1:boxcolor=black@0.85:boxborderw=6:x=10:y=10" % (font_esc, text))
    else:
        vf = "scale=470:-2"
    run([FF, "-v", "error", "-i", src, "-vf", vf + ",format=rgb24",
         "-update", "1", "-y", dst])


def parse_frames(spec, src_root):
    """'LABEL|file.mp4|t' -> [(LABEL, полный_путь, t)]"""
    out = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        bits = part.split("|")
        if len(bits) < 3:
            raise ValueError("неверный кадр: %s (ожидается подпись|файл|секунда)" % part)
        label_, rel, t = bits[0].strip(), bits[1].strip(), float(bits[2])
        path = rel if os.path.isabs(rel) else os.path.join(src_root, rel)
        out.append((label_, path, t))
    return out


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="grade_previews.py",
        description="варианты грейда на реальных кадрах исходника")
    p.add_argument("--src", default="", help="папка с исходниками (только чтение)")
    p.add_argument("--out", default="", help="корень проекта для результатов")
    p.add_argument("--frames", required=True,
                   help="кадры: подпись|файл|секунда, через запятую")
    p.add_argument("--font", default="", help="шрифт для подписей (ttf)")
    a = p.parse_args(argv)

    project = env_paths.project_root()
    root = os.path.abspath(a.out) if a.out else str(project)
    src = os.path.abspath(a.src) if a.src else str(env_paths.src_root() or "")
    if not src or not os.path.isdir(src):
        p.error("нет папки с исходниками (укажи --src)")

    base = os.path.join(root, "grade_preview")
    os.makedirs(base, exist_ok=True)
    raw = os.path.join(base, "raw")
    os.makedirs(raw, exist_ok=True)

    font = find_font(a.font)
    font_esc = font.replace("\\", "/").replace(":", r"\:") if font else ""
    if not font:
        print("шрифт для подписей не найден — подписи не рисуются")

    frames = parse_frames(a.frames, src)

    # 1) кадры-исходники
    src_frames = []
    for name, path, t in frames:
        if not os.path.exists(path):
            print("нет файла:", path)
            continue
        stem = os.path.splitext(os.path.basename(path))[0]
        dst = os.path.join(raw, stem + ".png")
        extract(path, t, dst)          # всегда заново: кадры могли смениться
        src_frames.append((name, dst))
    if not src_frames:
        p.error("ни один кадр не найден")

    # 2) варианты обработки -> плитки с подписью
    tiles = []
    for gname, chain in GRADES:
        gdir = os.path.join(base, "g_" + gname.split()[0].lower())
        os.makedirs(gdir, exist_ok=True)
        for name, src_png in src_frames:
            stem = os.path.splitext(os.path.basename(src_png))[0]
            graded = os.path.join(gdir, stem + ".png")
            if not os.path.exists(graded):
                apply_grade(src_png, graded, chain)
            tile = os.path.join(gdir, stem + "_lbl.png")
            label(graded, tile, gname, font_esc)
            tiles.append(tile)

    # 3) сетка: колонки = кадры, строки = варианты
    lst = os.path.join(base, "tiles.txt")
    with open(lst, "w", encoding="utf-8", newline="\n") as f:
        for t in tiles:
            f.write("file '%s'\n" % t.replace("\\", "/"))

    cols = max(1, len(src_frames))
    out = os.path.join(base, "grade_preview.jpg")
    run([FF, "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst,
         "-vf", "tile=%dx%d:padding=6:margin=6:color=#141414" % (cols, len(GRADES)),
         "-frames:v", "1", "-update", "1", out])
    print("OK", out, os.path.getsize(out))

    # 4) крупные стил-кадры для проверки тонов кожи и официального тона
    stems = [os.path.splitext(os.path.basename(s))[0] for _, s in src_frames]
    for gname, chain in GRADES:
        key = gname.split()[0].lower()
        for idx, stem in enumerate(stems):
            src_png = os.path.join(raw, stem + ".png")
            if not os.path.exists(src_png):
                continue
            dst = os.path.join(base, "big_%s_%d.png" % (key, idx))
            vf = (chain or "null") + ",scale=1500:-2,format=rgb24"
            run([FF, "-v", "error", "-i", src_png, "-vf", vf, "-update", "1", "-y", dst])
    print("OK big stills")
    return 0


if __name__ == "__main__":
    sys.exit(main())
