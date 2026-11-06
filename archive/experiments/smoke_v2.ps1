Set-Location C:\Repos\gitlab\OMR\omr-service
Write-Output '=== python compile (warnings = errors) ==='
py -3.13 -W error -m py_compile omr_sdk.py omr_service.py genlot_map.py
if ($LASTEXITCODE -ne 0) { Write-Output 'PY COMPILE FAILED'; exit 1 } else { Write-Output 'py OK' }
$errs = $null; [System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path 'start_omr.ps1'), [ref]$null, [ref]$errs) | Out-Null
if ($errs.Count) { $errs | ForEach-Object { Write-Output ("PARSE ERROR " + $_.Message) }; exit 1 } else { Write-Output 'ps OK  start_omr.ps1' }
Write-Output '=== smoke 1: omr_service.py on 8444 with the real scanner ==='
$env:WS_PORT = '8444'; Remove-Item Env:WS_CERT, Env:WS_KEY -ErrorAction SilentlyContinue
$p = Start-Process -FilePath py -ArgumentList '-3.13', 'C:\Repos\gitlab\OMR\omr-service\omr_service.py' -WorkingDirectory 'C:\Repos\gitlab\OMR\omr-service' -WindowStyle Hidden -PassThru
Start-Sleep 8
Get-Content logs\omr_service.log -Tail 6
Get-NetTCPConnection -LocalPort 8444 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { "listening 8444 pid " + $_.OwningProcess }
Stop-Process -Id $p.Id -Force; Start-Sleep 2
Write-Output ("smoke1 process alive after kill: " + [bool](Get-Process -Id $p.Id -ErrorAction SilentlyContinue))
Write-Output '=== smoke 2: launcher on 8443 (port held by zombie -> expect rc=1 + retry) ==='
Remove-Item Env:WS_PORT -ErrorAction SilentlyContinue
$l = Start-Process -FilePath powershell.exe -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-File','C:\Repos\gitlab\OMR\omr-service\start_omr.ps1' -WindowStyle Hidden -PassThru
Start-Sleep 14
Write-Output '--- launcher.log'; Get-Content logs\launcher.log -Tail 4
Write-Output '--- stderr.log'; if (Test-Path logs\stderr.log) { Get-Content logs\stderr.log -Tail 3 }
Write-Output '--- omr_service.log'; Get-Content logs\omr_service.log -Tail 5
Stop-Process -Id $l.Id -Force -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*omr_service.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; "stopped service pid $($_.ProcessId)" }
Start-Sleep 1
Write-Output ("python procs now: " + ((Get-Process python -ErrorAction SilentlyContinue | ForEach-Object Id) -join ','))
