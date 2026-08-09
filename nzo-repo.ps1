[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("check", "smoke", "add", "publish")]
    [string]$Command = "check",

    [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
    [string[]]$CommandArguments
)

$ErrorActionPreference = "Stop"
$scriptPath = Join-Path $PSScriptRoot "src\nzo_repo.py"
$python = Get-Command python -ErrorAction Stop

& $python.Source $scriptPath $Command @CommandArguments
exit $LASTEXITCODE
