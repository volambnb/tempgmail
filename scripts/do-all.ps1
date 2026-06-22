#Requires -Version 5.1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$tokenPath = Join-Path $Root "token.txt"
if (-not $env:CLOUDFLARE_API_TOKEN -and (Test-Path $tokenPath)) {
  $env:CLOUDFLARE_API_TOKEN = (Get-Content $tokenPath -Raw).Trim()
}
if (-not $env:CLOUDFLARE_API_TOKEN) {
  Write-Host "Thieu CLOUDFLARE_API_TOKEN hoac token.txt" -ForegroundColor Red
  exit 1
}
$env:WRANGLER_SEND_METRICS = "false"
if (-not $env:NODE_OPTIONS) { $env:NODE_OPTIONS = "--use-system-ca" }

$PagesProject = if ($env:PAGES_PROJECT_NAME) { $env:PAGES_PROJECT_NAME } else { "tempgmail" }
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
  if (-not (Test-Path node_modules)) {
    Write-Host "==> npm install"
    npm install
  }
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
  $apiDeploy = Invoke-Wrangler deploy 2>&1 | Out-String
  Write-Host $apiDeploy
  $apiUrl = $null
  if ($apiDeploy -match 'https://[a-zA-Z0-9.-]+\.workers\.dev') { $apiUrl = $Matches[0] }
  if (-not $apiUrl) { $apiUrl = "https://tempmail-api.workers.dev" }
  Pop-Location
  Write-Host "    API URL: $apiUrl"
  Write-Host "==> Deploy email-worker"
  Push-Location (Join-Path $Root "apps/email-worker")
  Invoke-Wrangler deploy
  Pop-Location
  Write-Host "==> Build web"
  $env:VITE_API_URL = $apiUrl
  if (-not $env:VITE_TURNSTILE_SITE_KEY) { $env:VITE_TURNSTILE_SITE_KEY = "" }
  npm run build -w @tempgmail/web
  Write-Host "==> Deploy Pages ($PagesProject)"
  Push-Location (Join-Path $Root "apps/web")
  $pagesOut = Invoke-Wrangler pages deploy dist --project-name=$PagesProject --commit-dirty=true 2>&1 | Out-String
  Write-Host $pagesOut
  $siteUrl = $null
  if ($pagesOut -match 'https://[a-zA-Z0-9.-]+\.pages\.dev[^\s]*') { $siteUrl = ($Matches[0] -replace '/+$','') }
  if (-not $siteUrl) { $siteUrl = "https://$PagesProject.pages.dev" }
  Pop-Location
  Write-Host ""
  Write-Host "========== LINK SITE ==========" -ForegroundColor Cyan
  Write-Host "  Web:  $siteUrl"
  Write-Host "  API:  $apiUrl/api/health"
  Write-Host "==============================" -ForegroundColor Cyan
  Write-Host "Tay: Email Routing catch-all -> tempmail-email. Xem DEPLOY-AZ.md"
} finally { Pop-Location }

