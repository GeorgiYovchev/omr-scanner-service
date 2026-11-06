"""Demo-scraping OMR service (Windows).

The vendor demo (LScannerSDKDemo.exe) is the only stable driver of the SDK: it
auto-scans + auto-ejects reliably. We launch it, press "Start Scan", then read its
"Decode Result" edit control's TEXT via Win32 WM_GETTEXT (accessibility, not pixels),
parse the per-row hex, map with genlot_map, and broadcast {type,blocks,draws} on :8443.

Run on Windows:  py -3.13 demo_scrape.py
  Env: WS_PORT (8443), WS_HOST (0.0.0.0), DEMO_EXE, OMR_LIB64.
"""
from __future__ import annotations
import asyncio
import ctypes
import ctypes.wintypes as wt
import json
import os
import re
import subprocess
import threading
import time

import websockets
from genlot_map import to_output

WS_HOST = os.environ.get("WS_HOST", "0.0.0.0")
WS_PORT = int(os.environ.get("WS_PORT", "8443"))
LIB64 = os.environ.get("OMR_LIB64", r"C:\Repos\gitlab\OMR\lib64")
DEMO_EXE = os.environ.get("DEMO_EXE", os.path.join(LIB64, "bin", "LScannerSDKDemo.exe"))
DEMO_TITLE = "LScannerSDKDemo"

u32 = ctypes.windll.user32
WM_GETTEXT, WM_GETTEXTLENGTH, BM_CLICK = 0x000D, 0x000E, 0x00F5
clients: set = set()
_loop = None

# ---- Win32 window/control helpers ----------------------------------------
def find_main():
    return u32.FindWindowW(None, DEMO_TITLE)

def _children(hwnd):
    out = []
    EP = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(h, _):
        out.append(h); return True
    u32.EnumChildWindows(hwnd, EP(cb), 0)
    return out

def _class(h):
    b = ctypes.create_unicode_buffer(128); u32.GetClassNameW(h, b, 128); return b.value

def _text(h):
    n = u32.SendMessageW(h, WM_GETTEXTLENGTH, 0, 0)
    b = ctypes.create_unicode_buffer(n + 1)
    u32.SendMessageW(h, WM_GETTEXT, n + 1, ctypes.byref(b))
    return b.value

def find_result_edit(main):
    """The multiline Edit whose text has the decode grid."""
    best, best_len = None, -1
    for h in _children(main):
        if _class(h).lower() == "edit":
            t = _text(h)
            if "Decode type" in t or re.search(r"[0-9A-Fa-f]{2}\s+[0-9A-Fa-f]{2}\s*\|", t):
                return h
            if len(t) > best_len:
                best, best_len = h, len(t)
    return best

def click_start(main):
    for h in _children(main):
        if _class(h).lower() == "button":
            t = _text(h).lower()
            if "start" in t and "scan" in t:
                u32.SendMessageW(h, BM_CLICK, 0, 0); return True
    return False

# ---- parse demo text -> our 51-byte buffer -> JSON ------------------------
HEADER = bytes([0x01, 0x2c, 0x00, 0x0f, 0x00, 0x16, 0x00])
ROW_RE = re.compile(r"\b([0-9A-Fa-f]{2})\s+([0-9A-Fa-f]{2})\s*\|")

def parse_to_json(text):
    rows = ROW_RE.findall(text)          # list of (hi, lo) hex per row, in order
    if len(rows) < 22:
        return None
    data = bytearray()
    for hi, lo in rows[:22]:
        data += bytes([int(hi, 16), int(lo, 16)])
    raw = HEADER + bytes(data)           # 7 + 44 = 51
    try:
        return json.dumps(to_output(raw))
    except Exception:
        return None

# ---- websocket ------------------------------------------------------------
async def _handler(ws):
    clients.add(ws); print(f"[ws] client +{len(clients)}", flush=True)
    try: await ws.wait_closed()
    finally: clients.discard(ws); print(f"[ws] client -{len(clients)}", flush=True)

async def _broadcast(m):
    for ws in list(clients):
        try: await ws.send(m)
        except Exception: clients.discard(ws)

def broadcast_ts(m):
    if _loop: asyncio.run_coroutine_threadsafe(_broadcast(m), _loop)

# ---- scrape loop ----------------------------------------------------------
def scrape_loop():
    # ensure the demo is running
    main = find_main()
    if not main:
        print("[demo] launching", DEMO_EXE, flush=True)
        subprocess.Popen([DEMO_EXE], cwd=os.path.dirname(DEMO_EXE))
        for _ in range(60):
            main = find_main()
            if main: break
            time.sleep(0.5)
    if not main:
        print("[demo] could not find/launch demo window", flush=True); return
    time.sleep(1.0)
    print("[demo] start scan:", click_start(main), flush=True)

    edit = None
    last = None
    while True:
        try:
            if not u32.IsWindow(main):
                main = find_main() or main; edit = None
            if edit is None or not u32.IsWindow(edit):
                edit = find_result_edit(main)
            if edit:
                t = _text(edit)
                if t and t != last:
                    last = t
                    msg = parse_to_json(t)
                    if msg:
                        print("[scan] ->", msg, flush=True)
                        broadcast_ts(msg)
        except Exception as e:
            print("[scrape] err:", e, flush=True)
        time.sleep(0.2)

async def main():
    global _loop
    _loop = asyncio.get_running_loop()
    threading.Thread(target=scrape_loop, daemon=True).start()
    async with websockets.serve(_handler, WS_HOST, WS_PORT):
        print(f"[ws] listening on ws://{WS_HOST}:{WS_PORT}", flush=True)
        await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
