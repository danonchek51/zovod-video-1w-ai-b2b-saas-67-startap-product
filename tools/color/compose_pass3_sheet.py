# -*- coding: utf-8 -*-
"""compose_pass3_sheet.py — контактный лист по кадрам одного захода.

    python compose_pass3_sheet.py --frames <папка с .jpg> [--out <файл .jpg>]
                                   [--cols 4] [--tile 480x270]
"""
import argparse
import os
import sys

from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def load_font(size):
    for cand in FONT_CANDIDATES:
        if os.path.exists(cand):
            try:
                return ImageFont.truetype(cand, size)
            except Exception:
                pass
    return ImageFont.load_default()


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="compose_pass3_sheet.py",
        description="контактный лист по кадрам захода")
    p.add_argument("--frames", required=True, help="папка с кадрами .jpg")
    p.add_argument("--out", default="", help="файл листа (по умолчанию <frames>/../pass3_sheet.jpg)")
    p.add_argument("--cols", type=int, default=4)
    p.add_argument("--tile", default="480x270")
    a = p.parse_args(argv)

    fr = os.path.abspath(a.frames)
    if not os.path.isdir(fr):
        p.error("нет папки с кадрами: %s" % fr)
    out = os.path.abspath(a.out) if a.out else os.path.join(
        os.path.dirname(fr), "pass3_sheet.jpg")
    cw, ch = (int(x) for x in a.tile.lower().split("x"))

    files = sorted(f for f in os.listdir(fr) if f.lower().endswith(".jpg"))
    if not files:
        p.error("в папке нет .jpg: %s" % fr)
    cols = max(1, a.cols)
    rows = (len(files) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cw, rows * (ch + 26)), (18, 18, 20))
    d = ImageDraw.Draw(sheet)
    font = load_font(18)
    for i, f in enumerate(files):
        im = Image.open(os.path.join(fr, f)).convert("RGB")
        im.thumbnail((cw, ch))
        x = (i % cols) * cw
        y = (i // cols) * (ch + 26)
        sheet.paste(im, (x + (cw - im.width) // 2, y))
        im.close()
        d.text((x + 8, y + ch + 3), os.path.splitext(f)[0], fill=(235, 235, 235), font=font)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    sheet.save(out, quality=92)
    print("written:", out, sheet.size)
    return 0


if __name__ == "__main__":
    sys.exit(main())
