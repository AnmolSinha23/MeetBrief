# Start Bifrost AI Gateway on Windows
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host " Starting Bifrost Gateway (http://localhost:8080)" -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan

if (-not (Get-Command npx -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: 'npx' command not found." -ForegroundColor Red
    Write-Host "Please install Node.js (v18+) from https://nodejs.org" -ForegroundColor Yellow
    exit 1
}

Write-Host "Running: npx -y @maximhq/bifrost" -ForegroundColor Green
Write-Host "Dashboard will be available at: http://localhost:8080" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop." -ForegroundColor Gray
npx -y @maximhq/bifrost
