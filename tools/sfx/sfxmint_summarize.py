#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Компактная сводка по результатам SFXMint (search_crash.json -> читаемый отчёт).

    python sfxmint_summarize.py <search_crash.json> [--json <out.json>]
"""
import argparse
import json
import sys


def brief_sound(s, keys=("slug", "title", "duration_ms", "character", "score", "match",
                         "attack_ms", "tail_ms", "centroid_hz", "loop", "page_url")):
    parts = []
    for k in keys:
        if k in s and s[k] is not None:
            v = s[k]
            if isinstance(v, list):
                v = ",".join(str(x) for x in v)
            parts.append("%s=%s" % (k, v))
    for k in ("mp3_url", "wav_url", "file_url", "url"):
        if s.get(k):
            parts.append("%s=%s" % (k, s[k]))
    return "  ".join(parts)


def summarize(path):
    """Компактная сводка: список блоков с количеством найденного."""
    data = json.load(open(path, encoding="utf-8"))
    out = []
    for block in data:
        r = block.get("result")
        row = {"tool": block.get("tool"), "args": block.get("args", {}),
               "results": 0, "closest": 0, "alternates": 0,
               "library_fit": None, "not_found": False,
               "generate_available": None, "error": None}
        if isinstance(r, dict):
            row["library_fit"] = r.get("library_fit")
            row["not_found"] = bool(r.get("not_found"))
            row["results"] = len(r.get("results") or [])
            row["closest"] = len(r.get("closest") or [])
            row["alternates"] = len(r.get("alternates") or [])
            row["generate_available"] = r.get("generate_available")
            row["error"] = r.get("error")
        out.append(row)
    return out


def main(path):
    data = json.load(open(path, encoding="utf-8"))
    for block in data:
        print("=" * 100)
        print("TOOL:", block["tool"], "ARGS:", json.dumps(block["args"], ensure_ascii=False))
        r = block["result"]
        if not isinstance(r, dict):
            print("  ", str(r)[:400])
            continue
        if "library_fit" in r:
            print("  library_fit:", r.get("library_fit"))
        if r.get("not_found"):
            print("  not_found")
        res = r.get("results") or []
        print("  results: %d" % len(res))
        for s in res:
            print("   *", brief_sound(s))
        cl = r.get("closest") or []
        print("  closest: %d" % len(cl))
        for s in cl:
            mt = s.get("missing_terms")
            print("   ~", brief_sound(s), "| missing_terms=%s" % (mt,))
        ga = r.get("generate_available")
        if ga:
            print("  generate_available:", json.dumps(ga, ensure_ascii=False)[:600])
        if "alternates" in r:
            print("  alternates:")
            for s in r.get("alternates", []):
                print("   a", brief_sound(s))
        if "sound" in r:
            print("  sound:", brief_sound(r["sound"]))
        if r.get("error"):
            print("  ERROR:", json.dumps(r["error"], ensure_ascii=False)[:400])


if __name__ == "__main__":
    p = argparse.ArgumentParser(
        prog="sfxmint_summarize.py",
        description="компактная сводка по результатам SFXMint")
    p.add_argument("input", help="JSON-файл с результатами поиска")
    p.add_argument("--json", default="", help="дополнительно записать сводку в JSON")
    a = p.parse_args()
    main(a.input)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(summarize(a.input), fh, ensure_ascii=False, indent=2)
        print("summary:", a.json)
