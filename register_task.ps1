# Registers PROMETHEUS as a Windows Scheduled Task that starts the always-on loop
# at logon and restarts it if it dies. Run this ONCE, in PowerShell, when you're ready
# to let PROMETHEUS live continuously:  powershell -ExecutionPolicy Bypass -File register_task.ps1
# Remove later with:  Unregister-ScheduledTask -TaskName "PROMETHEUS" -Confirm:$false

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$bat  = Join-Path $here "run_loop.bat"

$action  = New-ScheduledTaskAction -Execute $bat
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 5) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries

Register-ScheduledTask -TaskName "PROMETHEUS" -Action $action -Trigger $trigger `
    -Settings $settings -Description "PROMETHEUS always-on self-edit loop" -Force

Write-Host "Registered scheduled task 'PROMETHEUS' (runs $bat at logon)."
Write-Host "Start it now without logging out:  Start-ScheduledTask -TaskName PROMETHEUS"
