#Requires -Version 5.1
param(
  [Parameter(Mandatory = $true)]
  [string]$GoogleClientId,

  [Parameter(Mandatory = $true)]
  [string]$GoogleClientSecret,

  [string]$BackendsPath = "",

  [string]$TokenPath = ""
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
if (-not $BackendsPath) {
  $BackendsPath = Join-Path $root "gmail-backends.json"
}
if (-not $TokenPath) {
  $TokenPath = Join-Path $root "token.txt"
}
if (-not (Test-Path $BackendsPath)) {
  throw "Missing Gmail backends file: $BackendsPath"
}
if (-not $env:CLOUDFLARE_API_TOKEN) {
  if (-not (Test-Path $TokenPath)) {
    throw "Missing CLOUDFLARE_API_TOKEN and token file: $TokenPath"
  }
  $env:CLOUDFLARE_API_TOKEN = (Get-Content $TokenPath -Raw).Trim()
}
if (-not $env:NODE_OPTIONS) {
  $env:NODE_OPTIONS = "--use-system-ca"
}

function Push-Secret([string]$Name, [string]$Value) {
  $tmp = [System.IO.Path]::GetTempFileName()
  try {
    $utf8NoBom = [System.Text.UTF8Encoding]::new($false)
    [System.IO.File]::WriteAllText($tmp, $Value, $utf8NoBom)
    Get-Content $tmp -Raw | pnpm --filter "@tempgmail/api" exec wrangler secret put $Name
    if ($LASTEXITCODE -ne 0) {
      throw "Failed to upload secret $Name"
    }
  } finally {
    Remove-Item $tmp -Force -ErrorAction SilentlyContinue
  }
}

$backendsJson = Get-Content $BackendsPath -Raw
$parsed = $backendsJson | ConvertFrom-Json
if (-not $parsed -or @($parsed).Count -lt 1) {
  throw "No Gmail backends found in $BackendsPath"
}

Push-Location $root
try {
  Push-Secret "GOOGLE_CLIENT_ID" $GoogleClientId
  Push-Secret "GOOGLE_CLIENT_SECRET" $GoogleClientSecret
  Push-Secret "GMAIL_BACKENDS_JSON" $backendsJson
} finally {
  Pop-Location
}

Write-Host "Uploaded Gmail secrets for $(@($parsed).Count) backend(s)."
