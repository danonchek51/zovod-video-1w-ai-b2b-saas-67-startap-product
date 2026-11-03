# -*- coding: utf-8 -*-
"""compose_v2.py — финальные листы сравнения: оригинал + варианты стилей
(полный кадр) и зум на лицо.

    python compose_v2.py --old <папка с оригиналами> --new <папка с грейдами>
                         --dst <папка результата> --moments moments.json
                         --variants variants.json

moments.json: [{"id": "M1", "label": "подпись", "desc": "описание",
                "face": [x0, y0, x1, y1]}, ...]
variants.json: [{"id": "original", "label": "ИСХОДНИК", "folder": "old"|"new",
                 "pattern": "<moment>__<variant>.png"}, ...]
По умолчанию pattern = "<moment_id>__<variant_id>.png".
"""
import argparse
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

Image.MAX_IMAGE_PIXELS = None

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


def variant_path(folders, v, mid):
    """Путь к кадру варианта: явный pattern -> <moment>__<variant>.png."""
    pat = v.get("pattern")
    if pat:
        name = pat.replace("{moment}", mid).replace("{variant}", v["id"])
    else:
        name = "%s__%s.png" % (mid, v["id"])
    folder = folders.get(v.get("folder", "new"), folders.get("new", ""))
    return os.path.join(folder, name)


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="compose_v2.py",
        description="финальные листы сравнения: оригинал + стили + зум на лицо")
    p.add_argument("--old", required=True, help="папка с оригинальными кадрами")
    p.add_argument("--new", required=True, help="папка с грейдами")
    p.add_argument("--dst", required=True, help="папка для результата")
    p.add_argument("--moments", required=True, help="JSON со списком моментов")
    p.add_argument("--variants", required=True, help="JSON со списком вариантов")
    p.add_argument("--width", type=int, default=1500)
    a = p.parse_args(argv)

    folders = {"old": os.path.abspath(a.old), "new": os.path.abspath(a.new)}
    dst = os.path.abspath(a.dst)
    os.makedirs(dst, exist_ok=True)
    with open(a.moments, encoding="utf-8") as f:
        moments = json.load(f)
    with open(a.variants, encoding="utf-8") as f:
        variants = json.load(f)
    if not moments or not variants:
        p.error("пустые moments/variants")

    font = load_font(26)
    font_s = load_font(20)
    W = a.width
    H = int(W * 2160 / 3840)
    LBL = 32

    for m in moments:
        mid = m["id"]
        label = m.get("label", mid)
        desc = m.get("desc", "")
        panels = []
        for v in variants:
            path = variant_path(folders, v, mid)
            if not os.path.exists(path):
                continue
            im = Image.open(path).convert('RGB').resize((W, H), Image.LANCZOS)
            panels.append((v.get("label", v["id"]), im))
        if not panels:
            print("нет вариантов для", mid)
            continue
        sheet = Image.new('RGB', (W, len(panels) * (H + LBL) + 56), (14, 14, 16))
        d = ImageDraw.Draw(sheet)
        d.text((12, 12), '%s  |  %s' % (label, desc), fill=(245, 245, 245), font=font)
        for i, (vlabel, pan) in enumerate(panels):
            y = 56 + i * (H + LBL)
            sheet.paste(pan, (0, y))
            d.rectangle([0, y + H, W, y + H + LBL], fill=(24, 24, 28))
            d.text((12, y + H + 5), vlabel, fill=(240, 240, 240), font=font_s)
        out = os.path.join(dst, 'cmp_%s.jpg' % mid)
        sheet.save(out, quality=92, subsampling=0)
        sheet.close()
        print('saved', out)

    # ---- зум на лицо: строки = моменты, колонки = варианты
    FW, FH = 520, 520
    sheet = Image.new('RGB', (len(variants) * FW, len(moments) * (FH + 30)), (14, 14, 16))
    d = ImageDraw.Draw(sheet)
    for r, m in enumerate(moments):
        mid = m["id"]
        label = m.get("label", mid)
        box = m.get("face") or [0, 0, 1, 1]
        x0, y0, x1, y1 = box
        for c, v in enumerate(variants):
            path = variant_path(folders, v, mid)
            if not os.path.exists(path):
                continue
            im = Image.open(path).convert('RGB')
            W0, H0 = im.size
            crop = im.crop((int(x0 * W0), int(y0 * H0), int(x1 * W0), int(y1 * H0))).resize((FW, FH), Image.LANCZOS)
            im.close()
            x = c * FW
            y = r * (FH + 30)
            sheet.paste(crop, (x, y))
            d.rectangle([x, y + FH, x + FW, y + FH + 30], fill=(22, 22, 26))
            d.text((x + 6, y + FH + 4), v.get("label", v["id"]).split(':')[0],
                   fill=(238, 238, 238), font=font_s)
        d.text((6, r * (FH + 30) - 26), label, fill=(250, 250, 250), font=font_s)
    out = os.path.join(dst, 'cmp_faces.jpg')
    sheet.save(out, quality=93, subsampling=0)
    print('saved', out, sheet.size)
    return 0


if __name__ == "__main__":
    sys.exit(main())
