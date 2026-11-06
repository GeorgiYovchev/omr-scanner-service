# Remove the OMR scanner service / task, its firewall rule and stop running instances.
# Leaves the USB driver, Python and the VC++ runtimes in place.
# Run as Administrator:  powershell -ExecutionPolicy Bypass -File .\uninstall.ps1
$ErrorActionPreference = 'Continue'
$svcDir = Join-Path $PSScriptRoot 'service'
if (Get-Service OMRScanner -ErrorAction SilentlyContinue) {
    Stop-Service OMRScanner -Force -ErrorAction SilentlyContinue
    & py -3.13 (Join-Path $svcDir 'omr_winservice.py') remove
}
Unregister-ScheduledTask -TaskName 'OMR-Scanner' -Confirm:$false -ErrorAction SilentlyContinue
Get-NetFirewallRule -DisplayName 'OMR scanner websocket' -ErrorAction SilentlyContinue | Remove-NetFirewallRule
# The service is idle between scans, so a hard stop is safe; avoid the ~1 s eject right after a scan.
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*start_omr.ps1*' -or $_.CommandLine -like '*omr_service.py*' -or $_.CommandLine -like '*omr_winservice.py*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Write-Host 'OMR scanner removed (service/task, firewall rule, running processes).'
