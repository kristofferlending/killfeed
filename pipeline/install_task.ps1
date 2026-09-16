# Oppretter planlagt oppgave "WARDOGS auto-clips" som kjorer run_daily.py hver natt kl. 04:00
# og 20 min etter paalogging. Kjor via 4-installer-nattjobb.cmd (eller: powershell -ExecutionPolicy Bypass -File install_task.ps1)
$here   = Split-Path -Parent $MyInvocation.MyCommand.Path
$py     = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { $py = (Get-Command py).Source }
$script = Join-Path $here "run_daily.py"
$user   = "$env:USERDOMAIN\$env:USERNAME"
$action = New-ScheduledTaskAction -Execute $py -Argument "`"$script`"" -WorkingDirectory $here
$t1 = New-ScheduledTaskTrigger -Daily -At 04:00
$t2 = New-ScheduledTaskTrigger -AtLogOn -User $user
$t2.Delay = "PT20M"
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 4) -MultipleInstances IgnoreNew
try {
  Register-ScheduledTask -TaskName "WARDOGS auto-clips" -Action $action -Trigger $t1,$t2 -Principal $principal -Settings $settings -Description "Klipper nye WARDOGS-backtracks og laster opp private shorts" -Force -ErrorAction Stop | Out-Null
  Write-Host "OK: oppgaven WARDOGS auto-clips er registrert for $user (04:00 daglig + 20 min etter paalogging)."
} catch {
  Write-Host "Register-ScheduledTask feilet: $($_.Exception.Message)"
  Write-Host "Prover schtasks.exe i stedet ..."
  $tr = "`"$py`" `"$script`""
  schtasks /Create /F /TN "WARDOGS auto-clips" /TR $tr /SC DAILY /ST 04:00 /RL LIMITED
  schtasks /Create /F /TN "WARDOGS auto-clips (paalogging)" /TR $tr /SC ONLOGON /DELAY 0020:00 /RL LIMITED
}
schtasks /Query /TN "WARDOGS auto-clips" 2>$null
