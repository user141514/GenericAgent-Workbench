param(
    [string]$Python = "D:\anaconda0\python.exe",
    [switch]$SkipNpmAudit,
    [switch]$SkipReactBuild
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$reactDir = Join-Path $root "frontends\react_app"
$desktopPackageDir = Join-Path $root "packages\gagent-desktop"

function Invoke-Step {
    param(
        [string]$Name,
        [scriptblock]$Script
    )
    Write-Host ""
    Write-Host "==> $Name" -ForegroundColor Cyan
    & $Script
    Write-Host "OK: $Name" -ForegroundColor Green
}

if (-not (Test-Path $Python)) {
    throw "Python executable not found: $Python"
}

Push-Location $root
try {
    Invoke-Step "Python syntax check" {
        & $Python -m py_compile `
            "tools\security_scan.py" `
            "tools\performance_gate.py" `
            "tools\npm_pack_audit.py" `
            "core\api\app.py" `
            "core\quality\execution_honesty.py" `
            "core\quality\frontier_state.py" `
            "core\quality\research_workflow.py"
    }

    Invoke-Step "Electron main syntax check" {
        & node --check "packages\gagent-desktop\electron\main.cjs"
    }

    Invoke-Step "Release security tests" {
        & $Python -m pytest "tests\security\test_security_scan.py" -q
    }

    Invoke-Step "Release performance tests" {
        & $Python -m pytest "tests\performance\test_performance_gate.py" -q
    }

    Invoke-Step "React launch script tests" {
        & $Python -m pytest "tests\unit\test_react_launch_scripts.py" -q
    }

    Invoke-Step "Frontier state regression tests" {
        & $Python -m pytest "tests\unit\test_frontier_state.py" "tests\unit\test_frontier_bridge.py" -q
    }

    Invoke-Step "React API regression tests" {
        & $Python -m pytest "tests\unit\test_react_api.py" -q
    }

    Invoke-Step "Manifest safety scan" {
        & $Python "tools\security_scan.py" --manifest "frontends\react_app\package.json"
    }

    Invoke-Step "React unit tests" {
        & npm.cmd --prefix $reactDir run test
    }

    if (-not $SkipReactBuild) {
        Invoke-Step "React production build" {
            & npm.cmd --prefix $reactDir run build
        }

        Invoke-Step "React bundle budget" {
            & $Python "tools\performance_gate.py" --react-dist "frontends\react_app\dist"
        }

        Invoke-Step "Prepare gagent-desktop npm package" {
            & powershell -NoProfile -ExecutionPolicy Bypass -File "tools\prepare_gagent_desktop_package.ps1" -SkipReactBuild
        }

        Invoke-Step "gagent-desktop packaging tests" {
            & $Python -m pytest "tests\packaging\test_gagent_desktop_package.py" "tests\packaging\test_gagent_desktop_exe_package.py" -q
        }
    }

    if (-not $SkipNpmAudit) {
        Invoke-Step "npm audit high severity gate" {
            & npm.cmd --prefix $reactDir audit --audit-level=high
        }

        Invoke-Step "gagent-desktop npm audit high severity gate" {
            & npm.cmd --prefix $desktopPackageDir audit --audit-level=high
        }
    }

    Invoke-Step "gagent-desktop manifest safety scan" {
        & $Python "tools\security_scan.py" --manifest "packages\gagent-desktop\package.json" --scan "packages\gagent-desktop\backend"
    }

    Invoke-Step "gagent-desktop npm pack audit" {
        & $Python "tools\npm_pack_audit.py" --package-dir "packages\gagent-desktop"
    }

    Invoke-Step "gagent-desktop npm publish dry-run" {
        Push-Location $desktopPackageDir
        try {
            & npm.cmd publish --dry-run
        }
        finally {
            Pop-Location
        }
    }

    Write-Host ""
    Write-Host "Release gate passed." -ForegroundColor Green
}
finally {
    Pop-Location
}
