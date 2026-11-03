# -*- coding: utf-8 -*-
"""Генератор .cube LUT для DaVinci Resolve.

Три направления грейда (display-referred, без блума/вуали/виньетки):
  A_neutral      — нейтрально-документальный: мягкая S-кривая, без тонировки
  B_warm_comedy  — тёплый комедийный: тёплые света, приглушённая осень, кожа живая
  C_service      — служебный: холоднее, чище, контрастнее, фон спокойнее

Защита кожи делается по HUE (диапазон 8-52 градусов), чтобы лицо
не уходило в жёлтизну и не теряло насыщенность.

    python make_luts.py [--out <корень проекта>] [--luts <папка для .cube>]
                        [--resolve-lut <папка LUT Resolve>]
"""
import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import env_paths  # noqa: E402

SIZE = 33


def srgb_to_linear(x):
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(x):
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * (x ** (1 / 2.4)) - 0.055)


def contrast_curve(x, amount, pivot):
    """S-кривая вокруг пивота: amount<1 — мягче, >1 — жёстче."""
    if amount == 1.0:
        return x
    # нормализованная S-кривая: плавная, без жёсткой клиппинга
    t = np.clip((x - pivot) / (1.0 - pivot), -1.0, 1.0)
    t = np.sign(t) * np.abs(t) ** (1.0 / amount)
    return np.clip(pivot + t * (1.0 - pivot), 0.0, 1.0)


def midtone_lift(x, amount):
    """Подъём полутонов без сдвига чёрной и белой точки: x + a*4*x*(1-x)."""
    if amount == 0.0:
        return x
    return np.clip(x + amount * 4.0 * x * (1.0 - x), 0.0, 1.0)


def apply_look(rgb, look):
    """rgb: (N,3) float 0..1 (sRGB-энкодированные значения кадра)."""
    r, g, b = rgb[:, 0].copy(), rgb[:, 1].copy(), rgb[:, 2].copy()
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b

    # --- тоновая S-кривая (воспринимаемая, работает по гамма-кодированным) ---
    r = contrast_curve(r, look['contrast'], look['pivot'])
    g = contrast_curve(g, look['contrast'], look['pivot'])
    b = contrast_curve(b, look['contrast'], look['pivot'])

    # --- подъём полутонов (лицо читается, но чёрные не «вымываются») ---
    mt = look.get('midtone', 0.0)
    if mt:
        r = midtone_lift(r, mt)
        g = midtone_lift(g, mt)
        b = midtone_lift(b, mt)

    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b

    # --- сплит-тонирование: тени и света разными краями ---
    sh = np.clip(1.0 - lum / max(look['shadow_end'], 1e-6), 0.0, 1.0) ** 1.5
    hi = np.clip((lum - look['highlight_start']) / max(1.0 - look['highlight_start'], 1e-6), 0.0, 1.0) ** 1.5
    r = r + sh * look['shadow_tint'][0] + hi * look['highlight_tint'][0]
    g = g + sh * look['shadow_tint'][1] + hi * look['highlight_tint'][1]
    b = b + sh * look['shadow_tint'][2] + hi * look['highlight_tint'][2]

    # --- насыщенность по HUE (защита кожи) ---
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    d = mx - mn
    sat = np.where(mx > 1e-6, d / np.maximum(mx, 1e-6), 0.0)

    # HSV- Hue
    hue = np.zeros_like(r)
    c_r = d > 1e-9
    idx = c_r & (mx == r)
    hue[idx] = ((g[idx] - b[idx]) / d[idx]) % 6
    idx = c_r & (mx == g)
    hue[idx] = ((b[idx] - r[idx]) / d[idx]) + 2
    idx = c_r & (mx == b)
    hue[idx] = ((r[idx] - g[idx]) / d[idx]) + 4
    hue = hue * 60.0

    skin = (hue >= 8.0) & (hue <= 52.0) & (sat > 0.06) & (sat < 0.85)

    # базовый множитель насыщенности по секторам
    sat_mult = np.full_like(r, look['sat_global'])
    green = (hue >= 55.0) & (hue <= 170.0)
    sat_mult = np.where(green, sat_mult * look['sat_green'], sat_mult)
    sky = (hue >= 180.0) & (hue <= 260.0)
    sat_mult = np.where(sky, sat_mult * look['sat_blue'], sat_mult)
    warm = (hue >= 20.0) & (hue < 55.0)
    sat_mult = np.where(warm, sat_mult * look['sat_warm'], sat_mult)
    # кожа — почти не трогаем
    sat_mult = np.where(skin, look['sat_skin'], sat_mult)

    gray = 0.2126 * r + 0.7152 * g + 0.0722 * b
    r = gray + (r - gray) * sat_mult
    g = gray + (g - gray) * sat_mult
    b = gray + (b - gray) * sat_mult

    # --- мягкий ролл-офф светов (окна не должны выбиваться в белое) ---
    hi = np.clip((r + g + b) / 3.0 - 0.90, 0.0, 1.0)
    roll = look['highlight_rolloff']
    if roll < 1.0:
        for ch in (r, g, b):
            over = ch > 0.92
            ch[over] = 0.92 + (ch[over] - 0.92) * roll
    return np.stack([r, g, b], axis=1)


LOOKS = {
    'A_neutral': {
        'contrast': 1.09, 'pivot': 0.44, 'midtone': 0.060,
        'shadow_end': 0.45, 'highlight_start': 0.60,
        'shadow_tint': (-0.002, 0.000, 0.003),
        'highlight_tint': (0.002, 0.001, -0.003),
        'sat_global': 1.02, 'sat_green': 0.96, 'sat_blue': 1.00, 'sat_warm': 1.02, 'sat_skin': 1.02,
        'highlight_rolloff': 0.85,
        'desc': 'neutral documentary',
    },
    'B_warm_comedy': {
        'contrast': 1.09, 'pivot': 0.44, 'midtone': 0.070,
        'shadow_end': 0.40, 'highlight_start': 0.55,
        'shadow_tint': (0.006, 0.002, -0.008),
        'highlight_tint': (0.030, 0.010, -0.028),
        'sat_global': 1.08, 'sat_green': 0.78, 'sat_blue': 0.92, 'sat_warm': 1.10, 'sat_skin': 1.04,
        'highlight_rolloff': 0.80,
        'desc': 'warm comedy',
    },
    'C_service': {
        'contrast': 1.15, 'pivot': 0.50, 'midtone': 0.035,
        'shadow_end': 0.45, 'highlight_start': 0.62,
        'shadow_tint': (-0.008, -0.001, 0.012),
        'highlight_tint': (-0.004, 0.000, 0.004),
        'sat_global': 0.90, 'sat_green': 0.85, 'sat_blue': 0.90, 'sat_warm': 0.96, 'sat_skin': 0.98,
        'highlight_rolloff': 0.88,
        'desc': 'service / institutional',
    },
}


def write_cube(name, look, lutdir):
    n = SIZE
    vals = []
    b_axis = np.linspace(0, 1, n)
    r_axis = np.linspace(0, 1, n)
    g_axis = np.linspace(0, 1, n)

    # .cube: индексы идут b -> g -> r (быстрее меняется b)
    for bi in range(n):
        b = b_axis[bi]
        for gi in range(n):
            g = g_axis[gi]
            for ri in range(n):
                r = r_axis[ri]
                vals.append((r, g, b))

    arr = np.array(vals, dtype=np.float32)
    out = apply_look(arr, look)
    out = np.clip(out, 0.0, 1.0)

    path = os.path.join(lutdir, name + '.cube')
    with open(path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('# Generated by make_luts.py - %s\n' % look['desc'])
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
        prog="make_luts.py",
        description="генератор .cube LUT (три направления грейда)")
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
    for name, look in LOOKS.items():
        p_ = write_cube(name, look, lutdir)
        made.append(p_)
        print('wrote', p_, os.path.getsize(p_))

    # пробуем положить копию в папку LUT Resolve
    if resolve_lut:
        try:
            os.makedirs(resolve_lut, exist_ok=True)
            for p_ in made:
                dst = os.path.join(resolve_lut, os.path.basename(p_))
                with open(p_, 'rb') as src, open(dst, 'wb') as d:
                    d.write(src.read())
                print('copied ->', dst)
        except Exception as exc:
            print('copy to Resolve LUT dir failed:', exc)
    else:
        print('папка LUT Resolve не задана — копирование пропущено')
    return 0


if __name__ == '__main__':
    sys.exit(main())
