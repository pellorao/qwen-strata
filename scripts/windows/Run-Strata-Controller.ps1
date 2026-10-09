$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSCommandPath
$python = Join-Path $root 'runtime\Strata\.venv\Scripts\python.exe'
$entry = Join-Path $root 'src\windows_host.py'
if (!(Test-Path -LiteralPath $python)) { throw 'The installed Windows Python environment is missing.' }
# Bootstrap only the controller. Loading a model requires an ownership key.
& $python -B $entry native-controller
if ($LASTEXITCODE -ne 0) { throw 'The native Windows controller failed to start.' }
