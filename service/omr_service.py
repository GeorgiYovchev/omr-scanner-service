r"""OMR scanner -> WebSocket service (Windows / BS-UL080), callback model.

Mirrors the vendor demo, the one implementation known to run for hours:
  SInit(callback) -> SStart -> the SDK scan thread auto-scans on paper insert, calls
  callback(eventId, &data) and PARKS ("Waiting for paper feed or print") until
  SRollBack() notifies it. Our worker thread handles the event off the SDK thread:
  SGetTicketInfo -> genlot_map.to_output -> broadcast JSON -> SRollBack (eject) ->
  the SDK thread restarts its loop for the next ticket. No polling, no re-init.

Serves the Linux publisher's exact contract, {type, blocks[5], draws}, on :8443
(wss when the cert+key exist, else ws).

Self-healing: SInit is retried until the scanner is present (it may enumerate after boot or
be unplugged); if the SDK scan thread dies (scanner lost -> last error 0x3f0) the process
exits with code 3 and the supervisor (omr_winservice.py or start_omr.ps1) relaunches it.

Configuration: config.json next to this file; environment variables override it:
  WS_HOST, WS_PORT, WS_CERT, WS_KEY, OMR_INIT_RETRY, OMR_FETCH_IMAGE=1, OMR_SDK_DIR,
  OMR_STOP_EVENT (name of a Windows event the supervisor signals for a graceful stop).
Exit codes: 0 clean stop, 1 fatal (e.g. port in use), 3 scanner lost (relaunch quickly).
Logs: logs\omr_service.log (5 x 5 MB rotation); also stdout when run in a console.
"""
from __future__ import annotations
import asyncio
import ctypes
import json
import logging
import logging.handlers
import os
import queue
import signal
import ssl
import sys
import threading
import time

import websockets

from omr_sdk import OmrSdk, OmrError, EVENT_DECODED, EVENT_NO_DECODE, ERR_SCAN_THREAD_DEAD
from genlot_map import to_output

HERE = os.path.dirname(os.path.abspath(__file__))
EXIT_SCANNER_LOST = 3
HEALTH_S = 5.0


def _load_config() -> dict:
    path = os.path.join(HERE, "config.json")
    try:
        with open(path, encoding="utf-8-sig") as f:      # tolerate a BOM (PowerShell 5 writes one)
            return json.load(f)
    except FileNotFoundError:
        return {}


def _opt(env: str, key: str, default):
    v = os.environ.get(env)
    if v not in (None, ""):
        return v
    v = CFG.get(key)
    return default if v in (None, "") else v


def _path(p: str | None) -> str | None:
    """Config paths are relative to the service folder."""
    if not p:
        return None
    return p if os.path.isabs(p) else os.path.normpath(os.path.join(HERE, p))


CFG = _load_config()
WS_HOST = str(_opt("WS_HOST", "host", "0.0.0.0"))
WS_PORT = int(_opt("WS_PORT", "port", 8443))
WS_CERT = _path(_opt("WS_CERT", "cert", "../certs/fullchain.pem"))
WS_KEY = _path(_opt("WS_KEY", "key", "../certs/privkey.pem"))
INIT_RETRY_S = float(_opt("OMR_INIT_RETRY", "init_retry_seconds", 5))
FETCH_IMAGE = str(_opt("OMR_FETCH_IMAGE", "fetch_image", "0")) in ("1", "true", "True")
STOP_EVENT = os.environ.get("OMR_STOP_EVENT") or CFG.get("stop_event") or ""

log = logging.getLogger("omr")
clients: set = set()
_loop: asyncio.AbstractEventLoop | None = None
_stop: asyncio.Event | None = None
_running = True
_exit_code = 0


def setup_logging():
    logdir = os.path.join(HERE, "logs")
    os.makedirs(logdir, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh = logging.handlers.RotatingFileHandler(os.path.join(logdir, "omr_service.log"),
                                              maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
    fh.setFormatter(fmt)
    log.addHandler(fh)
    if sys.stdout and sys.stdout.isatty():          # console run: mirror to the terminal
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        log.addHandler(sh)
    log.setLevel(logging.INFO)


def request_exit(code: int):
    """Stop everything and exit with `code`. Safe from any thread."""
    global _running, _exit_code
    if not _running:
        return
    _exit_code = code
    _running = False
    if _loop is not None and _stop is not None:
        _loop.call_soon_threadsafe(_stop.set)


# ---- graceful stop: named Windows event from the supervisor, or Ctrl-C/Ctrl-Break ----
def _stop_event_watcher(name: str):
    k32 = ctypes.windll.kernel32
    SYNCHRONIZE, INFINITE, WAIT_OBJECT_0 = 0x00100000, 0xFFFFFFFF, 0
    h = None
    while _running and not h:                        # the supervisor creates it before us; retry anyway
        h = k32.OpenEventW(SYNCHRONIZE, False, name)
        if not h:
            time.sleep(1.0)
    if h and k32.WaitForSingleObject(h, INFINITE) == WAIT_OBJECT_0 and _running:
        log.info("[svc] stop requested by supervisor")
        request_exit(0)


def _install_signal_handlers():
    def _h(signum, frame):
        log.info("[svc] signal %s - stopping", signum)
        request_exit(0)
    for s in ("SIGINT", "SIGBREAK", "SIGTERM"):
        if hasattr(signal, s):
            try:
                signal.signal(getattr(signal, s), _h)
            except Exception:
                pass


# ---- websocket --------------------------------------------------------------
async def _handler(ws):
    clients.add(ws)
    log.info("[ws] client connected (%d total)", len(clients))
    try:
        await ws.wait_closed()
    finally:
        clients.discard(ws)
        log.info("[ws] client disconnected (%d total)", len(clients))


async def _broadcast(msg: str):
    for ws in list(clients):
        try:
            await ws.send(msg)
        except Exception:
            clients.discard(ws)


def broadcast_threadsafe(msg: str):
    if _loop is not None:
        asyncio.run_coroutine_threadsafe(_broadcast(msg), _loop)


# ---- scanner ----------------------------------------------------------------
def _handle_event(sdk: OmrSdk, event_id: int, data: int):
    log.info("[scan] event %d data %d", event_id, data)
    if event_id == EVENT_DECODED:
        raw = sdk.get_ticket_info()
        if raw and len(raw) >= 51:
            log.info("[scan] raw %s", raw[:51].hex())    # 7-byte header + 22 big-endian row words
            try:
                msg = json.dumps(to_output(raw))
                log.info("[scan] -> %s", msg)
                broadcast_threadsafe(msg)
            except Exception as e:
                log.error("[scan] decode error: %s raw=%s", e, raw.hex())
        else:
            log.warning("[scan] SGetTicketInfo returned nothing")
    elif event_id == EVENT_NO_DECODE:
        log.warning("[scan] scan finished with no decode result (unreadable slip?)")
    if FETCH_IMAGE:                                   # debug: keep the scan image next to the logs
        img = sdk.fetch_image()
        if img:
            path = os.path.join(HERE, "logs", time.strftime("scan_%Y%m%d_%H%M%S.bmp"))
            with open(path, "wb") as f:
                f.write(img)
            log.info("[scan] image saved %s (%d bytes)", path, len(img))
        else:
            log.warning("[scan] image not available")
    # Eject from THIS thread (like the demo's UI thread); the SDK thread is parked
    # until this notifies it, then it restarts its scan loop for the next ticket.
    log.info("[scan] eject: %s", sdk.rollback())


def scanner_loop():
    sdk = OmrSdk()
    events: queue.Queue = queue.Queue()

    def on_event(event_id: int, data: int):       # SDK scan thread: hand off and return
        events.put((event_id, data))

    # The scanner may not be enumerated yet right after boot, or be unplugged: keep trying.
    while _running:
        try:
            sdk.init(on_event)
            break
        except OmrError as e:
            log.warning("[scan] %s - retrying in %.0fs", e, INIT_RETRY_S)
            t_end = time.monotonic() + INIT_RETRY_S
            while _running and time.monotonic() < t_end:
                time.sleep(0.25)
    if not _running:
        return
    log.info("[scan] SInit: 0 (sdk dir %s)", sdk.sdk_dir)
    if not sdk.start():
        log.error("[scan] SStart failed (code %d) - exiting for restart", sdk.last_error())
        request_exit(EXIT_SCANNER_LOST)
        return
    log.info("[scan] SStart: True - armed, insert a betslip")

    last_health = time.monotonic()
    while _running:
        try:
            event_id, data = events.get(timeout=1.0)
        except queue.Empty:
            if time.monotonic() - last_health >= HEALTH_S:
                last_health = time.monotonic()
                code = sdk.last_error()          # no USB I/O; 0x3f0 = scan thread exited
                if code == ERR_SCAN_THREAD_DEAD:
                    log.error("[scan] SDK scan thread died (0x%x) - scanner unplugged? exiting for restart", code)
                    sdk.stop()
                    request_exit(EXIT_SCANNER_LOST)
                    return
            continue
        try:
            _handle_event(sdk, event_id, data)
        except Exception as e:
            log.exception("[scan] event handling failed: %s", e)
    log.info("[scan] SStop: %s", sdk.stop())


async def main():
    global _loop, _stop
    _loop = asyncio.get_running_loop()
    _stop = asyncio.Event()

    ssl_ctx = None
    scheme = "ws"
    if WS_CERT and WS_KEY and os.path.exists(WS_CERT) and os.path.exists(WS_KEY):
        ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_ctx.load_cert_chain(WS_CERT, WS_KEY)
        scheme = "wss"
    else:
        log.warning("[ws] no cert/key at %s / %s - serving plain ws://", WS_CERT, WS_KEY)

    worker = threading.Thread(target=scanner_loop, name="scanner", daemon=True)
    worker.start()
    try:
        async with websockets.serve(_handler, WS_HOST, WS_PORT, ssl=ssl_ctx):
            log.info("[ws] listening on %s://%s:%d", scheme, WS_HOST, WS_PORT)
            while not _stop.is_set():            # periodic wake-ups let Python signal handlers run
                try:
                    await asyncio.wait_for(_stop.wait(), timeout=1.0)
                except asyncio.TimeoutError:
                    pass
    finally:
        global _running
        _running = False
        worker.join(timeout=8)          # lets the worker run SStop for a clean exit


if __name__ == "__main__":
    setup_logging()
    log.info("=== omr_service starting (pid %d) ===", os.getpid())
    _install_signal_handlers()
    if STOP_EVENT:
        threading.Thread(target=_stop_event_watcher, args=(STOP_EVENT,), name="stop-event", daemon=True).start()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        _running = False
    except Exception as e:
        log.exception("fatal: %s", e)
        _exit_code = 1
    log.info("=== omr_service exit %d ===", _exit_code)
    sys.exit(_exit_code)
