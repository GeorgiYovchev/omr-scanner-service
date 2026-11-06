"""Capture BOTH the decoded grid and the scan image in one scan.

The image (8-bit BMP, ~948x2118) lets us see printed numbers next to marks,
so we can derive the grid-cell -> lottery-number mapping.
Run: py -3.13 capture_with_image.py   (insert the Rosetta ticket when prompted)
"""
import ctypes as C
import os
import time
from omr_sdk import OmrSdk

sdk = OmrSdk()
d = sdk.dll
d.SRollBack.restype = C.c_bool; d.SRollBack.argtypes = []
# SGetOriginImageSize takes 3 OUT pointers (size/width/height) — confirmed by disasm.
d.SGetOriginImageSize.restype = C.c_bool
d.SGetOriginImageSize.argtypes = [C.c_void_p, C.c_void_p, C.c_void_p]
d.SGetOriginImage.restype = C.c_int; d.SGetOriginImage.argtypes = [C.c_char_p, C.c_int]

print("SInit:", sdk.init(), flush=True)
print("SStart:", sdk.start(), flush=True)
print(">>> INSERT THE ROSETTA TICKET NOW (45s) <<<", flush=True)

raw = None
deadline = time.time() + 45
while time.time() < deadline:
    buf = C.create_string_buffer(65536)
    rc = d.SGetTicketInfo(buf, 65536)
    if rc and 1 < rc < 65536:
        raw = buf.raw[:rc]
        print("TICKET rc", rc, "hex:", raw.hex(), flush=True)
        break
    time.sleep(0.1)

try:
    a, b, c = C.c_int(0), C.c_int(0), C.c_int(0)
    ok = d.SGetOriginImageSize(C.byref(a), C.byref(b), C.byref(c))
    print("SGetOriginImageSize ok:", ok, "vals:", a.value, b.value, c.value, flush=True)
    sz = max(a.value, b.value, c.value)   # size is the large one; others are w/h
    if sz and sz > 0:
        ibuf = C.create_string_buffer(sz + 16)
        irc = d.SGetOriginImage(ibuf, sz)
        data = ibuf.raw[:sz]
        out_bmp = os.environ.get("OUT_BMP", "rosetta.bmp")
        with open(out_bmp, "wb") as f:
            f.write(data)
        print("saved", out_bmp, sz, "rc:", irc, "magic:", data[:2], flush=True)
except Exception as e:
    print("img err:", e, flush=True)

print("SRollBack (eject):", bool(d.SRollBack()), flush=True)
time.sleep(0.5)
os._exit(0)
