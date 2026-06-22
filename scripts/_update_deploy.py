from pathlib import Path
root = Path(r"D:/codex/tempgmail")
do_all = r'''#Requires -Version 5.1
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
$PagesProject = if ($env:PAGES_PROJECT_NAME) { $env:PAGES_PROJECT_NAME } else { "tempgmail" }
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
  $d1Json = npx wrangler d1 create $dbName --json 2>$null
  if ($LASTEXITCODE -eq 0 -and $d1Json) { $dbId = ($d1Json | ConvertFrom-Json).uuid }
  if (-not $dbId) {
    $d1List = npx wrangler d1 list --json | ConvertFrom-Json
    $dbId = ($d1List | Where-Object { $_.name -eq $dbName }).uuid
  }
  if (-not $dbId) { throw "Khong tao/list duoc D1" }
  Write-Host "    database_id = $dbId"
  Write-Host "==> R2 $bucket"
  npx wrangler r2 bucket create $bucket 2>$null
  Write-Host "==> KV $kvTitle"
  $kvId = $null
  $kvOut = npx wrangler kv namespace create $kvTitle 2>&1 | Out-String
  if ($kvOut -match 'id = "([a-f0-9]+)"') { $kvId = $Matches[1] }
  if (-not $kvId) {
    $kvList = npx wrangler kv namespace list --json | ConvertFrom-Json
    $kvId = ($kvList | Where-Object { $_.title -eq $kvTitle }).id
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
  npx wrangler d1 migrations apply $dbName --remote
  foreach ($f in @("0001_init.sql","0002_auth_stripe.sql","0003_password.sql")) {
    $p = Join-Path $Root "migrations/$f"
    if (Test-Path $p) { npx wrangler d1 execute $dbName --remote --file=$p }
  }
  Pop-Location
  Write-Host "==> Deploy API"
  Push-Location (Join-Path $Root "apps/api")
  $apiDeploy = npx wrangler deploy 2>&1 | Out-String
  Write-Host $apiDeploy
  $apiUrl = $null
  if ($apiDeploy -match 'https://[a-zA-Z0-9.-]+\.workers\.dev') { $apiUrl = $Matches[0] }
  if (-not $apiUrl) { $apiUrl = "https://tempmail-api.workers.dev" }
  Pop-Location
  Write-Host "    API URL: $apiUrl"
  Write-Host "==> Deploy email-worker"
  Push-Location (Join-Path $Root "apps/email-worker")
  npx wrangler deploy
  Pop-Location
  Write-Host "==> Build web"
  $env:VITE_API_URL = $apiUrl
  if (-not $env:VITE_TURNSTILE_SITE_KEY) { $env:VITE_TURNSTILE_SITE_KEY = "" }
  npm run build -w @tempgmail/web
  Write-Host "==> Deploy Pages ($PagesProject)"
  Push-Location (Join-Path $Root "apps/web")
  $pagesOut = npx wrangler pages deploy dist --project-name=$PagesProject --commit-dirty=true 2>&1 | Out-String
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
'''
(root / "scripts/do-all.ps1").write_text(do_all, encoding="utf-8", newline="\n")
print("written")
