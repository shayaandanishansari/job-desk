# Builds JobDesk-<version>-windows.zip: the dashboard (web/dist), then JobDesk.exe and the folder
# it runs from, with PyInstaller. Needs Node and Python 3.12+.
# PyInstaller bundles whatever the code can import, so it runs from its own clean environment
# (.venv-build) rather than a Python that has other packages installed.
param([string]$Dist = (Join-Path (Split-Path $PSScriptRoot) 'dist'))
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot

Push-Location (Join-Path $root 'web')
try {
    if (-not (Test-Path node_modules)) { npm ci; if ($LASTEXITCODE) { throw 'npm ci failed' } }
    npm run build; if ($LASTEXITCODE) { throw 'Dashboard build failed' }
} finally { Pop-Location }

$venv = Join-Path $root '.venv-build'
$python = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path $python)) {
    python -m venv $venv; if ($LASTEXITCODE) { throw 'Could not create .venv-build' }
}
& $python -m pip install --quiet --upgrade "$root[build]"; if ($LASTEXITCODE) { throw 'pip install failed' }

& $python -m PyInstaller --noconfirm --clean --distpath $Dist --workpath (Join-Path $root 'build') `
    (Join-Path $PSScriptRoot 'jobdesk.spec')
if ($LASTEXITCODE) { throw 'PyInstaller failed' }

$version = (& (Join-Path $Dist 'JobDesk\JobDesk.exe') version).Trim()
$zip = Join-Path $Dist "JobDesk-$version-windows.zip"
Remove-Item $zip -ErrorAction SilentlyContinue
Compress-Archive -Path (Join-Path $Dist 'JobDesk') -DestinationPath $zip
Write-Host "Built $zip"
