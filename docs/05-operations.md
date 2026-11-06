# 5. Operations

## Daily commands (PowerShell)

| action | service mode | task mode |
|---|---|---|
| status | `Get-Service OMRScanner` | `Get-ScheduledTask OMR-Scanner \| Select State` |
| start | `Start-Service OMRScanner` | `Start-ScheduledTask OMR-Scanner` |
| stop | `Stop-Service OMRScanner` | `Stop-ScheduledTask OMR-Scanner` |
| restart | `Restart-Service OMRScanner` | stop + start |
| last scans | `Get-Content service\logs\omr_service.log -Tail 20` | same |
| supervisor log | `service\logs\winservice.log` | `service\logs\launcher.log` |
| live test | `$env:WS_INSECURE='1'; py -3.13 service\wsclient.py wss://127.0.0.1:8443 60` | same |
| run in a console (debug) | `py -3.13 service\omr_service.py` (stop the service first) | same |

A healthy start looks like:

```
=== omr_service starting (pid 23056) ===
[ws] listening on wss://0.0.0.0:8443
[scan] SInit: 0 (sdk dir C:\omr-scanner\sdk)
[scan] SStart: True - armed, insert a betslip
```
and each scan:
```
[scan] event 5 data 2
[scan] raw 012c000f0016008164...
[scan] -> {"type": 42, "blocks": [[...]], "draws": []}
[scan] eject: True
```

## Rules that keep it stable

* **Never run the vendor demo (`sdk\bin\LScannerSDKDemo.exe`) while the service is running.** The
  driver lets both open the device; transfers interleave, both get garbage, both ejects time out.
  Stop the service first, start it again afterwards.
* Do not kill the process during the ~1 s eject after a scan; otherwise a hard stop is safe
  (between scans the SDK thread only does 100 ms timed USB polls).
* One scanner per machine; the service assumes the first BS-UL080 it finds.
* Keep `service/`, `sdk/`, `certs/` together — paths are relative.

## Routine checks

* Certificate expiry: `certs/fullchain.pem` (`openssl x509 -noout -enddate`). Replace both files
  and `Restart-Service OMRScanner`. Same wildcard as the Linux terminals.
* Disk: `service/logs` rotates (≤ 30 MB); `sdk/log` is capped by the SDK (20 MB × 5 per layer).
  The `*.dmp` files in `sdk/lib` are crash dumps from the fatal-exit path — none should appear any
  more; delete any that do after reading `06-troubleshooting`.
* After Windows updates / reboots: `Get-Service OMRScanner` should be Running within seconds of boot.

## Changing settings

Edit `service/config.json` (port, host, cert paths, retry, debug image) and restart the service.
Environment variables of the same names override the file (useful for one-off console runs).

## Open items

1. Frontend hostname: confirm what name the POS page uses for the scanner socket and make it resolve
   to each Windows terminal (hosts/DNS) — otherwise the browser rejects the wildcard cert.
2. OMR threshold tuning (`sdk/lib/DecodeCfg.ini`) for the flickering cell on the Rosetta test slip.
3. Unreadable slips (`eventId 3`) are logged and ejected only; nothing is sent. Decide whether the
   frontend wants an explicit "unreadable" message.
4. New games: see [03-ticket-layouts](03-ticket-layouts.md#adding-a-new-game--ticket-type).
