$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$checkOnly = $args -contains '-Check'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

try {
    $botPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $botPython)) {
        $basePython = $null
        if (Get-Command py -ErrorAction SilentlyContinue) {
            try { $basePython = (& py -3.12 -c 'import sys; print(sys.executable)' 2>$null) } catch { $basePython = $null }
        }
        if (-not $basePython -and (Get-Command python -ErrorAction SilentlyContinue)) {
            $basePython = (Get-Command python).Source
        }
        if (-not $basePython) { throw 'Install Python 3.12 from python.org and run start.cmd again.' }
        & $basePython -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Could not set up the Python environment.' }
    }

    & $botPython -c 'import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)'
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 or newer is required. Python 3.12 is recommended.' }
    $requirementsHash = (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'requirements.txt') -Algorithm SHA256).Hash
    $hashFile = Join-Path $PSScriptRoot '.venv\requirements.sha256'
    $savedHash = if (Test-Path -LiteralPath $hashFile) { (Get-Content -LiteralPath $hashFile -Raw).Trim() } else { '' }
    & $botPython -c 'import importlib.util, sys; sys.exit(0 if all(importlib.util.find_spec(m) for m in (''telegram'', ''PIL'', ''emoji'', ''rlottie_python'', ''imageio_ffmpeg'', ''dotenv'', ''httpx'')) else 1)'
    if ($LASTEXITCODE -ne 0 -or (-not $checkOnly -and $savedHash -ne $requirementsHash)) {
        Write-Host 'Installing or updating project dependencies...'
        & $botPython -m pip install --disable-pip-version-check -r requirements.txt
        if ($LASTEXITCODE -ne 0) { throw 'Could not install dependencies. Check your internet connection.' }
        Set-Content -LiteralPath $hashFile -Value $requirementsHash -Encoding ASCII
    }

    if ($checkOnly) {
        & $botPython -m emojigif.check
        exit $LASTEXITCODE
    }

    $botEnvFile = Join-Path $PSScriptRoot '.env'
    if (-not (Test-Path -LiteralPath $botEnvFile)) {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot '.env.example') -Destination $botEnvFile
    }
    $hasToken = Get-Content -LiteralPath $botEnvFile | Where-Object { $_ -match '^\s*BOT_TOKEN\s*=\s*\S+' }
    if (-not $hasToken -and -not $env:BOT_TOKEN) {
        Write-Host 'Open https://t.me/BotFather in Telegram, send /newbot, and copy the token.'
        $botSecret = Read-Host 'Paste the bot token (input is hidden)' -AsSecureString
        $botCredential = New-Object System.Management.Automation.PSCredential('bot', $botSecret)
        $botToken = $botCredential.GetNetworkCredential().Password.Trim()
        if ($botToken -notmatch '^\d+:[A-Za-z0-9_-]+$') { throw 'Invalid token format. Run start.cmd again.' }
        [System.IO.File]::WriteAllText($botEnvFile, "BOT_TOKEN=$botToken`n", (New-Object System.Text.UTF8Encoding($false)))
        $botToken = $null
        $botCredential = $null
        $botSecret = $null
    }
    Write-Host 'Starting the bot. Keep this window open. Press Ctrl+C to stop.'
    & $botPython main.py
    exit $LASTEXITCODE
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
