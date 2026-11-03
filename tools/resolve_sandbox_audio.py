# -*- coding: utf-8 -*-
"""resolve_sandbox_audio.py — проверка аудио-пути Resolve 21.1.1 в одноразовом проекте.

Создаёт проект AGENT_SANDBOX, проверяет утверждения отчётов на НАШЕЙ версии,
затем закрывает и удаляет проект. Пользовательские проекты не трогает.

Запуск: run_script_unsafe ->
    exec(compile(open(r'<ПАКЕТ>/tools/resolve_sandbox_audio.py',
                      encoding='utf-8').read(), 'resolve_sandbox_audio.py', 'exec'))

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
PROJ = "AGENT_SANDBOX"
TL_NAME = "AGENT_SANDBOX_Audio"

R = {"steps": {}}
_state = {}


def step(name, fn):
    try:
        R["steps"][name] = {"ok": True, "result": fn()}
    except Exception as e:
        R["steps"][name] = {"ok": False, "error": "%s: %s" % (type(e).__name__, e),
                             "trace": traceback.format_exc()[-300:]}


resolve = globals().get("resolve")
if resolve is None:
    print("SANDBOX_JSON:" + json.dumps({"ok": False, "error": "нет resolve"}, ensure_ascii=False))
else:
    pm = resolve.GetProjectManager()

    def _mk_proj():
        p = pm.CreateProject(PROJ)
        if p is None:
            p = pm.LoadProject(PROJ)
        if p is None:
            raise RuntimeError("не удалось создать/загрузить песочницу")
        _state["proj"] = p
        return {"name": p.GetName(), "timelines": p.GetTimelineCount()}
    step("create_sandbox_project", _mk_proj)

    proj = _state.get("proj")
    mp = proj.GetMediaPool() if proj else None

    def _mk_tl():
        tl = mp.CreateEmptyTimeline(TL_NAME)
        if tl is None:
            raise RuntimeError("CreateEmptyTimeline вернул None")
        proj.SetCurrentTimeline(tl)
        _state["tl"] = tl
        return {"name": tl.GetName()}
    step("create_timeline", _mk_tl)

    tl = _state.get("tl")

    def _add_track():
        ok = tl.AddTrack("audio", "stereo")
        return {"returned": ok, "track_count": tl.GetTrackCount("audio"),
                "name": tl.GetTrackName("audio", 1),
                "subtype": tl.GetTrackSubType("audio", 1)}
    step("add_audio_track", _add_track)

    def _import():
        res = mp.ImportMedia([WAV])
        if isinstance(res, dict):
            items = list(res.keys())
        elif isinstance(res, (list, tuple)):
            items = list(res)
        else:
            items = []
        _state["items"] = items
        return {"count": len(items),
                "names": [str(getattr(i, "GetName", lambda: "?"))() for i in items[:3]],
                "raw_type": type(res).__name__}
    step("import_media", _import)

    items = _state.get("items") or []

    def _append():
        res = mp.AppendToTimeline([{"mediaPoolItem": items[0], "startFrame": 0,
                                     "endFrame": 50, "mediaType": 2,
                                     "trackIndex": 1, "recordFrame": 100}])
        return {"returned_items": [{"name": str(i.GetName()), "start": i.GetStart(),
                                     "end": i.GetEnd(), "track": i.GetTrackTypeAndIndex()}
                                    for i in (res or [])]}
    step("append_to_timeline", _append)

    def _append2():
        if len(items) < 2:
            return {"skipped": "нет второго элемента в пуле"}
        res = mp.AppendToTimeline([{"mediaPoolItem": items[0], "startFrame": 0,
                                     "endFrame": 50, "mediaType": 2,
                                     "trackIndex": 1, "recordFrame": 200}])
        return {"returned_items": [{"start": i.GetStart(), "end": i.GetEnd()}
                                   for i in (res or [])]}
    step("append_second_same_track", _append2)

    def _list():
        its = tl.GetItemListInTrack("audio", 1) or []
        return [{"name": str(i.GetName()), "start": i.GetStart(), "end": i.GetEnd()}
                for i in its]
    step("list_audio_track", _list)

    def _volume():
        its = tl.GetItemListInTrack("audio", 1) or []
        if not its:
            return {"skipped": "нет айтема"}
        it = its[0]
        try:
            before = it.GetProperties()
        except Exception as e:
            before = {"error": str(e)}
        ok = it.SetProperties({"AudioVolume": -6.0, "AudioVolumeEnabled": True})
        try:
            after = it.GetProperties()
        except Exception as e:
            after = {"error": str(e)}
        return {"set_returned": ok,
                "before": before if isinstance(before, dict) else str(before),
                "after": after if isinstance(after, dict) else str(after)}
    step("set_audio_volume", _volume)

    def _fps():
        out = {}
        try:
            out["GetSetting_call"] = tl.GetSetting("timelineFrameRate")
        except Exception as e:
            out["GetSetting_error"] = "%s: %s" % (type(e).__name__, e)
        try:
            s = tl.GetSettings() or {}
            out["GetSettings_timelineFrameRate"] = s.get("timelineFrameRate")
            out["settings_keys"] = sorted(s.keys())[:16]
        except Exception as e:
            out["GetSettings_error"] = str(e)
        return out
    step("fps_source", _fps)

    def _marker_str():
        ok = tl.AddMarker(100, "Blue", "SFX: sandbox", "проверка customData", 1,
                          "sfx_id=sandbox_tone;mode=A")
        return {"returned": ok,
                "markers": {str(k): str(v) for k, v in (tl.GetMarkers() or {}).items()}}
    step("add_marker_string_customdata", _marker_str)

    def _marker_dict():
        ok = tl.AddMarker(120, "Blue", "SFX: dict", "проверка dict", 1,
                          {"sfx_id": "x", "mode": "A"})
        return {"returned": ok}
    step("add_marker_dict_customdata", _marker_dict)

    step("normalize_modes", lambda: tl.GetNormalizeAudioModes())
    step("detect_scene_cuts", lambda: tl.DetectSceneCuts())

    def _cleanup():
        out = {}
        try:
            out["delete_timeline"] = mp.DeleteTimeline(TL_NAME)
        except Exception as e:
            out["delete_timeline_error"] = str(e)
        try:
            out["close_project"] = pm.CloseProject(proj)
        except Exception as e:
            out["close_error"] = str(e)
        try:
            out["delete_project"] = pm.DeleteProject(PROJ)
        except Exception as e:
            out["delete_project_error"] = str(e)
        out["projects_left"] = pm.GetProjectListInCurrentFolder()
        return out
    step("cleanup", _cleanup)

    R["ok"] = True
    print("SANDBOX_JSON:" + json.dumps(R, ensure_ascii=False, default=str))
