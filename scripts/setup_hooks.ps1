# Install git pre-push hook for AI log submission (Windows PowerShell).
# Run once after cloning: powershell -ExecutionPolicy Bypass -File scripts\setup_hooks.ps1

$ErrorActionPreference = 'Stop'

$HookFile = '.git/hooks/pre-push'

# Git on Windows runs hooks via Git Bash, so the hook body must be bash.
$HookBody = @'
#!/usr/bin/env bash
# Pre-push: sweep recent Antigravity / Gemini prompts, then submit AI logs.
bash scripts/_pyrun.sh scripts/log_antigravity.py --auto || true
bash scripts/_pyrun.sh scripts/submit_log.py || true
exit 0
'@

# PowerShell 5.1's `Set-Content -Encoding UTF8` always prepends a BOM, which
# breaks the `#!/usr/bin/env bash` shebang (git fails with "cannot spawn
# .git/hooks/pre-push: No such file or directory"). Write via .NET with a
# BOM-less UTF8Encoding instead, and normalize to LF in case the here-string
# picked up CRLF from this file's own line endings on checkout.
$HookBodyLf = $HookBody -replace "`r`n", "`n"
$Utf8NoBom = New-Object System.Text.UTF8Encoding $false
$HookFileFullPath = Join-Path (Get-Location) $HookFile
[System.IO.File]::WriteAllText($HookFileFullPath, $HookBodyLf, $Utf8NoBom)

# Windows has no chmod, but git hooks still need the exec bit under Git Bash.
# A bare `bash` call can resolve to the WSL launcher stub in System32 or a
# WindowsApps execution alias instead of Git's own bash.exe (same class of
# footgun scripts/_pyrun.sh already works around for python.exe) — pick the
# first candidate that isn't one of those stubs, falling back to the default
# Git for Windows install path.
$GitBash = Get-Command bash -All -ErrorAction SilentlyContinue |
    Where-Object { $_.Source -notmatch 'WindowsApps' -and $_.Source -notmatch '\\System32\\' } |
    Select-Object -First 1 -ExpandProperty Source
if (-not $GitBash -and (Test-Path 'C:\Program Files\Git\bin\bash.exe')) {
    $GitBash = 'C:\Program Files\Git\bin\bash.exe'
}
if ($GitBash) {
    & $GitBash -c "chmod +x '$HookFile'"
} else {
    Write-Warning "[ai-log] Không tìm thấy Git Bash để chmod +x hook. Nếu push báo lỗi 'cannot spawn .git/hooks/pre-push', chạy 'bash scripts/setup_hooks.sh' thay thế."
}

Write-Host "[ai-log] Git pre-push hook installed."

if (-not (Test-Path .ai-log)) { New-Item -ItemType Directory -Path .ai-log | Out-Null }
if (-not (Test-Path .ai-log/.gitkeep)) { New-Item -ItemType File -Path .ai-log/.gitkeep | Out-Null }

Write-Host "[ai-log] Setup complete. Configure AI_LOG_SERVER in your .env file."
