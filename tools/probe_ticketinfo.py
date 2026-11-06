"""Capture the decoded SGetTicketInfo result, correctly.

Flow (from vendor logs): SStart -> (auto-scan on insert) -> poll SGetTicketInfo
until it returns the result -> SRollBack (ejects the slip) -> SStop.

Writes everything to result_capture.txt too, so nothing is lost to stdout buffering.
Run on Windows: py -3.13 probe_ticketinfo.py
"""
from __future__ import annotations
import binascii
import ctypes as C
import os
import time

from omr_sdk import OmrSdk

OUT = os.environ.get("CAP_OUT", "result_capture.txt")
BUFSIZE = 65536
_log_fh = open(OUT, "w", encoding="utf-8")


def log(*a):
    msg = " ".join(str(x) for x in a)
    print(msg, flush=True)
    _log_fh.write(msg + "\n"); _log_fh.flush()


def has_data(buf: bytes, rc: int) -> bool:
    # completion heuristic: rc looks like a byte count (e.g. 51), or buffer has content
    if rc and rc not in (0, 1) and rc < BUFSIZE:
        return True
    return any(b != 0 for b in buf[:64])


def dump(raw: bytes):
    trimmed = raw.rstrip(b"\x00") or raw
    log(f"\n--- result length (to last non-NUL): {len(trimmed)} bytes ---")
    log("[hex]\n" + binascii.hexlify(trimmed[:512]).decode())
    for enc in ("ascii", "utf-8", "utf-16-le", "gb2312", "gbk"):
        try:
            log(f"[{enc}]\n" + trimmed.decode(enc).strip())
        except Exception as e:  # noqa: BLE001
            log(f"[{enc}] <decode failed: {e}>")


def main() -> int:
    sdk = OmrSdk()
    sdk.dll.SRollBack.restype = C.c_bool
    sdk.dll.SRollBack.argtypes = []

    log("SInit:", sdk.init())
    log("SStart:", sdk.start())
    log(">>> INSERT THE BETSLIP NOW (polling up to 45s) <<<")

    raw = None
    deadline = time.time() + 45
    while time.time() < deadline:
        buf = C.create_string_buffer(BUFSIZE)
        rc = sdk.dll.SGetTicketInfo(buf, BUFSIZE)
        if has_data(buf.raw, rc):
            raw = buf.raw[:rc] if (rc and 1 < rc < BUFSIZE) else buf.raw
            log(f"GOT RESULT (SGetTicketInfo rc={rc})")
            break
        time.sleep(0.1)

    # Dump IMMEDIATELY — before any call that could wedge in USB I/O.
    if raw is not None:
        dump(raw)
    else:
        log("TIMED OUT — no result captured")

    # Eject the slip (SRollBack returns cleanly). Skip SStop: it blocks in a USB
    # call after a real decode and wedges the process. Hard-exit frees the device.
    log("SRollBack (eject):", bool(sdk.dll.SRollBack()))
    time.sleep(0.5)
    _log_fh.flush(); _log_fh.close()
    os._exit(0 if raw is not None else 1)


if __name__ == "__main__":
    main()
