# Changelog

## 2026-11-06 — repository + Windows service
* Repository restructured as the deployable unit (`service/`, `sdk/`, `driver/`, `certs/`, `tools/`, `docs/`, `archive/`).
* Windows service `OMRScanner` (`service/omr_winservice.py`, pywin32, hosted by `python.exe`) supervising `omr_service.py`;
  graceful stop via named event `Global\OMRScannerStop`.
* `omr_service.py`: `config.json`, BOM-tolerant, signal handlers, `OMR_FETCH_IMAGE` saves BMPs, SDK dir relative to the repo.
* `install.ps1 -Mode Service|Task`, timestamped transcripts, BOM-less config writes; `uninstall.ps1`, `package.ps1` updated.
* `tools/decode_raw.py`, `tools/grid_from_sdklog.py`.
* Documentation `docs/01`–`10`, archive of all experiments.
* Verified: install on the development PC, scan under the service (session 0), graceful stop, supervisor relaunch.

## 2026-10-16 — working service
* Root cause of the eject hangs found: `SInit`'s first argument is the scan-complete callback. Callback model implemented;
  continuous scanning stable.
* Type-35 signature added; raw buffer logged per scan; scheduled-task autostart; first installer; `*.oddstech.net` cert → `wss`.

## 2026-10-15/16 — reverse engineering
* SDK exports, result buffer format, grid → numbers mapping (via the Linux `util.c` tables + block mirroring), Linux
  publisher contract captured.
