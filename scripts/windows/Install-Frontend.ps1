#Requires -Version 7
# One-time setup for the resident frontend: firewall rule and logon task.
# Deployed to <installation>\maintenance\; run once as the installation user (asks for UAC).
param([string]$TaskUser)

$TaskName = 'QwenStrataFrontend'
$RuleName = 'QwenStrata-Frontend'
$RetiredRules = @('QwenStrata-WSL-API', 'QwenStrata-Native-8000')

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root 'runtime\Strata\.venv\Scripts\pythonw.exe'
$Entry = Join-Path $Root 'src\frontend.py'
$Config = Join-Path $Root 'config\frontend.json'

$principal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    # The task must belong to the calling user, so pass that identity to the elevated copy.
    $user = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    Start-Process pwsh.exe -Verb RunAs -Wait -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $PSCommandPath, '-TaskUser', $user)
    exit
}
if (-not $TaskUser) { throw 'Run without elevation; the script elevates itself.' }

foreach ($path in @($Python, $Entry, $Config)) {
    if (-not (Test-Path $path)) { throw "Missing $path; deploy the installation first." }
}
$frontend = Get-Content $Config -Raw | ConvertFrom-Json
$ListenAddress, $Port = $frontend.listen_address, $frontend.port

foreach ($name in $RetiredRules + $RuleName) {
    Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue | Remove-NetFirewallRule
}
New-NetFirewallRule -DisplayName $RuleName -Direction Inbound -Action Allow -Protocol TCP `
    -LocalAddress $ListenAddress -LocalPort $Port -RemoteAddress LocalSubnet -Profile Any | Out-Null

$action = New-ScheduledTaskAction -Execute $Python -Argument "-B `"$Entry`"" -WorkingDirectory $Root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $TaskUser
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$taskPrincipal = New-ScheduledTaskPrincipal -UserId $TaskUser -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Principal $taskPrincipal -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName

Write-Host "Firewall rule ${RuleName}: TCP $ListenAddress`:$Port from LocalSubnet"
Write-Host "Task $TaskName registered for $TaskUser and started"
Read-Host 'Press Enter to close'
