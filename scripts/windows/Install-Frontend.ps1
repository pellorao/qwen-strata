#Requires -Version 7
# One-time setup for the resident frontend: firewall rule, large-page right and logon task.
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

# Large pages need SeLockMemoryPrivilege for the task user; Windows adds it to tokens at the next logon.
$sid = ([Security.Principal.NTAccount]$TaskUser).Translate([Security.Principal.SecurityIdentifier]).Value
$rights = Join-Path $env:TEMP 'qwen-strata-rights'
secedit /export /cfg "$rights.inf" /areas USER_RIGHTS | Out-Null
if ($LASTEXITCODE) { throw 'secedit export failed' }
$line = Get-Content "$rights.inf" | Where-Object { $_ -match '^SeLockMemoryPrivilege\s*=' }
$LargePages = 'already granted'
# No match yields an empty collection, and an empty collection never satisfies -notmatch.
if (-not $line -or $line -notmatch "\*$sid(,|$)") {
    $granted = if ($line) { "$line,*$sid" } else { "SeLockMemoryPrivilege = *$sid" }
    @('[Unicode]', 'Unicode=yes', '[Version]', 'signature="$CHICAGO$"', 'Revision=1', '[Privilege Rights]', $granted) |
        Set-Content "$rights.new.inf" -Encoding Unicode
    secedit /configure /db "$rights.sdb" /cfg "$rights.new.inf" /areas USER_RIGHTS | Out-Null
    if ($LASTEXITCODE) { throw 'secedit configure failed' }
    $LargePages = 'granted; log off and on (or reboot) before it takes effect'
}
Remove-Item "$rights*" -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction -Execute $Python -Argument "-B `"$Entry`"" -WorkingDirectory $Root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $TaskUser
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -Priority 4
# Normal priority and the full token: the defaults (Below normal, limited token) slow model loading and strip
# SeLockMemoryPrivilege, so large pages would stay refused (Strata docs/DETAILS.md, Task Scheduler section).
$taskPrincipal = New-ScheduledTaskPrincipal -UserId $TaskUser -LogonType Interactive -RunLevel Highest
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Principal $taskPrincipal -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName

Write-Host "Firewall rule ${RuleName}: TCP $ListenAddress`:$Port from LocalSubnet"
Write-Host "Lock pages in memory for ${TaskUser}: $LargePages"
Write-Host "Task $TaskName registered for $TaskUser and started"
Read-Host 'Press Enter to close'
