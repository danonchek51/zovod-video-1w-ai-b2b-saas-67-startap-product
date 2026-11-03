# -*- coding: utf-8 -*-
"""compose_main_sheet.py — контактный лист по основному материалу.

Каждый кадр-миниатюра подписан именем клипа и (если есть) началом речи.

    python compose_main_sheet.py --thumbs <папка с миниатюрами .jpg>
                                 [--out <файл .jpg>] [--transcripts <json>]
                                 [--cols 7] [--tile 300x200]
"""
import argparse
import json
import os
import sys

from PIL import Image, ImageDraw

COLS_DEFAULT, TW_DEFAULT, TH_DEFAULT = 7, 300, 200
PAD, HDR = 6, 34


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="compose_main_sheet.py",
        description="контактный лист по миниатюрам с подписями")
    p.add_argument("--thumbs", required=True, help="папка с миниатюрами .jpg")
    p.add_argument("--out", default="", help="файл листа (по умолчанию <thumbs>/../contact_main.jpg)")
    p.add_argument("--transcripts", default="", help="JSON с расшифровками (клип -> сегменты)")
    p.add_argument("--cols", type=int, default=COLS_DEFAULT)
    p.add_argument("--tile", default="%dx%d" % (TW_DEFAULT, TH_DEFAULT),
                   help="размер плитки, например 300x200")
    a = p.parse_args(argv)

    thumbs = os.path.abspath(a.thumbs)
    if not os.path.isdir(thumbs):
        p.error("нет папки с миниатюрами: %s" % thumbs)
    tw, th = (int(x) for x in a.tile.lower().split("x"))
    out = os.path.abspath(a.out) if a.out else os.path.join(
        os.path.dirname(thumbs), "contact_main.jpg")

    trans = {}
    if a.transcripts and os.path.exists(a.transcripts):
        try:
            trans = json.load(open(a.transcripts, encoding="utf-8"))
        except Exception:
            trans = {}

    names = sorted(f[:-4] for f in os.listdir(thumbs) if f.endswith(".jpg"))
    if not names:
        p.error("в папке нет .jpg: %s" % thumbs)
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
        p_ = os.path.join(thumbs, n + ".jpg")
        if os.path.exists(p_):
            im = Image.open(p_).convert("RGB")
            im.thumbnail((tw, th))
            sheet.paste(im, (x + (tw - im.width) // 2, y + (th - im.height) // 2))
            im.close()
        txt = ""
        rec = trans.get(n)
        if isinstance(rec, dict):
            segs = rec.get("segments") or []
            txt = " ".join((s.get("text") if isinstance(s, dict) else str(s)) for s in segs)
        txt = txt[:58]
        d.rectangle([x, y + th, x + tw, y + th + HDR], fill=(40, 40, 46))
        d.text((x + 3, y + th + 2), n, fill=(240, 240, 240))
        d.text((x + 3, y + th + 15), txt, fill=(190, 190, 195))

    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    sheet.save(out, quality=88)
    print("saved", out, sheet.size, "clips", len(names))
    return 0


if __name__ == "__main__":
    sys.exit(main())
