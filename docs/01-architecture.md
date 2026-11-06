# 1. Architecture

## Components

```
                 USB                     ctypes                    queue                 WebSocket
 BS-UL080  ───────────►  LScannerSDK.dll ─────────►  omr_service.py  ─────────►  POS frontend
 scanner   ◄───────────  (vendor, x64)   ◄─────────  (Python 3.13)   ◄─────────  (browser, wss)
             BYSUSB.sys                   callback /                 {type,blocks,draws}
             (kernel drv)                 SRollBack
                                                       ▲
                                     supervised by     │ relaunch on exit, stop via named event
                                     omr_winservice.py (Windows service "OMRScanner")
                                     — or — start_omr.ps1 (scheduled task mode)
```

* **Scanner + driver**: SNBC BS-UL080(U), USB `VID_154F&PID_2002`, kernel driver `BYSUSB.sys`
  (`driver/BSdriver_x64`). The device is *not* exclusive: two processes can open it at once and
  corrupt each other's transfers — never run the vendor demo while the service is running.
* **Vendor SDK** (`sdk/`): `LScannerSDK.dll` (MFC-based, x64) on top of `lib/ScanPrnDevLib.dll`
  (device model, JSON-ish internal API), `BsUSBInt.dll` (USB), `decomr.dll` (OMR decode),
  `dec417/QRDecode/LinearBarDecode` (barcodes, PDF417 enabled but unused), image helpers.
  Config: `sdk/conf/LScannerConfig.ini`, `sdk/lib/DecodeCfg.ini` (OMR thresholds),
  `sdk/lib/FormatFile.txt` (grid geometry). It writes its own logs to `sdk/log/` (GBK encoded).
* **`service/omr_service.py`**: one process per scanner session (see below), two threads:
  * *asyncio thread* — `websockets.serve` on `host:port`, TLS when `certs/` has the pair;
    broadcasts every decoded slip to all connected clients.
  * *scanner worker thread* — `SInit(callback)` → `SStart()`; waits on a queue fed by the SDK
    callback; on an event: `SGetTicketInfo` → `genlot_map.to_output` → broadcast → `SRollBack`.
* **`service/genlot_map.py`**: pure function from the 51-byte SDK result to the JSON.
* **Supervisor**: `omr_winservice.py` (service mode) or `start_omr.ps1` (task mode) relaunches
  `omr_service.py` when it exits, with a short delay.

## The scan cycle (what the SDK does and what we do)

```
SDK scan thread                                   our worker thread
──────────────────────────────────────────────    ─────────────────────────────────────────
doScan(): ResumeToIdle (feed-out attempt ~2 s)
          StartScan, poll IsComplete (100 ms)
paper inserted → read image, decode OMR
fetchScanImage/DecodeResult
notifyScanCompleteStatus → callback(5, &2) ────►  queue.put((5, 2))
"Waiting for paper feed or print"  (PARKED)       SGetTicketInfo()  → 51 bytes
                                                  to_output()       → JSON, broadcast
                                                  SRollBack()       → FeedPaper (~0.8 s)
"Paper feed or print completed, restarting loop" ◄ notifyPaperFeedComplete (inside SRollBack)
doScan() again …
```

Key property: after the callback the SDK thread **blocks on a condition variable and does no USB
I/O** until our `SRollBack` wakes it. That is why the eject is safe and why the whole thing is
stable — see [08-history](08-history-and-reverse-engineering.md) for what happens without a
registered callback.

Events: `eventId 5` = decode result ready (`data 2` = OMR), `eventId 3` = scan finished with
nothing decoded (unreadable slip; we still eject). Rescans of the same slip are deterministic.

## One process per scanner session (self-healing)

The SDK cannot be safely re-initialised inside a process once the scanner is lost, so:

* `SInit` is retried every `init_retry_seconds` (5 s) while it fails (scanner not yet enumerated
  after boot, unplugged, or held by another process) — the WebSocket stays up meanwhile.
* Every 5 s of idle the worker reads `SGetLastErrorCode()` (no USB I/O). `0x3f0` means the SDK scan
  thread has exited ("Scan failed, exiting thread" — scanner unplugged mid-run) → `SStop()` and
  **exit code 3** → the supervisor relaunches in 5 s → the retry loop waits for the scanner.
* Any other crash → exit code 1 → relaunch in 10 s. Exit 0 = requested stop.
* Graceful stop: the supervisor signals the named Windows event `Global\OMRScannerStop`
  (`config.json: stop_event`); `omr_service.py` runs `SStop()` and exits 0. Console runs also stop
  on Ctrl-C / Ctrl-Break.

Never poll `ScannerIsReady()` / `LSQueryStatus()` as a health check — they perform USB I/O
concurrently with the SDK scan thread.

## Logs

| file | content |
|---|---|
| `service/logs/omr_service.log` | per scan: `event`, `raw <51-byte hex>`, the JSON sent, `eject: True/False`; init retries; 5 × 5 MB rotation |
| `service/logs/winservice.log` | supervisor (service mode): child pid, exit codes, relaunches |
| `service/logs/launcher.log` | supervisor (task mode) |
| `service/logs/stderr.log` | Python tracebacks of `omr_service.py`, if any |
| `sdk/log/lscanner_*.log` | SDK layer (GBK): `SInit`, callback, `Waiting for paper feed`, `SRollBack` |
| `sdk/log/scanprnliblog_*.log` | device layer (GBK): USB open/close, `FeedPaper`, raw OMR grid per scan (`pszOMRDecodeDest=`) |

Read the SDK logs with `iconv -f gbk -t utf-8` (WSL) or `Get-Content -Encoding` + a GBK code page.

## Configuration (`service/config.json`, env overrides in brackets)

| key | default | meaning |
|---|---|---|
| `host` [WS_HOST] | `0.0.0.0` | bind address |
| `port` [WS_PORT] | `8443` | WebSocket port (same as the Linux terminals) |
| `cert`, `key` [WS_CERT, WS_KEY] | `../certs/fullchain.pem`, `../certs/privkey.pem` | TLS pair; missing → plain `ws://` |
| `init_retry_seconds` [OMR_INIT_RETRY] | `5` | SInit retry interval |
| `fetch_image` [OMR_FETCH_IMAGE=1] | `false` | also pull the 2 MB BMP per scan (debug) |
| `stop_event` [OMR_STOP_EVENT] | `Global\OMRScannerStop` | graceful-stop event name |
| — [OMR_SDK_DIR] | `../sdk` | SDK folder |
