# -*- coding: utf-8 -*-
"""inventory_scan.py — инвентаризация всего, что лежит в папке исходников.

Пишет JSON со списком папок/файлов (UTF-8), чтобы читать без потерь кириллицы,
и текстовую сводку по папкам.

    python inventory_scan.py --src <папка с исходниками> [--out <корень проекта>]
                             [--json <имя файла отчёта>]

Исходники открываются ТОЛЬКО НА ЧТЕНИЕ.
"""
import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import env_paths  # noqa: E402

FFPROBE = env_paths.ffprobe() or "ffprobe"
VIDEO_EXT = (".mp4", ".mov", ".mkv", ".mxf", ".avi")


def scan(root):
    rows = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for fn in sorted(filenames):
            if not fn.lower().endswith(VIDEO_EXT):
                continue
            full = os.path.join(dirpath, fn)
            folder = os.path.relpath(dirpath, root)
            info = {"file": fn, "folder": folder, "path": full,
                    "size_mb": round(os.path.getsize(full) / 1048576.0, 1)}
            try:
                cmd = [FFPROBE, "-v", "error", "-print_format", "json",
                       "-show_format", "-show_streams", full]
                r = subprocess.run(cmd, capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", timeout=300)
                d = json.loads(r.stdout)
                v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), None)
                a = [s for s in d.get("streams", []) if s.get("codec_type") == "audio"]
                fmt = d.get("format", {})
                info["duration_s"] = round(float(fmt.get("duration", 0) or 0), 2)
                if v:
                    info.update(res="%sx%s" % (v.get("width"), v.get("height")),
                                fps=v.get("avg_frame_rate"),
                                codec=v.get("codec_name"),
                                pix=v.get("pix_fmt"),
                                primaries=v.get("color_primaries"),
                                transfer=v.get("color_transfer"),
                                nb_frames=v.get("nb_frames"))
                info["audio"] = [{"codec": s.get("codec_name"), "ch": s.get("channels"),
                                  "sr": s.get("sample_rate"),
                                  "layout": s.get("channel_layout")} for s in a]
                tc = []
                for k, v2 in (fmt.get("tags") or {}).items():
                    if "timecode" in k.lower():
                        tc.append(v2)
                for s in d.get("streams", []):
                    for k, v2 in (s.get("tags") or {}).items():
                        if "timecode" in k.lower():
                            tc.append(v2)
                info["timecode"] = tc
            except Exception as e:
                info["error"] = str(e)
            rows.append(info)
    return rows


def summarize(rows, root):
    folders = {}
    for r in rows:
        folders.setdefault(r["folder"], []).append(r)
    lines = ["root: %s" % root, "total clips: %d" % len(rows), ""]
    for folder in sorted(folders):
        files = folders[folder]
        tot = sum(x.get("duration_s", 0) for x in files)
        lines.append("%-45s %2d файлов  %8.1f с" % (folder, len(files), tot))
        for x in sorted(files, key=lambda z: z["file"]):
            lines.append("    %-14s %8.2f с  %-9s %-9s %s" % (
                x["file"], x.get("duration_s", 0), x.get("res", "?"),
                x.get("fps", "?"), (x.get("audio") or [{}])[0].get("codec", "нет звука")))
    return lines


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="inventory_scan.py",
        description="инвентаризация исходников (ffprobe по каждому видео)")
    p.add_argument("--src", default="", help="папка с исходниками (только чтение)")
    p.add_argument("--out", default="", help="корень проекта для результатов")
    p.add_argument("--json", default="inventory.json", help="имя файла отчёта")
    a = p.parse_args(argv)

    project = env_paths.project_root()
    root = os.path.abspath(a.out) if a.out else str(project)
    src = os.path.abspath(a.src) if a.src else str(env_paths.src_root() or "")
    if not src or not os.path.isdir(src):
        p.error("нет папки с исходниками (укажи --src)")

    rows = scan(src)
    out_json = os.path.join(root, a.json)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump({"root": src, "count": len(rows), "clips": rows},
                  f, ensure_ascii=False, indent=2)
    out_txt = os.path.join(root, os.path.splitext(a.json)[0] + "_summary.txt")
    with open(out_txt, "w", encoding="utf-8") as f:
        f.write("\n".join(summarize(rows, src)))
    print("written", out_json, len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
