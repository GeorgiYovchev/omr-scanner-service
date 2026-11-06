"""Thin ctypes binding for LScannerSDK.dll (Win64).

Signatures are PROVISIONAL (arity confirmed by RE of the export prologues; types/semantics
to be verified against the live device). Run on Windows Python — the DLL + driver are Win64.
"""
from __future__ import annotations
import ctypes as C
import os

# lib64 holds the SDK + its dependency DLLs; add it to the DLL search path.
LIB64 = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "lib64"))

def suppress_crash_dialogs():
    """Best-effort: set the process error mode so a native fault doesn't pop the
    classic GP-fault box. Safe to call repeatedly. Does NOT install an exception
    filter (that deadlocks the SDK worker thread). The real WER-dialog suppression
    is disable_wer_ui()."""
    try:
        # SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX|SEM_NOOPENFILEERRORBOX
        C.windll.kernel32.SetErrorMode(0x0001 | 0x0002 | 0x8000)
    except Exception:
        pass


def disable_wer_ui():
    """Suppress the Windows Error Reporting 'program stopped working' dialog for
    THIS user (HKCU, no admin). The SDK worker thread faults harmlessly at process
    teardown after the slip is already ejected; this stops the popup without
    interfering with the scan/eject. Revert: set DontShowUI back to 0."""
    try:
        import winreg
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                               r"Software\Microsoft\Windows\Windows Error Reporting")
        winreg.SetValueEx(key, "DontShowUI", 0, winreg.REG_DWORD, 1)
        winreg.CloseKey(key)
    except Exception:
        pass


class OmrError(RuntimeError):
    pass


class OmrSdk:
    def __init__(self, lib64: str = LIB64):
        self.lib64 = lib64
        if hasattr(os, "add_dll_directory"):          # Windows: let it find sibling DLLs
            os.add_dll_directory(lib64)
            os.add_dll_directory(os.path.join(lib64, "lib"))
        self.dll = C.WinDLL(os.path.join(lib64, "LScannerSDK.dll"))
        suppress_crash_dialogs()   # after DLL load (it resets error mode on load)
        self._bind()

    def _bind(self):
        d = self.dll
        # bool-returning, no-arg controls
        for name in ("SStart", "SStop", "ScanIsComplete", "ScannerIsReady"):
            fn = getattr(d, name)
            fn.restype = C.c_bool
            fn.argtypes = []
        # SInit(a, b, c) -> int. Provisional: (config_dir, log_dir, mode).
        d.SInit.restype = C.c_int
        # SInit(base_dir, callback, userdata) -> int.
        # Confirmed from logs: arg1 is a base dir ending in "bin"; the SDK derives
        # ..\lib, ..\conf, ..\log from it. arg2/arg3 provisional (scan-complete
        # callback + userdata); for polling we pass NULL/0 and use ScanIsComplete.
        d.SInit.argtypes = [C.c_char_p, C.c_void_p, C.c_void_p]
        # SGetTicketInfo(buf, size) -> int (bytes written / status). Provisional.
        d.SGetTicketInfo.restype = C.c_int
        d.SGetTicketInfo.argtypes = [C.c_char_p, C.c_int]
        # errors
        d.SGetLastErrorCode.restype = C.c_int
        d.SGetLastErrorCode.argtypes = []
        # SGetLastErrorStr signature unconfirmed (returned -1 when called w/ no args);
        # read as raw pointer and validate before deref so it can never crash a scan.
        d.SGetLastErrorStr.restype = C.c_void_p

    # --- lifecycle ---------------------------------------------------------
    def init(self, base_dir: str | None = None) -> int:
        # SDK derives ..\lib, ..\conf, ..\log from this; must be the "bin" dir.
        base = (base_dir or os.path.join(self.lib64, "bin")).encode()
        rc = self.dll.SInit(base, None, None)
        if rc != 0:
            raise OmrError(f"SInit failed rc={rc} code={self.last_error()} {self.last_error_str()}")
        return rc

    def start(self) -> bool: return bool(self.dll.SStart())
    def stop(self) -> bool: return bool(self.dll.SStop())
    def is_ready(self) -> bool: return bool(self.dll.ScannerIsReady())
    def scan_complete(self) -> bool: return bool(self.dll.ScanIsComplete())

    def last_error(self) -> int: return int(self.dll.SGetLastErrorCode())

    def last_error_str(self) -> str:
        try:
            p = self.dll.SGetLastErrorStr()
            if not p or p in (0xFFFFFFFFFFFFFFFF,):
                return ""
            return C.string_at(p).decode("gbk", errors="replace")  # SDK strings are GBK
        except Exception:
            return ""

    # --- decoded result ----------------------------------------------------
    def get_ticket_info(self, bufsize: int = 65536) -> bytes:
        """Return the raw decoded-result buffer. Format is parsed by result_parser."""
        buf = C.create_string_buffer(bufsize)
        n = self.dll.SGetTicketInfo(buf, bufsize)
        if n < 0:
            raise OmrError(f"SGetTicketInfo rc={n} code={self.last_error()} {self.last_error_str()}")
        # n may be a status or a length; return the whole buffer up to first NUL as a fallback.
        return buf.raw if n in (0, 1) else buf.raw[:n]
