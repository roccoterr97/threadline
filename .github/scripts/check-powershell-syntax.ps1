# Fails when a PowerShell script has a syntax error. The script is only read,
# never run, so this is safe for an installer that changes the computer.
param(
    [Parameter(Mandatory = $true)]
    [string] $Path
)

$Tokens = $null
$Errors = $null
$null = [System.Management.Automation.Language.Parser]::ParseFile(
    (Resolve-Path $Path).Path, [ref] $Tokens, [ref] $Errors
)

foreach ($ParseError in $Errors) {
    Write-Host "${Path}:$($ParseError.Extent.StartLineNumber): $($ParseError.Message)"
}
if ($Errors.Count -gt 0) {
    exit 1
}
Write-Host "$Path has no syntax errors (PowerShell $($PSVersionTable.PSVersion))."
