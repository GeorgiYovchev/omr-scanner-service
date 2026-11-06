<#
.SYNOPSIS
  Install the OMR betslip-scanner service (BS-UL080 -> WebSocket) on a Windows 10/11 x64 terminal.

.DESCRIPTION
  Clone or unzip this repository on the terminal (e.g. C:\omr-scanner), open PowerShell AS ADMINISTRATOR
  in that folder and run:

      powershell -ExecutionPolicy Bypass -File .\install.ps1 [-Online] [-Mode Service|Task] [-Port 8443]

  Steps: 1 USB driver (driver\BSdriver_x64)   2 VC++ 2013 + 2015-2022 x64 runtimes   3 Python 3.13 x64 + pip packages
         4 TLS cert check (certs\)            5 firewall rule                        6 autostart
         7 start + show the log
  -Mode Service (default): real Windows service "OMRScanner" (LocalSystem, starts at boot, auto-recovery).
  -Mode Task             : scheduled task "OMR-Scanner" at logon of the current user (no session-0 involved).
  Offline: put vc_redist.x64.exe, vcredist_x64.exe (2013), python-3.13.0-amd64.exe and the websockets / pywin32
  wheels into .\deps\ ; with -Online they are downloaded. A transcript is written to .\install-<timestamp>.log.
#>
param(
    [switch]$Online,
    [ValidateSet('Service', 'Task')] [string]$Mode = 'Service',
    [int]$Port = 8443,
    [switch]$NoFirewall,
    [switch]$SkipDriver,
    [switch]$SkipRuntimes,
    [switch]$SkipPython,
    [switch]$NoStart
)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
try { Start-Transcript -Path (Join-Path $root ('install-{0}.log' -f (Get-Date -Format 'yyyyMMdd-HHmmss'))) -ErrorAction Stop | Out-Null } catch { Write-Host '   !!  transcript not started: ' $_.Exception.Message }
function Step($m) { Write-Host "`n== $m" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "   OK  $m" -ForegroundColor Green }
function Warn($m) { Write-Host "   !!  $m" -ForegroundColor Yellow }

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { throw 'Run as Administrator (driver, runtimes, firewall and service registration need it).' }
if (-not [Environment]::Is64BitOperatingSystem) { throw '64-bit Windows is required (SDK and driver are x64 only).' }
$deps = Join-Path $root 'deps'; New-Item -ItemType Directory -Force -Path $deps | Out-Null
$svcDir = Join-Path $root 'service'

# ---------------------------------------------------------------- 1 driver
Step '1/7 USB driver (vendor BYSUSB)'
if ($SkipDriver) { Warn 'skipped' }
else {
    & pnputil.exe /add-driver (Join-Path $root 'driver\BSdriver_x64\bysusb.inf') /install | Out-Host
    Ok 'driver staged - plug the scanner in; Device Manager must show "USB Device Driver for Scanner and Printer"'
}

# ---------------------------------------------------------------- 2 runtimes
Step '2/7 Visual C++ runtimes'
function Ensure-Redist($name, $regKey, $file, $url, $silentArgs) {
    if (Test-Path $regKey) { Ok "$name present"; return }
    $exe = Join-Path $deps $file
    if (-not (Test-Path $exe)) {
        if ($Online) { Write-Host "   downloading $url"; Invoke-WebRequest -Uri $url -OutFile $exe -UseBasicParsing }
        else { throw "$name is missing: put $file into $deps or run with -Online" }
    }
    Start-Process -FilePath $exe -ArgumentList $silentArgs -Wait -NoNewWindow
    Ok "$name installed"
}
if ($SkipRuntimes) { Warn 'skipped' }
else {
    Ensure-Redist 'VC++ 2015-2022 x64' 'HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64' `
        'vc_redist.x64.exe' 'https://aka.ms/vs/17/release/vc_redist.x64.exe' '/install /quiet /norestart'
    Ensure-Redist 'VC++ 2013 x64' 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\VisualStudio\12.0\VC\Runtimes\x64' `
        'vcredist_x64.exe' 'https://aka.ms/highdpimfc2013x64enu' '/install /quiet /norestart'
}

# ---------------------------------------------------------------- 3 python
Step '3/7 Python 3.13 x64 + packages'
function Test-Py313 {
    try { $v = & py -3.13 -c "import sys;print(sys.version_info[0],sys.version_info[1],sys.maxsize>2**32)" 2>$null; return ($v -eq '3 13 True') }
    catch { return $false }
}
if ($SkipPython) { Warn 'skipped' }
else {
    if (Test-Py313) { Ok 'Python 3.13 x64 present' }
    else {
        $exe = Join-Path $deps 'python-3.13.0-amd64.exe'
        if (-not (Test-Path $exe)) {
            if ($Online) { Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.13.0/python-3.13.0-amd64.exe' -OutFile $exe -UseBasicParsing }
            else { throw "Python installer missing: put python-3.13.0-amd64.exe into $deps or run with -Online" }
        }
        Start-Process -FilePath $exe -ArgumentList '/quiet InstallAllUsers=1 PrependPath=1 Include_launcher=1 Include_test=0' -Wait -NoNewWindow
        $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
        if (-not (Test-Py313)) { throw 'Python install did not take - install Python 3.13 x64 manually and re-run' }
        Ok 'Python 3.13 x64 installed'
    }
    $pkgs = @('websockets>=13,<18'); if ($Mode -eq 'Service') { $pkgs += 'pywin32>=306' }
    $wheels = Get-ChildItem $deps -Filter '*.whl' -ErrorAction SilentlyContinue
    if ($wheels) { & py -3.13 -m pip install --quiet --no-index --find-links $deps @pkgs }
    else         { & py -3.13 -m pip install --quiet @pkgs }
    if ($LASTEXITCODE -ne 0) { throw 'pip install failed (needs internet, or the wheels in deps\)' }
    Ok ('websockets ' + (& py -3.13 -c "import websockets;print(websockets.__version__)"))
    if ($Mode -eq 'Service') {
        Ok ('pywin32 ' + (& py -3.13 -c "import win32api,sys;print(sys.modules['win32api'].__file__)"))
        # pywin32 post-install (registers pywintypes DLLs system-wide). Optional: the service is hosted
        # by python.exe, which finds the DLLs itself; so run it tolerantly and only if it exists.
        $ErrorActionPreference = 'Continue'
        $post = & py -3.13 -c "import sysconfig,os;print(os.path.join(sysconfig.get_paths()['scripts'],'pywin32_postinstall.py'))" 2>$null
        if ($post -and (Test-Path $post)) { & py -3.13 "$post" -install 2>&1 | Out-Null; Ok 'pywin32 post-install done' }
        else { Warn 'pywin32_postinstall.py not found - skipped (not required)' }
        $ErrorActionPreference = 'Stop'
    }
}

# ---------------------------------------------------------------- 4 certs
Step '4/7 TLS certificate'
$certs = Join-Path $root 'certs'
if ((Test-Path "$certs\fullchain.pem") -and (Test-Path "$certs\privkey.pem")) { Ok 'certs\fullchain.pem + privkey.pem found -> wss://' }
else { Warn 'no certs\fullchain.pem + privkey.pem -> plain ws:// (a browser page served over https will refuse it)' }

# ---------------------------------------------------------------- 5 firewall
Step '5/7 Firewall'
$pyExe = & py -3.13 -c "import sys;print(sys.executable)"
if ($NoFirewall) { Warn 'skipped' }
else {
    Get-NetFirewallRule -DisplayName 'OMR scanner websocket' -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    New-NetFirewallRule -DisplayName 'OMR scanner websocket' -Direction Inbound -Protocol TCP -LocalPort $Port `
        -Program $pyExe -Action Allow -Profile Any | Out-Null
    Ok "inbound TCP $Port allowed for $pyExe"
}

# ---------------------------------------------------------------- 6 autostart
Step "6/7 Autostart ($Mode)"
$cfg = Join-Path $svcDir 'config.json'
$json = Get-Content $cfg -Raw | ConvertFrom-Json
$json.port = $Port
[IO.File]::WriteAllText($cfg, ($json | ConvertTo-Json), (New-Object System.Text.UTF8Encoding $false))   # no BOM
# clean both variants first
Unregister-ScheduledTask -TaskName 'OMR-Scanner' -Confirm:$false -ErrorAction SilentlyContinue
if (Get-Service OMRScanner -ErrorAction SilentlyContinue) {
    Stop-Service OMRScanner -Force -ErrorAction SilentlyContinue
    & py -3.13 (Join-Path $svcDir 'omr_winservice.py') remove | Out-Null
}
if ($Mode -eq 'Service') {
    & py -3.13 (Join-Path $svcDir 'omr_winservice.py') --startup auto install | Out-Host
    # recovery if the service process itself dies (the supervisor already relaunches omr_service.py)
    & sc.exe failure OMRScanner reset= 86400 actions= restart/5000/restart/10000/restart/30000 | Out-Null
    & sc.exe failureflag OMRScanner 1 | Out-Null
    Ok 'Windows service OMRScanner registered (Automatic, LocalSystem, recovery = restart)'
} else {
    $launcher = Join-Path $svcDir 'start_omr.ps1'
    $exe  = "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe"
    $args = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$launcher`""
    $user = "$env:USERDOMAIN\$env:USERNAME"
    $action    = New-ScheduledTaskAction -Execute $exe -Argument $args -WorkingDirectory $svcDir
    $trigger   = New-ScheduledTaskTrigger -AtLogOn -User $user
    $settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
                     -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 99 -RestartInterval (New-TimeSpan -Minutes 1) `
                     -MultipleInstances IgnoreNew -Hidden
    $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName 'OMR-Scanner' -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
        -Description 'OMR betslip scanner -> WebSocket (service\start_omr.ps1)' | Out-Null
    Ok "scheduled task OMR-Scanner at logon of $user"
}

# ---------------------------------------------------------------- 7 start
Step '7/7 Start'
if ($NoStart) { Warn 'not started (-NoStart)' }
else {
    if ($Mode -eq 'Service') { Start-Service OMRScanner } else { Start-ScheduledTask -TaskName 'OMR-Scanner' }
    Start-Sleep -Seconds 10
    $svcLog = Join-Path $svcDir 'logs\omr_service.log'
    if (Test-Path $svcLog) { Get-Content $svcLog -Tail 6 | ForEach-Object { "   $_" } } else { Warn "no $svcLog yet - see service\logs\winservice.log / launcher.log" }
}
$scheme = if (Test-Path "$certs\privkey.pem") { 'wss' } else { 'ws' }
Write-Host "`nDone. Test:  `$env:WS_INSECURE='1'; py -3.13 `"$svcDir\wsclient.py`" $scheme`://127.0.0.1:$Port 60   then insert a betslip."
try { Stop-Transcript | Out-Null } catch {}
