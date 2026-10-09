param([Parameter(Mandatory=$true)][string]$HostAddress)
$ErrorActionPreference = 'Stop'
$installRoot = Split-Path -Parent $PSScriptRoot
$adapter = @(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -eq $HostAddress -and $_.InterfaceAlias -like '*WSL*' })
if ($adapter.Count -ne 1) { throw 'The address must belong to one Windows WSL virtual adapter.' }
$principal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    # UAC grants only this fixed firewall operation; model and Codex stay unelevated.
    $arguments = @('-NoProfile', '-File', ('"' + $PSCommandPath + '"'), '-HostAddress', $HostAddress)
    $process = Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList $arguments -Wait -PassThru
    exit $process.ExitCode
}
$python = Join-Path $installRoot 'runtime\Strata\.venv\Scripts\python.exe'
$program = (& $python -B -c 'import psutil; print(psutil.Process().exe())').Trim()
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $program)) { throw 'Cannot identify the installed Python executable.' }
$name = 'QwenStrata-WSL-API'
$description = 'Qwen Strata WSL APIs; installation=' + $installRoot
$existing = @(Get-NetFirewallRule -Name $name -ErrorAction SilentlyContinue)
if ($existing.Count -gt 0) {
    if ($existing.Count -ne 1 -or $existing[0].Description -ne $description) { throw 'Existing firewall rule is not owned by this installation.' }
    $existing | Remove-NetFirewallRule
}
New-NetFirewallRule -Name $name -DisplayName 'Qwen Strata APIs from WSL' -Description $description -Enabled True -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8100,8101 -Program $program -InterfaceAlias $adapter[0].InterfaceAlias -RemoteAddress LocalSubnet -Profile Any | Out-Null
Write-Host 'Allowed TCP 8100/8101 for the installed Python only on the WSL virtual adapter. NAT, forwarding and firewall defaults are unchanged.'
