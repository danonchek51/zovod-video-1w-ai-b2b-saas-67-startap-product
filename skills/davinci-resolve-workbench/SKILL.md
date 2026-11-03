---
name: davinci-resolve-workbench
description: |
  Workbench for any video task in DaVinci Resolve on this machine: environment
  setup and health check, talking to Resolve through its MCP server, importing
  media, building timelines, editing, color and Fusion work, stabilization,
  rendering, QC and delivery. Load this skill BEFORE handing over a new video
  task — it carries the verified paths, the launch procedure, the ready-to-run
  scripts and the Resolve 21.1 API traps, so the agent does not spend the
  session rediscovering where things live or which calls silently fail. Triggers
  on: the user posting a path to a folder or file of footage/references,
  "DaVinci Resolve", "Resolve", "ResolveMCP", "DaVinci", "Color Page",
  "Fusion comp", "timeline", "media pool", "render out of Resolve", "stabilize
  this clip", "grade this footage", ".cube LUT", "video task", plus any request
  to edit, restyle, cut, stabilize, grade or render a video file on this
  workstation. Do NOT use it for HyperFrames / Remotion / Premiere / CapCut
  style tasks that never touch Resolve, and not for pure image processing.
---

# DaVinci Resolve Workbench

> Копия скилла из рабочей среды монтажа. Пути обобщены: используйте `tools/env_paths.py`.
> Проверено на DaVinci Resolve 21.1.1 Studio; на других версиях поведение API может
> отличаться — сверяйтесь с `docs/RESOLVE_RECIPE.md`.

Everything needed to start a video task immediately: the environment is already
installed and configured, so the job is to find the right tool, not to set the
machine up.

## First action: check the workbench

```
python <ПАКЕТ>/skills/davinci-resolve-workbench/scripts/resolve_doctor.py
```

It prints one line per check (Resolve process, MCP server, `mcp.json` wiring,
ffmpeg/ffprobe, Python imaging modules, LUT folder, current project/timeline,
render queue) and exits non-zero if something blocks work. Fix what it reports
before starting the real task — most "Resolve does nothing" symptoms come from
the app not being up or from a render still running.

## Intake: the user hands you a path

When the request is just a folder or file path, treat it as an intake request
and do the triage yourself — the path is enough to start, but it does not
answer what the user wants done.

1. `python scripts/media_probe.py <path>` — a folder is walked recursively and
   every media file is probed: container, codec, resolution, fps, frame count,
   duration, colour tags, plus palette statistics (black point, contrast,
   saturation, shadow noise, dominant hues). A still is a colour key frame, a
   clip is a motion/grain reference, the long raw clips are the working
   material — sort the inventory into those roles yourself.
2. Report the inventory as a compact table before doing anything else, and
   flag what you noticed: mismatched frame rates, a Log source, missing audio,
   a reference with a different resolution than the footage.
3. Ask the remaining questions in one questionnaire: what to change, what must
   stay untouched, the target look, and the final spec.
4. Then run the loop below.

If the path is empty, missing, or contains nothing usable, say so plainly with
the search you ran instead of starting a pipeline against nothing.

## What is already installed

| Thing | Where |
|---|---|
| Resolve Studio 21.1.1.10 | путь определяется автоматически: `tools/env_paths.py` → `env_paths.resolve_exe()`; переопределяется переменной `RESOLVE_APP_DIR` |
| MCP server | `<Resolve App>\DaVinci Resolve\ResolveMCP.exe`, регистрируется в конфигурации MCP-клиента (`<профиль>/mcp.json`) как `davinci-resolve` с `RESOLVE_SCRIPT_API` / `RESOLVE_SCRIPT_LIB` |
| Scripting API stubs | `<Resolve App>\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\DaVinciResolveScript.pyi` — grep this for exact signatures instead of guessing |
| LUT folder | `env_paths.lut_dir()`; Resolve резолвит LUT-ы из `<Support\LUT>` |
| ffmpeg / ffprobe | `env_paths.ffmpeg()` / `env_paths.ffprobe()` (fallback — `shutil.which`) |
| Python | `sys.executable` (numpy, cv2, PIL available) |

Portable-сборка запускается лаунчером `ResolvePortable.exe` из каталога
`Resolve\`. Запуск `Resolve.exe` напрямую падает с `0xC0000409`, а MCP-инструмент
`launch_resolve` на portable-сборке не работает — стартуйте лаунчер сами, затем
подтвердите состояние через doctor или `get_resolve_status`.

## Tools at hand

**MCP tools (already available in the session):** `run_script`, `run_script_unsafe`,
`generate_lut`, `list_luts`, `update_dctl`, `delete_lut`, `get_scripting_api`,
`search_scripting_api`, `get_scripting_docs`, `get_resolve_status`,
`get_whats_new`. Use `search_scripting_api` to check a signature before using it.

**Bundled scripts (stdlib + ffmpeg, no installs):**

- `scripts/resolve_bridge.py` — MCP client with a timeout you control.
  `python resolve_bridge.py tools`, `call <tool> '<json>'`,
  `script <file.py> [--unsafe] [--timeout=600]`. Needed because the MCP
  `run_script` tool caps at 60 s while stabilization analysis and render setup
  take minutes.
- `scripts/resolve_doctor.py` — environment health check described above.
- `scripts/media_probe.py` — ffprobe metadata + palette statistics for any
  media file **or a whole folder** (walked recursively): resolution, fps,
  frames, duration, colour tags, black point, contrast, saturation, shadow
  noise, dominant hues.
- `scripts/frame_qc.py` — `compare` extracts the same frames from two videos
  and prints grade metrics plus a contact sheet; `motion` measures frame-to-frame
  difference, which is the only way to prove stabilization happened.

## Working loop for a video task

The shape is the same whatever the task is; the task-specific parts live in
`references/`.

1. **Understand the request.** Separate what the user wants changed (look,
   cuts, stabilization, export spec) from what must stay untouched (montage,
   speed, framing). Ask only about decisions you cannot infer; use one
   `ask_user` questionnaire.
2. **Probe the material first.** `media_probe.py` on the source and every
   reference. Record resolution, fps, frame count, duration, timecode and the
   colour tags — `primaries`/`transfer`/`matrix`/`range` decide whether a
   transform base is needed, and `nb_frames` tells you what "one frame" means
   when you extract control frames later. If the source is not where the user
   said, search for it before anything else and report the real path (Resolve's
   own project database and recent-project list often hold the original path of
   material that has been moved).
3. **Set up the project before editing.** Import into the media pool, set
   `timelineResolutionWidth/Height` and `timelineFrameRate` on the project
   *before* creating the timeline, then create the timeline and lay out clips.
   Setting the resolution afterwards forces a re-render of everything.
4. **Do the edit.** Pick the branch that matches the request:
   - look / grade / LUT / film grain / glow / vignette →
     `references/color-look-development.md`
   - stabilization → the `Stabilize()` section of the same reference, plus
     `frame_qc.py motion` to verify the result
   - plain cut / reorder / trim / speed → the timeline API section of
     `references/video-workflows.md`
   - anything else → read the API stubs file and probe with a tiny script

   Keep every generated script in one task folder inside the workspace
   (`<workspace>/scripts/`) instead of scattering files across the workspace
   root, and reuse a LUT already installed in the MCP LUT folder rather than
   regenerating an equivalent one.
5. **Verify before rendering.** Extract control frames, measure, and compare
   against the target. Cheap checks now are cheaper than a 4K render that has
   to be redone.
6. **Preview, then approve.** Render a low-res version, attach it, get an
   explicit go/no-go and the final spec (resolution, container, bitrate).
7. **Render the final** with the recipe in `references/video-workflows.md`,
   then verify: full decode without errors, exact frame count, audio present,
   and metrics inside the expected band.
8. **Deliver.** Report the absolute path, the technical specs, a control sheet
   and a compact low-res copy for chat — a 4K master is usually too big to
   attach directly.

## Output contract

- The result file at an explicit absolute path, with container, resolution,
  fps, frame count, duration, codec and audio stated.
- A short verification note: what was checked (decode, frame count, metrics,
  motion) and the actual numbers — not "looks good".
- For anything above ~100 MB, also a compact preview version for chat.
- If the work lives in a Resolve project, report the project and timeline
  names, because `ExportProject` is unavailable and the project only exists
  inside Resolve's database.

## Failure handling

- A call returns `False` or `None`: look it up in
  `references/resolve-api-gotchas.md` before retrying — these are unsupported
  operations, not flaky calls.
- "Nothing happened" after a change: check the render queue. While a render
  runs, every mutating call silently returns `None`.
- The active project is not the one you expected: `LoadProject()` switches
  projects. Status and polling scripts must only read `GetCurrentProject()`.
- A script hangs or Resolve crashes: it probably touched Fusion import, a
  hand-written `.comp`, or `comp.SaveAs()`. Those are documented as broken.
- Long task times out at 60 s: rerun through `resolve_bridge.py` with
  `--timeout=600`.
- Deliverables must survive the session: keep intermediate renders and the
  final in the user's workspace folder, not in temp.

## Windows (win32) platform notes

- PowerShell 5.1: no `&&` / `||`; separate statements. Quote paths with spaces
  for `Start-Process -ArgumentList '"C:\path with space\x.py"'`.
- `Remove-Item` and recursive delete/move are blocked by policy — use
  reversible renames through Python instead of destructive deletes.
- `python3` does not exist here; use `C:\Python314\python.exe`.
- OpenCV 5.x: `cv2.randn` needs an explicit `stddev`; for deterministic grain
  use `numpy.random.default_rng(seed).standard_normal(shape)`.

## References

- `references/environment.md` — full path map, how Resolve and the MCP server
  are wired, the API stub file, project database location, toolbox.
- `references/resolve-api-gotchas.md` — symptom → cause → workaround for every
  Resolve API trap hit so far (color graph, Fusion, render queue, MCP layer).
  Read before writing any script that touches nodes, Fusion or renders.
- `references/video-workflows.md` — import/media pool, timeline creation,
  render settings that actually apply, queue management, verification
  commands, measured render speeds, delivery packaging.
- `references/color-look-development.md` — the color branch: palette analysis,
  LUT design and validation, Fusion glow/grain, stabilization and how to
  verify it, QC metric thresholds.
