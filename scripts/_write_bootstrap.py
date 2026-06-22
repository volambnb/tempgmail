from pathlib import Path
root = Path(r"D:/codex/tempgmail")
scripts = root / "scripts"
scripts.mkdir(exist_ok=True)
bootstrap = scripts / "bootstrap-cloudflare.ps1"
content = r'''#Requires -Version 5.1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not $env:CLOUDFLARE_API_TOKEN) {
  Write-Host "Dat token tren may ban (KHONG gui chat):" -ForegroundColor Yellow
  Write-Host '  $env:CLOUDFLARE_API_TOKEN = "..."' -ForegroundColor Cyan
  exit 1
}
$env:WRANGLER_SEND_METRICS = "false"
Push-Location $Root
try {
  if (-not (Test-Path node_modules)) { npm install }
  $apiToml = Join-Path $Root "apps/api/wrangler.toml"
  $emailToml = Join-Path $Root "apps/email-worker/wrangler.toml"
  $dbName = "tempmail-db"
  $bucket = "tempmail-attachments"
  $kvTitle = "tempmail-rate-limit"
  Write-Host "==> D1 $dbName"
  $d1Json = npx wrangler d1 create $dbName --json 2>$null
  if ($LASTEXITCODE -ne 0) {
    $d1List = npx wrangler d1 list --json | ConvertFrom-Json
    $dbId = ($d1List | Where-Object { $_.name -eq $dbName }).uuid
    if (-not $dbId) { throw "Khong tao/list duoc D1" }
  } else {
    $dbId = ($d1Json | ConvertFrom-Json).uuid
  }
  Write-Host "    database_id = $dbId"
  Write-Host "==> R2 $bucket"
  npx wrangler r2 bucket create $bucket 2>$null
  Write-Host "==> KV $kvTitle"
  $kvOut = npx wrangler kv namespace create $kvTitle 2>&1 | Out-String
  if ($kvOut -match "id = `"([a-f0-9]+)`"") { $kvId = $Matches[1] }
  else {
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
  foreach ($f in @("0002_auth_stripe.sql","0003_password.sql")) {
    $p = Join-Path $Root "migrations/$f"
    if (Test-Path $p) { Get-Content $p -Raw | npx wrangler d1 execute $dbName --remote --file=- }
  }
  Pop-Location
  Write-Host "==> Deploy API"
  Push-Location (Join-Path $Root "apps/api")
  npx wrangler deploy
  Pop-Location
  Write-Host "==> Deploy email-worker"
  Push-Location (Join-Path $Root "apps/email-worker")
  npx wrangler deploy
  Pop-Location
  Write-Host "==> Secrets (Enter de bo qua tung secret)"
  Push-Location (Join-Path $Root "apps/api")
  foreach ($s in @("TURNSTILE_SECRET","GOOGLE_CLIENT_ID","GOOGLE_CLIENT_SECRET","BETTER_AUTH_SECRET","STRIPE_SECRET_KEY","STRIPE_WEBHOOK_SECRET","GMAIL_BACKENDS_JSON","OPERATOR_GMAIL")) {
    $v = Read-Host "Secret $s"
    if ($v) { $v | npx wrangler secret put $s }
  }
  Pop-Location
  Write-Host "Xong phan Worker. Tiep theo: Email Routing + Pages (xem DEPLOY-AZ.md)" -ForegroundColor Green
} finally { Pop-Location }
'''
bootstrap.write_text(content, encoding="utf-8")
deploy_az = root / "DEPLOY-AZ.md"
deploy_az.write_text("""# Deploy A-Z (TempGmail)

## 1. Token tren may ban (khong gui chat)

PowerShell:

```powershell
$env:CLOUDFLARE_API_TOKEN = "YOUR_TOKEN"
```

Tao token: Cloudflare Dashboard -> My Profile -> API Tokens -> **Edit Cloudflare Workers** (+ D1, R2, KV, Account Settings).

## 2. Chay bootstrap

```powershell
cd D:\\codex\\tempgmail
.\\scripts\\bootstrap-cloudflare.ps1
```

Script se: `npm install`, tao D1/R2/KV, patch `wrangler.toml`, migrate D1, deploy `tempmail-api` + `tempmail-email`, nhac nhap secrets.

## 3. Vars trong wrangler (sua tay neu can)

`apps/api/wrangler.toml` -> `[vars]`:

- `DEFAULT_DOMAIN` = `oegmail.store`
- `SYSTEM_DOMAIN` = `oegmail.store`

## 4. Email Routing (Dashboard)

Zone **oegmail.store** -> Email -> Routing -> Catch-all -> Send to Worker **tempmail-email**.

## 5. Web (Cloudflare Pages)

```powershell
cd D:\\codex\\tempgmail
npm run build -w @tempgmail/web
npx wrangler pages project create tempgmail-web
# Build output: apps/web/dist
# Env: VITE_API_URL = https://tempmail-api.<account>.workers.dev
```

Deploy Pages: upload `apps/web/dist` hoac ket noi Git.

## 6. Gmail / Stripe / Turnstile

- Google OAuth redirect: `https://<api-worker>/api/auth/callback/google`
- Stripe webhook: `https://<api-worker>/api/stripe/webhook`
- Turnstile site key -> `apps/web` env `VITE_TURNSTILE_SITE_KEY`

## 7. Kiem tra

```powershell
curl https://tempmail-api.<subdomain>.workers.dev/api/me
```
""", encoding="utf-8")
print("written")
