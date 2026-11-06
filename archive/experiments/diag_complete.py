"""SAFE diagnostic: learn ScanIsComplete() raw-int semantics across one scan.
Never loops SRollBack, so it cannot wedge. Insert ONE ticket during the window.
"""
import ctypes as C, time
from omr_sdk import OmrSdk, suppress_crash_dialogs, disable_wer_ui

LOG = open("diag.out", "w")
def log(*a):
    m = " ".join(str(x) for x in a); print(m, flush=True); LOG.write(m+"\n"); LOG.flush()

disable_wer_ui()
sdk = OmrSdk()
sdk.dll.ScanIsComplete.restype = C.c_int;  sdk.dll.ScanIsComplete.argtypes = []
sdk.dll.ScannerIsReady.restype = C.c_int;  sdk.dll.ScannerIsReady.argtypes = []
sdk.dll.SGetTicketInfo.restype = C.c_int
sdk.dll.SRollBack.restype = C.c_bool;      sdk.dll.SRollBack.argtypes = []
log("SInit:", sdk.init()); log("SStart:", sdk.start()); suppress_crash_dialogs()
log(">>> INSERT ONE TICKET NOW — watching ScanIsComplete for 40s <<<")

end = time.time() + 40
prev = object()
while time.time() < end:
    v = sdk.dll.ScanIsComplete()
    if v != prev:
        log(time.strftime("%H:%M:%S"), "ScanIsComplete =", v, "ScannerIsReady =", sdk.dll.ScannerIsReady())
        prev = v
    time.sleep(0.08)

# one read + eject at the very end (single SRollBack, not looped)
buf = C.create_string_buffer(65536)
rc = sdk.dll.SGetTicketInfo(buf, 65536)
log("final SGetTicketInfo rc =", rc, "data7-20 =", buf.raw[7:20].hex())
log("SRollBack:", bool(sdk.dll.SRollBack()))
time.sleep(1.0)
LOG.close()
C.windll.kernel32.TerminateProcess(C.windll.kernel32.GetCurrentProcess(), 0)
