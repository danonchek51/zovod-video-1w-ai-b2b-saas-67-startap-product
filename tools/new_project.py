# -*- coding: utf-8 -*-
"""new_project.py — скаффолд нового проекта по канону рабочей среды.

    python tools\\new_project.py <имя_проекта> --src "D:\\...\\исходники" --fps 25
        [--res 3840x2160] [--start-tc 01:00:00:00] [--rights A|B]
        [--duration 150] [--root "<корень рабочего пространства>"] [--force]

Создаёт каноническую раскладку (docs/WORKSPACE_LAYOUT.md), project.json с
параметрами проекта, README и копию универсальных инструментов.

Исходники НЕ копируются: --src фиксируется как корень только для чтения.
По умолчанию --src берётся из env_paths.src_root(), --root — из корня пакета.
"""
import argparse
import datetime
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import env_paths  # noqa: E402

DIRS = [
    "00_brief", "01_media", "02_proxies", "03_analysis", "04_selects",
    "05_blueprints", "06_timelines", "07_renders", "08_audio", "09_graphics",
    "10_qc", "11_delivery", "changelists", "logs", "_checkpoints", "tools",
]

BRIEF = """# {name}

**Дата создания:** {date}
**Источник (только чтение):** {src}
**Параметры:** {res} @ {fps} fps, таймкод старта {start_tc}, режим по правам: {rights}

## Что здесь

| Папка | Что внутри |
|---|---|
| `00_brief/` | бриф, ТЗ, правки заказчика |
| `01_media/` | манифест исходников (файлы остаются на месте, только чтение) |
| `02_proxies/` | прокси — **создавать только после одобрения** |
| `03_analysis/` | профили, транскрипции, опорные кадры |
| `04_selects/` | отобранные сцены, шутки, сюжетная карта |
| `05_blueprints/` | планы монтажа, карта музыкальных/сюжетных блоков |
| `06_timelines/` | описания таймлайнов, EDL, листы монтажа |
| `07_renders/` | рендеры (версионированные) |
| `08_audio/` | дорожки, микс, отчёты громкости (LUFS/true peak) |
| `09_graphics/` | титры, графика, шаблоны |
| `10_qc/` | QC-отчёты, чек-листы |
| `11_delivery/` | финальные файлы и манифест сдачи |
| `changelists/` | списки изменений |
| `logs/` | логи агента |
| `_checkpoints/` | точки отката (`tools/checkpoint.py`) |

## Протокол

Читать `AGENTS.md` в корне рабочего пространства и `docs/` рядом с ним.
Контекст проекта вести в `КОНТЕКСТ_ПРОЕКТА.md` (append-only, раздел на этап).
"""

README = """# Проект: {name}

Рабочая папка: `{path}`

- Источники: `{src}` — **только чтение**, ничего не переносим и не перезаписываем.
- Параметры: {res}, {fps} fps, таймкод старта {start_tc}.
- Права: режим {rights} (A — внутренний показ, B — публикация в соцсетях ведомств).

Порядок работы и правила — в `AGENTS.md` и `docs/` в корне рабочего пространства.
"""


def main(argv=None):
    p = argparse.ArgumentParser(description="скаффолд нового проекта")
    p.add_argument("name", help="имя проекта (папка)")
    p.add_argument("--src", default="", help="корень исходников (только чтение); по умолчанию env_paths.src_root()")
    p.add_argument("--root", default=str(env_paths.PACK_ROOT), help="корень рабочего пространства")
    p.add_argument("--fps", type=float, default=25.0)
    p.add_argument("--res", default="3840x2160")
    p.add_argument("--start-tc", default="01:00:00:00")
    p.add_argument("--rights", choices=["A", "B"], default="A")
    p.add_argument("--duration", type=float, default=0.0, help="целевой хронометраж, с")
    p.add_argument("--force", action="store_true", help="перезаписать project.json")
    a = p.parse_args(argv)

    if not a.src:
        _auto = env_paths.src_root()
        a.src = str(_auto) if _auto else ""
        if not a.src:
            p.error("нужен --src (или задайте src_root через tools/env_paths.py set src_root <путь>)")

    path = os.path.join(os.path.abspath(a.root), a.name)
    if os.path.exists(path) and not os.path.isdir(path):
        raise SystemExit("путь занят файлом: %s" % path)
    for d in DIRS:
        os.makedirs(os.path.join(path, d), exist_ok=True)

    today = datetime.date.today().isoformat()
    meta = {
        "name": a.name,
        "created": today,
        "source_root": os.path.abspath(a.src) if a.src else "",
        "source_mode": "read-only",
        "fps": a.fps,
        "resolution": a.res,
        "start_timecode": a.start_tc,
        "color_science": "",
        "rights_mode": a.rights,
        "target_duration_s": a.duration,
        "deliverables": [],
        "notes": "",
    }
    mpath = os.path.join(path, "project.json")
    if os.path.exists(mpath) and not a.force:
        with open(mpath, "r", encoding="utf-8") as f:
            meta = json.load(f)
        meta["updated"] = today
    with open(mpath, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    with open(os.path.join(path, "README.md"), "w", encoding="utf-8") as f:
        f.write(README.format(name=a.name, path=path, src=meta["source_root"],
                              res=a.res, fps=a.fps, start_tc=a.start_tc, rights=a.rights))
    with open(os.path.join(path, "00_brief", "БРИФ.md"), "w", encoding="utf-8") as f:
        f.write(BRIEF.format(name=a.name, date=today, src=meta["source_root"],
                             res=a.res, fps=a.fps, start_tc=a.start_tc, rights=a.rights))
    with open(os.path.join(path, "01_media", "media_manifest.json"), "w", encoding="utf-8") as f:
        json.dump({"source_root": meta["source_root"], "note":
                   "исходники только для чтения; здесь — манифест, а не копии",
                   "items": []}, f, ensure_ascii=False, indent=2)

    # копия универсальных инструментов
    src_tools = os.path.join(os.path.abspath(a.root), "tools")
    dst_tools = os.path.join(path, "tools")
    for fn in ("checkpoint.py", "verify_timeline.py", "resolve_probe_env.py",
               "env_paths.py", "doctor.py"):
        s = os.path.join(src_tools, fn)
        if os.path.exists(s):
            shutil.copy2(s, os.path.join(dst_tools, fn))

    print("created:", path)
    print("  %d папок, project.json, README.md, копия tools/" % len(DIRS))
    return path


if __name__ == "__main__":
    sys.exit(main())
