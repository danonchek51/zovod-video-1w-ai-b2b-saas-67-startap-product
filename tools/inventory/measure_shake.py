# -*- coding: utf-8 -*-
"""measure_shake.py — измерение тряски камеры по всем клипам из inventory.json.

Метод:
  ffmpeg отдаёт серые кадры шириной 320 px; между соседними кадрами phase
  correlation даёт сдвиг (dx, dy).
  Медленный дрейф камеры (pan/tilt) снимается скользящим средним 0.5 с.
  Остаток (dx-trend, dy-trend) — это и есть тряска рук: RMS в пикселях
  (масштаб 320 px ширины) и в пересчёте на 4K (×12).

Метрики по клипу:
  shake_head — RMS тряски в первых 2 с
  shake_rest  — RMS тряски в остатке
  shake_ratio — во сколько раз начало хуже остатка
  trim_suggest_s — с какого момента тряска падает до нормы клипа
  (вычисляется только если начало достоверно хуже: ratio >= 1.6)

Пишет: shake_report.json + shake_summary.txt

    python measure_shake.py --inventory inventory.json [--out <корень проекта>]
"""
import argparse
import json
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import env_paths  # noqa: E402

FF = env_paths.ffmpeg() or "ffmpeg"
FFPROBE = env_paths.ffprobe() or "ffprobe"
W = 320
FPS = 25.0
TREND_WIN = 13        # 0.52 с — окно «медленного» движения
SCALE_4K = 12.0      # 3840 / 320


def probe_h(path, width=W):
    cmd = [FFPROBE, "-v", "error", "-select_streams",
           "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", path]
    out = subprocess.run(cmd, check=True, stdout=subprocess.PIPE).stdout.decode().strip()
    sw, sh = [int(v) for v in out.split("x")[:2]]
    return max(2, int(round(width * sh / sw / 2.0)) * 2)


def frames_gray(path, width=W):
    h = probe_h(path, width)
    cmd = [FF, "-v", "error", "-i", path, "-vf", "scale=%d:-2" % width,
           "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    raw = proc.stdout.read()
    proc.wait()
    if proc.returncode != 0 or len(raw) < h * width:
        return None, None
    arr = np.frombuffer(raw, dtype=np.uint8)
    n = len(arr) // (h * width)
    return arr[: n * h * width].reshape(n, h, width), h


def measure(path):
    arr, h = frames_gray(path)
    if arr is None or len(arr) < 4:
        return None
    import cv2
    f = arr.astype(np.float32)
    f = f - f.mean(axis=(1, 2), keepdims=True)      # убираем скачки яркости
    win = cv2.createHanningWindow((W, h), cv2.CV_32F)
    dx = np.zeros(len(f) - 1)
    dy = np.zeros(len(f) - 1)
    resp = np.zeros(len(f) - 1)
    for i in range(1, len(f)):
        (a, b), r = cv2.phaseCorrelate(f[i - 1], f[i], win)
        if np.isfinite(a) and np.isfinite(b):
            dx[i - 1], dy[i - 1] = float(a), float(b)
        resp[i - 1] = float(r) if np.isfinite(r) else 0.0
    k = np.ones(TREND_WIN) / TREND_WIN
    tx = np.convolve(dx, k, mode="same")
    ty = np.convolve(dy, k, mode="same")
    rx = dx - tx
    ry = dy - ty
    shake = np.hypot(rx, ry)                       # px/кадр остаточной тряски
    # RMS по окнам 0.5 с
    w = max(3, int(round(0.5 * FPS)))
    n = len(shake) // w
    if n < 1:
        return None
    win_rms = np.sqrt((shake[: n * w].reshape(n, w) ** 2).mean(axis=1))
    win_t = (np.arange(n) + 0.5) * w / FPS
    return {
        "n_frames": int(len(f)),
        "drift_px_frame": float(np.hypot(dx, dy).mean()),
        "drift_p95": float(np.percentile(np.hypot(dx, dy), 95)),
        "corr_resp": float(np.median(resp)),
        "shake_rms_px": float(np.sqrt((shake ** 2).mean())),
        "shake_p95_px": float(np.percentile(shake, 95)),
        "shake_max_px": float(shake.max()),
        "win_t": win_t, "win_rms": win_rms,
    }


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="measure_shake.py",
        description="измерение тряски камеры по всем клипам из inventory.json")
    p.add_argument("--inventory", default="", help="inventory.json (список клипов)")
    p.add_argument("--out", default="", help="корень проекта для результатов")
    a = p.parse_args(argv)

    project = env_paths.project_root()
    root = os.path.abspath(a.out) if a.out else str(project)
    inv_path = os.path.abspath(a.inventory) if a.inventory else os.path.join(root, "inventory.json")
    if not os.path.exists(inv_path):
        p.error("нет инвентаризации: %s" % inv_path)
    out_json = os.path.join(root, "shake_report.json")
    out_txt = os.path.join(root, "shake_summary.txt")

    inv = json.load(open(inv_path, encoding="utf-8"))
    clips = inv["clips"]
    out = {}
    lines = []
    for i, c in enumerate(clips, 1):
        name = os.path.splitext(c["file"])[0]
        path = c["path"]
        dur = float(c.get("duration_s") or 0)
        res = measure(path)
        if res is None:
            out[name] = {"error": "decode failed", "path": path}
            print("[%d/%d] %s FAIL" % (i, len(clips), name), flush=True)
            continue
        wt = res.pop("win_t")
        wr = res.pop("win_rms")
        head_s = 2.0 if dur > 4.0 else max(1.0, dur / 3.0)
        head_mask = wt <= head_s
        rest_mask = wt > head_s
        head = float(wr[head_mask].mean()) if head_mask.any() else float(wr.mean())
        rest = float(wr[rest_mask].mean()) if rest_mask.any() else float(wr.mean())
        rest_med = float(np.median(wr[rest_mask])) if rest_mask.any() else float(np.median(wr))
        ratio = head / rest if rest > 1e-6 else None

        # точка, после которой тряска держится на уровне остатка клипа
        trim = None
        if ratio is not None and ratio >= 1.6 and len(wr) >= 3:
            ok = rest * 1.3
            for j in range(1, len(wr)):
                if wr[j] <= ok and wr[j:].max() <= ok * 1.25:
                    trim = round(float(wt[j]), 2)
                    break
        res.update({
            "folder": c["folder"], "duration_s": dur, "path": path,
            "head_s": head_s,
            "shake_head_px": round(head, 4),
            "shake_rest_px": round(rest, 4),
            "shake_rest_median_px": round(rest_med, 4),
            "shake_head_px_4k": round(head * SCALE_4K, 1),
            "shake_ratio": round(ratio, 2) if ratio is not None else None,
            "static": bool(res["drift_p95"] < 1.2),
            "trim_suggest_s": trim,
        })
        out[name] = res
        print("[%d/%d] %s dur=%.1fs drift=%.2f shake_head=%.3f rest=%.3f ratio=%s trim=%s"
              % (i, len(clips), name, dur, res["drift_px_frame"], head, rest,
                 ("%.2f" % ratio) if ratio is not None else " n/a", trim), flush=True)
        lines.append(
            "%s %-34s dur=%6.1fs drift=%6.3f | shake: head=%6.3f rest=%6.3f (4K head=%6.1fpx) "
            "| ratio=%5s | trim=%s%s"
            % (name, c["folder"][:34], dur, res["drift_px_frame"], head, rest,
               head * SCALE_4K,
               ("%.2f" % ratio) if ratio is not None else "n/a",
               ("%5.2f" % trim) if trim is not None else "  n/a",
               "  [СТАТИКА]" if res["static"] else ""))

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    with open(out_txt, "w", encoding="utf-8") as f:
        f.write("=== ТРЯСКА: shake = остаток межкадрового сдвига после снятия дрейфа, px/кадр (320px) ===\n")
        f.write("=== head = первые 2 с, rest = остаток клипа. ratio >= 1.6 -> клип «замахован» ===\n")
        f.write("=== trim_suggest_s = с какого момента тряска держится на уровне остатка ===\n\n")
        f.write("\n".join(lines))
    print("DONE", len(out), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
