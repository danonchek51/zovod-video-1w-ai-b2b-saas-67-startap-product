"""Check that the DaVinci Resolve workbench is ready before starting a video task.

Run:  python resolve_doctor.py
Exit code 0 when nothing is blocking; 1 when a required piece is missing.

It answers, in one shot: is Resolve running, does the MCP server answer, is the
MCP config pointing at the right build, are ffmpeg and the Python imaging
modules present, is the LUT folder writable, and what project/timeline is open.
"""
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True          # keep the skill folder free of __pycache__
sys.path.insert(0, HERE)
import resolve_bridge as RB  # noqa: E402

PYTHON = sys.executable
MCP_CONFIG = os.path.join(os.path.expanduser("~"), ".minimax", "mcp.json")
FFMPEG_HINTS = [
    r"C:\Program Files\ffmpeg\bin",
    "/usr/local/bin",
    "/opt/homebrew/bin",
    "/usr/bin",
]
LUT_DIRS = [
    r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\LUT",
    "/Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT",
]

results = []


def _env_paths():
    """tools/env_paths.py пакета (если доступен) — источник настроек путей."""
    try:
        pkg_root = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
        tools_dir = os.path.join(pkg_root, "tools")
        if os.path.isfile(os.path.join(tools_dir, "env_paths.py")):
            if tools_dir not in sys.path:
                sys.path.insert(0, tools_dir)
            import env_paths
            return env_paths
    except Exception:
        pass
    return None


def ok(name, detail=""):
    results.append(("OK", name, detail))


def warn(name, detail=""):
    results.append(("WARN", name, detail))


def fail(name, detail=""):
    results.append(("FAIL", name, detail))


def which_tool(name):
    found = shutil.which(name)
    if found:
        return found
    ep = _env_paths()
    if ep is not None:
        cfg = ep.ffmpeg() if name == "ffmpeg" else ep.ffprobe()
        if cfg and os.path.isfile(cfg):
            return cfg
    for hint in FFMPEG_HINTS:
        p = os.path.join(hint, name + (".exe" if os.name == "nt" else ""))
        if os.path.isfile(p):
            return p
    return None


def check_process():
    if os.name == "nt":
        try:
            out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Resolve.exe"],
                                 capture_output=True, text=True, timeout=30).stdout
            if "Resolve.exe" in out:
                ok("Resolve process", "running")
                return
            out2 = subprocess.run(["tasklist", "/FI", "IMAGENAME eq ResolvePortable.exe"],
                                  capture_output=True, text=True, timeout=30).stdout
            if "ResolvePortable.exe" in out2:
                warn("Resolve process", "only the launcher is visible; Resolve.exe may still be booting")
                return
        except Exception as e:
            warn("Resolve process", "tasklist failed: %s" % e)
    fail("Resolve process", "not running — start ResolvePortable.exe (Resolve.exe alone crashes with 0xC0000409)")


def check_paths():
    try:
        app = RB.find_app_dir()
    except SystemExit as e:
        fail("Resolve install", str(e))
        return None
    mcp_exe = os.path.join(app, "DaVinci Resolve", "ResolveMCP.exe")
    api = os.path.join(app, "Blackmagic Design", "DaVinci Resolve", "Support",
                        "Developer", "Scripting", "Modules")
    lib = os.path.join(app, "DaVinci Resolve", "fusionscript.dll")
    stubs = os.path.join(app, "Blackmagic Design", "DaVinci Resolve", "Support",
                         "Developer", "Scripting", "DaVinciResolveScript.pyi")
    for label, path, must in (("ResolveMCP.exe", mcp_exe, True),
                              ("RESOLVE_SCRIPT_API", api, True),
                              ("RESOLVE_SCRIPT_LIB", lib, True),
                              ("API stubs (.pyi)", stubs, False)):
        if os.path.exists(path):
            ok(label, path)
        elif must:
            fail(label, "missing: " + path)
        else:
            warn(label, "missing (API lookup will be slower): " + path)
    return app


def check_mcp_config():
    if not os.path.isfile(MCP_CONFIG):
        warn("mcp.json", "not found at " + MCP_CONFIG)
        return
    try:
        with open(MCP_CONFIG, "r", encoding="utf-8-sig") as f:
            cfg = json.load(f)
    except Exception as e:
        fail("mcp.json", "unreadable: %s" % e)
        return
    servers = cfg.get("mcpServers", {})
    entry = servers.get("davinci-resolve")
    if not entry:
        warn("mcp.json", "no 'davinci-resolve' entry — the agent can still use scripts/resolve_bridge.py")
        return
    cmd = entry.get("command", "")
    if os.path.isfile(cmd):
        ok("mcp.json davinci-resolve", cmd)
    else:
        fail("mcp.json davinci-resolve", "command not found: " + cmd)
    env = entry.get("env", {})
    for k in ("RESOLVE_SCRIPT_API", "RESOLVE_SCRIPT_LIB"):
        v = env.get(k, "")
        if v and os.path.exists(v):
            ok("mcp.json " + k, "ok")
        else:
            warn("mcp.json " + k, "missing or stale: " + v)


def check_mcp_live():
    try:
        out = subprocess.run([PYTHON, os.path.join(HERE, "resolve_bridge.py"),
                              "call", "get_resolve_status", "{}"],
                             capture_output=True, text=True, timeout=120).stdout.strip()
    except Exception as e:
        fail("MCP server", "bridge call failed: %s" % e)
        return
    try:
        data = json.loads(out)
    except Exception:
        fail("MCP server", "unexpected answer: " + out[:200])
        return
    if data.get("running"):
        ok("MCP server", "Resolve %s is answering" % data.get("version"))
    else:
        fail("MCP server", "not running (version %s)" % data.get("version"))


def check_project():
    script = os.path.join(HERE, "_doctor_state.py")
    try:
        out = subprocess.run([PYTHON, os.path.join(HERE, "resolve_bridge.py"), "script", script],
                             capture_output=True, text=True, timeout=180).stdout.strip()
    except Exception as e:
        warn("project state", "probe failed: %s" % e)
        return
    marker = "DOCTORSTATE "
    if marker not in out:
        warn("project state", "no data: " + out[:200])
        return
    raw = out.split(marker, 1)[1].strip()
    fields = {}
    for chunk in raw.split("|"):
        if "=" in chunk:
            k, v = chunk.split("=", 1)
            fields[k.strip()] = v.strip()
    if "project" not in fields:
        warn("project state", "unparsable: " + raw[:200])
        return
    if fields.get("error"):
        warn("project state", fields["error"][:200])
        return
    if fields.get("project") and fields["project"] != "none":
        ok("current project", fields["project"])
    else:
        warn("current project", "none open")
    if fields.get("timeline") and fields["timeline"] != "none":
        ok("current timeline", fields["timeline"])
    else:
        warn("current timeline", "none open")
    if fields.get("rendering") == "true":
        warn("render queue", "a render is in progress — mutating API calls return None until it finishes")
    else:
        ok("render queue", "idle")


def check_tools():
    ff = which_tool("ffmpeg")
    fp = which_tool("ffprobe")
    if ff:
        ok("ffmpeg", ff)
    else:
        fail("ffmpeg", "not found — add it to PATH or place it in " + FFMPEG_HINTS[0])
    if fp:
        ok("ffprobe", fp)
    else:
        fail("ffprobe", "not found")
    for mod in ("numpy", "cv2", "PIL"):
        try:
            __import__(mod)
            ok("python module " + mod, "available")
        except Exception:
            warn("python module " + mod, "not installed — needed for frame/metric work")
    for d in LUT_DIRS:
        if os.path.isdir(d):
            ok("LUT folder", d)
            try:
                probe = os.path.join(d, "_write_probe.tmp")
                with open(probe, "w", encoding="utf-8") as f:
                    f.write("x")
                os.remove(probe)
            except Exception as e:
                fail("LUT folder writable", "%s: %s" % (d, e))
        else:
            warn("LUT folder", "missing: " + d)


def main():
    check_process()
    check_paths()
    check_mcp_config()
    check_mcp_live()
    check_project()
    check_tools()

    width = max(len(n) for _, n, _ in results) + 2
    order = {"FAIL": 0, "WARN": 1, "OK": 2}
    for level, name, detail in sorted(results, key=lambda r: order[r[0]]):
        print("[%s] %s %s" % (level, name.ljust(width), detail))
    fails = sum(1 for lvl, _, _ in results if lvl == "FAIL")
    warns = sum(1 for lvl, _, _ in results if lvl == "WARN")
    print("\n%d ok, %d warnings, %d failures" % (
        sum(1 for lvl, _, _ in results if lvl == "OK"), warns, fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
