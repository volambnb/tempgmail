#Requires -Version 5.1
param(
  [Parameter(Mandatory = $true)]
  [string]$ClientId,

  [Parameter(Mandatory = $true)]
  [string]$ClientSecret,

  [Parameter(Mandatory = $true)]
  [string]$Email,

  [string]$BackendsPath = "",

  [int]$Port = 8789
)

$ErrorActionPreference = "Stop"

if (-not $BackendsPath) {
  $BackendsPath = Join-Path (Split-Path -Parent $PSScriptRoot) "gmail-backends.json"
}

function ConvertTo-CanonicalGmail([string]$Address) {
  $normalized = $Address.Trim().ToLowerInvariant()
  if (-not $normalized.EndsWith("@gmail.com")) {
    throw "Only @gmail.com backends are supported by the Gmail alias generator."
  }
  $parts = $normalized.Split("@", 2)
  $local = $parts[0].Replace(".", "")
  if ($local.Contains("+")) {
    $local = $local.Split("+", 2)[0]
  }
  return "$local@gmail.com"
}

$canonicalEmail = ConvertTo-CanonicalGmail $Email
$redirectUri = "http://127.0.0.1:$Port/callback"
$scope = "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send"
$state = [Guid]::NewGuid().ToString("N")

$query = [System.Web.HttpUtility]::ParseQueryString("")
$query["client_id"] = $ClientId
$query["redirect_uri"] = $redirectUri
$query["response_type"] = "code"
$query["scope"] = $scope
$query["access_type"] = "offline"
$query["prompt"] = "consent"
$query["state"] = $state
$query["login_hint"] = $canonicalEmail
$authUrl = "https://accounts.google.com/o/oauth2/v2/auth?$($query.ToString())"

$listener = [System.Net.HttpListener]::new()
$listener.Prefixes.Add("http://127.0.0.1:$Port/")
$listener.Start()

Write-Host "Opening Google OAuth browser for $canonicalEmail"
Write-Host "If the browser does not open, paste this URL manually:"
Write-Host $authUrl
Start-Process $authUrl

try {
  $context = $listener.GetContext()
  $request = $context.Request
  $response = $context.Response

  $html = "<html><body><h2>TempGmail Gmail backend connected.</h2><p>You can close this tab.</p></body></html>"
  $bytes = [System.Text.Encoding]::UTF8.GetBytes($html)
  $response.ContentType = "text/html; charset=utf-8"
  $response.ContentLength64 = $bytes.Length
  $response.OutputStream.Write($bytes, 0, $bytes.Length)
  $response.Close()

  if ($request.QueryString["state"] -ne $state) {
    throw "OAuth state mismatch."
  }
  $code = $request.QueryString["code"]
  if (-not $code) {
    throw "Google did not return an authorization code: $($request.Url.Query)"
  }
} finally {
  $listener.Stop()
}

$tokenBody = @{
  client_id = $ClientId
  client_secret = $ClientSecret
  code = $code
  grant_type = "authorization_code"
  redirect_uri = $redirectUri
}

$token = Invoke-RestMethod `
  -Method Post `
  -Uri "https://oauth2.googleapis.com/token" `
  -ContentType "application/x-www-form-urlencoded" `
  -Body $tokenBody

if (-not $token.refresh_token) {
  throw "Google did not return refresh_token. Re-run and make sure prompt=consent appears, or remove this app from Google Account access and try again."
}

$items = @()
if (Test-Path $BackendsPath) {
  $existing = Get-Content $BackendsPath -Raw
  if ($existing.Trim()) {
    $items = @($existing | ConvertFrom-Json)
  }
}

$items = @($items | Where-Object { $_.email -ne $canonicalEmail })
$items += [pscustomobject]@{
  email = $canonicalEmail
  refreshToken = [string]$token.refresh_token
}

$json = $items | ConvertTo-Json -Depth 5
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText($BackendsPath, $json, $utf8NoBom)

Write-Host "Saved Gmail backend: $canonicalEmail"
Write-Host "Backends file: $BackendsPath"
Write-Host "Next: run scripts\push-gmail-secrets.ps1 to upload this to Cloudflare."
