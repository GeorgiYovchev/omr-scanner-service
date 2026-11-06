# 2. LScannerSDK.dll — verified API

Vendor: the scanner manufacturer (name omitted in this public copy; the SDK's internal classes are written `Vendor*Impl` below, their real prefix is the vendor's name). `sdk/LScannerSDK.dll` v1.0.0.1 (x64, MFC, MSVC), 31 undecorated C exports,
no documentation shipped. Everything below was established by decompiling the DLL with Ghidra
(via [REA](https://github.com/morluto/rea)) and confirmed against the SDK's own logs and the live
device on 2026-10-16. Addresses are image-relative to base `0x180000000`.

## Lifecycle

| export | signature | notes |
|---|---|---|
| `SInit` | `int SInit(ScanCallback cb, const char* input_dir, const char* output_dir)` | **arg 1 is the callback** (see below). `input_dir` = folder containing `lib\`, `conf\`, `log\` (NULL/"" → the DLL's own folder); `output_dir` NULL → same. Opens the device. 0 = OK, `1001` = reader not found (`ScanPrnOpenDev ret=-2`), `1500` = init failed (runtime/driver). Logged as `VendorInitImpl::SInit`; args recorded by `PreParameter` as `input_dir=… output_dir=…`. |
| `SStart` | `bool SStart(void)` | starts the SDK scan thread (`ScanProcessControlBase::scanThreadFunction`). |
| `SStop` | `bool SStop(void)` | sets the stop flag, joins the scan thread (~200 ms). `0x3ec` on failure. |
| `SRollBack` | `bool SRollBack(void)` | eject: device `FeedPaper {"direction":1,"distance":0,"time-out":10000}` then `notifyPaperFeedComplete` (wakes the parked scan thread). ~0.8 s. Returns false after a 10 s feed timeout. |
| `SGetTicketInfo` | `int SGetTicketInfo(char* buf, int size)` | copies the decoded result; returns its length (51 for OMR) or 0/`Get decode result failed`. |
| `SGetOriginImageSize` | `bool (int* size, int* width, int* height)` | 3 OUT pointers (calling it with no args crashes). |
| `SGetOriginImage` | `int (char* buf, int size)` | 8-bit BMP, ~2 MB, 948 px stride × 2118 rows. |
| `SGetLastErrorCode` | `int (void)` | last error (`DAT_1802eba30`). No USB I/O → used as the health probe. |
| `ScannerIsReady` | `bool (void)` | **does USB I/O** (`ScanPrnGetStatus` + JSON parse, true when `"process"==0`). Do not call while scanning is armed. |
| `ScanIsComplete` | `bool (void)` | unused by us. |
| `LSReceiveInfo` | `int (buf, len, int, timeout)` | low-level receive with timeout — *not* callback registration. |
| `LSQueryStatus`, `LSSendCommand`, `SGetHWInformation`, `SGetSWVersion`, `SGetBrandDpi`, `SGetScanDpi`, `SQueryCapability`, `SRecognizeItem`, `SAdjustSensibility`, `SPrintBrandImage`, `LSCalibrateSensor`, `LSUpgradeFirmware`, `GetConfigFile*`, `WriteConfigFile*`, `SGetLastErrorStr` | — | not used. `LSCalibrateSensor`/`LSUpgradeFirmware` touch device firmware — keep out. `SGetLastErrorStr` has an unknown signature (crashes with no args). |

Every export is a thin forwarder: lock the API mutex (`DAT_1802eba70`), fetch the context
singleton, call `vtable[n](this, args…)` on the matching `Vendor*Impl` object. Error 0x3e9 (1001)
is returned when the singleton is missing — so **1001 has two meanings**: "not initialised" and
"ticket reader not found".

## The callback

```c
typedef void (*ScanCallback)(int eventId, int* pData);
```

* Stored by `VendorInitImpl::PreParameter` at `this+8`; `VendorInitImpl::vftable` (0x18028c580)
  slot 6 (0x180015290) returns it.
* Invoked by `VendorScanProcessControlImpl::notifyScanCompleteStatus` (0x18001d940) **on the SDK scan
  thread**: `if (cb) { log("Calling scanner callback, eventId=%d, data=%d"); cb(eventId, &data);
  log("Scanner callback called successfully"); }`. Call site: `MOV ECX,R14D; LEA RDX,[RBP+0x6f];
  CALL R15`. Return value ignored.
* `eventId 5` = decode result available; `data` = result-type code: OMR (SDK type 13) → 2,
  PDF417/QR/1D → other values. `eventId 3` = scan complete, no decode result (`data 0`).
* After the callback returns, `scanThreadFunction` (0x18001c160) parks on a condition variable
  ("Waiting for paper feed or print") until `notifyPaperFeedComplete` flips the flag (called
  inside `SRollBack`). Calling `SRollBack` *inside* the callback is also supported ("Paper feed
  notification received during scan, skipping wait").
* Python: `ctypes.CFUNCTYPE(None, c_int, POINTER(c_int))`; keep the object alive for the DLL's
  lifetime; do the minimum in it (enqueue) and the SDK calls from another thread, as the vendor
  demo does from its UI thread ~100 ms later.

## Result buffer (OMR, type 1)

51 bytes = 7-byte header + 22 × 2-byte big-endian row words.

```
offset  value
0       0x01   result type 1 (OMR grid)
1       0x2c   data length 44
2-3     0x000f columns (15)
4-5     0x0016 rows (22)
6       0x00   reserved
7..50   row words r0..r21, big-endian; column c (0..15) is set when bit (15-c) is set
```

The lower layer (`ScanPrnDevLib`) reports the raw decoder output as JSON (`{"count":1,"type":[13],
"size":[351],...}`, type 13 = OMR, 351 = 22×15 chars + commas) and logs the grid as
`pszOMRDecodeDest=100000010010011,…`; the SDK packs that into the words above with a column
permutation — see [03-ticket-layouts](03-ticket-layouts.md#decomr-string--scanner-word).

## Scan-thread state machine (`scanThreadFunction`)

```
loop while !stopFlag(this+0xa9):
  waitFlag(this+0xaa)=1, ejectNotified(this+0xac)=0
  r = doScan()                      // vtable[8]: ResumeToIdle → StartScan → poll IsComplete → fetch image+result → notify callback
  r==1: "Scan failed, exiting thread"   → lastError=0x3f0, thread ends     (scanner lost)
  r==2: "Stop Scan, exiting thread"     (SStop)
  r==3: "Scan needs retry, continuing loop"
  r==0: if !ejectNotified: "Waiting for paper feed or print"; cond_wait until waitFlag==0
        else "Paper feed notification received during scan, skipping wait"
        "Paper feed or print completed, restarting loop"
```

`doScan` → `ResumeToIdle` tries a feed-out first (`FeedPaper`, 2 s, `-9 No entry feed paper
status` when the tray is empty — normal), so there are ~2 s between the eject and the next arm.

## Internals map (for future work)

| symbol / address | role |
|---|---|
| `DAT_1802eba50` | the "Init interface" (`VendorInitImpl`, 0x58 bytes: +8 callback, +0x10 `std::string input_dir`, +0x30 `output_dir`, +0x50 initialised flag) |
| `DAT_1802ebc90 … DAT_1802ebd48` | the 24 `Vendor*Impl` singletons, created by `FUN_18001fa20` |
| `DAT_1802eba30` | last error code; `DAT_1802ebc38` error reporter (`FUN_180002420(rep, fn, params, code)`) |
| `FUN_180014b70` | `VendorInitImpl::SInit`; `FUN_1800152a0` `PreParameter`; `FUN_180015010` `DisableInitStatus` (closes device; not exported) |
| `FUN_18001d940` | `notifyScanCompleteStatus`; `FUN_18001c160` `scanThreadFunction`; `FUN_18001baa0` `SStop`; `FUN_180017090` `ScannerIsReady`; `FUN_180018e60` `LSReceiveInfo` |
| `FUN_180020d70` | unhandled-exception filter: writes a dump (`*_ScanPrnDevLib_*.dmp`), then `FatalAppExitA(0, msg)` = the "Fatal Application Exit" box, then exit |
| `FUN_18000a360` + `FUN_18000ad60/a9d0/a770/a910/ac30` | logger / log helpers (`[SDK]` lines in `lscanner_*.log`) |

Runtime dependencies of the DLL set: `VCRUNTIME140`, `MSVCP140` (VC++ 2015-2022 x64) **and**
`MSVCR120` (VC++ 2013 x64), plus `gdiplus`, `dbghelp`, `winspool`, `oleacc` (Windows). A missing
runtime shows as `Load lib …\bitmap.dll failed … side-by-side configuration is incorrect` and
`SInit` → 1500.

## SDK configuration files

* `sdk/conf/LScannerConfig.ini` — `PaperOutDirection=1` (eject towards the entry slot),
  `OMRDecodeEnable=1`, `PDF417DecodeEnable=1`, `QRDecodeEnable=0`, `BarcodeDecodeEnable=0`,
  `AutoDeskewCrop=1`, and the log settings (20 MB files, 5 backups).
* `sdk/lib/DecodeCfg.ini` — deskew/zoom parameters and the OMR section: `threshold=120`,
  `threshold_mark=80`, `mark_block_ratio=50`, error tolerances. This is where mark sensitivity is tuned.
* `sdk/lib/FormatFile.txt` — the `{1001}` grid geometry (timing track, 22 rows × 15 columns).
* `sdk/lib/ImgConfig.ini`, `sdk/lib/scanprnlib_logconfig.ini` — image pipeline and device-layer log settings.
