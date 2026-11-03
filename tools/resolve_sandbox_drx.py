# -*- coding: utf-8 -*-
"""resolve_sandbox_drx.py — смоук-тест DRX на Resolve 21.1.1 (песочница), v2.

Проверяет, не только «ApplyGradeFromDRX вернул True», но и что грейд РЕАЛЬНО
применился: число нод, подписи, состав тулов и рендер кадра до/после.

Проект AGENT_SANDBOX3 создаётся и удаляется за собой.

Пути: $ZOVOD_SANDBOX_SRC (папка с исходниками), $ZOVOD_SANDBOX_DRX (папка с .drx),
$ZOVOD_SANDBOX_OUT (куда писать контрольные кадры). По умолчанию — ./drx_lab и ./drx_lab/stills.
"""
import json
import os
import traceback


def _env(name, default_rel):
    v = os.environ.get(name, "")
    if v:
        return os.path.abspath(v)
    return os.path.abspath(os.path.join(os.getcwd(), default_rel))


SRC_DIR = _env("ZOVOD_SANDBOX_SRC", "src")
DRX_DIR = _env("ZOVOD_SANDBOX_DRX", "drx_lab")
OUT_DIR = _env("ZOVOD_SANDBOX_OUT", os.path.join("drx_lab", "stills"))
PROJ = "AGENT_SANDBOX3"
TL = "AGENT_SANDBOX3_V1"
R = {"steps": {}}
_st = {}


def call(obj, name, *args):
    """Вызов, который терпит и метод, и свойство."""
    v = getattr(obj, name, None)
    if v is None:
        return None
    if callable(v):
        return v(*args)
    return v


def step(name, fn):
    try:
        R["steps"][name] = {"ok": True, "result": fn()}
    except Exception as e:
        R["steps"][name] = {"ok": False, "error": "%s: %s" % (type(e).__name__, e),
                            "trace": traceback.format_exc()[-300:]}


resolve = globals().get("resolve")
if resolve is None:
    print("DRX_JSON:" + json.dumps({"ok": False, "error": "нет resolve"}, ensure_ascii=False))
else:
    os.makedirs(OUT_DIR, exist_ok=True)
    pm = resolve.GetProjectManager()

    def _mk():
        p = pm.CreateProject(PROJ)
        if p is None:
            p = pm.LoadProject(PROJ)
        if p is None:
            raise RuntimeError("песочница не создалась")
        mp = p.GetMediaPool()
        tl = mp.CreateEmptyTimeline(TL)
        p.SetCurrentTimeline(tl)
        cand = None
        for fn in sorted(os.listdir(SRC_DIR)):
            if fn.lower().endswith(".mp4"):
                cand = os.path.join(SRC_DIR, fn)
                break
        items = mp.ImportMedia([cand])
        lst = list(items.keys()) if isinstance(items, dict) else list(items)
        if not lst:
            raise RuntimeError("импорт не дал элементов")
        _st.update(p=p, mp=mp, tl=tl, item=lst[0], src=cand)
        return {"project": p.GetName(), "src": os.path.basename(cand)}
    step("setup", _mk)

    mp, tl, p = _st.get("mp"), _st.get("tl"), _st.get("p")

    def _append():
        res = mp.AppendToTimeline([{"mediaPoolItem": _st["item"], "startFrame": 0,
                                     "endFrame": 80, "mediaType": 1,
                                     "trackIndex": 1, "recordFrame": 90000}])
        if not res:
            raise RuntimeError("AppendToTimeline вернул пусто")
        _st["tlitem"] = res[0]
        return {"start": res[0].GetStart(), "end": res[0].GetEnd()}
    step("append_video", _append)

    tlitem = _st.get("tlitem")

    def _graph(tag=None):
        g = tlitem.GetNodeGraph()
        n = call(g, "GetNumNodes")
        info = {"nodes": n}
        if isinstance(n, int) and n > 0:
            labels, tools = [], []
            for i in range(1, n + 1):
                labels.append(call(g, "GetNodeLabel", i))
                try:
                    tools.append(call(g, "GetToolsInNode", i))
                except Exception as e:
                    tools.append("err: %s" % e)
            info["labels"] = labels
            info["tools"] = tools
        return info
    step("graph_before", _graph)

    def _page():
        out = {"page": call(resolve, "GetCurrentPage")}
        try:
            resolve.OpenPage("color")
            out["page_after_open"] = call(resolve, "GetCurrentPage")
        except Exception as e:
            out["open_page_error"] = "%s: %s" % (type(e).__name__, e)
        try:
            tl.SetCurrentTimecode("01:00:00:04")
            out["timecode"] = tl.GetCurrentTimecode()
        except Exception as e:
            out["tc_error"] = "%s: %s" % (type(e).__name__, e)
        try:
            out["current_video_item"] = str(call(tl, "GetCurrentVideoItem"))
        except Exception as e:
            out["cvi_error"] = str(e)
        return out
    step("page_and_playhead", _page)

    def _export(tag):
        path = os.path.join(OUT_DIR, "frame_%s.png" % tag)
        try:
            tl.SetCurrentTimecode("01:00:00:04")
        except Exception:
            pass
        ok = p.ExportCurrentFrameAsStill(path)
        return {"path": path, "returned": ok, "exists": os.path.exists(path),
                "size": os.path.getsize(path) if os.path.exists(path) else 0}
    step("export_before", lambda: _export("before"))

    for drx in ("drx_primary_r21.drx", "drx_window_r21.drx", "drx_multinode_r21.drx"):
        def _apply(d=drx):
            g = tlitem.GetNodeGraph()
            ok = g.ApplyGradeFromDRX(os.path.join(DRX_DIR, d), 0)
            return {"file": d, "apply_returned": ok}
        step("apply_" + drx, _apply)
        step("graph_after_" + drx, _graph)
        step("export_after_" + drx, (lambda d=drx: _export(d.replace(".drx", ""))))

    def _cleanup():
        out = {}
        pr = _st.get("p")
        try:
            out["close"] = pm.CloseProject(pr)
        except Exception as e:
            out["close_error"] = str(e)
        try:
            out["delete"] = pm.DeleteProject(PROJ)
        except Exception as e:
            out["delete_error"] = str(e)
        out["projects_left"] = pm.GetProjectListInCurrentFolder()
        return out
    step("cleanup", _cleanup)

    R["ok"] = True
    print("DRX_JSON:" + json.dumps(R, ensure_ascii=False, default=str))
