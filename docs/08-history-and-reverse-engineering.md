# 8. History and reverse engineering

Chronological summary of how this project reached its final shape (2026-10-14 → 2026-11-06). The
unedited working notes are in [07-project-journal-raw.md](07-project-journal-raw.md).

## Starting point

* Hardware: BS-UL080(U) OMR scanner, vendor SDK (`lib64/` = `sdk/` here) with a demo app
  (`LScannerSDKDemo.exe`) but no documentation, Chinese comments in the configs, Windows-only driver.
* Reference: the Linux POS terminals use a *different* reader (Atmel-based "a4ocr"/GENLOT on
  `/dev/ttyACM`, `libreaderGENLOT.so`, C source in `/home/pos/test/pixel_scanner/`) feeding a node
  WebSocket publisher on `wss://:8443`. Goal: produce the same JSON on Windows from the Windows scanner.

## Phase 1 — static analysis (2026-10-15)

* `LScannerSDK.dll` exports 31 clean C functions; every export is a forwarder into a `Vendor*Impl`
  singleton. Arities recovered from the export prologues (`objdump`), e.g. `SInit` has 3 args,
  `SGetTicketInfo(buf, size)`.
* Toolchain: [REA](https://github.com/morluto/rea) (MIT) driving Ghidra 12.1 headless, Node 22, JDK 21,
  installed under `~/tools`; also exposed as an MCP server for the assistant.

## Phase 2 — live device + mapping (2026-10-16 morning)

* `SInit(..)` returned 0, `SStart()` armed auto-scan on insert, `SGetTicketInfo` returned a 51-byte
  buffer: header + 22 big-endian row words = the 22×15 mark grid. Verified bit-for-bit against the
  demo's "Decode Result" panel.
* The Linux terminal's publisher output was captured for a known ticket ("Rosetta", 6/42); its
  `util.c` contained the `scara42`/`scara35` number tables. The scanner grid matched those tables only
  after mirroring columns within each 7-column block (`blockmirror`). `genlot_map.py` reproduced the
  Linux JSON exactly. (`archive/captures/` holds the images and buffers used.)

## Phase 3 — the instability (2026-10-16 midday)

Every automated design (one process per scan, one long process, Win32 message pump, a C# WinForms
host — all in `archive/`) decoded the first slip correctly and then **hung in `SRollBack`**, leaving
a `python.exe` that even `taskkill /F` could not end and that survived unplugging the scanner. A
"Fatal Application Exit" box with Chinese text appeared after each scan; a watcher thread was
written to auto-dismiss it, which made the hang deterministic. Hypotheses chased: MFC message pump
requirements, thread affinity, "scrape the vendor demo's window".

## Phase 4 — root cause (2026-10-16 afternoon)

The SDK's own logs were the key. In the demo's log the scan thread prints:

```
Calling scanner callback, eventId=5, data=2
Scanner callback called successfully
Waiting for paper feed or print
```

In ours: `Calling scanner callback` — and then nothing. Decompiling `VendorInitImpl::PreParameter` and
`VendorInitImpl::vftable` slot 6 showed that **`SInit`'s first argument is the callback function
pointer**, not a base directory (arguments 2 and 3 are `input_dir`/`output_dir`, defaulting to the
DLL's folder — which is why resources still loaded). We had been passing the string
`"C:\…\lib64\bin"`; after each scan the SDK jumped into the string bytes → access violation →
the SDK's unhandled-exception filter (`FUN_180020d70`: dump + `FatalAppExitA`) → the message box →
on dismissal `ExitProcess` → `CloseDev` on that thread while our `SRollBack`'s `FeedPaper` was
waiting for a status that never came on a closed handle → an IRP the 2012 driver never cancels →
unkillable process. Six of the day's 36 ejects hung exactly when `CloseDev` landed ~200 ms into the
feed wait.

With a real `CFUNCTYPE` callback the scan thread parks after each scan, the eject completes in
~0.8 s, the thread restarts its loop, and the process keeps scanning indefinitely. Eight consecutive
scans passed at once; the design has not changed since.

## Phase 5 — productisation (2026-10-16 → 2026-11-06)

* Callback-model service, file logging, raw-buffer logging, `SInit` retry loop, health probe via
  `SGetLastErrorCode()==0x3f0` (after verifying `ScannerIsReady()` does USB I/O and must not be
  polled), named-event graceful stop.
* Type-35 signature derived from `util.c` and confirmed on a real 5/35 slip.
* Installer (`install.ps1`), task-mode supervisor, then the Windows service (`omr_winservice.py`,
  pywin32 hosted by `python.exe` so per-user Python installs work).
* Persistence verified across reboots on the development PC; scanner-absent behaviour verified
  (`1001` retry loop) on 2026-11-06.

## Lessons

1. Read the vendor's own logs before theorising — they named the missing log line.
2. A crash handler that shows a dialog is not "cosmetic": dismissing it exits the process.
3. Shared-device drivers from 2012 may never cancel I/O; design the process model so the device is
   never closed while a transfer is pending.
4. Keep the decode path pure and offline-reproducible (`tools/`), it makes every later question a
   two-minute job.

## REA / Ghidra workflow used

`search_strings` (log literals) → `xrefs` → `resolve_containing_procedure` → `procedure_pseudo_code` /
`procedure_assembly`; imports are found via `search_procedures` ("KERNEL32.DLL::FatalAppExitA") then
`xrefs` on the external address. First analysis of the DLL takes 2–3 minutes, later queries are
instant. The analysis itself is not stored in this repo (REA's snapshot is tiny metadata); re-run it
from the DLL if needed.
