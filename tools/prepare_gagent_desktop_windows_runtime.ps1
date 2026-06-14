param(
    [string]$PythonVersion = "3.13.9",
    [ValidateSet("amd64", "win32", "arm64")]
    [string]$Architecture = "amd64",
    [string]$PipIndexUrl = "",
    [switch]$Force,
    [switch]$SkipDependencyInstall
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$packageDir = Join-Path $root "packages\gagent-desktop"
$backendDir = Join-Path $packageDir "backend"
$runtimeDir = Join-Path $packageDir "python-runtime"
$cacheDir = Join-Path $root ".cache\gagent-desktop"
$pythonZip = Join-Path $cacheDir "python-$PythonVersion-embed-$Architecture.zip"
$getPip = Join-Path $cacheDir "get-pip.py"

function Download-File {
    param(
        [string]$Url,
        [string]$Destination
    )
    if (Test-Path $Destination) {
        return
    }
    Write-Host "Downloading $Url" -ForegroundColor Cyan
    Invoke-WebRequest -Uri $Url -OutFile $Destination
}

function Invoke-Native {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$Label
    )
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE"
    }
}

if (-not $PipIndexUrl) {
    $PipIndexUrl = if ($env:PIP_INDEX_URL) { $env:PIP_INDEX_URL } else { "https://pypi.tuna.tsinghua.edu.cn/simple" }
}

$desktopRequirements = Join-Path $backendDir "requirements-desktop.txt"
$fullRequirements = Join-Path $backendDir "requirements.txt"
$requirementsFile = if (Test-Path $desktopRequirements) { $desktopRequirements } else { $fullRequirements }

if (-not (Test-Path $requirementsFile)) {
    throw "Packaged backend is missing. Run tools\prepare_gagent_desktop_package.ps1 first."
}

if ($Force -and (Test-Path $runtimeDir)) {
    Remove-Item -LiteralPath $runtimeDir -Recurse -Force
}

New-Item -ItemType Directory -Force -Path $cacheDir | Out-Null
New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null

$pythonUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-$Architecture.zip"
Download-File -Url $pythonUrl -Destination $pythonZip

if (-not (Test-Path (Join-Path $runtimeDir "python.exe"))) {
    Write-Host "Extracting embedded Python runtime" -ForegroundColor Cyan
    Expand-Archive -LiteralPath $pythonZip -DestinationPath $runtimeDir -Force
}

$pthFile = Get-ChildItem -Path $runtimeDir -Filter "python*._pth" | Select-Object -First 1
if (-not $pthFile) {
    throw "Embedded Python ._pth file was not found in $runtimeDir"
}

$pthLines = Get-Content -LiteralPath $pthFile.FullName
$pthLines = $pthLines | ForEach-Object {
    if ($_.Trim() -eq "#import site") { "import site" } else { $_ }
}
if (-not ($pthLines -contains "Lib\site-packages")) {
    $pthLines += "Lib\site-packages"
}
if (-not ($pthLines -contains "..\backend")) {
    $pthLines += "..\backend"
}
Set-Content -LiteralPath $pthFile.FullName -Value $pthLines -Encoding ASCII

$pythonExe = Join-Path $runtimeDir "python.exe"
if (-not (Test-Path $pythonExe)) {
    throw "Embedded python.exe was not created: $pythonExe"
}

if (-not $SkipDependencyInstall) {
    Download-File -Url "https://bootstrap.pypa.io/get-pip.py" -Destination $getPip
    Write-Host "Installing pip into embedded Python" -ForegroundColor Cyan
    Invoke-Native -FilePath $pythonExe -Arguments @($getPip, "--index-url", $PipIndexUrl) -Label "get-pip"
    Write-Host "Installing backend requirements into embedded Python" -ForegroundColor Cyan
    Invoke-Native -FilePath $pythonExe -Arguments @("-m", "pip", "install", "--upgrade", "pip", "--index-url", $PipIndexUrl) -Label "pip upgrade"
    Invoke-Native -FilePath $pythonExe -Arguments @("-m", "pip", "install", "-r", $requirementsFile, "--index-url", $PipIndexUrl) -Label "pip install backend requirements"
}

Write-Host "Prepared embedded Python runtime: $runtimeDir" -ForegroundColor Green
