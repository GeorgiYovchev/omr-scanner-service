# Task-mode launcher / supervisor (alternative to the Windows service, no admin needed).
# Runs omr_service.py in a loop: rc 3 (scanner lost) -> relaunch in 5 s, other -> 10 s, 0 -> stop.
# Settings come from config.json (environment variables override it).
#   powershell -ExecutionPolicy Bypass -File start_omr.ps1
$ErrorActionPreference = 'Continue'
$here = $PSScriptRoot
Set-Location $here
$logDir = Join-Path $here 'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$launcherLog = Join-Path $logDir 'launcher.log'
function Log($m) { "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $m" | Out-File -FilePath $launcherLog -Append -Encoding utf8 }

$created = $false
$mutex = New-Object System.Threading.Mutex($true, 'Global\OMR-Scanner-Launcher', [ref]$created)
if (-not $created) { Log "another launcher is already running - exiting"; exit 0 }

$py = (Get-Command py.exe -ErrorAction SilentlyContinue).Source
if (-not $py) { foreach ($c in @("$env:LOCALAPPDATA\Programs\Python\Launcher\py.exe", "$env:WINDIR\py.exe")) { if (Test-Path $c) { $py = $c; break } } }
if (-not $py) { Log "py.exe not found - install Python 3.13 x64 (install.ps1)"; exit 2 }

Log "launcher start via $py"
while ($true) {
    $t0 = Get-Date
    $p = Start-Process -FilePath $py -ArgumentList '-3.13', "`"$here\omr_service.py`"" -WorkingDirectory $here `
         -NoNewWindow -Wait -PassThru -RedirectStandardError (Join-Path $logDir 'stderr.log')
    $rc = $p.ExitCode
    Log "omr_service exited rc=$rc after $([int]((Get-Date) - $t0).TotalSeconds)s"
    if ($rc -eq 0) { break }
    Start-Sleep -Seconds $(if ($rc -eq 3) { 5 } else { 10 })
}
Log "launcher stop"
$mutex.ReleaseMutex()
