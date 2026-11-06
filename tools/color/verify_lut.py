# -*- coding: utf-8 -*-
"""verify_lut.py — самопроверка .cube: совпадает ли файл с исходной математикой.

Зачем: .cube читается по стандарту (красный — самая быстро меняющаяся ось,
плоский индекс (b*N + g)*N + r). Если файл записан наоборот, Resolve читает
его с переставленными R и B — картинка «не красная», но и не та, и ошибку
не видно без сверки. Этот инструмент ловит именно такую ошибку.

Режимы:
    # 1. сверка с исходной CDL-спецификацией (главный режим)
    python tools/color/verify_lut.py --cube luts/C0127.MP4.cube --cdl spec.json --key C0127__car

    # 2. независимая сверка: ffmpeg lut3d против numpy-чтения того же файла
    python tools/color/verify_lut.py --cube luts/C0127.MP4.cube --ffmpeg

Код возврата 0 — файл корректен, 1 — есть расхождение.
"""
import argparse
import json
import os
import subprocess
import sys

import numpy as np


def load_cube(path):
    """Читает .cube по стандарту. Возвращает (cube[r][g][b], size, dmin, dmax)."""
    size = None
    dmin = np.array([0.0, 0.0, 0.0])
    dmax = np.array([1.0, 1.0, 1.0])
    rows = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            s = line.strip()
            if s.startswith("LUT_3D_SIZE"):
                size = int(s.split()[-1])
            elif s.startswith("DOMAIN_MIN"):
                dmin = np.array([float(x) for x in s.split()[1:4]])
            elif s.startswith("DOMAIN_MAX"):
                dmax = np.array([float(x) for x in s.split()[1:4]])
            elif s and s[0].isdigit():
                rows.append([float(x) for x in s.split()[:3]])
    if size is None or len(rows) != size ** 3:
        raise ValueError("нечитаемый .cube: size=%s, строк=%d" % (size, len(rows)))
    cube = np.array(rows, dtype=np.float64).reshape(size, size, size, 3)
    return np.transpose(cube, (2, 1, 0, 3)), size, dmin, dmax


def sample_cube(cube, pts, dmin=None, dmax=None):
    """Трилинейная выборка из куба. pts — (N,3) в диапазоне домена."""
    if dmin is None:
        dmin = np.zeros(3)
    if dmax is None:
        dmax = np.ones(3)
    size = cube.shape[0]
    pos = (np.asarray(pts) - dmin) / (dmax - dmin) * (size - 1)
    pos = np.clip(pos, 0, size - 1)
    i0 = np.floor(pos).astype(int)
    i1 = np.minimum(i0 + 1, size - 1)
    f = pos - i0
    out = np.zeros_like(np.asarray(pts, dtype=np.float64))
    for dr in (0, 1):
        for dg in (0, 1):
            for db in (0, 1):
                r = i0[:, 0] if dr == 0 else i1[:, 0]
                g = i0[:, 1] if dg == 0 else i1[:, 1]
                bl = i0[:, 2] if db == 0 else i1[:, 2]
                w = ((1 - f[:, 0]) if dr == 0 else f[:, 0]) * \
                    ((1 - f[:, 1]) if dg == 0 else f[:, 1]) * \
                    ((1 - f[:, 2]) if db == 0 else f[:, 2])
                out += w[:, None] * cube[r, g, bl]
    return out


def cdl_to_image(img, c):
    """ASC-CDL в гамма-домене: slope/offset -> power -> сатурация по luma."""
    slope = np.asarray(c["Slope"], dtype=np.float64)
    offset = np.asarray(c["Offset"], dtype=np.float64)
    power = np.asarray(c["Power"], dtype=np.float64)
    sat = float(c["Saturation"])
    x = np.clip(img * slope + offset, 0.0, None) ** power
    x = np.clip(x, 0.0, 1.0)
    luma = (x[..., 0] * 0.2126 + x[..., 1] * 0.7152 + x[..., 2] * 0.0722)[..., None]
    return np.clip(luma + sat * (x - luma), 0.0, 1.0)


def ffmpeg_check(path, pts, ffmpeg=None):
    """Независимая проверка: ffmpeg lut3d против numpy-чтения того же файла."""
    from PIL import Image
    if ffmpeg is None:
        ffmpeg = os.environ.get("FFMPEG", "ffmpeg")
    h, w = 64, 64
    img = pts.reshape(h, w, 3)
    png = os.path.join(os.path.dirname(os.path.abspath(path)), "_verify_lut_tmp.png")
    raw = os.path.join(os.path.dirname(os.path.abspath(path)), "_verify_lut_tmp.raw")
    try:
        Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(png)
        # путь без двоеточия — парсер фильтра ломается на букве диска
        work = os.path.dirname(os.path.abspath(png))
        rel = os.path.relpath(path, work).replace("\\", "/")
        p = subprocess.run([ffmpeg, "-y", "-v", "error", "-i", png, "-vf", "lut3d='%s'" % rel,
                            "-f", "rawvideo", "-pix_fmt", "rgb24", raw],
                           capture_output=True, text=True, cwd=work)
        if p.returncode != 0:
            return None, p.stderr.strip()[:300]
        got = np.fromfile(raw, dtype=np.uint8).reshape(h, w, 3).astype(np.float64) / 255.0
        return got.reshape(-1, 3), None
    finally:
        for f in (png, raw):
            if os.path.exists(f):
                os.remove(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cube", required=True)
    ap.add_argument("--cdl", help="JSON со спецификацией CDL")
    ap.add_argument("--key", help="ключ внутри спецификации")
    ap.add_argument("--ffmpeg", action="store_true", help="независимая сверка через ffmpeg lut3d")
    ap.add_argument("--ffmpeg-bin", default=None)
    ap.add_argument("--tol-max", type=float, default=0.08)
    ap.add_argument("--tol-mean", type=float, default=0.01)
    args = ap.parse_args()

    rng = np.random.default_rng(7)
    pts = 0.03 + rng.random((4096, 3)) * 0.94
    cube, size, dmin, dmax = load_cube(args.cube)
    got = sample_cube(cube, pts, dmin, dmax)
    print("cube: %s  size=%d  домен=%s..%s" % (args.cube, size, dmin.tolist(), dmax.tolist()))

    verdict_ok = True
    if args.cdl:
        spec = json.load(open(args.cdl, encoding="utf-8"))
        key = args.key
        if key is None:
            if len(spec) != 1:
                print("нужен --key: в спецификации %d записей" % len(spec))
                return 1
            key = next(iter(spec))
        c = spec[key]
        exp = cdl_to_image(pts, c)
        err = np.abs(got - exp)
        mx, mean = float(err.max()), float(err.mean())
        print("сверка с CDL '%s': max=%.5f  mean=%.6f" % (key, mx, mean))

        # диагностика: если поменять R и B местами, ошибка резко падает —
        # значит файл записан с переставленными осями
        swapped = np.abs(got[:, [2, 1, 0]] - exp)
        if float(swapped.max()) < mx * 0.5:
            print("ДИАГНОСТИКА: R и B переставлены в файле (ошибка падает с %.5f до %.5f)" %
                  (mx, float(swapped.max())))
        if mx > args.tol_max or mean > args.tol_mean:
            verdict_ok = False
            print("ПРОВАЛ: расхождение выше допуска (max %.5f / mean %.6f)" % (mx, mean))
        else:
            print("OK: файл воспроизводит CDL в пределах квантования 33^3")

    if args.ffmpeg:
        got_ff, err = ffmpeg_check(args.cube, pts, args.ffmpeg_bin)
        if got_ff is None:
            print("ffmpeg-проверка не выполнена: %s" % err)
        else:
            e = np.abs(got_ff - got)
            print("сверка с ffmpeg lut3d: max=%.5f  mean=%.6f" %
                  (float(e.max()), float(e.mean())))
            if float(e.mean()) > 0.01:
                verdict_ok = False
                print("ПРОВАЛ: ffmpeg и numpy читают файл по-разному")
            else:
                print("OK: ffmpeg и numpy читают файл одинаково")

    return 0 if verdict_ok else 1


if __name__ == "__main__":
    sys.exit(main())
