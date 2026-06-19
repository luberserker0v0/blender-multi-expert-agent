param(
    [switch]$InstallLocalLlm
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$venvPath = Join-Path $repoRoot ".venv"
$pythonExe = Join-Path $venvPath "Scripts\python.exe"
$activateScript = Join-Path $venvPath "Scripts\Activate.ps1"

if (-not (Test-Path $venvPath)) {
    Write-Host "Creating virtual environment at $venvPath"
    python -m venv $venvPath
}
else {
    Write-Host "Virtual environment already exists at $venvPath"
}

Write-Host "Upgrading pip"
& $pythonExe -m pip install --upgrade pip

Write-Host "Installing project in editable mode"
& $pythonExe -m pip install -e $repoRoot

if ($InstallLocalLlm) {
    Write-Host "Installing optional local-llm dependencies"
    & $pythonExe -m pip install -e "$repoRoot[local-llm]"
}

Write-Host ""
Write-Host "Done."
Write-Host "Activate with:"
Write-Host "  $activateScript"
