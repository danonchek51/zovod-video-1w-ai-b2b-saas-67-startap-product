# -*- coding: utf-8 -*-
"""resolve_probe_env.py — READ-ONLY пробник окружения Resolve.

Первый шаг протокола (AGENTS.md, п.2): сообщить состояние, ничего не меняя.

Запуск внутри Resolve (MCP davinci-resolve -> run_script_unsafe):
    exec(compile(open(r'<ПАКЕТ>/tools/resolve_probe_env.py',
                      encoding='utf-8').read(), 'resolve_probe_env.py', 'exec'))

Печатает JSON. Ничего не мутирует.
"""
import json
import os
import traceback

try:
    resolve = globals().get("resolve")
    out = {"ok": False}
    if resolve is None:
        out["error"] = "переменная resolve недоступна — скрипт вне Resolve"
    else:
        pm = resolve.GetProjectManager()
        out["resolve_version"] = getattr(resolve, "GetVersionString", lambda: "?")()
        out["projects"] = pm.GetProjectListInCurrentFolder() or []
        cur = pm.GetCurrentProject()
        if cur is None:
            out["current_project"] = None
        else:
            out["current_project"] = cur.GetName()
            tl = cur.GetCurrentTimeline()
            out["timelines"] = cur.GetTimelineCount()
            if tl is None:
                out["current_timeline"] = None
            else:
                out["current_timeline"] = tl.GetName()
                out["timeline_settings"] = tl.GetSettings()
                out["start_frame"] = tl.GetStartFrame()
                out["end_frame"] = tl.GetEndFrame()
                out["markers"] = {str(k): str(v) for k, v in (tl.GetMarkers() or {}).items()}
                tracks = {}
                for ttype in ("video", "audio"):
                    n = tl.GetTrackCount(ttype)
                    tinfo = []
                    for i in range(1, n + 1):
                        items = tl.GetItemListInTrack(ttype, i) or []
                        tinfo.append({
                            "index": i,
                            "name": tl.GetTrackName(ttype, i),
                            "items": len(items),
                            "subtype": (tl.GetTrackSubType(ttype, i)
                                        if ttype == "audio" else None),
                        })
                    tracks[ttype] = tinfo
                out["tracks"] = tracks
                mp = cur.GetMediaPool()
                out["media_pool_items"] = mp.GetClipCount() if mp else None
        out["ok"] = True
    print("PROBE_JSON:" + json.dumps(out, ensure_ascii=False, default=str))
except Exception:
    print("PROBE_JSON:" + json.dumps(
        {"ok": False, "error": traceback.format_exc()}, ensure_ascii=False))
