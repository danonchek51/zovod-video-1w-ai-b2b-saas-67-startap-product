# -*- coding: utf-8 -*-
"""compare_frames.py — попиксельное сравнение контрольных кадров (RMS, % различий).

    python compare_frames.py --dir <папка со стиллами> [--frames a.png,b.png] [--json out.json]

Базовая рама берётся как первый файл из списка (по умолчанию frame_before.png).
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image

DEFAULT_FRAMES = ["frame_before.png", "frame_drx_primary_r21.png",
                   "frame_drx_window_r21.png", "frame_drx_multinode_r21.png"]


def load(p):
    with open(p, "rb") as f:
        im = Image.open(f)
        im.load()
        return np.asarray(im.convert("RGB")).astype(np.float32)


def compare(d, files):
    data = {}
    for fn in files:
        p = os.path.join(d, fn)
        if os.path.exists(p):
            data[fn] = load(p)
            print("%-34s %s  shape=%s" % (fn, os.path.getsize(p), data[fn].shape))

    base_name = files[0] if files else None
    base = data.get(base_name)
    if base is None:
        sys.exit("нет контрольного кадра: %s" % os.path.join(d, str(base_name)))

    rows = []
    for fn, arr in data.items():
        if fn == base_name:
            continue
        if arr.shape != base.shape:
            print("%-34s РАЗНЫЙ РАЗМЕР %s vs %s" % (fn, arr.shape, base.shape))
            continue
        diff = arr - base
        rms = float(np.sqrt((diff ** 2).mean()))
        maxd = float(np.abs(diff).max())
        nz = float((np.abs(diff) > 1).mean() * 100)
        rows.append({"frame": fn, "rms": round(rms, 4), "max_diff": round(maxd, 3),
                     "pixels_diff_gt_1_pct": round(nz, 4)})
        print("%-34s RMS=%7.3f  max=%6.1f  пикселей с diff>1: %6.3f %%"
              % (fn, rms, maxd, nz))

    # попиксельные средние
    print("\nсредние по каналам (R,G,B):")
    means = {}
    for fn, arr in data.items():
        m = arr.reshape(-1, 3).mean(axis=0)
        means[fn] = [round(float(m[0]), 3), round(float(m[1]), 3), round(float(m[2]), 3)]
        print("  %-34s %7.2f %7.2f %7.2f" % (fn, m[0], m[1], m[2]))
    return {"dir": os.path.abspath(d), "base": base_name, "frames": rows,
            "channel_means": means}


def main(argv=None):
    p = argparse.ArgumentParser(prog="compare_frames.py",
                                description="попиксельное сравнение контрольных кадров")
    p.add_argument("--dir", required=True, help="папка с контрольными кадрами")
    p.add_argument("--frames", default=",".join(DEFAULT_FRAMES),
                   help="список кадров через запятую (первый — база)")
    p.add_argument("--json", default="", help="куда записать отчёт JSON")
    a = p.parse_args(argv)

    files = [x.strip() for x in a.frames.split(",") if x.strip()]
    if not files:
        p.error("--frames пуст")
    report = compare(a.dir, files)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        print("report:", a.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
