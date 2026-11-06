"""Scan exactly one betslip, print its JSON, eject, exit — the PROVEN sequence.

Mirrors capture_with_image.py, which ejected cleanly 3x in a row: a FRESH process
per scan that reads the image BEFORE SRollBack, then os._exit. Reusing the SDK for
a 2nd scan in one process wedges SRollBack, so the supervisor spawns one of these
per ticket.

stdout: "READY" once armed, "RESULT <json>" on a scan. Exit 0 = scanned, 2 = timeout.
"""
from __future__ import annotations
import ctypes as C
import json
import os
import time

from omr_sdk import OmrSdk, suppress_crash_dialogs, disable_wer_ui
from genlot_map import to_output

TIMEOUT = int(os.environ.get("SCAN_TIMEOUT", "3600"))


def main() -> int:
    disable_wer_ui()
    sdk = OmrSdk()
    d = sdk.dll
    d.SRollBack.restype = C.c_bool; d.SRollBack.argtypes = []
    d.SGetOriginImageSize.restype = C.c_bool
    d.SGetOriginImageSize.argtypes = [C.c_void_p, C.c_void_p, C.c_void_p]
    d.SGetOriginImage.restype = C.c_int; d.SGetOriginImage.argtypes = [C.c_char_p, C.c_int]
    sdk.init()
    sdk.start()
    suppress_crash_dialogs()
    print("READY", flush=True)

    raw = None
    deadline = time.time() + TIMEOUT
    while time.time() < deadline:
        buf = C.create_string_buffer(65536)
        rc = d.SGetTicketInfo(buf, 65536)
        if rc and 1 < rc < 65536 and any(buf.raw[7:51]):
            raw = buf.raw[:rc]
            break
        time.sleep(0.05)

    if raw is not None:
        print("RESULT " + json.dumps(to_output(raw)), flush=True)
        # Consume the image BEFORE SRollBack — required or SRollBack wedges.
        try:
            a, b, c = C.c_int(0), C.c_int(0), C.c_int(0)
            d.SGetOriginImageSize(C.byref(a), C.byref(b), C.byref(c))
            sz = max(a.value, b.value, c.value)
            if 0 < sz < 8 * 1024 * 1024:
                d.SGetOriginImage(C.create_string_buffer(sz + 16), sz)
        except Exception:
            pass

    try:
        d.SRollBack()            # eject
    except Exception:
        pass
    time.sleep(0.8)
    os._exit(0 if raw is not None else 2)


if __name__ == "__main__":
    main()
