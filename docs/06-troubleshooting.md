# 6. Troubleshooting

## By symptom

| symptom | cause | fix |
|---|---|---|
| log loops `SInit failed rc=1001 (ticket reader not found…)` | scanner unplugged / not enumerated / held by another process (vendor demo, a stuck process) | plug it in; check Device Manager; close the demo; look for stray `python.exe` holding it. The service recovers by itself when the device appears. |
| `SInit failed rc=1500` + `Load lib …\bitmap.dll failed … side-by-side configuration is incorrect` in `sdk\log\scanprnliblog_*` | VC++ 2013 or 2015-2022 x64 runtime missing | `install.ps1 -Online` (step 2) or install both redistributables |
| `SDK scan thread died (0x3f0)` then exit 3 and relaunch | scanner lost mid-run (cable, power) | plug back in; automatic |
| `eject: False` | feed timed out (10 s): slip jammed, or two processes drove the device | pull the slip, make sure the demo is closed, `Restart-Service OMRScanner` |
| decoded numbers look random, every row the same pattern, or boards with 30+ numbers | a slip of an unknown template, or a scan made while the demo was also reading the device | see [03-ticket-layouts](03-ticket-layouts.md); rescan with the demo closed |
| `type: 42` for a 5/35 slip | its row-0 signature is not in `TYPE_SIGNATURES` (fixed for 35 on 2026-10-16) | add the signature — `tools\decode_raw.py <raw hex>` shows the row-0 columns |
| one number more/less on rescans of the same slip | borderline mark vs OMR threshold | `sdk\lib\DecodeCfg.ini` `[OMR] threshold/threshold_mark`; the service output is deterministic otherwise |
| `OSError: [Errno 10048] … bind on address … 8443` | port in use (another instance, or a zombie from the old buggy builds) | `Get-NetTCPConnection -LocalPort 8443` → stop the owner; a truly unkillable process (see below) needs a reboot |
| browser cannot connect; `wsclient.py` works with `WS_INSECURE=1` | hostname ≠ certificate (`*.oddstech.net`) or plain `ws://` from an https page | put the cert pair in `certs/`, use an `oddstech.net` name that resolves to the terminal |
| service installs but `Start-Service` fails with error 1053 / "did not respond" | `python.exe` not reachable for LocalSystem, or `pywin32` missing for that interpreter | `py -3.13 -c "import win32serviceutil"`; re-run `install.ps1` step 3; `service\logs\winservice.log` and the Application event log have the Python traceback |
| a "Fatal Application Exit" message box with Chinese text | the SDK crashed on its scan thread — with the current code this must not happen; it meant the callback argument of `SInit` was wrong (see [08](08-history-and-reverse-engineering.md)) | do **not** build a watcher that auto-closes it; fix the cause. Clicking OK exits the process and closes the device under any eject in flight. |
| a `python.exe` that `taskkill /F` cannot end | a thread stuck in an uncancellable USB request in `BYSUSB.sys` (only ever caused by the crash path above) | reboot; it may also clear by itself when another instance cycles the device |

## Reading the SDK logs

`sdk\log\lscanner_*.log` (SDK layer) and `sdk\log\scanprnliblog_*.log` (device layer) are GBK
encoded. In WSL: `iconv -f gbk -t utf-8 -c file | grep …`. Useful greps:

```
grep -E 'SInit:|callback|Waiting for paper|restarting loop|SRollBack'   lscanner_*.log      # one scan cycle
grep -E 'FeedPaper\] (Enter|Leave)|OpenDev\] Leave|CloseDev\] Enter|pszOMRDecodeDest'  scanprnliblog_*.log
```

A healthy cycle at the SDK layer:
```
Calling scanner callback, eventId=5, data=2
Scanner callback called successfully
Waiting for paper feed or print
SRollBack:37] Enter.
notifyPaperFeedComplete … m_ejectNotified=true
SRollBack:106] Leave, result=TRUE.
Paper feed or print completed, restarting loop
doScan() called
```
If you see `Calling scanner callback` and then nothing from that thread, the callback crashed.

## Error codes (SDK)

| code | meaning |
|---|---|
| 0 | OK |
| 1001 / 0x3e9 | ticket reader not found (`ScanPrnOpenDev ret=-2`) — also "not initialised" |
| 1500 | device init failed (runtime, driver, model) |
| 1008 / 0x3f0 | scan thread exited ("Scan failed") |
| 1004 / 0x3ec | stop failed |
| 1006 / 0x3ee | device not initialised |
| 1500 / 0x5dc | invalid parameter (also used as a generic internal error) |
| `SGetTicketInfo` = 51 | OMR result present; 0 = none |
| `FeedPaper` = -9 | no paper at the entry sensor (normal for the idle feed-out) |

## Recovering scans from the log

If the service was down but the demo or an old build scanned slips, the device log still has the
grids: `py -3.13 tools\grid_from_sdklog.py sdk\log\scanprnliblog_<date>_000.log HH:MM:SS HH:MM:SS`.
