<#
Simple helper script to guide Windows users to install ffmpeg.
Usage:
  - To show instructions only:
      .\install_ffmpeg.ps1
  - To perform Chocolatey install automatically (requires running as Administrator and Chocolatey installed):
      .\install_ffmpeg.ps1 -Install
#>
param(
    [switch]$Install
)

Write-Host "ffmpeg helper"
Write-Host "This script will show instructions to install ffmpeg."

if ($Install) {
    Write-Host "Install flag provided. Attempting to install via Chocolatey..."
    if (-not (Get-Command choco -ErrorAction SilentlyContinue)) {
        Write-Host "Chocolatey not found. Please install Chocolatey first: https://chocolatey.org/install"
        exit 1
    }
    # Confirm elevated privileges
    $isElevated = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $isElevated) {
        Write-Host "This operation requires Administrator privileges. Run an elevated PowerShell and try again."
        exit 1
    }
    choco install ffmpeg -y
    if ($LASTEXITCODE -eq 0) {
        Write-Host "ffmpeg installed. You may need to restart your terminal to pick up PATH changes."
    } else {
        Write-Host "Chocolatey install failed. See the output above for details."
    }
} else {
    Write-Host "Manual installation instructions:"
    Write-Host " - Download a static build from https://ffmpeg.org/download.html"
    Write-Host " - Unzip and add the folder containing ffmpeg.exe to your PATH"
    Write-Host " - Or run (admin) 'choco install ffmpeg' if you have Chocolatey"
}
