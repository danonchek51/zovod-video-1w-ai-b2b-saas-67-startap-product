# -*- coding: utf-8 -*-
"""scene_map.py — хронологическая карта сцен по всем клипам проекта.

Собирает: инвентаризацию + транскрипции + измерения звука + измерения тряски
+ ручную визуальную классификацию (локация/тип плана/тег) в карту сцен.

Ручная классификация — это ПРОЕКТНЫЕ ДАННЫЕ, поэтому вынесены во внешний
файл (--classification), а не зашиты в код:

    {
      "blocks":      {"1": ["НАЗВАНИЕ БЛОКА", "краткое описание"]},
      "clips":       {"<CLIP>": [номер_блока, "тип плана", "тег"]},
      "speech_types":{"<CLIP>": "ДИАЛОГ"},
      "prompt_echo": ["фраза, которую whisper ухватил как промпт"]
    }

Пишет:
  ХРОНОЛОГИЯ_СЦЕН.md   — карта для монтажа (читаемая)
  scene_map.json        — то же машиночитаемо

    python scene_map.py --out <корень проекта> [--classification scene_classification.json]
                        [--transcripts <файл.json> ...]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import env_paths  # noqa: E402

ROOT = ""
CLASSIFICATION = {"blocks": {}, "clips": {}, "speech_types": {}, "prompt_echo": []}
BLOCKS = {}
CLIP = {}
SPEECH_TYPE = {}
PROMPT_ECHO_LIST = []


def load(path, default=None):
    if path and os.path.exists(path):
        try:
            return json.load(open(path, encoding="utf-8"))
        except Exception:
            return default if default is not None else {}
    return default if default is not None else {}


def apply_classification(data):
    """Загружает ручную классификацию в глобальные таблицы."""
    global BLOCKS, CLIP, SPEECH_TYPE, PROMPT_ECHO_LIST
    BLOCKS = {int(k): tuple(v) for k, v in (data.get("blocks") or {}).items()}
    CLIP = {k: tuple(v) for k, v in (data.get("clips") or {}).items()}
    SPEECH_TYPE = dict(data.get("speech_types") or {})
    PROMPT_ECHO_LIST = list(data.get("prompt_echo") or [])


def collect_speech(root, extra_files):
    """Собирает речь по всем клипам из всех доступных расшифровок.

    Приоритет: файлы из --transcripts (в порядке аргумента) > transcripts/*.json.
    """
    speech = {}
    tdir = os.path.join(root, "transcripts")
    sources = []
    if tdir and os.path.isdir(tdir):
        for fn in sorted(os.listdir(tdir)):
            if fn.endswith(".json"):
                sources.append(os.path.join(tdir, fn))
    for path in reversed(list(extra_files or [])):
        if os.path.exists(path):
            sources.insert(0, path)
    for path in sources:
        rec = load(path, {})
        if not isinstance(rec, dict):
            continue
        for name, val in rec.items():
            if not isinstance(val, dict):
                continue
            segs = val.get("segments") or []
            if segs:
                speech[name] = segs
    return speech


def main(argv=None):
    global ROOT

    p = argparse.ArgumentParser(
        prog="scene_map.py",
        description="хронологическая карта сцен по клипам проекта")
    p.add_argument("--out", default="", help="корень проекта (где лежат отчёты)")
    p.add_argument("--inventory", default="", help="inventory.json")
    p.add_argument("--audio", default="", help="audio_report.json")
    p.add_argument("--shake", default="", help="shake_report.json")
    p.add_argument("--classification", default="",
                   help="JSON с ручной классификацией (блоки/планы/теги/типы речи)")
    p.add_argument("--transcripts", default="",
                   help="файлы расшифровок через запятую (приоритетнее transcripts/*.json)")
    a = p.parse_args(argv)

    project = env_paths.project_root()
    ROOT = os.path.abspath(a.out) if a.out else str(project)

    inv_path = os.path.abspath(a.inventory) if a.inventory else os.path.join(ROOT, "inventory.json")
    if not os.path.exists(inv_path):
        p.error("нет инвентаризации: %s" % inv_path)

    cls_path = os.path.abspath(a.classification) if a.classification else \
        os.path.join(ROOT, "scene_classification.json")
    apply_classification(load(cls_path, {}) or {})
    if not CLIP:
        print("внимание: ручная классификация не задана (файл %s) — "
              "планы/теги/типы речи будут «?»" % cls_path)

    inv = load(inv_path)
    audio = load(os.path.join(ROOT, "audio_report.json"))
    shake = load(os.path.join(ROOT, "shake_report.json"))
    extra = [x.strip() for x in a.transcripts.split(",") if x.strip()]
    speech = collect_speech(ROOT, extra)

    rows = []
    for c in inv["clips"]:
        name = os.path.splitext(c["file"])[0]
        blk, shot, tag = CLIP.get(name, (0, "?", "?"))
        segs = speech.get(name) or []
        parts = []
        for s in segs:
            if isinstance(s, dict):
                t = s.get("text", "")
                st = s.get("start", 0)
                en = s.get("end", 0)
                parts.append("[%.1f–%.1f] %s" % (st, en, t))
            else:
                parts.append(str(s))
        txt = " ".join(parts).strip()
        echo = any(pe and pe in txt for pe in PROMPT_ECHO_LIST)
        stype = SPEECH_TYPE.get(name)
        if echo:
            stype = "ПРОМПТ"
        elif not txt:
            stype = "НЕТ РЕЧИ"
        elif stype is None:
            stype = "СПОРНО"
        aud = audio.get(name, {}) or {}
        sh = shake.get(name, {}) or {}
        head4k = sh.get("shake_head_px_4k")
        ratio = sh.get("shake_ratio")
        shaky = bool(ratio and ratio >= 1.6 and head4k and head4k >= 3.0)
        rows.append({
            "clip": name, "folder": c["folder"], "block": blk,
            "block_name": BLOCKS.get(blk, ("?", ""))[0] if blk else "?",
            "shot": shot, "tag": tag,
            "duration_s": c.get("duration_s"), "path": c["path"],
            "speech": txt, "speech_segments": len(parts),
            "prompt_echo": echo, "speech_type": stype,
            "lufs": aud.get("lufs"), "rms_dbfs": aud.get("rms_dbfs"),
            "tp_dbfs": aud.get("true_peak_dbfs"), "clip_pct": aud.get("clip_pct"),
            "floor_dbfs": aud.get("floor_dbfs"), "snr_db": aud.get("snr_db"),
            "shake_head_px_4k": head4k, "shake_ratio": ratio,
            "shaky_start": shaky,
            "trim_suggest_s": sh.get("trim_suggest_s"),
            "static_cam": sh.get("static"),
        })

    with open(os.path.join(ROOT, "scene_map.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    # --- markdown ---
    L = []
    L.append("# ХРОНОЛОГИЯ СЦЕН")
    L.append("")
    L.append("Карта по **всем %d клипам**. Каждый клип = строка: где снят, "
             "что в кадре, что сказано, состояние звука и камеры." % len(rows))
    L.append("")
    L.append("**Это карта, а не монтаж.** Отбор и порядок — за заказчиком. "
             "Порядок блоков ниже — реконструкция сюжета по содержанию, "
             "она помечена как гипотеза и её легко переставить.")
    L.append("")
    L.append("## Условные обозначения")
    L.append("")
    L.append("| Тег | Значение |")
    L.append("|---|---|")
    L.append("| СЮЖЕТ | Постановочный кадр, идёт в ролик |")
    L.append("| БЭКСТЕЙДЖ | Съёмочная кухня: режиссёр, реплики «в кадр», обсуждение |")
    L.append("| ПРОХОДНОЕ | Проходная/установочная перебивка |")
    L.append("| ПЕРЕБИВКА | Деталь без речи (табличка, стенд, стена) |")
    L.append("")
    L.append("| Пометка | Значение |")
    L.append("|---|---|")
    L.append("| `ТРЯСА` | Начало клипа трясётся сильнее остатка (нужна обрезка) |")
    L.append("| `ЭХО` | Whisper ухватил промпт — речи фактически нет |")
    L.append("")
    L.append("### Тип речи")
    L.append("")
    L.append("| Тип | Значение |")
    L.append("|---|---|")
    L.append("| ДИАЛОГ | Речь персонажа в кадре — идёт в ролик как реплика |")
    L.append("| ОЗВУЧКА | Озвучка/титры, говорящего не видно |")
    L.append("| ЗА КАДРОМ | Съёмочная кухня: режиссёр, «давай ещё раз», обсуждение |")
    L.append("| СПОРНО | По расшифровке нельзя решить — решает заказчик на слух |")
    L.append("| ПРОМПТ / НЕТ РЕЧИ | Речи нет, только шум |")
    L.append("")
    L.append("> Тип речи — оценка по расшифровке и плану кадра, **не** измерение. "
             "Все `СПОРНО` стоит послушать глазами/ушами: слушается текст, а не тон и "
             "близость микрофона.")
    L.append("")
    L.append("---")
    L.append("")

    for blk in sorted(BLOCKS):
        items = [r for r in rows if r["block"] == blk]
        if not items:
            continue
        nm, desc = BLOCKS[blk]
        tot = sum(r["duration_s"] or 0 for r in items)
        L.append("## Блок %d. %s — %s" % (blk, nm, desc))
        L.append("")
        L.append("Клипов: %d · суммарно %.1f с" % (len(items), tot))
        L.append("")
        L.append("| Клип | План | Тег | Длит. | Тип речи | Речь | LUFS | TP | SNR | Пол | Тряска | Обрезка |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
        for r in items:
            sp = r["speech"]
            if r["prompt_echo"]:
                sp = "_(речи нет — эхо промпта)_"
            elif not sp:
                sp = "_(речи нет)_"
            else:
                sp = sp.replace("|", "/")
                if len(sp) > 150:
                    sp = sp[:147] + "…"
            fl = []
            if r["shaky_start"]:
                fl.append("**ТРЯСА**")
            if r["prompt_echo"]:
                fl.append("ЭХО")
            shake_txt = " ".join(fl) if fl else "—"
            if r["shaky_start"] and r["shake_head_px_4k"]:
                shake_txt += " (%s px)" % r["shake_head_px_4k"]
            L.append("| %s | %s | %s | %.1f | %s | %s | %s | %s | %s | %s | %s | %s |" % (
                r["clip"], r["shot"], r["tag"], r["duration_s"] or 0,
                r["speech_type"], sp,
                ("%.1f" % r["lufs"]) if r["lufs"] is not None else "—",
                ("%.1f" % r["tp_dbfs"]) if r["tp_dbfs"] is not None else "—",
                ("%.1f" % r["snr_db"]) if r["snr_db"] is not None else "—",
                ("%.1f" % r["floor_dbfs"]) if r["floor_dbfs"] is not None else "—",
                shake_txt,
                ("%.2f с" % r["trim_suggest_s"]) if r["trim_suggest_s"] else "—"))
        L.append("")

    # сводка
    L.append("---")
    L.append("")
    L.append("## Сводка по звуку")
    L.append("")
    lufs = [r["lufs"] for r in rows if r["lufs"] is not None]
    snr = [r["snr_db"] for r in rows if r["snr_db"] is not None]
    L.append("- Клипов: **%d**, суммарно **%.1f с** (%.2f мин)"
             % (len(rows), sum(r["duration_s"] or 0 for r in rows),
                sum(r["duration_s"] or 0 for r in rows) / 60.0))
    if lufs:
        L.append("- Разброс громкости: LUFS от **%.1f** до **%.1f** (разница %.1f дБ) — "
                 "исходники выровнены по-разному, это главный дефект звука"
                 % (min(lufs), max(lufs), max(lufs) - min(lufs)))
    if snr:
        L.append("- SNR: от **%.1f** до **%.1f** дБ (шум пола в паузах) — "
                 "средний %.1f дБ" % (min(snr), max(snr), sum(snr) / len(snr)))
    L.append("- Клипов с речью: **%d**, без речи (только шум/эхо): **%d**"
             % (len([r for r in rows if r["speech"] and not r["prompt_echo"]]),
                len([r for r in rows if r["prompt_echo"] or not r["speech"]])))
    L.append("- Клипов с трясущимся началом: **%d** — см. пометку `ТРЯСА`"
             % len([r for r in rows if r["shaky_start"]]))
    L.append("")
    L.append("## Где смотреть кадры")
    L.append("")
    L.append("- `resolve_check/frames/<клип>_NN.png` — опорные кадры (18 %, 50 %, 82 %)")
    L.append("- `thumbs/<клип>.jpg` — миниатюры, если собраны")

    md_path = os.path.join(ROOT, "ХРОНОЛОГИЯ_СЦЕН.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print("written %s, scene_map.json, rows=%d" % (md_path, len(rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
