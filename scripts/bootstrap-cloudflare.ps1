#Requires -Version 5.1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$tokenPath = Join-Path $Root "token.txt"
if (-not $env:CLOUDFLARE_API_TOKEN -and (Test-Path $tokenPath)) {
  $env:CLOUDFLARE_API_TOKEN = (Get-Content $tokenPath -Raw).Trim()
}
if (-not $env:CLOUDFLARE_API_TOKEN) {
  Write-Host "Thieu CLOUDFLARE_API_TOKEN hoac token.txt" -ForegroundColor Yellow
  exit 1
}
$env:WRANGLER_SEND_METRICS = "false"
if (-not $env:NODE_OPTIONS) { $env:NODE_OPTIONS = "--use-system-ca" }
function Invoke-Wrangler {
  $wrangler = Join-Path $Root "node_modules/.pnpm/node_modules/.bin/wrangler.CMD"
  $oldPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  if (Test-Path $wrangler) {
    & $wrangler @args
    $code = $LASTEXITCODE
    $ErrorActionPreference = $oldPreference
    if ($code -ne 0) { throw "wrangler failed: $($args -join ' ')" }
    return
  }
  pnpm --filter "@tempgmail/api" exec wrangler @args
  $code = $LASTEXITCODE
  $ErrorActionPreference = $oldPreference
  if ($code -ne 0) { throw "wrangler failed: $($args -join ' ')" }
}
function Invoke-WranglerAllowFailure {
  $wrangler = Join-Path $Root "node_modules/.pnpm/node_modules/.bin/wrangler.CMD"
  $oldPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  if (Test-Path $wrangler) {
    & $wrangler @args
  } else {
    pnpm --filter "@tempgmail/api" exec wrangler @args
  }
  $ErrorActionPreference = $oldPreference
}
Push-Location $Root
try {
  if (-not (Test-Path node_modules)) { npm install }
  $apiToml = Join-Path $Root "apps/api/wrangler.toml"
  $emailToml = Join-Path $Root "apps/email-worker/wrangler.toml"
  $dbName = "tempmail-db"
  $bucket = "tempmail-attachments"
  $kvTitle = "tempmail-rate-limit"
  Write-Host "==> D1 $dbName"
  $dbId = $null
  $d1List = Invoke-Wrangler d1 list --json | ConvertFrom-Json
  $dbId = ($d1List | Where-Object { $_.name -eq $dbName }).uuid
  if (-not $dbId) {
    Invoke-Wrangler d1 create $dbName
    $d1List = Invoke-Wrangler d1 list --json | ConvertFrom-Json
    $dbId = ($d1List | Where-Object { $_.name -eq $dbName }).uuid
  }
  if (-not $dbId) { throw "Khong tao/list duoc D1" }
  Write-Host "    database_id = $dbId"
  Write-Host "==> R2 $bucket"
  Invoke-WranglerAllowFailure r2 bucket create $bucket
  Write-Host "==> KV $kvTitle"
  $kvId = $null
  $kvOut = Invoke-WranglerAllowFailure kv namespace create $kvTitle 2>&1 | Out-String
  if ($kvOut -match 'id = "([a-f0-9]+)"') { $kvId = $Matches[1] }
  if (-not $kvId) {
    $kvList = Invoke-Wrangler kv namespace list | ConvertFrom-Json
    $kvId = ($kvList | Where-Object { $_.title -eq $kvTitle -or $_.title -eq "worker-$kvTitle" } | Select-Object -First 1).id
  }
  if (-not $kvId) { throw "Khong lay duoc KV id" }
  Write-Host "    kv id = $kvId"
  function Patch-Toml($path) {
    $t = Get-Content $path -Raw
    $t = $t -replace 'database_id = "local-tempmail-db"', "database_id = `"$dbId`""
    $t = $t -replace 'id = "local-rate-limit"', "id = `"$kvId`""
    Set-Content $path $t -Encoding utf8
  }
  Patch-Toml $apiToml
  Patch-Toml $emailToml
  Write-Host "==> D1 migrate"
  Push-Location (Join-Path $Root "apps/api")
  Invoke-Wrangler d1 migrations apply $dbName --remote
  Pop-Location
  Write-Host "==> Deploy API"
  Push-Location (Join-Path $Root "apps/api")
  Invoke-Wrangler deploy
  Pop-Location
  Write-Host "==> Deploy email-worker"
  Push-Location (Join-Path $Root "apps/email-worker")
  Invoke-Wrangler deploy
  Pop-Location
  Write-Host "Xong Worker. Tiep: DEPLOY-AZ.md (Email Routing, secrets, Pages)" -ForegroundColor Green
} finally { Pop-Location }
