"""Init-only validation — no betslip needed.

Confirms our ctypes binding + SInit base-dir arg work against the live device.
Run on Windows: py -3.13 init_test.py   (close the vendor demo first; it holds the device)
"""
import time
from omr_sdk import OmrSdk

sdk = OmrSdk()
print("SInit...", flush=True)
rc = sdk.init()
print("  SInit rc:", rc)
print("  ScannerIsReady:", sdk.is_ready())
print("SStart...", sdk.start())
time.sleep(1.0)
print("  ScanIsComplete (no paper -> expect False):", sdk.scan_complete())
print("SStop...", sdk.stop())
print("last_error:", sdk.last_error(), sdk.last_error_str())
print("OK")
