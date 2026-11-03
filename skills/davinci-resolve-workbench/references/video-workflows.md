# Video workflows: media in, delivery out

Task-independent mechanics of a video job in Resolve. The color branch lives in
`color-look-development.md`.

## Media pool and timeline

```python
import resolve
pm = resolve.GetProjectManager()
proj = pm.GetCurrentProject()          # never LoadProject() here - it switches projects
pool = pm.GetMediaPool()

# import: returns a list of MediaPoolItem
items = pool.ImportMedia([r"C:\path\clip.mov"])

# project settings must be set BEFORE the timeline is created
proj.SetSetting("timelineResolutionWidth", "3840")
proj.SetSetting("timelineResolutionHeight", "2160")
proj.SetSetting("timelineFrameRate", "25")

tl = pool.CreateTimelineFromClips("My Timeline", items)   # or pool.CreateEmptyTimeline(name)
proj.SetCurrentTimeline(tl)
```

- `SetSetting` for the timeline resolution/frame rate affects timelines created
  afterwards. Changing it later does not re-scale an existing timeline.
- Items on the timeline: `tl.GetItemListInTrack("video", 1)` /
  `tl.GetItemListInTrack("audio", 1)`; the clip frame range is
  `ti.GetStart()` / `ti.GetEnd()` (absolute frame numbers).
- Keep the source frame rate. A 25 fps source rendered at 25 fps keeps
  duration and motion identical; mismatches introduce judder that no amount of
  grading hides.

## Render settings that actually apply

```python
project.SetCurrentRenderFormatAndCodec("mp4", "H264")
project.SetRenderSettings({
    "TargetDir":  r"C:\path\to\raw",
    "CustomName": "render_name",
    "ExportVideo": True,
    "ExportAudio": True,
    "FormatWidth": 3840,
    "FormatHeight": 2160,
    "VideoCodec": "H264",
    "VideoBitDepth": 8,
    "AudioCodec": "aac",
    "AudioBitDepth": 16,
    "AudioSampleRate": 48000,
    "SelectAllFrames": True,
})
job_id = project.AddRenderJob()
project.StartRendering()
```

Notes:

- `SetRenderSettings` may return `False` while still applying most keys.
  `StartFrame`/`EndFrame` are ignored — use `MarkIn`/`MarkOut`.
- `VideoQuality`, `ColorSpaceTag` and `GammaTag` were not accepted; bitrate
  therefore cannot be steered from the API. Compensate at the post pass
  (CRF-based x264 encode) if a specific size matters.
- After `AddRenderJob()`, read the created job back and check `FormatWidth`,
  `FormatHeight`, `MarkIn`, `MarkOut`:
  `project.GetRenderJobList()`.

## Queue management (the fragile part)

```python
# 1. stop whatever is running and WAIT for it to stop
project.StopRendering()
while project.IsRenderingInProgress():
    time.sleep(2)

# 2. now the queue can be edited
project.DeleteAllRenderJobs()          # DeleteRenderJob(id) does nothing here
project.SetRenderSettings({...})
project.AddRenderJob()

# 3. start exactly the job you want
project.StartRendering()
```

`StopRendering()` is asynchronous — the job flips to `Cancelled` a few seconds
later and the output file keeps growing while the encoder flushes. And
`StartRendering()` restarts every job still queued, including cancelled ones,
so always clear the queue first.

Progress polling: `project.GetRenderJobStatus(job_id)` gives `JobStatus` and a
coarse `CompletionPercentage`. For real progress, watch the output file size
and `nb_frames` instead. The MCP call itself blocks while Resolve renders, so
poll the file from outside rather than hammering the API.

## Measured speeds (portable build, 3840×2160 source)

| Work | Speed | Note |
|---|---|---|
| Resolve render, LUT + Fusion glow + grain, 4K | ~3.7 fps | 988 frames ≈ 4–5 min |
| Resolve render, same chain, 720p | ~13 fps | |
| Offline numpy post pass (CDL + vignette) at 4K | ~0.7 fps | 988 frames ≈ 23 min — move convolution work to `cv2` if it needs to be faster |
| Offline preview render at 1080p | ~1.25 fps | includes the Python glow implementation |

## Verification commands

```powershell
# full decode check (no output == clean)
ffmpeg -v error -i OUT.mp4 -f null -

# technical specs
ffprobe -v error `
  -select_streams v:0 -show_entries stream=width,height,nb_frames,r_frame_rate `
  -show_entries format=duration,size -of default=nw=1 OUT.mp4
```

Путь к ffmpeg/ffprobe берётся из `tools/env_paths.py`
(`env_paths.ffmpeg()` / `env_paths.ffprobe()`); если они не заданы —
используется `ffmpeg` / `ffprobe` из PATH.

Or use the bundled scripts: `media_probe.py OUT.mp4` for metadata plus palette
stats, `frame_qc.py compare --src A --graded B` for control frames and metrics,
`frame_qc.py motion --src A --graded B --start 200 --count 40` for
stabilization verification.

## Packaging for delivery

A 4K master is ~1.5 GB and usually cannot be attached to a chat message.
Produce two extra files:

- a compact full-length copy (960×540, CRF 20) — a few MB, good for review;
- an 8-second excerpt (1080p) for a quick look at the part that matters.

```powershell
ffmpeg -v error -y -i FINAL.mp4 `
  -vf "scale=960:540:flags=lanczos" -c:v libx264 -preset medium -crf 20 `
  -pix_fmt yuv420p -c:a aac -b:a 128k -movflags +faststart COMPACT.mp4
```

Keep the master in the workspace, deliver the master path plus the compact
files, and state the technical specs of each.

## Delivery checklist

1. Full decode without errors.
2. Frame count equals the source (988 frames at 25 fps for a 39.5 s clip).
3. Audio stream present when the source had audio.
4. Metrics measured, not eyeballed (`media_probe.py`, `frame_qc.py`).
5. Absolute path reported, plus a compact version for chat.
