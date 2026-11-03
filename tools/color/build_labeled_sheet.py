# -*- coding: utf-8 -*-
"""build_labeled_sheet.py — контактный лист с подписями (имя клипа) для разбора сюжета.

Каждый кадр подписывается именем клипа, затем кадры склеиваются в сетку.

    python build_labeled_sheet.py --thumbs <папка с .jpg> [--out <файл .jpg>]
                                  [--font <шрифт>] [--tile 340:-1] [--cols 6] [--rows 7]
"""
import argparse
import glob
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import env_paths  # noqa: E402

FF = env_paths.ffmpeg() or "ffmpeg"

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\arialbd.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def find_font(explicit=""):
    if explicit:
        return explicit if os.path.exists(explicit) else None
    for cand in FONT_CANDIDATES:
        if os.path.exists(cand):
            return cand
    return None


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="build_labeled_sheet.py",
        description="контактный лист с подписями (имя клипа)")
    p.add_argument("--thumbs", required=True, help="папка с кадрами .jpg")
    p.add_argument("--out", default="", help="файл листа (по умолчанию <thumbs>/../contact_labeled.jpg)")
    p.add_argument("--font", default="", help="шрифт для подписей (ttf)")
    p.add_argument("--tile", default="340:-1", help="размер плитки, например 340:-1")
    p.add_argument("--cols", type=int, default=6)
    p.add_argument("--rows", type=int, default=7)
    a = p.parse_args(argv)

    th = os.path.abspath(a.thumbs)
    if not os.path.isdir(th):
        p.error("нет папки с кадрами: %s" % th)
    out = os.path.abspath(a.out) if a.out else os.path.join(
        os.path.dirname(th), "contact_labeled.jpg")

    files = sorted(glob.glob(os.path.join(th, "*.jpg")))
    if not files:
        p.error("в папке нет .jpg: %s" % th)

    font = find_font(a.font)
    if not font:
        print("шрифт для подписей не найден — подписи не рисуются")

    # подписываем каждый кадр именем клипа, затем склеиваем в сетку
    lab_dir = os.path.join(th, "labeled")
    os.makedirs(lab_dir, exist_ok=True)
    for p_ in files:
        name = os.path.splitext(os.path.basename(p_))[0]
        dst = os.path.join(lab_dir, name + ".jpg")
        if font:
            # в filter-строке ffmpeg двоеточие пути экранируется как '\:'
            fnt = font.replace("\\", "/").replace(":", r"\:")
            vf = ("drawtext=fontfile='%s':text='%s':fontcolor=yellow:fontsize=34:"
                  "box=1:boxcolor=black@0.75:boxborderw=8:x=12:y=12" % (fnt, name))
        else:
            vf = "null"
        subprocess.run([FF, "-v", "error", "-y", "-i", p_, "-vf", vf, "-frames:v", "1", dst],
                       check=True)

    lab = sorted(glob.glob(os.path.join(lab_dir, "*.jpg")))
    lst = os.path.join(lab_dir, "tiles.txt")
    with open(lst, "w", encoding="utf-8", newline="\n") as f:
        for p_ in lab:
            f.write("file '%s'\n" % p_.replace("\\", "/"))

    subprocess.run([FF, "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst,
                    "-vf", "scale=%s,tile=%dx%d:padding=4:margin=4:color=black"
                           % (a.tile, a.cols, a.rows), "-frames:v", "1", out], check=True)
    print("ok", len(lab), out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
