# -*- coding: utf-8 -*-
"""look_preview.py — превью цветовых регистров на кадрах с героем.

Показать надо не «средний кадр клипа», а те кадры, где виден герой.
Каждая картинка: сверху оригинал (100 % пикселей, 1600x900), снизу — тот же
кадр после обработки регистром сцены.

ВНИМАНИЕ: модуль с самими луками (`look.py`) НЕ входит в пакет — это
проектный файл. Укажите его через --look-module (по умолчанию ищется
`look.py` рядом со скриптом). Без него скрипт печатает понятную ошибку
и завершается, не падая с трассировкой.

    python look_preview.py --src <папка с исходниками> --out <корень проекта>
                           --shots "ИМЯ|сцена|папка|клип|сек|crop_x|crop_y,..."
                           [--look-module look.py]
"""
import argparse
import importlib.util
import json
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import env_paths  # noqa: E402

FF = env_paths.ffmpeg() or "ffmpeg"
W, H = 3840, 2160
CW, CH = 1600, 900

L = None


def load_look_module(path):
    """Загружает модуль луков. None — если модуля нет."""
    if not path or not os.path.exists(path):
        return None
    spec = importlib.util.spec_from_file_location("look", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sh(cmd, **kw):
    return subprocess.run(cmd, check=True, stdout=subprocess.PIPE, **kw)


def extract_png(src, t, dst):
    sh([FF, "-v", "error", "-i", src, "-ss", str(t), "-frames:v", "1",
        "-update", "1", "-y", dst])


def read_rgb(path, w, h):
    p = sh([FF, "-v", "error", "-i", path, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
    return np.frombuffer(p.stdout, dtype=np.uint8).reshape(h, w, 3).astype(np.float32) / 255.0


def write_rgb(arr, dst):
    data = (np.clip(arr, 0, 1) * 255.0 + 0.5).astype(np.uint8).tobytes()
    p = subprocess.run([FF, "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                        "-s", "%dx%d" % (arr.shape[1], arr.shape[0]), "-i", "-",
                        "-frames:v", "1", "-update", "1", "-y", dst],
                       input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode("utf-8", "replace")[-500:])


def auto_face_crop(base, cw=CW, ch=CH):
    """Кадр сам находит лицо героя (детектор профиля OpenCV).

    Ручные координаты промахиваются на полсосы, а в превью лицо героини
    обязано быть — иначе грейд оценивают не по тому кадру.
    """
    try:
        import cv2
        gray = (base @ L.LUMA * 255.0).astype(np.uint8)
        best = None
        for name in ("haarcascade_frontalface_profile.xml",
                     "haarcascade_frontalface_default.xml"):
            clf = cv2.CascadeClassifier(cv2.data.haarcascades + name)
            faces = clf.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4,
                                         minSize=(150, 150))
            for (x, y, w, h) in faces:
                a = int(w) * int(h)
                if best is None or a > best[0]:
                    best = (a, int(x), int(y), int(w), int(h))
            if best:
                break
        if best:
            _, x, y, w, h = best
            cx, cy = x + w // 2, y + h // 2
            ox = max(0, min(cx - cw // 2, W - cw))
            oy = max(0, min(cy - ch // 2, H - ch))
            return ox, oy
    except Exception as e:
        print("   face detect failed:", e, flush=True)
    return None


def parse_shots(spec):
    """'ИМЯ|сцена|папка|клип|сек|crop_x|crop_y' -> список кортежей."""
    out = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        bits = part.split("|")
        if len(bits) < 5:
            raise ValueError("неверный кадр: %s" % part)
        label = bits[0].strip()
        scene = bits[1].strip()
        folder = bits[2].strip()
        clip = bits[3].strip()
        t = float(bits[4])
        cx = int(bits[5]) if len(bits) > 5 and bits[5] else 0
        cy = int(bits[6]) if len(bits) > 6 and bits[6] else 0
        out.append((label, scene, folder, clip, t, cx, cy))
    return out


def main(argv=None):
    global L

    p = argparse.ArgumentParser(
        prog="look_preview.py",
        description="превью цветовых регистров на кадрах с героем")
    p.add_argument("--src", default="", help="папка с исходниками (только чтение)")
    p.add_argument("--out", default="", help="корень проекта для результатов")
    p.add_argument("--shots", required=True,
                   help="кадры: ИМЯ|сцена|папка|клип|сек|crop_x|crop_y,...")
    p.add_argument("--look-module", default="",
                   help="путь к модулю с луками (look.py)")
    a = p.parse_args(argv)

    project = env_paths.project_root()
    root = os.path.abspath(a.out) if a.out else str(project)
    src = os.path.abspath(a.src) if a.src else str(env_paths.src_root() or "")
    if not src or not os.path.isdir(src):
        p.error("нет папки с исходниками (укажи --src)")

    look_path = a.look_module or os.path.join(os.path.dirname(os.path.abspath(__file__)), "look.py")
    L = load_look_module(look_path)
    if L is None:
        print("модуль с луками не найден: %s" % look_path)
        print("укажите его через --look-module <путь> (в пакет он не входит: "
              "это проектный файл)")
        return 2

    base = os.path.join(root, "look_preview")
    os.makedirs(base, exist_ok=True)
    raw = os.path.join(base, "raw")
    os.makedirs(raw, exist_ok=True)
    report = {}

    shots = parse_shots(a.shots)
    for label, scene, folder, clip, t, cx, cy in shots:
        src_path = os.path.join(src, folder, clip + ".MP4")
        if not os.path.exists(src_path):
            alt = os.path.join(src, folder, clip + ".mp4")
            src_path = alt if os.path.exists(alt) else src_path
        if not os.path.exists(src_path):
            print("нет файла:", src_path)
            continue
        png = os.path.join(raw, "%s.png" % label)
        extract_png(src_path, t, png)
        frame = read_rgb(png, W, H)

        params = L.scene_params(scene)
        graded = L.grade(frame, params)

        # Полный кадр, без кропа: претензия «не вижу лица» как раз и выросла
        # из обрезанных кусков. Сверху оригинал, снизу обработка.
        o_png = os.path.join(base, "full_orig_%s.png" % label)
        g_png = os.path.join(base, "full_graded_%s.png" % label)
        write_rgb(frame, o_png)
        write_rgb(graded, g_png)
        out_png = os.path.join(base, "look_%s.png" % label)
        subprocess.run([FF, "-v", "error", "-i", o_png, "-i", g_png,
                        "-filter_complex",
                        "[0:v]scale=1600:900:flags=lanczos[a];"
                        "[1:v]scale=1600:900:flags=lanczos[b];[a][b]vstack=inputs=2",
                        "-frames:v", "1", "-update", "1", "-y", out_png],
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        report[label] = {
            "scene": scene,
            "clip": clip,
            "time_s": t,
            "orig": L.measure(frame),
            "graded": L.measure(graded),
            "params": {k: v for k, v in params.items()},
        }
        print("OK", label, scene, flush=True)

    with open(os.path.join(base, "look_stats.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
