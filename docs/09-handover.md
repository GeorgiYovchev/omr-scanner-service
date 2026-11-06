# 9. Handover — how to continue this project

Audience: the DevOps / POS engineers taking over. Read [01-architecture](01-architecture.md) first,
then this page; everything else is reference.

## Status at handover (2026-11-06)

| area | state |
|---|---|
| Decoding 6/42 and 5/35 betslips on the SNBC BS-UL080 | done, verified against the Linux terminals' output and physical slips |
| WebSocket output in the Linux publisher's format | done (`{type, blocks, draws}`, `wss://:8443`) |
| Stability (continuous scanning, scanner unplug/replug, reboot) | done; root cause of the earlier instability documented in [08](08-history-and-reverse-engineering.md) |
| Windows service (`OMRScanner`) + installer + packaging | done, installed and scan-tested on the development PC |
| Install on a **second** machine | **not yet exercised** — do the first one supervised (see "Deploying") |
| Frontend integration (hostname/cert) | **open** — see Open items |
| Other games / ticket templates | procedure documented, none added yet |

The development PC is being decommissioned; this repository is the only copy of everything,
including the vendor SDK, the driver and the certificate. Do not rely on anything outside it.

## Where things are

| what | where |
|---|---|
| code, SDK, driver, cert, installer, docs | this repo — `https://gitlab.oddstech.net/devops/omr-scanner` |
| Linux reference implementation (the thing we mimic) | POS terminal `.248` (`172.16.30.161`, user `pos`): `/home/pos/test/pixel_scanner/` (C source: `main.c`, `util.c`, `communication.c`, `Makefile`), `/home/pos/test/node/pipe-websocket-publisher-https.js`, systemd units `pixel-scanner`, `omr-websocket`. Details: [10-linux-reference](10-linux-reference.md). Credentials: DevOps password store / terminal onboarding notes, not in this repo. |
| POS frontend | `https://stage-lotto-pos.oddstech.net` (stage); the scanner socket URL it opens is the open question below |
| vendor | SNBC / BeiYang, scanner model BS-UL080(U). No support contact was used; the SDK came with the device. |
| RE tooling | [REA](https://github.com/morluto/rea) + Ghidra (free). Not needed to run or extend the service; needed only to go deeper into the DLL. Findings so far are in [02-sdk-api](02-sdk-api.md). |

## Working on it

### Development machine
* 64-bit Windows 10/11 with the scanner attached (the SDK is Windows-only; the decode/mapping code
  (`genlot_map.py`, `tools/`) is pure Python and runs anywhere).
* `git clone` the repo, then `install.ps1 -Online` once (gets driver/runtimes/Python) — or, if you
  don't want the service on your dev box, install only the prerequisites: driver (`pnputil`), the two
  VC++ runtimes, Python 3.13 x64, `pip install websockets pywin32`.
* Editor of choice; no build step. Python 3.13, no type-checker/linter enforced (keep it that way
  simple, or add one — nothing depends on it).

### Run it by hand (the normal dev loop)
```powershell
Stop-Service OMRScanner                      # only one process may own the scanner
py -3.13 service\omr_service.py              # console run: logs to the terminal and logs\omr_service.log
# env overrides, e.g.:  $env:WS_PORT='8444'; $env:OMR_FETCH_IMAGE='1'
# Ctrl-C stops it cleanly (SStop)
Start-Service OMRScanner                     # afterwards
```
Test client: `$env:WS_INSECURE='1'; py -3.13 service\wsclient.py wss://127.0.0.1:8443 60`.

### Debugging a decode without the scanner
Every scan logs `[scan] raw <hex>`; `py -3.13 tools\decode_raw.py <hex>` reproduces it anywhere.
Scans made by the vendor demo or while the service was down are recoverable from the SDK's device
log with `tools\grid_from_sdklog.py` ([03](03-ticket-layouts.md#reproducing-a-decode-offline)).

### The vendor demo
`sdk\bin\LScannerSDKDemo.exe` is the reference for "what the scanner can do": shows the image and
the raw grid, has sensitivity / status / firmware buttons. **Stop the service before starting it**
(shared device). Never use its firmware/calibration buttons casually.

### Things you must not change without re-reading [08](08-history-and-reverse-engineering.md)
* The `SInit` call and the callback model in `omr_sdk.py` / `omr_service.py`.
* The "one process per scanner session" supervision (no in-process re-init after scanner loss).
* No polling of `ScannerIsReady()` / `LSQueryStatus()` while scanning is armed.
* No automatic dismissal of SDK dialogs.

## Deploying a change

1. Edit, test by hand on a machine with a scanner (console run above), commit, push.
2. On each terminal: `git pull` in the repo folder (or copy the new files), then
   `Restart-Service OMRScanner`. Nothing else is cached. If `config.json` or `certs/` changed, same.
3. New terminal: [04-install](04-install.md). First one supervised: check the installer transcript,
   Device Manager, `Get-Service OMRScanner`, the log, one scan with `wsclient.py`.

## Adding a new game (summary; full procedure in [03](03-ticket-layouts.md#adding-a-new-game--ticket-type))

1. Scan one slip of the new game (service running, or demo + `grid_from_sdklog.py`).
2. `tools\decode_raw.py <raw hex>` → note the **row-0 columns** (the type signature).
3. In `service/genlot_map.py`: add `frozenset({...}): <type>` to `TYPE_SIGNATURES`, add a
   `SCARA<type>` table (22×16, cell = `block*100 + number`, 0 = empty) and the `draws` rule in
   `to_output`. If the slip reuses the 6/42 or 5/35 board geometry, copy that table and renumber.
4. Validate with a slip whose marks you know; commit; deploy. Mirror the table into the Linux
   terminals' `util.c` so both scanner types agree. Confirm the `type` id with the frontend team.

## Open items — with a suggested approach

1. **Frontend hostname / certificate.** The POS page is https, so the browser needs
   `wss://<name>:8443` where `<name>` is covered by the `*.oddstech.net` certificate and resolves to
   the terminal. Find out what the Linux terminals do: `/etc/hosts` on `.248`, the publisher script, or
   the frontend's config (it is probably a fixed name like `localhost.oddstech.net` → 127.0.0.1, or a
   per-terminal name). Replicate the same on Windows (`C:\Windows\System32\drivers\etc\hosts` entry,
   which `install.ps1` could add). Until then test with `wsclient.py` + `WS_INSECURE=1`.
2. **OMR sensitivity.** One test slip ("Rosetta") has a borderline cell that flips between scans.
   Tune `[OMR] threshold` / `threshold_mark` / `mark_block_ratio` in `sdk/lib/DecodeCfg.ini` with a
   set of real slips; or expose `SAdjustSensibility` (signature unknown — decompile first). Compare
   with the demo's image (`OMR_FETCH_IMAGE=1` saves the BMP).
3. **Unreadable slips** (`eventId 3`): currently log + eject, nothing published. If the frontend
   wants feedback, publish e.g. `{"error":"unreadable"}` — agree the shape with the frontend team
   first; the Linux publisher never emits such a message today.
4. **Second-machine install** has not been done. Expect the usual suspects: driver signature prompt,
   firewall profile, Python not on PATH for LocalSystem (installer uses `InstallAllUsers=1`).
5. **Hardening ideas** (nice to have): silent task-mode launch (`pythonw`/VBS) if task mode is ever
   used again; a `/health` HTTP endpoint or a periodic `[health]` log line for monitoring; packaging
   the Python runtime (embeddable zip) to drop the Python install step.

## Glossary

| term | meaning |
|---|---|
| OMR | optical mark recognition — reading filled bubbles |
| betslip / ticket | the paper form with number boards the customer marks |
| board / block | one 1…42 (or 1…35) number area on the slip; `blocks` in the JSON |
| type 42 / 35 | 6-from-42 lotto / 5-from-35 "Golden Ball" templates |
| scara table | the row×column → `block*100+number` table from the Linux reader's `util.c` |
| SNBC / BeiYang | the scanner vendor; `SNBC*Impl` are the SDK's internal classes |
| GENLOT / a4ocr | the Linux terminals' different reader hardware/SDK |
| eject / `SRollBack` | feeding the slip back out after a scan |
| session 0 | where Windows services run (no desktop); the service works there |
