# OMR betslip scanner service (Windows / BS-UL080)

Reads lotto.ge betslips on the **BS-UL080(U)** OMR scanner and publishes the
decoded picks over a WebSocket in the exact format the Linux terminals' publisher uses:

```json
{"type": 42, "blocks": [[7,9,17,25,33,34],[7,10,25,30,38,42],[3,4,5,25,31,37],[7,15,18,27,32,36],[]], "draws": []}
```

`type` = game (42 = 6/42, 35 = 5/35), `blocks` = boards 1–5 (sorted picks, `[]` if empty),
`draws` = draw-selection area. Default port **8443** (`wss://` when `..\certs\` holds the cert).

## How it works

```
paper in ──► SDK scan thread (LScannerSDK.dll) ──callback(eventId, &data)──► queue
                     │ parks: "Waiting for paper feed or print"              │
                     ◄──── SRollBack() wakes it, loop restarts ◄── worker: SGetTicketInfo
                                                                        → genlot_map.to_output
                                                                        → broadcast JSON
                                                                        → SRollBack (eject)
```

* `omr_sdk.py` – ctypes binding. The one signature that matters:
  **`SInit(callback, input_dir, output_dir)`** – arg 1 is the scan-complete callback
  `void cb(int eventId, int* pData)` (eventId 5 = decode ready, data 2 = OMR; eventId 3 = scan
  finished, nothing decoded). Passing anything else there (we once passed a path string) makes
  the SDK execute garbage after every scan: "Fatal Application Exit", process exit mid-eject,
  unkillable zombie. `input_dir` = folder holding `lib\`, `conf\`, `log\` (NULL → DLL folder).
* `genlot_map.py` – 22×15 mark grid → numbers, using the GENLOT `scara42`/`scara35` tables
  from the Linux reader's source; scanner columns are mirrored within each 7-column block.
* `omr_service.py` – the service (asyncio WebSocket + scanner worker thread). Self-healing:
  retries `SInit` until the scanner is present; exits with code 3 when the SDK scan thread dies
  (last error `0x3f0`, scanner unplugged) so the launcher restarts it. Logs: `logs\omr_service.log`
  (5 × 5 MB rotation).
* `start_omr.ps1` – launcher/supervisor loop (restart in 5 s on code 3, 10 s otherwise), single
  instance via a global mutex, `logs\launcher.log` + `logs\stderr.log`.
* `config.ps1` – port / TLS settings per terminal.
* `wsclient.py` – test client: `py -3.13 wsclient.py wss://127.0.0.1:8443 60`.

Do **not** call `ScannerIsReady()` / `LSQueryStatus()` while scanning is armed – they do USB I/O
concurrently with the SDK scan thread. Health is read from `SGetLastErrorCode()` instead.

## Install on a terminal

See `..\install.ps1` (run as Administrator). Prerequisites it handles: vendor USB driver
(`..\BSdriver_x64`), VC++ 2013 + 2015-2022 x64 runtimes, Python 3.13 x64 + `websockets`,
firewall rule, scheduled task **OMR-Scanner** (runs at logon of the kiosk user, restarts on failure).
`..\package.ps1` builds the zip to copy over. Cert: put `fullchain.pem` + `privkey.pem`
(the `*.oddstech.net` wildcard) into `..\certs\`.

## Operate

| action | how |
|---|---|
| status | `Get-ScheduledTask OMR-Scanner`, `Get-Content omr-service\logs\omr_service.log -Tail 20` |
| restart | `Stop-ScheduledTask OMR-Scanner; Start-ScheduledTask OMR-Scanner` |
| stop | `Stop-ScheduledTask OMR-Scanner` (safe when idle; the only sensitive moment is the ~1 s eject) |
| test | `py -3.13 omr-service\wsclient.py wss://127.0.0.1:8443 60`, insert a betslip |
| SDK's own logs | `lib64\log\lscanner_*.log` (GBK encoded); the scan thread should show `Scanner callback called successfully` → `Waiting for paper feed or print` → `restarting loop` per ticket |
| OMR sensitivity | `lib64\lib\DecodeCfg.ini` threshold (a borderline mark on one test ticket occasionally reads as filled) |

## Not done / known gaps

* Unknown row-0 signatures decode as type 42 (42 and 35 are known; see `TYPE_SIGNATURES`).
* Unreadable slips (eventId 3) are only logged and ejected; nothing is sent to the frontend.
* The raw 51-byte grid is logged per scan (`[scan] raw …`) – paste it into `genlot_map.py`'s
  `__main__` block to reproduce any decode offline.
