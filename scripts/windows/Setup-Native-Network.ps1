$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$config = Get-Content -LiteralPath (Join-Path $root 'config\service.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($config.transport -ne 'ssh-windows') { throw 'This operation is for the configured Windows LAN installation.' }
$address = $config.listen_address
$adapter = @(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -eq $address })
if ($adapter.Count -ne 1 -or $config.allowed_clients.Count -eq 0) { throw 'A specific local LAN address and client list are required.' }
$python = Join-Path $root 'runtime\Strata\.venv\Scripts\python.exe'
$program = (& $python -B -c 'import psutil; print(psutil.Process().exe())').Trim()
if ($LASTEXITCODE -ne 0) { throw 'Installed Python identity could not be resolved.' }
$name = 'QwenStrata-Native-' + $config.listen_port
$description = 'Qwen Strata native API; installation=' + $root
$existing = @(Get-NetFirewallRule -Name $name -ErrorAction SilentlyContinue)
if ($existing.Count -gt 0) {
    if ($existing.Count -ne 1 -or $existing[0].Description -ne $description) { throw 'Existing firewall rule belongs to another installation.' }
    $existing | Remove-NetFirewallRule
}
New-NetFirewallRule -Name $name -DisplayName 'Qwen Strata native API' -Description $description -Enabled True -Direction Inbound -Action Allow -Protocol TCP -LocalPort $config.listen_port -LocalAddress $address -RemoteAddress $config.allowed_clients -Program $program -InterfaceAlias $adapter[0].InterfaceAlias -Profile Any | Out-Null
Write-Output (@{configured=$true;listen_port=$config.listen_port;private_model_port_exposed=$false} | ConvertTo-Json -Compress)
