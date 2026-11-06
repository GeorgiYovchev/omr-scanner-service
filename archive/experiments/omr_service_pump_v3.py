"""OMR scanner -> WebSocket service (Windows), matching the Linux box.

Single long-lived process. The vendor SDK is MFC-based: its paper-feed/scan-complete
notifications are delivered as WINDOW MESSAGES to the thread that called SInit. A
plain Python thread has no message queue, so SRollBack never gets its "feed
complete" message and wedges. Fix: the scanner thread creates a message queue and
pumps messages around every SDK call, exactly like the vendor's MFC demo.

Serves {type,blocks,draws} JSON on :8443 — same contract as the Linux publisher.

Run on Windows:  py -3.13 omr_service.py
  Env: WS_PORT (default 8443), WS_CERT + WS_KEY (wss; else ws), WS_HOST.
"""
from __future__ import annotations
import asyncio
import ctypes
import ctypes.wintypes as wt
import json
import os
import ssl
import threading
import time

import websockets

from omr_sdk import OmrSdk, suppress_crash_dialogs, disable_wer_ui
from genlot_map import to_output

WS_HOST = os.environ.get("WS_HOST", "0.0.0.0")
WS_PORT = int(os.environ.get("WS_PORT", "8443"))
WS_CERT = os.environ.get("WS_CERT")
WS_KEY = os.environ.get("WS_KEY")
BUFSIZE = 65536

clients: set = set()
_loop: asyncio.AbstractEventLoop | None = None
_running = True

_user32 = ctypes.windll.user32
_PM_REMOVE = 0x0001


def _pump():
    """Process (and drain) this thread's Windows message queue. The first call
    also CREATES the thread's message queue so the SDK's PostMessage lands."""
    msg = wt.MSG()
    while _user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, _PM_REMOVE):
        _user32.TranslateMessage(ctypes.byref(msg))
        _user32.DispatchMessageW(ctypes.byref(msg))


def _dialog_watcher():
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    WM_CLOSE, WM_COMMAND, IDOK = 0x0010, 0x0111, 1
    buf = ctypes.create_unicode_buffer(512)

    def _enum(hwnd, _):
        _user32.GetWindowTextW(hwnd, buf, 512)
        t = buf.value
        if t and ("fatal application exit" in t.lower() or "fatal error" in t.lower()):
            _user32.PostMessageW(hwnd, WM_COMMAND, IDOK, 0)
            _user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        return True

    cb = WNDENUMPROC(_enum)
    while True:
        try:
            _user32.EnumWindows(cb, 0)
        except Exception:
            pass
        time.sleep(0.08)


async def _handler(ws):
    clients.add(ws)
    print(f"[ws] client connected ({len(clients)} total)", flush=True)
    try:
        await ws.wait_closed()
    finally:
        clients.discard(ws)
        print(f"[ws] client disconnected ({len(clients)} total)", flush=True)


async def _broadcast(msg: str):
    for ws in list(clients):
        try:
            await ws.send(msg)
        except Exception:
            clients.discard(ws)


def broadcast_threadsafe(msg: str):
    if _loop is not None:
        asyncio.run_coroutine_threadsafe(_broadcast(msg), _loop)


def _consume_image(sdk):
    try:
        a, b, c = ctypes.c_int(0), ctypes.c_int(0), ctypes.c_int(0)
        sdk.dll.SGetOriginImageSize(ctypes.byref(a), ctypes.byref(b), ctypes.byref(c))
        sz = max(a.value, b.value, c.value)
        if 0 < sz < 8 * 1024 * 1024:
            sdk.dll.SGetOriginImage(ctypes.create_string_buffer(sz + 16), sz)
    except Exception as e:
        print("[scan] image read err:", e, flush=True)


def scanner_loop():
    disable_wer_ui()
    _pump()                                  # create this thread's message queue FIRST
    sdk = OmrSdk()
    sdk.dll.SRollBack.restype = ctypes.c_bool; sdk.dll.SRollBack.argtypes = []
    sdk.dll.SGetOriginImageSize.restype = ctypes.c_bool
    sdk.dll.SGetOriginImageSize.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    sdk.dll.SGetOriginImage.restype = ctypes.c_int
    sdk.dll.SGetOriginImage.argtypes = [ctypes.c_char_p, ctypes.c_int]
    print("[scan] SInit:", sdk.init(), flush=True)
    print("[scan] SStart:", sdk.start(), flush=True)
    suppress_crash_dialogs()
    print("[scan] armed — insert a betslip", flush=True)

    had = False
    while _running:
        _pump()                              # keep the SDK's window messages flowing
        buf = ctypes.create_string_buffer(BUFSIZE)
        rc = sdk.dll.SGetTicketInfo(buf, BUFSIZE)
        raw = buf.raw[:rc] if (rc and 1 < rc < BUFSIZE) else b""
        has = len(raw) >= 51 and any(raw[7:51])
        if has and not had:
            msg = json.dumps(to_output(raw))
            print("[scan] ->", msg, flush=True)
            broadcast_threadsafe(msg)
            _consume_image(sdk)
            _pump()
            try:
                sdk.dll.SRollBack()          # feed-complete msg now has a queue to land in
            except Exception as e:
                print("[scan] SRollBack err:", e, flush=True)
            _pump()
            had = True
            time.sleep(0.4)
        elif not has:
            had = False
        _pump()
        time.sleep(0.04)


async def main():
    global _loop
    _loop = asyncio.get_running_loop()

    ssl_ctx = None
    scheme = "ws"
    if WS_CERT and WS_KEY and os.path.exists(WS_CERT) and os.path.exists(WS_KEY):
        ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_ctx.load_cert_chain(WS_CERT, WS_KEY)
        scheme = "wss"

    threading.Thread(target=_dialog_watcher, daemon=True).start()
    threading.Thread(target=scanner_loop, daemon=True).start()
    async with websockets.serve(_handler, WS_HOST, WS_PORT, ssl=ssl_ctx):
        print(f"[ws] listening on {scheme}://{WS_HOST}:{WS_PORT}", flush=True)
        await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    finally:
        _running = False
