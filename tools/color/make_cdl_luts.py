# -*- coding: utf-8 -*-
"""make_cdl_luts.py — 3D LUT (.cube) по ASC-CDL спецификации.

Спецификация (JSON): словарь "ключ" -> {
    "name":    "C0127.MP4",          # имя для отчёта и имени файла
    "Slope":   [r, g, b],
    "Offset":  [r, g, b],
    "Power":   [r, g, b],
    "Saturation": 1.0,
    "items":   [{"trk": "V1", "s": 90175, "e": 90309, "name": "C0127.MP4"}]
}

Математика (ASC-CDL в гамма-домене):
    out = clip(slope*in + offset, 0, None) ** power
    out = clip(out, 0, 1)
    luma = 0.2126R + 0.7152G + 0.0722B
    out = luma + saturation * (out - luma)

ПОРЯДОК ЗАПИСИ .cube — критичен: в стандарте КРАСНЫЙ меняется быстрее всех,
плоский индекс (b*N + g)*N + r. Если писать наоборот, Resolve читает файл с
переставленными R и B и молча портит грейд. Этот скрипт пишет по стандарту и
сразу проверяет результат через verify_lut.py.

    python tools/color/make_cdl_luts.py --cdl spec.json --out luts
    python tools/color/make_cdl_luts.py --cdl spec.json --out luts --install
"""
import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_lut import cdl_to_image, load_cube, sample_cube  # noqa: E402

N = 33


def safe_name(name, limit=60):
    return "".join(ch if (ch.isalnum() or ch in "._-") else "_" for ch in name)[:limit]


def write_cube(path, title, out, n=N):
    """out[r][g][b] -> файл в стандартном порядке (красный быстрее всех)."""
    with open(path, "w", encoding="utf-8") as f:
        f.write('TITLE "%s"\n' % title)
        f.write("LUT_3D_SIZE %d\n" % n)
        f.write("DOMAIN_MIN 0.0 0.0 0.0\nDOMAIN_MAX 1.0 1.0 1.0\n")
        for b in range(n):
            for g in range(n):
                for r in range(n):
                    px = out[r, g, b]
                    f.write("%.6f %.6f %.6f\n" % (px[0], px[1], px[2]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cdl", required=True, help="JSON со спецификацией CDL")
    ap.add_argument("--out", required=True, help="папка для .cube")
    ap.add_argument("--size", type=int, default=N)
    ap.add_argument("--install", action="store_true",
                    help="скопировать .cube в папку LUT Resolve и обновить карту установки")
    ap.add_argument("--lut-dir", default=None,
                    help="папка LUT Resolve (по умолчанию берётся из окружения)")
    ap.add_argument("--prefix", default="MU2_lut_", help="префикс ASCII-имён при установке")
    ap.add_argument("--no-verify", action="store_true")
    args = ap.parse_args()

    spec = json.load(open(args.cdl, encoding="utf-8"))
    os.makedirs(args.out, exist_ok=True)

    lut_dir = args.lut_dir
    if args.install and not lut_dir:
        from env_paths import resolve_lut_dir
        lut_dir = resolve_lut_dir()

    g = np.linspace(0.0, 1.0, args.size)
    R, G, B = np.meshgrid(g, g, g, indexing="ij")
    img = np.stack([R, G, B], axis=-1).reshape(-1, 3)

    index, install_map = [], {}
    worst = 0.0
    for i, (key, c) in enumerate(spec.items()):
        out = cdl_to_image(img, c).reshape(args.size, args.size, args.size, 3)
        name = c.get("name", key)
        path = os.path.join(args.out, safe_name(name) + ".cube")
        write_cube(path, name, out, args.size)
        index.append({"key": key, "name": name, "path": path,
                      "items": c.get("items", [])})
        if args.install:
            import shutil
            ascii_name = "%s%02d.cube" % (args.prefix, i)
            dst = os.path.join(lut_dir, ascii_name)
            shutil.copy2(path, dst)
            install_map[ascii_name] = {"key": key, "name": name, "orig": path,
                                       "installed": dst, "items": c.get("items", [])}
        if not args.no_verify:
            cube, size, dmin, dmax = load_cube(path)
            err = np.abs(sample_cube(cube, img, dmin, dmax) -
                         cdl_to_image(img, c).reshape(-1, 3)).max()
            worst = max(worst, float(err))

    json.dump(index, open(os.path.join(args.out, "index.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    if args.install:
        json.dump(install_map, open(os.path.join(args.out, "install_map.json"), "w",
                                    encoding="utf-8"), ensure_ascii=False, indent=1)
        print("установлено в:", lut_dir)

    print("LUT готовы:", len(index), "->", args.out)
    if not args.no_verify:
        print("самопроверка: максимальная ошибка против CDL = %.6f" % worst)
        if worst > 0.08:
            print("ВНИМАНИЕ: ошибка выше 0.08 — проверь порядок осей в .cube")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
