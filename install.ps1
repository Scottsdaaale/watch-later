# One-time install for watch-later on Windows. Run from this folder in PowerShell:
#   powershell -ExecutionPolicy Bypass -File .\install.ps1                  # install + schedule nightly at 02:30
#   powershell -ExecutionPolicy Bypass -File .\install.ps1 -NoSchedule      # install only
#   powershell -ExecutionPolicy Bypass -File .\install.ps1 -Time "03:00"    # different run time
#   powershell -ExecutionPolicy Bypass -File .\install.ps1 -Uninstall       # remove the nightly task
#
# What it does:
#   1. creates a Python venv here and installs yt-dlp, faster-whisper, todoist-api-python (+ CUDA libs)
#   2. runs `watch_later.py --check` (changes nothing)
#   3. registers a Task Scheduler task "Watch Later review" that runs nightly while you're logged in,
#      and catches up at the next opportunity if the PC was off.
# Secrets are not handled here: put them in .env yourself (see .env.example and SETUP.md).
param(
    [string]$Time = "02:30",
    [switch]$NoSchedule,
    [switch]$Uninstall
)
$ErrorActionPreference = "Stop"
$Here = $PSScriptRoot
$TaskName = "Watch Later review"

if ($Uninstall) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Removed the scheduled task. The folder, venv and config are left in place."
    exit 0
}

# 1. Python environment ------------------------------------------------------------
# faster-whisper's dependencies (ctranslate2, PyAV, onnxruntime) lag new Python releases, so use the
# newest installed 3.10-3.13 through the py launcher rather than whatever is newest.
# (Probing with `py -3.13 -c pass` doesn't work here: under ErrorActionPreference=Stop, Windows
# PowerShell turns the launcher's "No suitable Python runtime" stderr into a terminating error.)
$pyArgs = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    $installed = (& py -0p) -join "`n"
    foreach ($v in "3.13", "3.12", "3.11", "3.10") {
        if ($installed -match "-V:$([regex]::Escape($v))\b") { $pyArgs = @("-$v"); $pyExe = "py"; break }
    }
}
if (-not $pyArgs) {
    $pyExe = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $pyExe) { throw "Python 3.10-3.13 isn't installed. Install it from python.org (tick 'Add python.exe to PATH') and re-run." }
    $pyArgs = @()
}
if (-not (Test-Path "$Here\.venv")) {
    Write-Host "Creating venv with $pyExe $pyArgs..."
    & $pyExe @pyArgs -m venv "$Here\.venv"
}
$VenvPy = "$Here\.venv\Scripts\python.exe"
& $VenvPy -m pip install --quiet --upgrade pip
Write-Host "Installing yt-dlp, faster-whisper, todoist-api-python..."
& $VenvPy -m pip install --quiet --upgrade -r "$Here\requirements.txt"
# CUDA 12 runtime libraries for the GPU path. If these fail, transcription falls back to CPU.
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    Write-Host "NVIDIA GPU found; installing CUDA libraries for faster transcription..."
    & $VenvPy -m pip install --quiet nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*"
    if ($LASTEXITCODE -ne 0) { Write-Warning "CUDA libraries didn't install; transcription will use the CPU." }
}

if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    Write-Warning "The 'claude' command (Claude Code) isn't on PATH. Install it and sign in once by running 'claude'."
}

# 2. Quick check ----------------------------------------------------------------------
Write-Host "Checking libraries, GPU, Claude Code and your save source (changes nothing)..."
& $VenvPy "$Here\watch_later.py" --check
if ($LASTEXITCODE -ne 0) { throw "Check failed; fix the message above and re-run." }

# 3. Scheduled task -------------------------------------------------------------------
if ($NoSchedule) {
    Write-Host "Installed. Not scheduled (-NoSchedule). Re-run without it to schedule the nightly review."
    exit 0
}
$action = New-ScheduledTaskAction -Execute $VenvPy -Argument "`"$Here\watch_later.py`"" -WorkingDirectory $Here
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Principal $principal -Description "watch-later: reviews the videos you saved for later ($Here)." -Force | Out-Null
Write-Host "Scheduled '$TaskName' daily at $Time (runs while you're logged in; catches up if missed)."
Write-Host "Run it now:  Start-ScheduledTask -TaskName '$TaskName'   or   .\.venv\Scripts\python.exe watch_later.py"
