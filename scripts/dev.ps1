param([switch]$Api,[switch]$Web)
if ($Api) { npm run dev:api }
elseif ($Web) { npm run dev:web }
else { Write-Host "Usage: .\scripts\dev.ps1 -Api | -Web" }
