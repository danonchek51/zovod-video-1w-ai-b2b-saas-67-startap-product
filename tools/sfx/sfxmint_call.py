#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sfxmint_call.py - вызов SFXMint MCP (Streamable HTTP) напрямую, без ключа.

Зачем: MCP-сервер SFXMint удалённый (https://sfxmint.com/mcp), библиотечные
инструменты работают без API-ключа. Этот скрипт - тот же JSON-RPC вызов, но
из обычного Python: работает, когда рантайм ещё не подхватил сервер, и годится
для батчей (скачать много звуков за один проход).

Использование:
    python sfxmint_call.py tools
    python sfxmint_call.py call search_sounds '{"query":"car crash impact","limit":5}'
    python sfxmint_call.py call get_role_sound '{"role":"impact"}'

Ключ (необязателен, только для генерации):
    set SFXMINT_API_KEY=sfx_live_...   -> уходит в заголовок Authorization

Замечание про лимиты: скачивание без ключа - 20 РАЗНЫХ звуков в сутки на сеть.
Прослушивание в браузере не считается. 429 download_limit - не ретраить.
"""
import argparse
import json
import sys
import urllib.request
import urllib.error

ENDPOINT = "https://sfxmint.com/mcp"
PROTOCOL = "2025-06-18"
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


def _rpc(method, params, _id=1, path=None):
    """Один JSON-RPC вызов. path=None -> initialize, иначе tools/call."""
    if path is None:
        payload = {
            "jsonrpc": "2.0",
            "id": _id,
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL,
                "capabilities": {},
                "clientInfo": {"name": "sfxmint_call.py", "version": "1.0"},
            },
        }
        url = ENDPOINT
    else:
        payload = {"jsonrpc": "2.0", "id": _id, "method": path, "params": params}
        url = ENDPOINT

    headers = dict(HEADERS)
    key = _env_key()
    if key:
        headers["Authorization"] = "Bearer " + key

    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode("utf-8", "replace")
    return _parse(raw)


def _env_key():
    import os
    return os.environ.get("SFXMINT_API_KEY", "").strip()


def _parse(raw):
    """Streamable HTTP может вернуть SSE-формат (data: {...}) или чистый JSON."""
    raw = raw.strip()
    if raw.startswith("event:") or raw.startswith("data:"):
        for line in raw.splitlines():
            if line.startswith("data:"):
                chunk = line[5:].strip()
                if chunk:
                    try:
                        return json.loads(chunk)
                    except json.JSONDecodeError:
                        continue
        return {"_raw": raw}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw": raw}


def _unwrap(resp):
    """Достаёт содержимое из JSON-RPC ответа (result.content[0].text -> json)."""
    if "_raw" in resp:
        return resp
    if "error" in resp:
        return {"error": resp["error"]}
    res = resp.get("result", resp)
    if isinstance(res, dict) and "content" in res:
        out = []
        for blk in res.get("content", []):
            if blk.get("type") == "text":
                txt = blk.get("text", "")
                try:
                    out.append(json.loads(txt))
                except json.JSONDecodeError:
                    out.append(txt)
            else:
                out.append(blk)
        res = out[0] if len(out) == 1 else out
    if isinstance(res, dict) and res.get("isError"):
        return {"error": res.get("content", res)}
    return res


def call(tool, args):
    _rpc("initialize", None, 1)
    resp = _rpc(None, {"name": tool, "arguments": args}, 2, path="tools/call")
    return _unwrap(resp)


def list_tools():
    resp = _rpc(None, {}, 2, path="tools/list")
    if "error" in resp:
        return resp
    return [t["name"] for t in resp.get("result", {}).get("tools", [])]


def _load_args(raw):
    """Аргументы: либо inline-JSON, либо @путь_к_json_файлу (надёжнее в PowerShell)."""
    if not raw:
        return {}
    if raw.startswith("@"):
        with open(raw[1:], "r", encoding="utf-8") as fh:
            return json.load(fh)
    return json.loads(raw)


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="sfxmint_call.py",
        description="вызов SFXMint MCP (Streamable HTTP) напрямую, без ключа")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("tools", help="показать список инструментов сервера")
    c = sub.add_parser("call", help="вызвать один инструмент")
    c.add_argument("tool", help="имя инструмента")
    c.add_argument("args", nargs="?", default="",
                   help="аргументы: inline-JSON или @путь_к_json_файлу")
    b = sub.add_parser("batch", help="вызвать пачку инструментов из @файла")
    b.add_argument("spec", nargs="?", default="", help="@путь_к_json_файлу со списком вызовов")
    b.add_argument("--out", default="", help="куда сохранить JSON-отчёт")
    a = p.parse_args(argv)

    if a.cmd == "tools":
        for n in list_tools():
            print(n)
        return 0
    if a.cmd == "call":
        args = _load_args(a.args or None)
        print(json.dumps(call(a.tool, args), ensure_ascii=False, indent=2))
        return 0
    if a.cmd == "batch":
        spec = _load_args(a.spec or None)
        out = []
        for item in spec:
            out.append({"tool": item["tool"], "args": item.get("args", {}),
                        "result": call(item["tool"], item.get("args", {}))})
        blob = json.dumps(out, ensure_ascii=False, indent=2)
        if a.out:
            with open(a.out, "w", encoding="utf-8") as fh:
                fh.write(blob)
            print("saved: %s (%d bytes)" % (a.out, len(blob.encode("utf-8"))))
        else:
            print(blob)
        return 0
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
