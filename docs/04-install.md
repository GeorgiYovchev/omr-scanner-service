# 4. Installation and replication

## Requirements

| item | detail |
|---|---|
| Windows | 64-bit Windows 10/11 (verified: 10 Pro 19045). The SDK and driver are x64-only. |
| Scanner | BS-UL080(U), USB `VID_154F&PID_2002` |
| Driver | `driver/BSdriver_x64` (`bysusb.inf`, vendor v3.2.0.0, 2012, signed cat). Installed with `pnputil`. |
| VC++ runtimes | 2015-2022 x64 **and** 2013 x64 (the DLLs import `VCRUNTIME140/MSVCP140` and `MSVCR120`) |
| Python | 3.13 x64 (`py -3.13`), packages `websockets` (13–17) and, for service mode, `pywin32` |
| TLS | `certs/fullchain.pem` + `certs/privkey.pem` → `wss://`; absent → `ws://` (an https page cannot connect to `ws://`) |
| Admin | once, to run `install.ps1` |

## Install (online)

```powershell
git clone https://gitlab.oddstech.net/devops/omr-scanner.git C:\omr-scanner    # or unzip package
cd C:\omr-scanner
# PowerShell as Administrator:
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Online
```

What it does (transcript in `install.log`):

1. `pnputil /add-driver driver\BSdriver_x64\bysusb.inf /install`
2. VC++ 2015-2022 x64 (`https://aka.ms/vs/17/release/vc_redist.x64.exe`) and VC++ 2013 x64
   (`https://aka.ms/highdpimfc2013x64enu`), checked via the registry keys
   `HKLM\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64` and
   `HKLM\SOFTWARE\WOW6432Node\Microsoft\VisualStudio\12.0\VC\Runtimes\x64`
3. Python 3.13.0 x64 (`InstallAllUsers=1 PrependPath=1 Include_launcher=1`) + `pip install websockets pywin32`
   + `pywin32_postinstall -install`
4. cert check
5. firewall rule "OMR scanner websocket": inbound TCP 8443 for `python.exe`
6. autostart: **service mode** (default) registers Windows service `OMRScanner` (Automatic,
   LocalSystem, recovery = restart 5 s / 10 s / 30 s); **task mode** (`-Mode Task`) registers scheduled
   task `OMR-Scanner` at logon of the current user (restart on failure, no time limit, hidden)
7. starts it and prints the last log lines

Switches: `-Mode Service|Task`, `-Port 8443`, `-NoFirewall`, `-SkipDriver`, `-SkipRuntimes`,
`-SkipPython`, `-NoStart`, `-Online`.

## Install (offline)

Put into `deps\` before running `install.ps1` **without** `-Online`:

```
vc_redist.x64.exe          VC++ 2015-2022 x64
vcredist_x64.exe           VC++ 2013 x64
python-3.13.0-amd64.exe    Python 3.13 x64
websockets-*.whl           py -3.13 -m pip download websockets pywin32 -d deps   (on a machine with internet)
pywin32-*.whl
```

## Service mode vs task mode

| | Windows service `OMRScanner` | scheduled task `OMR-Scanner` |
|---|---|---|
| starts | at boot, before logon | at logon of the kiosk user |
| runs as | LocalSystem (session 0) | the logged-on user |
| supervisor | `service/omr_winservice.py` (pywin32, hosted by `python.exe`) | `service/start_omr.ps1` |
| stop | `Stop-Service OMRScanner` (graceful: named event → `SStop`) | `Stop-ScheduledTask OMR-Scanner` (hard kill, safe when idle) |
| needs admin to install | yes | yes for driver/firewall, task itself no |
| visible window | none | none (hidden PowerShell); may flash briefly at logon |

Both relaunch `omr_service.py` on exit (5 s after a scanner loss, 10 s otherwise).

## Replicating to another terminal

1. `powershell -ExecutionPolicy Bypass -File .\package.ps1` on a machine with the repo → `omr-scanner-<date>.zip`
   (includes `certs/` if present; excludes `archive/`, logs, dumps), or just `git clone`.
2. Copy to the terminal, run `install.ps1 -Online` as Administrator, plug the scanner in.
3. Verify: Device Manager shows "USB Device Driver for Scanner and Printer";
   `Get-Service OMRScanner` = Running; `service\logs\omr_service.log` ends with
   `listening on wss://0.0.0.0:8443` … `SInit: 0` … `SStart: True - armed`.
4. `$env:WS_INSECURE='1'; py -3.13 service\wsclient.py wss://127.0.0.1:8443 60` and insert a betslip.
5. Frontend: the POS page (https) must open `wss://<name>.oddstech.net:8443` where `<name>` resolves
   to the terminal (hosts entry or DNS) so the wildcard certificate validates — same mechanism as
   the Linux terminals.

Nothing is machine-specific: all paths are relative to the repository folder.

## Uninstall

```powershell
powershell -ExecutionPolicy Bypass -File .\uninstall.ps1     # as Administrator
```
Removes the service/task, the firewall rule and running processes; keeps driver, Python, runtimes.
