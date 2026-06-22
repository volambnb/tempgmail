#Requires -Version 5.1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$tokenPath = Join-Path $Root "token.txt"
if (-not $env:CLOUDFLARE_API_TOKEN) {
  if (-not (Test-Path $tokenPath)) {
    Write-Host "Thieu token.txt hoac CLOUDFLARE_API_TOKEN" -ForegroundColor Red
    exit 1
  }
  $env:CLOUDFLARE_API_TOKEN = (Get-Content $tokenPath -Raw).Trim()
}
if (-not $env:CLOUDFLARE_API_TOKEN) { exit 1 }
& (Join-Path $PSScriptRoot "bootstrap-cloudflare.ps1")
