"""Control-frame QC for video work: compare a source against a processed version.

Usage:
  python frame_qc.py compare --src A.mp4 --graded B.mp4 [--frames 0,220,320,900]
                             [--out QC_DIR] [--sheet SHEET.png]
  python frame_qc.py motion  --src A.mp4 --graded B.mp4 [--start 200] [--count 40]

`compare` extracts the same frame indices from both files, prints grade metrics
per frame (black point, mid, highlight, contrast, saturation, clipping, shadow
noise) plus the difference between the two files, and can write a
source-vs-processed contact sheet.

`motion` measures mean absolute frame-to-frame difference over a frame range in
both files — the way to prove that stabilization actually happened, since the
Resolve API does not report it.

Stdlib + ffmpeg only; PIL is used for the contact sheet when available.
"""
import json
import math
import os
import shutil
import subprocess
import sys

FFMPEG_HINTS = [r"C:\Program Files\ffmpeg\bin", "/usr/local/bin", "/opt/homebrew/bin",
                 "/usr/bin"]


def _env_paths():
    """tools/env_paths.py пакета (если доступен) — источник настроек путей."""
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        pkg_root = os.path.abspath(os.path.join(here, "..", "..", ".."))
        tools_dir = os.path.join(pkg_root, "tools")
        if os.path.isfile(os.path.join(tools_dir, "env_paths.py")):
            if tools_dir not in sys.path:
                sys.path.insert(0, tools_dir)
            import env_paths
            return env_paths
    except Exception:
        pass
    return None


def tool(name):
    p = shutil.which(name)
    if p:
        return p
    ep = _env_paths()
    if ep is not None:
        found = ep.ffmpeg() if name == "ffmpeg" else ep.ffprobe()
        if found and os.path.isfile(found):
            return found
    for h in FFMPEG_HINTS:
        c = os.path.join(h, name + (".exe" if os.name == "nt" else ""))
        if os.path.isfile(c):
            return c
    return name


def pct(vals, p):
    if not vals:
        return 0.0
    k = (len(vals) - 1) * p / 100.0
    f = math.floor(k)
    c = min(f + 1, len(vals) - 1)
    return vals[f] + (vals[c] - vals[f]) * (k - f)


def read_png(path):
    """Return (width, height, rgb bytes) using PIL when available."""
    try:
        from PIL import Image
        im = Image.open(path).convert("RGB")
        return im.width, im.height, im.tobytes()
    except Exception:
        return None


def read_rgb(path, w, h):
    cmd = [tool("ffmpeg"), "-v", "error", "-i", path, "-vf", "scale=%d:%d" % (w, h),
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    r = subprocess.run(cmd, capture_output=True, timeout=900)
    size = w * h * 3
    n = len(r.stdout) // size
    return [r.stdout[i * size:(i + 1) * size] for i in range(n)]


def stats(buf):
    lums, sats = [], []
    clipped = 0
    total = 0
    for i in range(0, len(buf) - 2, 3):
        r, g, b = buf[i] / 255.0, buf[i + 1] / 255.0, buf[i + 2] / 255.0
        lums.append(0.2126 * r + 0.7152 * g + 0.0722 * b)
        mx, mn = max(r, g, b), min(r, g, b)
        sats.append(0.0 if mx <= 1e-6 else (mx - mn) / mx)
        if mx >= 0.999:
            clipped += 1
        total += 1
    lums.sort()
    shadow = [x for x in lums if x <= pct(lums, 10)]
    ms = sum(shadow) / len(shadow) if shadow else 0.0
    sd = math.sqrt(sum((x - ms) ** 2 for x in shadow) / len(shadow)) if shadow else 0.0
    return {
        "black_p01": round(pct(lums, 1), 4),
        "mid_p50": round(pct(lums, 50), 4),
        "high_p99": round(pct(lums, 99), 4),
        "contrast": round(pct(lums, 99) - pct(lums, 1), 4),
        "mean_sat": round(sum(sats) / len(sats), 4) if sats else 0.0,
        "clip_pct": round(clipped / total * 100, 3) if total else 0.0,
        "shadow_std": round(sd, 4),
    }


def mean_abs_diff(a, b):
    n = min(len(a), len(b))
    if n == 0:
        return None
    s = 0
    for i in range(0, n, 3):
        s += abs(a[i] - b[i]) + abs(a[i + 1] - b[i + 1]) + abs(a[i + 2] - b[i + 2])
    return round(s / (n * 3) / 255.0, 5)


def extract(path, indices, outdir, tag):
    os.makedirs(outdir, exist_ok=True)
    expr = "+".join("eq(n\\,%d)" % i for i in indices)
    pattern = os.path.join(outdir, "%s_%%03d.png" % tag)
    cmd = [tool("ffmpeg"), "-v", "error", "-y", "-i", path,
           "-vf", "select='%s'" % expr, "-fps_mode", "passthrough", "-start_number", "0",
           pattern]
    subprocess.run(cmd, capture_output=True, timeout=900)
    produced = sorted(p for p in os.listdir(outdir) if p.startswith(tag + "_") and p.endswith(".png"))
    return [os.path.join(outdir, p) for p in produced]


def cmd_compare(args):
    src = args.get("--src")
    graded = args.get("--graded")
    outdir = args.get("--out", "qc")
    sheet = args.get("--sheet")
    frames = [int(x) for x in args.get("--frames", "0,220,320,900").split(",") if x.strip()]
    if not src or not graded:
        print("compare needs --src and --graded")
        return 1
    os.makedirs(outdir, exist_ok=True)
    a_imgs = extract(src, frames, outdir, "src")
    b_imgs = extract(graded, frames, outdir, "graded")
    if not a_imgs or not b_imgs:
        print("frame extraction failed")
        return 1
    a_raw = read_png(a_imgs[0]) if read_png(a_imgs[0]) else None
    b_raw = read_png(b_imgs[0]) if read_png(b_imgs[0]) else None
    rows = []
    print("%-6s %-42s %-42s %s" % ("frame", "SOURCE", "GRADED", "mean|diff|"))
    for i, (pa, pb) in enumerate(zip(a_imgs, b_imgs)):
        da, db = read_png(pa), read_png(pb)
        if not da or not db:
            continue
        sa, sb = stats(da[2]), stats(db[2])
        diff = mean_abs_diff(da[2], db[2])
        rows.append({"frame": frames[i] if i < len(frames) else i, "source": sa, "graded": sb, "mean_diff": diff})
        print("%-6s %-42s %-42s %s" % (
            frames[i] if i < len(frames) else i,
            "blk %.3f mid %.3f hi %.3f con %.3f sat %.3f clip %.2f%%" % (
                sa["black_p01"], sa["mid_p50"], sa["high_p99"], sa["contrast"], sa["mean_sat"], sa["clip_pct"]),
            "blk %.3f mid %.3f hi %.3f con %.3f sat %.3f clip %.2f%%" % (
                sb["black_p01"], sb["mid_p50"], sb["high_p99"], sb["contrast"], sb["mean_sat"], sb["clip_pct"]),
            diff))
    if sheet:
        try:
            from PIL import Image
            ims = []
            for pa, pb in zip(a_imgs, b_imgs):
                ia, ib = Image.open(pa).convert("RGB"), Image.open(pb).convert("RGB")
                w, h = ia.width, ia.height
                pair = Image.new("RGB", (w * 2, h))
                pair.paste(ia, (0, 0))
                pair.paste(ib, (w, 0))
                ims.append(pair)
            w, h = ims[0].width, ims[0].height
            cols = 2
            rowsn = (len(ims) + cols - 1) // cols
            canvas = Image.new("RGB", (w * cols, h * rowsn), (18, 18, 18))
            for i, im in enumerate(ims):
                canvas.paste(im, ((i % cols) * w, (i // cols) * h))
            canvas.save(sheet)
            print("contact sheet: %s" % sheet)
        except Exception as e:
            print("contact sheet skipped: %s" % e)
    with open(os.path.join(outdir, "qc_report.json"), "w", encoding="utf-8") as f:
        json.dump({"src": src, "graded": graded, "frames": rows}, f, indent=2)
    print("report: %s" % os.path.join(outdir, "qc_report.json"))
    return 0


def cmd_motion(args):
    src = args.get("--src")
    graded = args.get("--graded")
    start = int(args.get("--start", 0))
    count = int(args.get("--count", 40))
    if not src or not graded:
        print("motion needs --src and --graded")
        return 1
    w, h = 480, 270
    a = read_rgb(src, w, h)
    b = read_rgb(graded, w, h)
    if len(a) < 2 or len(b) < 2:
        print("not enough frames")
        return 1

    def motion(frames):
        vals = []
        for i in range(len(frames) - 1):
            p, q = frames[i], frames[i + 1]
            s = 0
            for k in range(0, len(p), 3 * 7):  # sparse sample, enough for motion energy
                s += abs(p[k] - q[k]) + abs(p[k + 1] - q[k + 1]) + abs(p[k + 2] - q[k + 2])
            cnt = len(range(0, len(p), 3 * 7))
            vals.append(s / max(cnt * 3 * 255, 1))
        return vals

    ma = motion(a[start:start + count])
    mb = motion(b[start:start + count])
    if not ma or not mb:
        print("no overlap")
        return 1
    am, bm = sum(ma) / len(ma), sum(mb) / len(mb)
    print("frames %d..%d" % (start, start + count - 1))
    print("  source mean |frame diff| = %.5f" % am)
    print("  graded mean |frame diff| = %.5f" % bm)
    print("  motion reduction = %.1f%%" % (100 * (1 - bm / am)) if am else "  n/a")
    return 0


def parse(argv):
    args = {}
    i = 0
    while i < len(argv):
        if argv[i].startswith("--"):
            key = argv[i]
            val = argv[i + 1] if i + 1 < len(argv) and not argv[i + 1].startswith("--") else ""
            args[key] = val
            i += 2 if val else 1
        else:
            i += 1
    return args


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    mode = sys.argv[1]
    args = parse(sys.argv[2:])
    if mode == "compare":
        return cmd_compare(args)
    if mode == "motion":
        return cmd_motion(args)
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
