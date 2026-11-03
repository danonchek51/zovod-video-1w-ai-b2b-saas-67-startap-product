# -*- coding: utf-8 -*-
"""compose_pass4_sheet.py — контактный лист по новым клипам.

Каждый кадр подписан именем клипа и началом речи из расшифровки.

    python compose_pass4_sheet.py --frames <папка с .jpg> --json <расшифровки.json>
                                  [--out <файл .jpg>] [--cols 7] [--tile 300x200]
"""
import argparse
import json
import os
import sys

from PIL import Image, ImageDraw

COLS_DEFAULT, TW_DEFAULT, TH_DEFAULT = 7, 300, 200
PAD, HDR = 6, 22


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="compose_pass4_sheet.py",
        description="контактный лист по клипам с подписями речи")
    p.add_argument("--frames", required=True, help="папка с кадрами .jpg")
    p.add_argument("--json", required=True, help="JSON с расшифровками (клип -> сегменты)")
    p.add_argument("--out", default="", help="файл листа (по умолчанию <frames>/../contact_pass4.jpg)")
    p.add_argument("--cols", type=int, default=COLS_DEFAULT)
    p.add_argument("--tile", default="%dx%d" % (TW_DEFAULT, TH_DEFAULT))
    a = p.parse_args(argv)

    fr = os.path.abspath(a.frames)
    if not os.path.isdir(fr):
        p.error("нет папки с кадрами: %s" % fr)
    if not os.path.exists(a.json):
        p.error("нет файла расшифровок: %s" % a.json)
    out = os.path.abspath(a.out) if a.out else os.path.join(
        os.path.dirname(fr), "contact_pass4.jpg")
    tw, th = (int(x) for x in a.tile.lower().split("x"))

    with open(a.json, encoding="utf-8") as f:
        tr = json.load(f)
    names = sorted(tr.keys())
    if not names:
        p.error("в расшифровках нет клипов: %s" % a.json)
    cols = max(1, a.cols)
    rows = (len(names) + cols - 1) // cols
    W = cols * (tw + PAD) + PAD
    H = rows * (th + HDR + PAD) + PAD
    sheet = Image.new("RGB", (W, H), (18, 18, 20))
    d = ImageDraw.Draw(sheet)

    for i, n in enumerate(names):
        r, c = divmod(i, cols)
        x = PAD + c * (tw + PAD)
        y = PAD + r * (th + HDR + PAD)
        p_ = os.path.join(fr, n + ".jpg")
        if os.path.exists(p_):
            im = Image.open(p_).convert("RGB")
            im.thumbnail((tw, th))
            sheet.paste(im, (x + (tw - im.width) // 2, y + (th - im.height) // 2))
            im.close()
        segs = tr[n].get("segments") or []
        txt = " ".join(s["text"] for s in segs)[:46]
        d.rectangle([x, y + th, x + tw, y + th + HDR], fill=(40, 40, 46))
        d.text((x + 3, y + th + 2), "%s  %s" % (n, txt[:42]), fill=(235, 235, 235))

    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    sheet.save(out, quality=88)
    print("saved", out, sheet.size, "clips", len(names))
    return 0


if __name__ == "__main__":
    sys.exit(main())
