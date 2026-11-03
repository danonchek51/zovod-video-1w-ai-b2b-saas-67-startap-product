# -*- coding: utf-8 -*-
"""Луки v2: 3 стиля x 5 регистров сцен, art-directed (сильнее, чем v1).

Стили: doc (нейтральный собранный) / warm (тёплый комедийный) / service (служебный).
Регистры сцен: car / dps / territory / build / kitchen — типовые группы кадров,
для каждой свой набор поправок к стилю.

    python make_luts_v2.py [--out <корень проекта>] [--luts <папка для .cube>]
                          [--resolve-lut <папка LUT Resolve>]
"""
import argparse
import importlib.util
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import env_paths  # noqa: E402

SIZE = 33

# базовый модуль make_luts.py лежит рядом
_spec = importlib.util.spec_from_file_location(
    'ml1', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'make_luts.py'))
ml1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ml1)


def apply_look_v2(rgb, look):
    out = ml1.apply_look(rgb, look)
    wc = look.get('white_ceiling')
    if wc and wc < 1.0:
        for ch in range(3):
            c = out[:, ch]
            over = c > 0.85
            c[over] = 0.85 + (c[over] - 0.85) * (wc - 0.85) / 0.15
    return np.clip(out, 0.0, 1.0)


BASE = dict(
    contrast=1.12, pivot=0.44, midtone=0.05,
    shadow_end=0.42, highlight_start=0.58,
    shadow_tint=(0.0, 0.0, 0.0), highlight_tint=(0.0, 0.0, 0.0),
    sat_global=1.04, sat_green=0.95, sat_blue=0.98, sat_warm=1.03, sat_skin=1.02,
    highlight_rolloff=0.88, white_ceiling=1.0,
)


def L(**kw):
    d = dict(BASE)
    d.update(kw)
    return d


# ------------------------------------------------------------------ стили
STYLES = {
    'doc': L(
        contrast=1.11, pivot=0.45, midtone=0.055,
        shadow_tint=(0.000, 0.000, 0.004), highlight_tint=(0.000, 0.000, -0.004),
        sat_global=1.03, sat_green=0.96, sat_blue=1.00, sat_warm=1.02, sat_skin=1.02),
    'warm': L(
        contrast=1.13, pivot=0.44, midtone=0.065,
        shadow_tint=(-0.005, -0.002, 0.011), highlight_tint=(0.030, 0.011, -0.026),
        sat_global=1.10, sat_green=0.76, sat_blue=0.94, sat_warm=1.12, sat_skin=1.05),
    'service': L(
        contrast=1.17, pivot=0.50, midtone=0.030,
        shadow_tint=(-0.010, -0.003, 0.016), highlight_tint=(-0.004, 0.000, 0.005),
        sat_global=0.92, sat_green=0.88, sat_blue=0.90, sat_warm=0.96, sat_skin=1.00),
}

# ------------------------------------------------- регистры: модификаторы стиля
REGISTERS = {
    # регистр: поправки к стилю для этой группы сцен
    'car':       dict(),
    'dps':       dict(sat_global=-0.02, highlight_tint=(-0.010, -0.004, 0.010), contrast=-0.01),
    'territory': dict(sat_global=-0.05, highlight_tint=(-0.020, -0.008, 0.018), contrast=0.01),
    'build':     dict(sat_global=-0.07, highlight_tint=(-0.024, -0.010, 0.020), contrast=0.02),
    'kitchen':   dict(sat_global=-0.01, highlight_tint=(-0.004, -0.001, 0.004)),
}

# только для «тёплого»: часть регистров — «её мир», остальное чуть холоднее
WARM_REGISTER = {
    'car':       dict(),
    'dps':       dict(sat_global=-0.03, highlight_tint=(-0.012, -0.005, 0.011)),
    'territory': dict(sat_global=-0.06, highlight_tint=(-0.022, -0.009, 0.020)),
    'build':     dict(sat_global=-0.08, highlight_tint=(-0.026, -0.011, 0.022)),
    'kitchen':   dict(sat_global=-0.02, highlight_tint=(-0.006, -0.002, 0.006)),
}


def build(style, group):
    d = dict(STYLES[style])
    reg = (WARM_REGISTER if style == 'warm' else REGISTERS)[group]
    if 'sat_global' in reg:
        d['sat_global'] = d['sat_global'] + reg['sat_global']
    if 'contrast' in reg:
        d['contrast'] = d['contrast'] + reg['contrast']
    if 'highlight_tint' in reg:
        ht = reg['highlight_tint']
        base = d['highlight_tint']
        d['highlight_tint'] = (base[0] + ht[0], base[1] + ht[1], base[2] + ht[2])
    return d


def write_cube(name, look, lutdir):
    n = SIZE
    b_axis = np.linspace(0, 1, n)
    r_axis = np.linspace(0, 1, n)
    g_axis = np.linspace(0, 1, n)
    vals = []
    for bi in range(n):
        for gi in range(n):
            for ri in range(n):
                vals.append((r_axis[ri], g_axis[gi], b_axis[bi]))
    arr = np.array(vals, dtype=np.float32)
    out = np.clip(apply_look_v2(arr, look), 0.0, 1.0)
    path = os.path.join(lutdir, name + '.cube')
    with open(path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('# make_luts_v2.py\n')
        fh.write('TITLE "%s"\n' % name)
        fh.write('LUT_3D_SIZE %d\n' % n)
        fh.write('DOMAIN_MIN 0.0 0.0 0.0\n')
        fh.write('DOMAIN_MAX 1.0 1.0 1.0\n')
        for i in range(out.shape[0]):
            r, g, b = out[i]
            fh.write('%.6f %.6f %.6f\n' % (r, g, b))
    return path


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="make_luts_v2.py",
        description="генератор .cube LUT (стили x регистры сцен)")
    p.add_argument("--out", default="", help="корень проекта")
    p.add_argument("--luts", default="", help="папка для .cube (по умолчанию <out>/luts)")
    p.add_argument("--resolve-lut", default="",
                   help="папка LUT Resolve (по умолчанию берётся из env_paths)")
    a = p.parse_args(argv)

    project = env_paths.project_root()
    root = os.path.abspath(a.out) if a.out else str(project)
    lutdir = os.path.abspath(a.luts) if a.luts else os.path.join(root, "luts")
    resolve_lut = a.resolve_lut or env_paths.lut_dir() or ""
    os.makedirs(lutdir, exist_ok=True)

    made = []
    for style in ('doc', 'warm', 'service'):
        for group in ('car', 'dps', 'territory', 'build', 'kitchen'):
            name = 'v2_%s_%s' % (style, group)
            path = write_cube(name, build(style, group), lutdir)
            made.append(path)
            print('wrote', os.path.basename(path), os.path.getsize(path))
    if resolve_lut:
        try:
            os.makedirs(resolve_lut, exist_ok=True)
            for path in made:
                dst = os.path.join(resolve_lut, os.path.basename(path))
                with open(path, 'rb') as src, open(dst, 'wb') as d:
                    d.write(src.read())
            print('copied to Resolve LUT dir:', len(made))
        except Exception as exc:
            print('copy failed:', exc)
    else:
        print('папка LUT Resolve не задана — копирование пропущено')
    return 0


if __name__ == '__main__':
    sys.exit(main())
