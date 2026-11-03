# -*- coding: utf-8 -*-
"""compose_compare.py — сборка сравнительных листов: полный кадр, варианты друг
под другом + зум на лицо.

    python compose_compare.py --src <папка с вариантами> --dst <папка результата>
                              --moments moments.json --variants variants.json

moments.json: [{"id": "M1", "label": "подпись", "desc": "описание",
                "face": [x0, y0, x1, y1]}, ...]   # face — доли кадра
variants.json: [{"id": "V0_original", "label": "ИСХОДНИК (без грейда)"}, ...]
Файлы кадров: <src>/<moment_id>__<variant_id>.png
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


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="compose_compare.py",
        description="сравнительные листы: полный кадр + зум на лицо")
    p.add_argument("--src", required=True, help="папка с вариантами кадров")
    p.add_argument("--dst", required=True, help="папка для результата")
    p.add_argument("--moments", required=True, help="JSON со списком моментов")
    p.add_argument("--variants", required=True, help="JSON со списком вариантов")
    p.add_argument("--width", type=int, default=1600, help="ширина полнокадровой плитки")
    a = p.parse_args(argv)

    src = os.path.abspath(a.src)
    dst = os.path.abspath(a.dst)
    if not os.path.isdir(src):
        p.error("нет папки с вариантами: %s" % src)
    os.makedirs(dst, exist_ok=True)
    with open(a.moments, encoding="utf-8") as f:
        moments = json.load(f)
    with open(a.variants, encoding="utf-8") as f:
        variants = json.load(f)
    if not moments or not variants:
        p.error("пустые moments/variants")

    font = load_font(26)
    font_s = load_font(20)
    made = []

    # --- 1. полнокадровые листы ---
    W = a.width
    for m in moments:
        mid = m["id"]
        label = m.get("label", mid)
        desc = m.get("desc", "")
        panels = []
        for v in variants:
            path = os.path.join(src, '%s__%s.png' % (mid, v["id"]))
            if not os.path.exists(path):
                continue
            im = Image.open(path).convert('RGB')
            h = int(round(im.height * W / im.width))
            panels.append((v.get("label", v["id"]), im.resize((W, h), Image.LANCZOS)))
            im.close()
        if not panels:
            print("нет вариантов для", mid)
            continue
        ph = panels[0][1].height
        LBL = 34
        sheet = Image.new('RGB', (W, len(panels) * (ph + LBL) + 58), (14, 14, 16))
        d = ImageDraw.Draw(sheet)
        d.text((12, 12), '%s  |  %s' % (label, desc), fill=(245, 245, 245), font=font)
        for i, (vlabel, pan) in enumerate(panels):
            y = 58 + i * (ph + LBL)
            sheet.paste(pan, (0, y))
            d.rectangle([0, y + ph, W, y + ph + LBL], fill=(24, 24, 28))
            d.text((12, y + ph + 6), vlabel, fill=(240, 240, 240), font=font_s)
        out = os.path.join(dst, 'cmp_%s.jpg' % mid)
        sheet.save(out, quality=93, subsampling=0)
        made.append(out)
        print('saved', out, sheet.size)
        sheet.close()

    # --- 2. зум на лицо ---
    FW = 520
    rows = len(moments)
    cols = len(variants)
    face = Image.new('RGB', (cols * FW, rows * (int(FW * 1.2) + 30)), (14, 14, 16))
    df = ImageDraw.Draw(face)
    for r, m in enumerate(moments):
        mid = m["id"]
        label = m.get("label", mid)
        box = m.get("face") or [0, 0, 1, 1]
        x0, y0, x1, y1 = box
        for c, v in enumerate(variants):
            path = os.path.join(src, '%s__%s.png' % (mid, v["id"]))
            if not os.path.exists(path):
                continue
            im = Image.open(path).convert('RGB')
            W0, H0 = im.size
            crop = im.crop((int(x0 * W0), int(y0 * H0), int(x1 * W0), int(y1 * H0)))
            crop = crop.resize((FW, int(crop.height * FW / crop.width)), Image.LANCZOS)
            im.close()
            x = c * FW
            y = r * (int(FW * 1.2) + 30)
            face.paste(crop, (x, y))
            df.text((x + 6, y + crop.height + 4),
                    v.get("label", v["id"]).split(' - ')[0],
                    fill=(235, 235, 235), font=font_s)
        df.text((6, r * (int(FW * 1.2) + 30) - 24), label, fill=(250, 250, 250), font=font_s)
    out = os.path.join(dst, 'cmp_faces.jpg')
    face.save(out, quality=93, subsampling=0)
    made.append(out)
    print('saved', out, face.size)

    with open(os.path.join(dst, 'made.json'), 'w', encoding='utf-8') as fh:
        json.dump(made, fh, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
