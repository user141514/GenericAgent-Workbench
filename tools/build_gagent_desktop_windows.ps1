param(
    [string]$PythonVersion = "3.13.9",
    [switch]$SkipReactBuild,
    [switch]$SkipPythonRuntime,
    [switch]$SkipDependencyInstall,
    [switch]$DirOnly
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$packageDir = Join-Path $root "packages\gagent-desktop"

Push-Location $root
try {
    $prepareArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "tools\prepare_gagent_desktop_package.ps1")
    if ($SkipReactBuild) {
        $prepareArgs += "-SkipReactBuild"
    }
    & powershell @prepareArgs

    if (-not $SkipPythonRuntime) {
        $runtimeArgs = @(
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            "tools\prepare_gagent_desktop_windows_runtime.ps1",
            "-PythonVersion",
            $PythonVersion
        )
        if ($SkipDependencyInstall) {
            $runtimeArgs += "-SkipDependencyInstall"
        }
        & powershell @runtimeArgs
    }

    & npm.cmd --prefix $packageDir install --ignore-scripts
    if ($DirOnly) {
        & npm.cmd --prefix $packageDir run dist:dir
    }
    else {
        & npm.cmd --prefix $packageDir run dist:win
    }
}
finally {
    Pop-Location
}
