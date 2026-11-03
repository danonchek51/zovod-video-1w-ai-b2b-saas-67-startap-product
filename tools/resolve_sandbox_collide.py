# -*- coding: utf-8 -*-
"""resolve_sandbox_collide.py — проверка семантики AppendToTimeline и Dialogue Leveler.

Проверяет утверждения отчётов:
  1. Что происходит, когда recordFrame попадает ВНУТРЬ существующего айтема:
     overwrite / отказ / вставка рядом?
  2. Есть ли одноключевой getter GetProperty (в отчёте он используется) и работает ли.
  3. Пишется ли AudioDialogueLevelerBackgroundReduction через SetProperties
     (в отчёте названо UI-only) — проверяем записью + readback.

Проект AGENT_SANDBOX2 создаётся и удаляется за собой.

Тестовый WAV (тон 2 с) ищется: $ZOVOD_SANDBOX_WAV -> ./sandbox_tone_2s.wav.
"""
import json
import os
import traceback


def _tone_path():
    """Путь к тестовому тону: env -> текущий каталог."""
    env = os.environ.get("ZOVOD_SANDBOX_WAV", "")
    if env and os.path.exists(env):
        return env
    return os.path.join(os.getcwd(), "sandbox_tone_2s.wav")


WAV = _tone_path()
PROJ = "AGENT_SANDBOX2"
TL = "AGENT_SANDBOX2_Audio"
R = {"steps": {}}
_st = {}


def step(name, fn):
    try:
        R["steps"][name] = {"ok": True, "result": fn()}
    except Exception as e:
        R["steps"][name] = {"ok": False, "error": "%s: %s" % (type(e).__name__, e),
                            "trace": traceback.format_exc()[-300:]}


def _name(it):
    v = getattr(it, "GetName", None)
    if v is None:
        return "?"
    return str(v() if callable(v) else v)


resolve = globals().get("resolve")
if resolve is None:
    print("COLLIDE_JSON:" + json.dumps({"ok": False, "error": "нет resolve"}, ensure_ascii=False))
else:
    pm = resolve.GetProjectManager()

    def _mk():
        p = pm.CreateProject(PROJ)
        if p is None:
            p = pm.LoadProject(PROJ)
        if p is None:
            raise RuntimeError("песочница не создалась")
        _st["p"] = p
        mp = p.GetMediaPool()
        tl = mp.CreateEmptyTimeline(TL)
        p.SetCurrentTimeline(tl)
        tl.AddTrack("audio", "stereo")
        items = mp.ImportMedia([WAV])
        lst = list(items.keys()) if isinstance(items, dict) else list(items)
        _st.update(mp=mp, tl=tl, items=lst)
        return {"project": p.GetName(), "timeline": tl.GetName(),
                "imported": len(lst)}
    step("setup", _mk)

    mp, tl, items = _st.get("mp"), _st.get("tl"), _st.get("items") or []

    def _place(rec_start, rec_end, src_in=0, src_len=50):
        res = mp.AppendToTimeline([{
            "mediaPoolItem": items[0], "startFrame": src_in,
            "endFrame": src_in + src_len, "mediaType": 2,
            "trackIndex": 1, "recordFrame": rec_start}])
        return {"returned": [{"start": i.GetStart(), "end": i.GetEnd(),
                               "name": _name(i)} for i in (res or [])]}

    step("place_A_at_100", lambda: _place(100, 150))
    step("place_B_overlapping_at_120", lambda: _place(120, 170))
    step("place_C_after_at_200", lambda: _place(200, 250))

    def _list():
        its = tl.GetItemListInTrack("audio", 1) or []
        return [{"start": i.GetStart(), "end": i.GetEnd(), "name": _name(i)}
                for i in its]
    step("track_contents", _list)

    def _getters():
        out = {}
        its = tl.GetItemListInTrack("audio", 1) or []
        if not its:
            return {"skipped": "пусто"}
        it = its[0]
        try:
            out["GetProperty_single"] = it.GetProperty("AudioVolume")
        except Exception as e:
            out["GetProperty_single_error"] = "%s: %s" % (type(e).__name__, e)
        try:
            out["GetProperties_dict"] = it.GetProperties()
        except Exception as e:
            out["GetProperties_error"] = str(e)
        try:
            out["SetProperty_single"] = it.SetProperty("AudioVolume", -3.0)
        except Exception as e:
            out["SetProperty_single_error"] = "%s: %s" % (type(e).__name__, e)
        return out
    step("getters_setters", _getters)

    def _leveler():
        its = tl.GetItemListInTrack("audio", 1) or []
        if not its:
            return {"skipped": "пусто"}
        it = its[0]
        before = None
        try:
            before = it.GetProperties().get("AudioDialogueLevelerBackgroundReduction")
        except Exception as e:
            before = "err: %s" % e
        ok = None
        err = None
        try:
            ok = it.SetProperties({"AudioDialogueLevelerBackgroundReduction": True,
                                   "AudioDialogueLevelerEnabled": True})
        except Exception as e:
            err = "%s: %s" % (type(e).__name__, e)
        after = None
        try:
            after = it.GetProperties().get("AudioDialogueLevelerBackgroundReduction")
        except Exception as e:
            after = "err: %s" % e
        return {"before": before, "set_returned": ok, "set_error": err, "after": after}
    step("dialogue_leveler_write", _leveler)

    def _cleanup():
        out = {}
        p = _st.get("p")
        try:
            out["close"] = pm.CloseProject(p)
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
    print("COLLIDE_JSON:" + json.dumps(R, ensure_ascii=False, default=str))
