"""Eject a slip cleanly (fresh process, no SStop wedge)."""
import ctypes as C, os, time
from omr_sdk import OmrSdk
sdk = OmrSdk()
sdk.dll.SRollBack.restype = C.c_bool
sdk.dll.SRollBack.argtypes = []
print("SInit:", sdk.init(), flush=True)
print("SStart:", sdk.start(), flush=True)
time.sleep(0.4)
print("SRollBack (eject):", bool(sdk.dll.SRollBack()), flush=True)
time.sleep(0.6)
os._exit(0)
