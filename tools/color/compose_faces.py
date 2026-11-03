# -*- coding: utf-8 -*-
"""compose_faces.py — лист зума на лицо: область лица определяется автоматически
по тону кожи.

    python compose_faces.py --src <папка с вариантами> --dst <папка результата>
                            --moments moments.json --variants variants.json

moments.json: [{"id": "M1", "label": "подпись", "zone": [x0, x1]}, ...]
variants.json: [{"id": "V0_original", "label": "ИСХОДНИК"}, ...]
Файлы кадров: <src>/<moment_id>__<variant_id>.png
"""
import argparse
import json
import os
import sys

import numpy as np
import cv2
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


def skin_boxes(path, x_lo, x_hi):
    """Ищет самое высокое крупное пятно кожи в горизонтальной зоне -> bbox лица."""
    im = Image.open(path).convert('RGB')
    small = im.resize((960, 540), Image.LANCZOS)
    im.close()
    a = np.asarray(small, dtype=np.uint8)
    hsv = cv2.cvtColor(a, cv2.COLOR_RGB2HSV)
    h, s, v = hsv[..., 0].astype(int), hsv[..., 1].astype(int), hsv[..., 2].astype(int)
    mask = ((h >= 3) & (h <= 30) & (s >= 45) & (s <= 190) & (v >= 60)).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    zone = np.zeros_like(mask)
    zone[:, int(x_lo * 960):int(x_hi * 960)] = 1
    mask = mask * zone
    n, lab, stats, cent = cv2.connectedComponentsWithStats(mask, 8)
    best = None
    for i in range(1, n):
        area = stats[i, cv2.CC_STAT_AREA]
        if area < 900:
            continue
        x, y = stats[i, cv2.CC_STAT_LEFT], stats[i, cv2.CC_STAT_TOP]
        w, hh = stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT]
        if best is None or y < best['y']:
            best = {'x': x, 'y': y, 'w': w, 'h': hh, 'area': int(area)}
    if best is None:
        return None
    # -> в координаты полного кадра
    return {'x': best['x'] / 960.0, 'y': best['y'] / 540.0,
            'w': best['w'] / 960.0, 'h': best['h'] / 540.0, 'area': best['area']}


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="compose_faces.py",
        description="лист зума на лицо (область ищется по тону кожи)")
    p.add_argument("--src", required=True, help="папка с вариантами кадров")
    p.add_argument("--dst", required=True, help="папка для результата")
    p.add_argument("--moments", required=True, help="JSON со списком моментов")
    p.add_argument("--variants", required=True, help="JSON со списком вариантов")
    p.add_argument("--tile", default="520x520", help="размер плитки")
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
    fw, fh = (int(x) for x in a.tile.lower().split("x"))

    font = load_font(22)
    rows = len(moments)
    cols = len(variants)
    sheet = Image.new('RGB', (cols * fw, rows * (fh + 30)), (14, 14, 16))
    d = ImageDraw.Draw(sheet)
    report = {}

    for r, m in enumerate(moments):
        mid = m["id"]
        label = m.get("label", mid)
        zone = m.get("zone", [0.0, 1.0])
        x_lo, x_hi = float(zone[0]), float(zone[1])
        box = None
        for v in variants:
            path = os.path.join(src, '%s__%s.png' % (mid, v["id"]))
            if os.path.exists(path):
                box = skin_boxes(path, x_lo, x_hi)
                if box:
                    break
        if box is None:
            print("не найдено лицо:", mid)
            box = {'x': x_lo, 'y': 0.1, 'w': 0.2, 'h': 0.3, 'area': 0}
        report[mid] = [box['x'], box['y'], box['x'] + box['w'], box['y'] + box['h']]

        for c, v in enumerate(variants):
            path = os.path.join(src, '%s__%s.png' % (mid, v["id"]))
            if not os.path.exists(path):
                continue
            im = Image.open(path).convert('RGB')
            W0, H0 = im.size
            x0 = int(report[mid][0] * W0)
            y0 = int(report[mid][1] * H0)
            x1 = int(report[mid][2] * W0)
            y1 = int(report[mid][3] * H0)
            crop = im.crop((x0, y0, x1, y1))
            crop = crop.resize((fw, fh), Image.LANCZOS)
            im.close()
            x = c * fw
            y = r * (fh + 30)
            sheet.paste(crop, (x, y))
            d.rectangle([x, y + fh, x + fw, y + fh + 30], fill=(22, 22, 26))
            d.text((x + 6, y + fh + 4), v.get("label", v["id"]), fill=(238, 238, 238), font=font)
        d.text((6, r * (fh + 30) - 26), label, fill=(250, 250, 250), font=font)

    out = os.path.join(dst, 'cmp_faces.jpg')
    sheet.save(out, quality=94, subsampling=0)
    with open(os.path.join(dst, 'faces_boxes.json'), 'w', encoding='utf-8') as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=True, indent=1))
    print(out, sheet.size)
    return 0


if __name__ == "__main__":
    sys.exit(main())
