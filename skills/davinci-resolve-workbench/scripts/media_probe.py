"""Probe media files or a whole folder of them: technical metadata + palette.

Usage:
  python media_probe.py <file-or-folder> [<file-or-folder> ...] [--frames 3]
                       [--size 320x180] [--json] [--list]

A folder argument is expanded recursively: every media file inside is probed and
printed as an inventory, so handing the agent a path is enough to start.

Stdlib + ffmpeg only. For every file it reports container/codec/resolution/fps/
frame count/duration and the colour tags (primaries/transfer/matrix/range) that
decide how a grade has to be built, plus palette statistics of a few evenly
spaced frames: black point, mid, highlight, contrast, mean saturation, shadow
noise and a saturation-weighted hue histogram that reveals dominant colour
pairs.
"""
import json
import math
import os
import shutil
import subprocess
import sys

FFMPEG_HINTS = [r"C:\Program Files\ffmpeg\bin", "/usr/local/bin", "/opt/homebrew/bin",
                 "/usr/bin"]
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm", ".mts", ".m2ts", ".wmv", ".flv"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".dng", ".exr", ".arw", ".nef"}
AUDIO_EXT = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".m4b"}


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


def ffprobe(path):
    cmd = [tool("ffprobe"), "-v", "error", "-show_format", "-show_streams",
           "-print_format", "json", path]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        return {"error": r.stderr.strip()[:400]}
    return json.loads(r.stdout or "{}")


def pick_stream(info, kind):
    for s in info.get("streams", []):
        if s.get("codec_type") == kind:
            return s
    return {}


def read_frames(path, count, w, h, duration=None):
    """Decode `count` spread-out frames as rgb24 and return them as byte blocks.

    Uses a seek per sample instead of decoding the whole file, so probing a
    folder of long clips stays fast.
    """
    if duration is None:
        info = ffprobe(path)
        duration = float((info.get("format") or {}).get("duration") or 0)
    size = w * h * 3
    out = []
    if duration and duration > 0:
        for i in range(count):
            t = duration * (i + 0.5) / count
            cmd = [tool("ffmpeg"), "-v", "error", "-ss", "%.3f" % t, "-i", path,
                   "-vf", "scale=%d:%d" % (w, h), "-frames:v", "1",
                   "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
            r = subprocess.run(cmd, capture_output=True, timeout=300)
            if len(r.stdout) >= size:
                out.append(r.stdout[:size])
    else:
        cmd = [tool("ffmpeg"), "-v", "error", "-i", path, "-vf", "scale=%d:%d" % (w, h),
               "-frames:v", str(count), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
        r = subprocess.run(cmd, capture_output=True, timeout=600)
        raw = r.stdout
        n = len(raw) // size
        for i in range(min(n, count)):
            out.append(raw[i * size:(i + 1) * size])
    return out


def pct(sorted_vals, p):
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * p / 100.0
    f = math.floor(k)
    c = min(f + 1, len(sorted_vals) - 1)
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def frame_stats(buf):
    lums = []
    sats = []
    hues = []
    vals = []
    step = 3
    for i in range(0, len(buf) - 2, step):
        r, g, b = buf[i] / 255.0, buf[i + 1] / 255.0, buf[i + 2] / 255.0
        mx = max(r, g, b)
        mn = min(r, g, b)
        lums.append(0.2126 * r + 0.7152 * g + 0.0722 * b)
        sats.append(0.0 if mx <= 1e-6 else (mx - mn) / mx)
        vals.append(mx)
        if mx <= 1e-6:
            hues.append(None)
            continue
        d = mx - mn
        if d <= 1e-6:
            h = 0.0
        elif mx == r:
            h = ((g - b) / d) % 6
        elif mx == g:
            h = (b - r) / d + 2
        else:
            h = (r - g) / d + 4
        hues.append(h * 60.0)
    lums.sort()
    shadow = [x for x in lums if x <= pct(lums, 10)]
    mean_shadow = sum(shadow) / len(shadow) if shadow else 0.0
    var = sum((x - mean_shadow) ** 2 for x in shadow) / len(shadow) if shadow else 0.0
    hist = [0.0] * 12
    for h, s, v in zip(hues, sats, vals):
        if h is None or s < 0.08:
            continue
        idx = int(h // 30) % 12
        hist[idx] += s * v
    total = sum(hist) or 1.0
    hist = [round(x / total * 100, 1) for x in hist]
    names = ["red", "orange", "yellow", "yel-green", "green", "spring", "cyan",
             "azure", "blue", "violet", "magenta", "rose"]
    dominant = sorted(zip(hist, names), reverse=True)[:3]
    return {
        "black_p01": round(pct(lums, 1), 4),
        "mid_p50": round(pct(lums, 50), 4),
        "high_p99": round(pct(lums, 99), 4),
        "contrast": round(pct(lums, 99) - pct(lums, 1), 4),
        "mean_sat": round(sum(sats) / len(sats), 4),
        "shadow_std": round(math.sqrt(var), 4),
        "hue_hist_pct": dict(zip(names, hist)),
        "dominant_hues": ["%s %.1f%%" % (n, p) for p, n in dominant],
    }


def describe(path, frames, w, h):
    info = ffprobe(path)
    if "error" in info:
        return {"file": path, "error": info["error"]}
    v = pick_stream(info, "video")
    a = pick_stream(info, "audio")
    fmt = info.get("format", {})
    fps = v.get("avg_frame_rate") or v.get("r_frame_rate") or "?"
    out = {
        "file": path,
        "size_bytes": int(fmt.get("size") or 0),
        "duration_s": round(float(fmt.get("duration") or 0), 3),
        "bit_rate": int(fmt.get("bit_rate") or 0),
        "container": fmt.get("format_name"),
        "video": {
            "codec": v.get("codec_name"),
            "width": v.get("width"),
            "height": v.get("height"),
            "fps": fps,
            "nb_frames": v.get("nb_frames"),
            "pix_fmt": v.get("pix_fmt"),
            "color_primaries": v.get("color_primaries"),
            "color_transfer": v.get("color_transfer"),
            "color_matrix": v.get("color_matrix"),
            "color_range": v.get("color_range"),
            "field_order": v.get("field_order"),
        },
        "audio": ({"codec": a.get("codec_name"), "channels": a.get("channels"),
                   "sample_rate": a.get("sample_rate")} if a else None),
        "timecode": (fmt.get("tags") or {}).get("timecode"),
    }
    try:
        bufs = read_frames(path, frames, w, h, duration=out["duration_s"])
        out["palette"] = frame_stats(bufs[0]) if bufs else None
        if len(bufs) > 1:
            out["palette_per_frame"] = [frame_stats(b) for b in bufs[1:]]
    except Exception as e:
        out["palette_error"] = str(e)
    return out


def expand(path):
    """Return (files, kind) where kind is 'video', 'image', 'audio' or 'other'."""
    if os.path.isfile(path):
        ext = os.path.splitext(path)[1].lower()
        if ext in VIDEO_EXT:
            return [path], "video"
        if ext in IMAGE_EXT:
            return [path], "image"
        if ext in AUDIO_EXT:
            return [path], "audio"
        return [path], "other"
    if not os.path.isdir(path):
        return [], "missing"
    videos, images, audios, others = [], [], [], []
    for root, _dirs, names in os.walk(path):
        for n in sorted(names):
            if n.startswith("."):
                continue
            ext = os.path.splitext(n)[1].lower()
            full = os.path.join(root, n)
            if ext in VIDEO_EXT:
                videos.append(full)
            elif ext in IMAGE_EXT:
                images.append(full)
            elif ext in AUDIO_EXT:
                audios.append(full)
            else:
                others.append(full)
    return videos + images + audios, "folder"


def main():
    args = sys.argv[1:]
    as_json = "--json" in args
    only_list = "--list" in args
    args = [a for a in args if a not in ("--json", "--list")]
    frames, w, h = 3, 320, 180
    roots = []
    i = 0
    while i < len(args):
        if args[i] == "--frames":
            frames = int(args[i + 1]); i += 2
        elif args[i] == "--size":
            wh = args[i + 1].split("x"); w, h = int(wh[0]), int(wh[1]); i += 2
        else:
            roots.append(args[i]); i += 1
    if not roots:
        print(__doc__)
        return 1

    results = []
    for root in roots:
        files, kind = expand(root)
        if kind == "missing":
            print("MISSING %s" % root)
            continue
        if kind == "folder":
            print("### %s  (%d media files found)" % (root, len(files)))
            print("#" * 78)
        for f in files:
            if not os.path.isfile(f):
                continue
            ext = os.path.splitext(f)[1].lower()
            if only_list or ext in AUDIO_EXT:
                results.append({"file": f, "kind": "audio" if ext in AUDIO_EXT else "media",
                                "size_bytes": os.path.getsize(f)})
                continue
            results.append(describe(f, frames, w, h))

    if as_json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return 0

    for r in results:
        print("=" * 78)
        print(r["file"])
        if "error" in r:
            print("  error:", r["error"])
            continue
        if r.get("kind") == "audio" or "video" not in r:
            print("  %d bytes" % r.get("size_bytes", 0))
            continue
        v = r["video"]
        print("  container %s | %s %sx%s @ %s | %s frames | %.2fs | %d bps"
              % (r["container"], v["codec"], v["width"], v["height"], v["fps"],
                 v["nb_frames"], r["duration_s"], r["bit_rate"]))
        print("  colour: primaries=%s transfer=%s matrix=%s range=%s field=%s | pix=%s"
              % (v["color_primaries"], v["color_transfer"], v["color_matrix"],
                 v["color_range"], v["field_order"], v["pix_fmt"]))
        print("  audio: %s | timecode: %s" % (r["audio"], r["timecode"]))
        p = r.get("palette")
        if p:
            print("  palette: black %.3f | mid %.3f | high %.3f | contrast %.3f | sat %.3f | shadow_std %.4f"
                  % (p["black_p01"], p["mid_p50"], p["high_p99"], p["contrast"],
                     p["mean_sat"], p["shadow_std"]))
            print("  dominant hues: %s" % ", ".join(p["dominant_hues"]))
        elif r.get("palette_error"):
            print("  palette: unavailable (%s)" % r["palette_error"][:120])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
