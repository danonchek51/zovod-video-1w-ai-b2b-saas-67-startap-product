# Environment map

Everything the workbench depends on, verified on this machine. Re-check with
`scripts/resolve_doctor.py` when something behaves oddly.

## DaVinci Resolve

Portable Studio build, version 21.1.1.10 (`resolve.GetVersionString()` returns
`21.1.1.10`).

```
<Resolve App>\
  ResolvePortable.exe                   <- launcher для portable-сборки
  Resolve\App\                          <- RESOLVE_APP_DIR
    DaVinci Resolve\
      Resolve.exe                       <- не запускать напрямую (crash 0xC0000409)
      ResolveMCP.exe                   <- MCP server
      fusionscript.dll                  <- RESOLVE_SCRIPT_LIB
    Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\
      Modules\                          <- RESOLVE_SCRIPT_API (DaVinciResolveScript.py)
      DaVinciResolveScript.pyi          <- typed API stubs, grep for signatures
      README.md                         <- settings/property tables
```

Путь `<Resolve App>` берётся из `tools/env_paths.py` → `env_paths.resolve_exe()`
(переопределяется переменной `RESOLVE_APP_DIR`).

Start it with `Start-Process -FilePath <ResolvePortable.exe> -WorkingDirectory
<Split-Path>` (Windows) or `open -a <Resolve>.app` (macOS). First boot takes
40–90 s; the MCP server answers only after the scripting API is up, so poll
`get_resolve_status` instead of assuming failure.

## MCP wiring

Конфигурация MCP-клиента (`<профиль>/mcp.json`) содержит сервер:

```json
"davinci-resolve": {
  "type": "stdio",
  "command": "<Resolve App>\\DaVinci Resolve\\ResolveMCP.exe",
  "env": {
    "RESOLVE_SCRIPT_API": "<Resolve App>\\Blackmagic Design\\DaVinci Resolve\\Support\\Developer\\Scripting\\Modules",
    "RESOLVE_SCRIPT_LIB": "<Resolve App>\\DaVinci Resolve\\fusionscript.dll"
  }
}
```

Both env vars must exist, otherwise the server starts but every scripting call
fails. The version path in this config is tied to the portable build — if
Resolve is updated, the config path and the stubs location change together.

Tools the server exposes: `run_script`, `run_script_unsafe`, `generate_lut`,
`list_luts`, `list_dctls`, `update_dctl`, `delete_dctl`, `delete_lut`,
`get_scripting_api`, `search_scripting_api`, `get_scripting_docs`,
`get_resolve_status`, `get_whats_new`.

Timeout ceiling for `run_script` / `run_script_unsafe` is 60 s. `scripts/resolve_bridge.py`
speaks the same protocol and lifts that ceiling, which is what makes long
operations (stabilization, LUT generation, render setup) possible.

## Toolchain

- ffmpeg / ffprobe: `env_paths.ffmpeg()` / `env_paths.ffprobe()` (fallback — `shutil.which`)
- Python: `sys.executable` — numpy, cv2, PIL установлены
- LUT folder (Resolve): `env_paths.lut_dir()` — записываемый; Resolve резолвит
  cube по имени файла в подкаталоге

## Project database

Projects live in Resolve's own database, not as files. `ExportProject` is not
available in this build, so a project cannot be handed over as a `.drp` — report
the project and timeline names instead. The database for the portable build
lives under the Resolve install / user profile; find it with
`%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Resolve Disk Database`.

## Workspace conventions

The user's working folder for a video task is whatever workspace the session
opens in. Keep a predictable layout so the next step can find things:

```
<workspace>/
  preview/      low-res previews and stills
  qc/           control frames, contact sheets, metric reports
  final/        the delivered master and its compact copy
  raw/          intermediate renders straight out of Resolve
```

Intermediate renders are large (a 4K master is ~1.5 GB). Do not keep more than
one raw render and one final per iteration.

## Housekeeping rules on this machine

- `Remove-Item` and recursive delete/move are blocked by policy; rename instead
  of deleting.
- PowerShell 5.1 has no `&&` / `||`.
- `python3` is not available; use `C:\Python314\python.exe`.
