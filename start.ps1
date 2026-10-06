# Starts Job Desk: the API (port 8780) and the dashboard (port 5180), each in its own minimised
# window, then opens the dashboard. Close those windows to stop it.
# A server that's already running (from an earlier start, or one Claude started) is left alone:
# starting a second copy would only fail with "port already in use".
$root = $PSScriptRoot

function Test-Listening($port) {
    [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}

if (Test-Listening 8780) {
    Write-Host 'The API is already running on port 8780.'
} else {
    Start-Process powershell -WindowStyle Minimized -WorkingDirectory $root `
        -ArgumentList '-NoExit', '-Command', '$Host.UI.RawUI.WindowTitle = "Job Desk API"; python -m jobdesk serve --reload'
}
if (Test-Listening 5180) {
    Write-Host 'The dashboard is already running on port 5180.'
} else {
    Start-Process powershell -WindowStyle Minimized -WorkingDirectory (Join-Path $root 'web') `
        -ArgumentList '-NoExit', '-Command', '$Host.UI.RawUI.WindowTitle = "Job Desk dashboard"; npx vite'
}

# Open the dashboard once it answers (up to 20 seconds), not before.
foreach ($i in 1..40) {
    try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 1 'http://127.0.0.1:5180/' | Out-Null; break }
    catch { Start-Sleep -Milliseconds 500 }
}
Start-Process 'http://127.0.0.1:5180/'
