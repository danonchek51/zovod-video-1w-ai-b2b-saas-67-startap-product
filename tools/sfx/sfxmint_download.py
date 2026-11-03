#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sfxmint_download.py - скачать оригиналы звуков SFXMint в проект.

Правила (из инструкций сервера SFXMint):
  * хранить ОРИГИНАЛ рядом с производными;
  * писать URL источника (page_url, не файловый с g=), лицензию, SHA-256;
  * скачивания без ключа: 20 РАЗНЫХ звуков в сутки на сеть; 429 download_limit
    не ретраить — сообщить пользователю.

Использование:
    python sfxmint_download.py <manifest.json> [--out <папка>]
manifest.json: [{"slug": "...", "page_url": "...", "license": "CC0-1.0",
                  "wav_sha256": "...", "use": "назначение в ролике"}, ...]
"""
import argparse
import hashlib
import json
import os
import sys
import time
import urllib.request
import urllib.error

DL = "https://sfxmint.com/dl/%s.wav?src=mcp"
UA = {"User-Agent": "sfxmint-download/1.0"}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url, dest):
    if os.path.exists(dest) and os.path.getsize(dest) > 1024:
        return "cached", os.path.getsize(dest)
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:400]
        return "HTTP %s: %s" % (e.code, body), 0
    with open(dest, "wb") as fh:
        fh.write(data)
    return "ok", len(data)


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="sfxmint_download.py",
        description="скачать оригиналы звуков SFXMint по манифесту")
    p.add_argument("manifest", help="путь к manifest.json")
    p.add_argument("--out", default="",
                   help="папка для оригиналов (по умолчанию <папка манифеста>/orig)")
    a = p.parse_args(argv)

    manifest_path = os.path.abspath(a.manifest)
    with open(manifest_path, encoding="utf-8") as fh:
        manifest = json.load(fh)
    out_dir = os.path.abspath(a.out) if a.out else os.path.join(
        os.path.dirname(manifest_path), "orig")
    os.makedirs(out_dir, exist_ok=True)

    report = []
    for item in manifest:
        slug = item["slug"]
        dest = os.path.join(out_dir, slug + ".wav")
        status, size = download(DL % slug, dest)
        rec = {"slug": slug, "file": dest, "status": status, "bytes": size}
        if status == "ok" or status == "cached":
            got = sha256_file(dest)
            rec["sha256_local"] = got
            exp = item.get("wav_sha256")
            rec["sha256_expected"] = exp
            rec["sha256_match"] = (got == exp) if exp else None
            rec["page_url"] = item.get("page_url")
            rec["license"] = item.get("license", "CC0-1.0")
            rec["use"] = item.get("use", "")
        report.append(rec)
        print("%-26s %-8s %10s  sha=%s  match=%s" %
              (slug, status, size, rec.get("sha256_local", "")[:16], rec.get("sha256_match")))
        time.sleep(0.6)

    rep_path = os.path.join(os.path.dirname(manifest_path), "download_report.json")
    with open(rep_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print("report:", rep_path)


if __name__ == "__main__":
    sys.exit(main())
