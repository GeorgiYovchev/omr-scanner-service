r"""Windows service "OMRScanner": supervises omr_service.py.

Why a supervisor and not the scanner in-process: the SDK cannot be re-initialised safely
inside one process after the scanner is lost, so the proven model is "one process per
scanner session" - this service relaunches omr_service.py whenever it exits
(exit 3 = scanner lost -> 5 s, anything else -> 10 s) and stops it gracefully via a named
Windows event (omr_service.py runs SStop, then exits 0).

Hosted by python.exe itself (_exe_name_), not pywin32's pythonservice.exe, so it also works
with a per-user Python install and never hits the "DLL not found / error 1053" trap.

  install:   py -3.13 omr_winservice.py --startup auto install     (as Administrator)
  start:     py -3.13 omr_winservice.py start      (or: sc start OMRScanner)
  stop:      py -3.13 omr_winservice.py stop
  remove:    py -3.13 omr_winservice.py remove
  debug:     py -3.13 omr_winservice.py debug      (runs in the console)
Logs: logs\winservice.log and logs\omr_service.log (+ Windows Application event log).
"""
from __future__ import annotations
import logging
import logging.handlers
import os
import subprocess
import sys
import time

import servicemanager
import win32event
import win32service
import win32serviceutil

HERE = os.path.dirname(os.path.abspath(__file__))
SERVICE_SCRIPT = os.path.join(HERE, "omr_service.py")
STOP_EVENT_NAME = r"Global\OMRScannerStop"
EXIT_SCANNER_LOST = 3


def _python_exe() -> str:
    exe = sys.executable
    if exe.lower().endswith("pythonw.exe"):
        exe = exe[:-len("pythonw.exe")] + "python.exe"
    return exe


def _logger() -> logging.Logger:
    log = logging.getLogger("omr.winservice")
    if not log.handlers:
        os.makedirs(os.path.join(HERE, "logs"), exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(os.path.join(HERE, "logs", "winservice.log"),
                                                  maxBytes=1024 * 1024, backupCount=3, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(fh)
        log.setLevel(logging.INFO)
    return log


class OmrScannerService(win32serviceutil.ServiceFramework):
    _svc_name_ = "OMRScanner"
    _svc_display_name_ = "OMR Betslip Scanner"
    _svc_description_ = "SNBC BS-UL080 betslip scanner -> WebSocket JSON (supervises service\\omr_service.py)"
    _exe_name_ = _python_exe()                       # host the service in python.exe
    _exe_args_ = f'"{os.path.abspath(__file__)}"'

    def __init__(self, args):
        super().__init__(args)
        # manual-reset, named: omr_service.py opens it and exits cleanly when it is signalled
        self.stop_event = win32event.CreateEvent(None, True, False, STOP_EVENT_NAME)
        self.stopping = False
        self.child: subprocess.Popen | None = None

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self.stopping = True
        win32event.SetEvent(self.stop_event)

    def SvcDoRun(self):
        servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATION_TYPE, servicemanager.PYS_SERVICE_STARTED,
                              (self._svc_name_, ""))
        try:
            self.supervise()
        except Exception as e:                        # never die silently
            _logger().exception("supervisor crashed: %s", e)
            servicemanager.LogErrorMsg(f"OMRScanner supervisor crashed: {e}")
            raise
        servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATION_TYPE, servicemanager.PYS_SERVICE_STOPPED,
                              (self._svc_name_, ""))

    def _wait_stop(self, seconds: float) -> bool:
        """True if a stop was requested within `seconds`."""
        return win32event.WaitForSingleObject(self.stop_event, int(seconds * 1000)) == win32event.WAIT_OBJECT_0

    def supervise(self):
        log = _logger()
        py = _python_exe()
        env = os.environ.copy()
        env["OMR_STOP_EVENT"] = STOP_EVENT_NAME
        log.info("supervisor start (python %s)", py)
        os.makedirs(os.path.join(HERE, "logs"), exist_ok=True)
        stderr_path = os.path.join(HERE, "logs", "stderr.log")
        while not self.stopping:
            t0 = time.monotonic()
            with open(stderr_path, "ab") as err:
                self.child = subprocess.Popen([py, SERVICE_SCRIPT], cwd=HERE, env=env,
                                              stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=err,
                                              creationflags=subprocess.CREATE_NO_WINDOW)
                log.info("omr_service started pid %d", self.child.pid)
                while self.child.poll() is None:
                    if self._wait_stop(1.0):
                        break
                if self.stopping or self.child.poll() is None:
                    # stop requested: the child sees the named event and runs SStop; give it time
                    try:
                        self.child.wait(timeout=12)
                        log.info("omr_service stopped cleanly rc=%s", self.child.returncode)
                    except subprocess.TimeoutExpired:
                        log.warning("omr_service did not stop in time - killing")
                        self.child.kill()
                    break
            rc = self.child.returncode
            up = int(time.monotonic() - t0)
            log.warning("omr_service exited rc=%s after %ds - relaunching", rc, up)
            if self._wait_stop(5 if rc == EXIT_SCANNER_LOST else 10):
                break
        log.info("supervisor stop")


if __name__ == "__main__":
    if len(sys.argv) == 1:
        # started by the Service Control Manager
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(OmrScannerService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(OmrScannerService)
