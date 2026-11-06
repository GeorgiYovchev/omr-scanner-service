r"""ctypes binding for LScannerSDK.dll (SNBC/BeiYang BS-UL080, Win64).

Signatures recovered by decompiling the DLL with Ghidra (2026-10-16); see docs/02-sdk-api.md.
The one that matters, and that was wrong for a whole day:

    int SInit(ScanCallback cb, const char* input_dir, const char* output_dir)

  * arg1 is the SCAN-COMPLETE CALLBACK, not a path. SNBCInitImpl::PreParameter stores it
    at this+8, SNBCInitImpl vtable[6] returns it, and
    SNBCScanProcessControlImpl::notifyScanCompleteStatus calls it from the SDK scan thread
    as  cb(int eventId, int* pData)  (x64 call site: ECX=eventId, RDX=&data).
      eventId 5 = decode result ready (data 2 = OMR)  -> SGetTicketInfo()
      eventId 3 = scan finished, nothing decoded      -> still eject
    Passing anything else there makes the SDK execute garbage after every scan:
    "Fatal Application Exit", process exit while an eject is in flight, unkillable zombie.
  * input_dir: folder holding lib\, conf\, log\  (NULL -> the DLL's own folder).
  * output_dir: NULL -> the DLL's own folder.
  After the callback the SDK scan thread parks ("Waiting for paper feed or print") until
  SRollBack() notifies it, then restarts its scan loop by itself.

Other exports used: SStart/SStop/SRollBack -> bool, SGetTicketInfo(buf,size) -> int
(51 on an OMR result), SGetOriginImageSize(int*,int*,int*) -> bool,
SGetOriginImage(buf,size) -> int, SGetLastErrorCode() -> int.
"""
from __future__ import annotations
import ctypes as C
import os

# The SDK folder (LScannerSDK.dll + lib\ conf\ log\). Default: ..\sdk next to this file.
SDK_DIR = os.environ.get("OMR_SDK_DIR") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "sdk"))

# void cb(int eventId, int* pData). x64 has a single calling convention.
SCAN_CALLBACK = C.CFUNCTYPE(None, C.c_int, C.POINTER(C.c_int))

EVENT_DECODED = 5      # decode result available
EVENT_NO_DECODE = 3    # scan done, nothing decoded (paper still inside)

# SGetLastErrorCode() / SInit return values we act on (from the decompile + SDK logs):
ERR_NOT_INIT = 0x3e9          # 1001: SInit not done / singleton missing ...
ERR_READER_NOT_FOUND = 1001   # ... and ALSO SInit's "ticket reader not found" (ScanPrnOpenDev ret=-2)
ERR_DEVICE_INIT = 1500        # ScanPrnInitModel failed (bitmap.dll / VC++ runtime missing, bad driver)
ERR_SCAN_THREAD_DEAD = 0x3f0  # 1008: "Scan failed, exiting thread" - scanner lost mid-run


def suppress_crash_dialogs():
    """SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX | SEM_NOOPENFILEERRORBOX."""
    try:
        C.windll.kernel32.SetErrorMode(0x0001 | 0x0002 | 0x8000)
    except Exception:
        pass


class OmrError(RuntimeError):
    pass


class OmrSdk:
    def __init__(self, sdk_dir: str = SDK_DIR):
        self.sdk_dir = sdk_dir
        if hasattr(os, "add_dll_directory"):          # let Windows find the sibling DLLs
            os.add_dll_directory(sdk_dir)
            os.add_dll_directory(os.path.join(sdk_dir, "lib"))
        self.dll = C.WinDLL(os.path.join(sdk_dir, "LScannerSDK.dll"))
        suppress_crash_dialogs()   # after DLL load (it resets error mode on load)
        self._cb = None            # keeps the ctypes callback alive for the DLL
        self._bind()

    def _bind(self):
        d = self.dll
        d.SInit.restype = C.c_int
        d.SInit.argtypes = [SCAN_CALLBACK, C.c_char_p, C.c_char_p]
        for name in ("SStart", "SStop", "ScanIsComplete", "ScannerIsReady", "SRollBack"):
            fn = getattr(d, name)
            fn.restype = C.c_bool
            fn.argtypes = []
        d.SGetTicketInfo.restype = C.c_int
        d.SGetTicketInfo.argtypes = [C.c_char_p, C.c_int]
        d.SGetOriginImageSize.restype = C.c_bool
        d.SGetOriginImageSize.argtypes = [C.POINTER(C.c_int)] * 3
        d.SGetOriginImage.restype = C.c_int
        d.SGetOriginImage.argtypes = [C.c_char_p, C.c_int]
        d.SGetLastErrorCode.restype = C.c_int
        d.SGetLastErrorCode.argtypes = []

    # --- lifecycle ---------------------------------------------------------
    def init(self, on_event, input_dir: str | None = None, output_dir: str | None = None) -> int:
        """on_event(event_id, data) runs on the SDK's scan thread: keep it tiny."""
        def _cb(event_id, pdata):
            try:
                on_event(int(event_id), int(pdata[0]) if pdata else 0)
            except Exception as e:          # never let an exception cross into the DLL
                print("[sdk] callback error:", e, flush=True)
        self._cb = SCAN_CALLBACK(_cb)
        rc = self.dll.SInit(self._cb,
                            (input_dir or self.sdk_dir).encode(),
                            (output_dir or self.sdk_dir).encode())
        if rc != 0:
            raise OmrError(f"SInit failed rc={rc} ({describe_error(rc)})")
        return rc

    def start(self) -> bool: return bool(self.dll.SStart())
    def stop(self) -> bool: return bool(self.dll.SStop())
    def rollback(self) -> bool: return bool(self.dll.SRollBack())     # eject the slip
    def last_error(self) -> int: return int(self.dll.SGetLastErrorCode())
    # NOTE: ScannerIsReady()/LSQueryStatus do USB I/O - never call them while scanning is armed.

    # --- results -----------------------------------------------------------
    def get_ticket_info(self, bufsize: int = 65536) -> bytes | None:
        """Raw decoded-result buffer (51 bytes for OMR: 7-byte header + 22 rows), or None."""
        buf = C.create_string_buffer(bufsize)
        n = self.dll.SGetTicketInfo(buf, bufsize)
        return buf.raw[:n] if 1 < n < bufsize else None

    def fetch_image(self) -> bytes | None:
        """8-bit BMP of the scan (~2 MB). Not needed for decoding."""
        size, w, h = C.c_int(0), C.c_int(0), C.c_int(0)
        if not self.dll.SGetOriginImageSize(C.byref(size), C.byref(w), C.byref(h)):
            return None
        n = max(size.value, w.value, h.value)
        if not 0 < n < 16 * 1024 * 1024:
            return None
        buf = C.create_string_buffer(n + 16)
        self.dll.SGetOriginImage(buf, n)
        return buf.raw[:n]


def describe_error(code: int) -> str:
    return {
        1001: "ticket reader not found / not initialised (scanner unplugged or held by another process)",
        1500: "device init failed (VC++ runtime, bitmap.dll or driver problem)",
        0x3f0: "scan thread exited (scanner lost)",
        0x3ec: "stop failed",
        0x3ee: "device not initialised",
        0x5dc: "invalid parameter / internal",
    }.get(code, "unknown")
