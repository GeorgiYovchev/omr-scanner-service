# omr-scanner — BS-UL080 betslip scanner → WebSocket (Windows)

Reads lotto.ge OMR betslips on the **BS-UL080(U)** USB scanner and publishes the
decoded picks over a WebSocket in exactly the JSON the Linux POS terminals' publisher emits, so the
POS frontend works unchanged:

```json
{"type": 42, "blocks": [[7,9,17,25,33,34],[7,10,25,30,38,42],[3,4,5,25,31,37],[7,15,18,27,32,36],[]], "draws": []}
```

`type` = game (42 = 6-from-42 lotto, 35 = 5-from-35 "Golden Ball"), `blocks` = boards 1–5
(sorted picks, `[]` if empty), `draws` = draw-selection area. Default endpoint **wss://0.0.0.0:8443**.

This repository is the complete, self-contained project: vendor SDK + driver, the service, the
installer, the certificate, every experiment that led here and the full reverse-engineering record.
Nothing else is needed to deploy it on a fresh 64-bit Windows 10/11 machine.

## Quick start (fresh terminal)

```powershell
# 1. get the repo onto the terminal (git clone, or unzip the archive built by package.ps1)
# 2. PowerShell AS ADMINISTRATOR, inside the folder:
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Online
# 3. plug the scanner in (Device Manager: "USB Device Driver for Scanner and Printer")
# 4. test:
$env:WS_INSECURE='1'; py -3.13 .\service\wsclient.py wss://127.0.0.1:8443 60   # then insert a betslip
```

`install.ps1` installs the USB driver, the VC++ runtimes, Python 3.13 + packages, the firewall
rule and registers the Windows service **OMRScanner** (starts at boot, restarts on failure).
Details and the offline/no-internet variant: [docs/04-install.md](docs/04-install.md).

## Repository layout

| path | what |
|---|---|
| `service/omr_service.py` | the service: SDK callback → decode → broadcast → eject; self-healing |
| `service/omr_sdk.py` | ctypes binding for `LScannerSDK.dll` with the *correct* `SInit(callback, …)` |
| `service/genlot_map.py` | mark-grid → lottery numbers (layout tables + game-type signatures) |
| `service/omr_winservice.py` | Windows service wrapper (pywin32), supervises `omr_service.py` |
| `service/start_omr.ps1` | alternative supervisor for scheduled-task mode (no admin) |
| `service/config.json` | port / TLS / retry settings |
| `service/wsclient.py` | test client |
| `install.ps1`, `uninstall.ps1`, `package.ps1` | deployment |
| `sdk/` | vendor SDK (`LScannerSDK.dll`, `lib/`, `conf/`, demo app in `bin/`); its logs go to `sdk/log/` |
| `driver/BSdriver_x64/` | vendor USB kernel driver (`bysusb.inf`, 2012, signed) |
| `certs/` | `*.oddstech.net` wildcard cert used for `wss://` |
| `tools/` | offline decoders, capture/probe scripts for new ticket types |
| `docs/` | architecture, SDK API, ticket layouts, install, operations, troubleshooting, history |
| `archive/` | everything that was tried before the final design (kept for reference) |

## Documentation

1. [Architecture](docs/01-architecture.md) — how a scan flows, threads, exit codes, logs
2. [SDK API](docs/02-sdk-api.md) — the verified `LScannerSDK.dll` interface and its internals
3. [Ticket layouts](docs/03-ticket-layouts.md) — the grid, the mapping tables, adding a new game
4. [Install](docs/04-install.md) — prerequisites, service vs task mode, offline install, replication
5. [Operations](docs/05-operations.md) — start/stop, logs, health, routine checks
6. [Troubleshooting](docs/06-troubleshooting.md) — error codes, symptoms → causes → fixes
7. [Project journal (raw)](docs/07-project-journal-raw.md) — the complete working notes, chronological
8. [History & reverse engineering](docs/08-history-and-reverse-engineering.md) — how the SDK was decoded and the root cause of the instability
9. [**Handover — how to continue**](docs/09-handover.md) — status, environment, dev loop, deploying changes, adding games, open items
10. [Linux reference implementation](docs/10-linux-reference.md) — the terminals' reader/publisher chain and the JSON contract

See also [CHANGELOG.md](CHANGELOG.md).

## Status

Production-ready for the 6/42 and 5/35 betslips. Verified on Windows 10 Pro 19045 (dozens of
consecutive scans, reboot persistence, scanner unplug/replug recovery). Open items, with suggested approaches, are in
[docs/09-handover.md](docs/09-handover.md#open-items--with-a-suggested-approach).
