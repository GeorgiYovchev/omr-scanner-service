# archive/ — what was tried before the final design

Kept because the machine the project was developed on is being decommissioned; nothing here is
needed to run the service.

* `experiments/` — every earlier service/probe variant (`omr_sdk_v1_wrong_sinit.py` = the binding
  with the wrong `SInit` argument that caused the day-long instability; `omr_service_pump_v3.py`
  = message-pump attempt; `scan_once.py` + `start_test.ps1` = process-per-scan supervisor;
  `demo_scrape.py` = plan to scrape the vendor demo's window; `probe/diag/eject/init_test` =
  first-contact probes; `*.out/*.err` = their outputs).
* `csharp/` — the C# WinForms host attempt (same wrong `SInit` call; decoding/mapping port is correct).
* `captures/` — the test tickets as scanned BMPs (`rosetta.bmp`/`t1` = the 6/42 "Rosetta" slip with
  known Linux output, `t2`, `t3`), their raw buffers (`rosetta.txt`, `result_capture.txt`).
* `driver-x86/` — the 32-bit variant of the SNBC driver (unused; the SDK is x64).
* `install-log-2026-10-16.txt` — transcript of the first installation.
* `README-omr-service-2026-10-16.md` — the service README as of the day the root cause was found.

See `docs/08-history-and-reverse-engineering.md` for the narrative.
