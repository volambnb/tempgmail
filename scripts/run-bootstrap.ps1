$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$tf = Join-Path $Root "token.txt"
if (-not (Test-Path $tf)) { Write-Error "Thieu token.txt"; exit 1 }
$env:CLOUDFLARE_API_TOKEN = (Get-Content $tf -Raw).Trim()
$env:WRANGLER_SEND_METRICS = "false"
& (Join-Path $PSScriptRoot "bootstrap-cloudflare.ps1")
