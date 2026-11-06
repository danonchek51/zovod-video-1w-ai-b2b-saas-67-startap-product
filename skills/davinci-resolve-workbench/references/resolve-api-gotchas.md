# Resolve API gotchas (21.1.1.10, portable build)

Every entry is something that actually broke or silently misbehaved. Format:
**symptom → cause → workaround**. When a call returns `False`/`None`, look
here before retrying — most of these are unsupported operations, not flaky
calls.

## Project and session

| Symptom | Cause | Workaround |
|---|---|---|
| A running render dies and the queue looks empty | `pm.LoadProject(name)` switches the *current* project; the queue belongs to the project you left | Status/polling scripts must use `pm.GetCurrentProject()` only. Call `LoadProject` only when the name differs, and never inside a polling loop |
| `pm.ExportProject(name, path)` raised `'NoneType' object is not callable` in older notes | **It works** (verified 06.11.2026): returns `True` and writes a real `.drp` (~1 MB for a 90-minute project) | Use it for rollback points: `pm.SaveProject()` → `pm.ExportProject(project.GetName(), drp)` → copy `Project.db`. See `tools/resolve_checkpoint.py` |
| Every mutation suddenly returns `False` (`SaveProject`, `ApplyGradeFromDRX`, `SetLUT`) | The **Project Manager** window is in front, not the Edit page | `resolve.OpenPage("edit")` before mutating and check `resolve.GetCurrentPage() == "edit"` |
| `project` (the injected object) refers to a closed/other project | After a Resolve restart the injected handle is stale | Always take the project fresh: `resolve.GetCurrentProject()` |
| `GetTimelineList()`, `tl.GetPropertyList()`, `ti.GetPropertyList()` raise `'NoneType' object is not callable` | Not exposed | Use `GetCurrentTimeline()` and specific getters; enumerate by other means |
| `ti.GetProperty("Stabilization")` returns `False` while stabilization is active | Property is not readable through the API | `ti.Stabilize()` returning `True` is the only signal. Verify the effect by measuring frame-to-motion in the rendered output |
| `project.GetSetting("colorSpaceOutputGamma")` kills Resolve / always returns the same value | Unknown keys abort the call; the output gamma is not writable through the API | Read only `project.GetSettings()` (a dict of ~158 keys). To change the output gamma use the UI: Shift+9 → Color Management → Output Gamma |
| Timeline frame numbers look huge (`90000..90988`) | Projects can start at a non-zero frame offset | All frame-index APIs (render `MarkIn`/`MarkOut`, `GetStart`/`GetEnd`) use the same absolute numbering — do not treat them as 0-based |
| A crash dialog «Отчёт о проблемах DaVinci Resolve» ignores clicks and blocks every script call | It is a Qt window, not a modal the API can dismiss | `tools/dismiss_dialogs.py` does not recognise it (template says «Отчет», the window says «Отчёт»). Kill and relaunch Resolve instead, then `pm.LoadProject(name)` |

## Color page / node graph

| Symptom | Cause | Workaround |
|---|---|---|
| No way to add nodes to the graph | `Graph` in the scripting API exposes only `SetLUT`, `SetNodeEnabled`, `ResetAllGrades`, `GetToolsInNode`, `GetLUT`, `GetNumNodes` — there is no `AddNode` | Script one Color node carrying the LUT, and move every other stage into the Fusion comp. Encode WB/exposure inside the LUT instead of building 4 nodes |
| `SetCDL` paints the whole clip **red** (measured means R 192 / G 46 / B 46) | Resolve applies the CDL with its own transfer curve | Do not use `SetCDL` for grade at all. Put WB/exposure/curve into the LUT and apply the CDL in the offline post pass with the same math the preview used |
| `SetCDL` returns `False` although the dictionary looks right | The API rejects the whole dict if it contains **any unexpected key** (e.g. a leftover `"err": 0.035` from a fit report) | Pass exactly the five documented keys: `NodeIndex`, `Slope`, `Offset`, `Power`, `Saturation`. Strip everything else before calling |
| `SetCDL({"NodeIndex": 2, ...})` returns `False` | There is no node 2 | `SetCDL` can only address node 1 |
| Disabling a node cannot be undone reliably | `SetNodeEnabled` is not a clean round-trip: re-enabling resets the node's tools (the CDL disappears) | Recover with `ResetAllGrades()` then `SetLUT(1, absolute_path)` |
| `SetLUT(1, path)` returns `False` although the file exists | **An absolute path outside Resolve's LUT folder is rejected.** Only a file inside `…\DaVinci Resolve\Support\LUT\` (any subfolder, e.g. `MCP\`) is accepted | Copy the cube into the LUT folder, call `project.RefreshLUTList()`, then `SetLUT(1, <absolute path inside that folder>)`. Confirm with `GetLUT(1)` — it returns the path **relative to the LUT folder** (`MCP\Name.cube`) |
| `SetLUT` returns `False` right after copying a new cube | `RefreshLUTList()` ran **before** the file was copied, so Resolve does not know it | Order is fixed: copy all cubes → `RefreshLUTList()` → `SetLUT` |
| The LUT file was edited on disk but the picture did not change | Resolve keeps the previously read LUT | Force a re-read: `SetLUT(1, "")` and then `SetLUT(1, path)` |
| `GetNodeGraph()` returns `None` | The item is a **transition**, not a clip — transitions have no colour graph | Find the clip by name, not only by start frame: a transition and a clip can share the same start frame |
| The wrong clip got the grade | Selection by start frame picked the transition that starts at the same frame | Select by (track, start) **and** name; skip items without a graph |
| `ApplyGradeFromDRX` returns `True` but the picture is unchanged | Malformed/unsupported DRX | Do not rely on it; build the grade from LUT + Fusion |
| `ApplyGradeFromDRX` **crashes Resolve** (process dies, crash dialog) | Reproducible on clips overlapped by a transition (4 crashes in one session: V2@93179, V1@90309, V1@93285, V1@93285 C0141_cut) | Do not call it on a live timeline. If a multi-node grade is required, apply the DRX by hand in the Color page (the file path is known) or bake it into the LUT |
| A grade looks right in the viewer but the render does not change | The single-frame render path does not always carry the grade | Prove the grade with an A/B render: same frame with and without the LUT, then compare pixel-wise (see `docs/COLOR_LOOK.md` § «Проверка грейда») |
| `ExportCurrentFrameAsStill` shows no colour change | It exports the colour branch only in some builds | Verify the grade by rendering, not by still export |

## Fusion

| Symptom | Cause | Workaround |
|---|---|---|
| `ti.ImportFusionComp(path)` hangs for 60 s, then Resolve crashes | Importing a hand-written `.comp` is unstable here | Build the comp programmatically with `comp.AddTool(...)` and `ConnectInput(...)` |
| `comp.SaveAs()` never returns; `comp.RunScript(lua)` returns nothing | Not functional in this build | Neither is needed; do not build a workflow that depends on them |
| `tool.ConnectInput(1, tool)` returns `False` | Connections take the input **name**, not the index | Use `"Input"`, `"Background"`, `"Foreground"`, `"Matte"`, `"Garbage.Matte"`, `"EffectMask"` |
| A tool input change has no effect and no error | `SetInput` with an unknown name is silently ignored | List the real inputs first: `tool.GetInputList()` and read each item's `.ID` via `getattr(v, "ID")` (there is no `v.GetID()`) |
| `ti.DeleteFusionCompByName(name)` does nothing | Only the active comp can be deleted | Call `LoadFusionCompByName(name)` first, then delete |
| A Fusion vignette gives either no effect or a black/garbage frame | EllipseMask + Merge/EffectMask does not produce a soft radial gradient here (Width 1.6 → no effect; Width 1.25–4.0 with Invert → broken frame) | Apply the vignette in the post pass with the same math as the offline preview |
| Node parameter values look wrong after a rebuild | Default tool set differs from a UI-created comp | Set every parameter that affects the result explicitly and re-render one frame to confirm |
| `ti.AddFusionComp()` returns `None` or raises | The clip already owns a comp | Check `ti.GetFusionCompCount()` / `ti.GetFusionCompByIndex(i)` first and reuse the existing comp instead of adding a second one |

Tools that were verified to work: **Glow** (inputs `Blend`, `Low`, `High`, `Glow`,
`XGlowSize`, `YGlowSize`, `Passes`, `ColorScale`, `Alpha`, filter `Fog Glow`) and
**FilmGrain** (`Blend`, `MasterStrength`, `MasterXSize`, `MasterYSize`,
`MasterRoughness`, `Monochrome`, `Randomize`, `Complexity`).

Creating a Fusion comp programmatically (the only reliable route here):

```python
comp = ti.AddFusionComp()              # or ti.GetFusionCompByIndex(i) to reuse
glow = comp.AddTool("Glow", 0, 0)
grain = comp.AddTool("FilmGrain", 0, 0)
comp.ConnectInput("Input", glow)       # name, not index
comp.ConnectInput("Background", grain)
comp.ConnectInput("Foreground", mediaout)
```

`ti.AddFusionComp()` is not listed in every build's docs but exists in 21.1.1
(verified). `ti.GetFusionCompCount()` and `ti.GetFusionCompByIndex(i)` are the
way to find a comp that is already attached. After building, read every
parameter back with `tool.GetInputList()` / `GetInput()` — a wrong input name
fails silently.

## Resource limits

- With Resolve running, only ~3.5 GB of RAM may be free. OpenCV float32
  buffers at 1080p can fail to allocate under that pressure. Keep image
  processing frame-by-frame, convert to float32 per plane rather than for the
  whole frame at once, and close Resolve before a heavy offline pass if the
  allocation fails.
- The MCP LUT folder survives between sessions: check
  `C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\LUT\MCP\` before
  regenerating a cube — a validated LUT from an earlier job may already be
  installed and reusable.

## Render queue

| Symptom | Cause | Workaround |
|---|---|---|
| `SetRenderSettings`, `AddRenderJob`, `StartRendering`, `DeleteAllRenderJobs` all return `None` and nothing changes | Mutating calls are no-ops while a render is running | Order: `StopRendering()` → poll `IsRenderingInProgress()` until False → mutate the queue → `StartRendering()` |
| `DeleteRenderJob(jobId)` returns `None` | Not implemented | Use `DeleteAllRenderJobs()` — it works, but only while nothing is rendering |
| A cancelled job starts rendering again | `StartRendering()` restarts every job still in the queue | After cancelling, clear the queue, then add exactly one job |
| `StopRendering()` seems to do nothing | It is asynchronous | The job flips to `Cancelled` a few seconds later; the output file keeps growing briefly while the encoder flushes |
| `SetRenderSettings` returns `False` | Some keys are rejected (`VideoQuality`, `ColorSpaceTag`, `GammaTag` were the suspects) | Most keys still apply. After `AddRenderJob()` read back `FormatWidth`, `FormatHeight`, `MarkIn`, `MarkOut` from the job and verify |
| `StartFrame` / `EndFrame` in render settings do nothing | Not honored | Use `MarkIn` / `MarkOut` (absolute timeline frame numbers) |
| `ti.SetMarkInOut()` returns `False` | Not functional | Set the range through render settings |
| `AddRenderJob()` returns an id but nothing renders | Adding a job does not start it | Call `StartRendering()` afterwards |
| Render percentage seems stuck or jumps | `CompletionPercentage` is coarse (1 % ≈ 10 frames at 988) | Poll the output file size and `nb_frames` for real progress |
| The queue appears empty after a project switch | The queue belongs to the current project | Check `GetCurrentProject().GetName()` before concluding anything is wrong |

## MCP bridge layer

| Symptom | Cause | Workaround |
|---|---|---|
| An MCP call times out on work that takes minutes | `run_script` / `run_script_unsafe` cap the timeout at 60 s | Use `scripts/resolve_bridge.py script <file.py> --timeout=600` |
| Bridge output looks like `{"output": "…"}` instead of raw text | The MCP server returns the result as a plain object on some calls | Parse both shapes; print flat `key=value` markers from inside Resolve instead of JSON to avoid escaping problems |
| A script cannot write files | `run_script` is sandboxed | Use the bridge's `--unsafe` flag (`run_script_unsafe`) when filesystem writes are required |
| Bridge scripts "see" an undefined name such as `project` | The script relies on injected globals that are absent when the project cannot be resolved | Resolve the project inside the script (`resolve.GetProjectManager().GetCurrentProject()`) and guard every call |
| The script produced no output at all and wrote no file | `sys.exit()` inside the Resolve context is swallowed by the MCP server, and `__name__` is not `"__main__"` | Do not use `sys.exit()`; call `main()` at the end of the module and print a marker line (`LUT_JSON:…`) |
| `NameError: name '__file__' is not defined` | The script is executed from a string, not from a file | Use `os.getcwd()` as a fallback, or pass paths through environment variables |
| `NameError: name 'globals' is not defined` | The sandboxed `run_script` has no `globals` builtin | In `run_script` use the injected names directly (`resolve`, `project`); the bridge variant does provide `globals()` |
| `SyntaxError: invalid non-printable character U+FEFF` | The script was written by PowerShell `Set-Content -Encoding UTF8`, which adds a BOM | The bridge reads scripts as `utf-8-sig`; for other readers strip the BOM or write with `utf-8` without BOM |

## Scripts executed inside Resolve

The MCP server compiles the script from a string and runs it in Resolve's own
Python. Three rules follow from that, and all three cost a cycle if forgotten:

1. **No `sys.exit()`.** The server swallows it — the call returns "no output".
2. **No `__file__`, no `globals()`** in the sandboxed `run_script`. Use
   `os.getcwd()` and the injected names.
3. **The script must not depend on the caller's working directory.** Pass paths
   through environment variables (`ZOVOD_*`) — the bridge forwards the
   environment of the calling shell.

Everything else behaves like normal Python 3.


## ffmpeg / numpy

| Symptom | Cause | Workaround |
|---|---|---|
| `lut3d` filter fails to parse a file path | A Windows drive letter contains a colon, which the filter parser treats as a separator | Copy the `.cube` to a colon-free path and reference the copy |
| The grade looks wrong but the cube is valid | The 3D LUT was indexed as `lut[g,r,b]` instead of the flat `(b*N+g)*N+r` | Red is the fastest-varying axis in a `.cube` for Resolve; verify with the anchor points |
| `cv2.randn` raises | OpenCV 5 requires an explicit `stddev` | Use `numpy.random.default_rng(seed).standard_normal(shape)` for deterministic grain |
| The numpy post pass takes ~25 min at 4K | `np.apply_along_axis` + `np.convolve` is orders of magnitude slower than `cv2.filter2D` | Move convolution work to OpenCV, or accept the cost and run it in the background |

## Background/housekeeping

- `Remove-Item` and recursive delete/move are blocked by policy on this
  machine; use reversible renames through Python instead.
- Resolve must be started through `ResolvePortable.exe`; `Resolve.exe` crashes
  with `0xC0000409`, and the MCP `launch_resolve` tool fails on this build.
