"""Thin stdio client for DaVinci Resolve's built-in MCP server (ResolveMCP.exe).

Why this exists: the MCP tools exposed to an agent cap `run_script` at a 60 s
timeout, while operations like stabilization analysis or render setup take
minutes. This client speaks the same MCP protocol but lets the caller raise
the timeout to minutes.

Usage:
  python resolve_bridge.py tools
  python resolve_bridge.py call <tool> ['<json>' | @<file.json>]
  python resolve_bridge.py script <file.py> [--unsafe] [--timeout=600]

Stdlib only. Resolve's location is auto-detected; override with the
RESOLVE_APP_DIR environment variable. В пакете путь также берётся из
tools/env_paths.py (env_paths.resolve_exe()), если модуль доступен.
"""
import json
import os
import subprocess
import sys
import threading
import time
import queue

PROTOCOL = "2024-11-05"

# Известные формы установки, сначала самые специфичные.
CANDIDATE_APP_DIRS = [
    r"C:\Program Files\Blackmagic Design\DaVinci Resolve",
    r"C:\Program Files\Blackmagic Design\DaVinci Resolve Studio",
    "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents",
]


def _env_paths():
    """tools/env_paths.py пакета (если доступен) — источник настроек путей."""
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        pkg_root = os.path.abspath(os.path.join(here, "..", "..", ".."))
        tools_dir = os.path.join(pkg_root, "tools")
        if os.path.isfile(os.path.join(tools_dir, "env_paths.py")):
            if tools_dir not in sys.path:
                sys.path.insert(0, tools_dir)
            import env_paths
            return env_paths
    except Exception:
        pass
    return None


def find_app_dir():
    env = os.environ.get("RESOLVE_APP_DIR")
    if env and os.path.isdir(env):
        return env
    # путь из конфигурации пакета
    ep = _env_paths()
    if ep is not None:
        exe = ep.resolve_exe()
        if exe:
            # .../Resolve/App/DaVinci Resolve/Resolve.exe -> .../Resolve/App
            app = os.path.dirname(os.path.dirname(exe))
            if os.path.isdir(app):
                return app
    for c in CANDIDATE_APP_DIRS:
        if os.path.isdir(c):
            return c
    # ограниченный поиск портативной сборки в Downloads
    downloads = os.path.join(os.path.expanduser("~"), "Downloads")
    if os.path.isdir(downloads):
        for root, dirs, _files in os.walk(downloads):
            if os.path.basename(root) == "App" and "DaVinci Resolve" in root:
                return root
            if root.count(os.sep) - downloads.count(os.sep) > 6:
                dirs[:] = []
    return None


def resolve_paths():
    app = find_app_dir()
    if not app:
        raise SystemExit("Resolve install not found. Set RESOLVE_APP_DIR to the folder "
                         "containing 'DaVinci Resolve\\ResolveMCP.exe'.")
    mcp_exe = os.path.join(app, "DaVinci Resolve", "ResolveMCP.exe")
    if not os.path.isfile(mcp_exe):
        raise SystemExit("ResolveMCP.exe not found under: " + app)
    env = os.environ.copy()
    env["RESOLVE_SCRIPT_API"] = os.path.join(
        app, "Blackmagic Design", "DaVinci Resolve", "Support", "Developer", "Scripting", "Modules")
    env["RESOLVE_SCRIPT_LIB"] = os.path.join(app, "DaVinci Resolve", "fusionscript.dll")
    return mcp_exe, env


class MCPClient:
    def __init__(self, timeout=180):
        self.mcp_exe, env = resolve_paths()
        self.timeout = timeout
        self.p = subprocess.Popen([self.mcp_exe], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, env=env, bufsize=0)
        self._id = 0
        self.msgs = queue.Queue()
        self.err = []
        threading.Thread(target=self._pump_out, daemon=True).start()
        threading.Thread(target=self._pump_err, daemon=True).start()

    def _pump_out(self):
        for line in self.p.stdout:
            line = line.decode("utf-8", "replace").strip()
            if not line:
                continue
            try:
                self.msgs.put(json.loads(line))
            except Exception:
                self.msgs.put({"_raw": line})

    def _pump_err(self):
        for line in self.p.stderr:
            self.err.append(line.decode("utf-8", "replace").rstrip())

    def _send(self, obj):
        self.p.stdin.write((json.dumps(obj) + "\n").encode("utf-8"))
        self.p.stdin.flush()

    def _await(self, want_id, timeout=None):
        timeout = timeout or self.timeout
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                msg = self.msgs.get(timeout=max(0.1, deadline - time.time()))
            except queue.Empty:
                break
            if msg.get("id") == want_id:
                return msg
        raise TimeoutError("no response for id=%s; stderr tail: %s" % (want_id, self.err[-6:]))

    def initialize(self):
        self._id += 1
        self._send({"jsonrpc": "2.0", "id": self._id, "method": "initialize",
                    "params": {"protocolVersion": PROTOCOL, "capabilities": {},
                               "clientInfo": {"name": "resolve-bridge", "version": "1.0"}}})
        res = self._await(self._id, 60)
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        return res

    def call(self, tool, arguments=None, timeout=None):
        self.initialize()
        self._id += 1
        self._send({"jsonrpc": "2.0", "id": self._id, "method": "tools/call",
                    "params": {"name": tool, "arguments": arguments or {}}})
        return self._await(self._id, timeout)

    def list_tools(self):
        self.initialize()
        self._id += 1
        self._send({"jsonrpc": "2.0", "id": self._id, "method": "tools/list", "params": {}})
        return self._await(self._id, 60)

    def close(self):
        try:
            self.p.terminate()
            self.p.wait(timeout=5)
        except Exception:
            try:
                self.p.kill()
            except Exception:
                pass


def text_of(resp):
    """Flatten an MCP tool result into plain text.

    The server returns script output either as content blocks (raw text) or as
    a plain object like {"output": "..."}; both shapes are handled here.
    """
    if "error" in resp:
        return "ERROR: " + json.dumps(resp["error"], ensure_ascii=False)
    out = []
    for blk in resp.get("result", {}).get("content", []):
        if blk.get("type") == "text":
            out.append(blk.get("text", ""))
        else:
            out.append(json.dumps(blk, ensure_ascii=False))
    if out:
        return "\n".join(out)
    result = resp.get("result", resp)
    if isinstance(result, dict):
        for key in ("output", "text", "result"):
            v = result.get(key)
            if isinstance(v, str):
                return v
    return json.dumps(result, ensure_ascii=False)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    mode = sys.argv[1]
    client = MCPClient()
    try:
        if mode == "tools":
            r = client.list_tools()
            tools = r.get("result", {}).get("tools", [])
            print(json.dumps(tools, ensure_ascii=False, indent=2))
        elif mode == "call":
            tool = sys.argv[2]
            raw = sys.argv[3] if len(sys.argv) > 3 else ""
            if raw.startswith("@"):
                with open(raw[1:], "r", encoding="utf-8-sig") as f:
                    args = json.load(f)
            elif raw:
                args = json.loads(raw)
            else:
                args = {}
            print(text_of(client.call(tool, args)))
        elif mode == "script":
            path = os.path.abspath(sys.argv[2])
            with open(path, "r", encoding="utf-8") as f:
                code = f.read()
            unsafe = "--unsafe" in sys.argv
            tool = "run_script_unsafe" if unsafe else "run_script"
            tmo = 60
            for a in sys.argv[3:]:
                if a.startswith("--timeout="):
                    tmo = int(a.split("=", 1)[1])
            args = {"script": code, "timeout": tmo}
            print(text_of(client.call(tool, args, timeout=tmo + 90)))
        else:
            print(__doc__)
    finally:
        client.close()


if __name__ == "__main__":
    main()
