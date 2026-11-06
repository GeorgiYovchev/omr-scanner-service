# Compile-check, then start the callback-model service on a free port + a capture client.
Set-Location C:\Repos\gitlab\OMR\omr-service
py -3.13 -m py_compile omr_sdk.py omr_service.py genlot_map.py
if ($LASTEXITCODE -ne 0) { Write-Output "COMPILE FAILED"; exit 1 }
Write-Output "compile OK"
$env:WS_PORT = '8444'
$svc = Start-Process -FilePath py -ArgumentList '-3.13','omr_service.py' -WindowStyle Hidden -RedirectStandardOutput svc_cb.out -RedirectStandardError svc_cb.err -PassThru
Write-Output ("service pid " + $svc.Id)
Start-Sleep 5
Write-Output "--- svc_cb.out ---"; Get-Content svc_cb.out
Write-Output "--- svc_cb.err ---"; Get-Content svc_cb.err
$cli = Start-Process -FilePath py -ArgumentList '-3.13','wsclient.py','ws://127.0.0.1:8444','1800' -WindowStyle Hidden -RedirectStandardOutput wsclient_cb.out -RedirectStandardError wsclient_cb.err -PassThru
Write-Output ("client pid " + $cli.Id)
Start-Sleep 3
Write-Output "--- wsclient_cb.out ---"; Get-Content wsclient_cb.out
Write-Output "--- wsclient_cb.err ---"; Get-Content wsclient_cb.err
Write-Output "--- svc_cb.out (after client) ---"; Get-Content svc_cb.out
