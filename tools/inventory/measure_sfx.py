#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
measure_sfx.py - замерить произвольные звуковые файлы той же методикой, что и
process_sfx.py (true peak, RMS, LUFS, клиппинг, центроид по активной части).

Нужен, чтобы честно сравнить файлы заказчика с вариантами из SFXMint.
Исходники открываются ТОЛЬКО НА ЧТЕНИЕ.

    python measure_sfx.py <файл.wav> [<файл2.wav> ...] [--json out.json]
"""
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sfx"))
from process_sfx import measure, pcm_stats, sha256  # noqa: E402


def measure_paths(paths):
    rows = []
    for p in paths:
        if not os.path.exists(p):
            rows.append({"file": p, "error": "не найден"})
            continue
        m = measure(p)
        ps = pcm_stats(p)
        row = {"file": p, "bytes": os.path.getsize(p), "sha256": sha256(p)}
        row.update(m)
        if ps:
            row["rms_db"] = 20 * math.log10(ps["rms_linear"]) if ps.get("rms_linear") else None
            row["tail_rms_db"] = (20 * math.log10(ps["tail_rms_linear"])
                                  if ps.get("tail_rms_linear") else None)
            row["clip_pct"] = ps.get("clip_pct")
            row["centroid_hz"] = ps.get("centroid_hz")
            row["active_ms"] = ps.get("active_ms")
        rows.append(row)
    return rows


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="measure_sfx.py",
        description="замеры звука по методике process_sfx.py")
    p.add_argument("paths", nargs="+", help="файлы для замера")
    p.add_argument("--json", default="", help="куда записать отчёт JSON")
    a = p.parse_args(argv)

    rows = measure_paths(a.paths)
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, ensure_ascii=False, indent=2)
        print("report:", a.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
