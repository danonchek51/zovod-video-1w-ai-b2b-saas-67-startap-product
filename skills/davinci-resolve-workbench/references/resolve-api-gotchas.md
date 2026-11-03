# Resolve API gotchas (21.1.1.10, portable build)

Every entry is something that actually broke or silently misbehaved. Format:
**symptom → cause → workaround**. When a call returns `False`/`None`, look
here before retrying — most of these are unsupported operations, not flaky
calls.

## Project and session

| Symptom | Cause | Workaround |
|---|---|---|
| A running render dies and the queue looks empty | `pm.LoadProject(name)` switches the *current* project; the queue belongs to the project you left | Status/polling scripts must use `pm.GetCurrentProject()` only. Call `LoadProject` only when the name differs, and never inside a polling loop |
| `ExportProject` raises `'NoneType' object is not callable` | Not exposed in this build | The project lives in Resolve's database. Promise the project/timeline name, not a `.drp` file |
| `GetTimelineList()`, `tl.GetPropertyList()`, `ti.GetPropertyList()` raise `'NoneType' object is not callable` | Not exposed | Use `GetCurrentTimeline()` and specific getters; enumerate by other means |
| `ti.GetProperty("Stabilization")` returns `False` while stabilization is active | Property is not readable through the API | `ti.Stabilize()` returning `True` is the only signal. Verify the effect by measuring frame-to-frame motion in the rendered output |
| Timeline frame numbers look huge (`90000..90988`) | Projects can start at a non-zero frame offset | All frame-index APIs (render `MarkIn`/`MarkOut`, `GetStart`/`GetEnd`) use the same absolute numbering — do not treat them as 0-based |

## Color page / node graph

| Symptom | Cause | Workaround |
|---|---|---|
| No way to add nodes to the graph | `Graph` in the scripting API exposes only `SetLUT`, `SetNodeEnabled`, `ResetAllGrades`, `GetToolsInNode`, `GetLUT`, `GetNumNodes` — there is no `AddNode` | Script one Color node carrying the LUT, and move every other stage into the Fusion comp. Encode WB/exposure inside the LUT instead of building 4 nodes |
| `SetCDL` on the clip blows the image out (measured transfer ≈ `y = 1.19·x^0.196` instead of the intended linear mapping) | Resolve applies the CDL with its own transfer curve | Do not use `SetCDL`. Put WB/exposure in the LUT and apply the CDL in the offline post pass with the same math the preview used |
| `SetCDL({"NodeIndex": 2, ...})` returns `False` | There is no node 2 | `SetCDL` can only address node 1 |
| Disabling a node cannot be undone reliably | `SetNodeEnabled` is not a clean round-trip | Recover with `ResetAllGrades()` then `SetLUT(1, absolute_path)` |
| LUT seems applied but the picture is unchanged | Relative path or wrong folder | Install the cube in `…\DaVinci Resolve\Support\LUT\MCP\` and reference it as `MCP\Name.cube`; elsewhere use an absolute path. Confirm with `ti.GetNodeGraph(1).GetLUT(1)` |
| `ApplyGradeFromDRX` does nothing | Malformed/unsupported DRX | Do not rely on it; build the grade from LUT + Fusion |

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
