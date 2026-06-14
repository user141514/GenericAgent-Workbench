param(
    [switch]$SkipReactBuild
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$reactDir = Join-Path $root "frontends\react_app"
$reactDist = Join-Path $reactDir "dist"
$packageDir = Join-Path $root "packages\gagent-desktop"
$packageDist = Join-Path $packageDir "dist"
$packageBackend = Join-Path $packageDir "backend"

function Invoke-Robocopy {
    param(
        [string]$Source,
        [string]$Destination,
        [string[]]$Options
    )
    & robocopy $Source $Destination @Options | Out-Host
    if ($LASTEXITCODE -gt 7) {
        throw "robocopy failed from $Source to $Destination with exit code $LASTEXITCODE"
    }
}

Push-Location $root
try {
    if (-not $SkipReactBuild) {
        Write-Host "==> Building React UI" -ForegroundColor Cyan
        & npm.cmd --prefix $reactDir run build
    }

    if (-not (Test-Path (Join-Path $reactDist "index.html"))) {
        throw "React dist is missing: $reactDist"
    }

    if (Test-Path $packageDist) {
        Remove-Item -LiteralPath $packageDist -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $packageDist | Out-Null
    Copy-Item -Path (Join-Path $reactDist "*") -Destination $packageDist -Recurse -Force

    Write-Host "Prepared package dist: $packageDist" -ForegroundColor Green

    Write-Host "==> Preparing sanitized backend snapshot" -ForegroundColor Cyan
    if (Test-Path $packageBackend) {
        Remove-Item -LiteralPath $packageBackend -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $packageBackend | Out-Null

    Invoke-Robocopy (Join-Path $root "core") (Join-Path $packageBackend "core") @(
        "/E", "/XD", "__pycache__", "graphify-out", "/XF", "*.pyc", "*.pyo"
    )
    $frontendDest = Join-Path $packageBackend "frontends"
    New-Item -ItemType Directory -Force -Path $frontendDest | Out-Null
    foreach ($file in @("chatapp_common.py", "file_processor.py")) {
        Copy-Item -LiteralPath (Join-Path $root "frontends\$file") -Destination (Join-Path $frontendDest $file) -Force
    }
    Invoke-Robocopy (Join-Path $root "frontends\services") (Join-Path $frontendDest "services") @(
        "/E", "/XD", "__pycache__", "/XF", "*.pyc", "*.pyo"
    )

    $assetsDest = Join-Path $packageBackend "assets"
    New-Item -ItemType Directory -Force -Path $assetsDest | Out-Null
    foreach ($file in @(
        "code_run_header.py",
        "global_mem_insight_template.txt",
        "global_mem_insight_template_en.txt",
        "insight_fixed_structure.txt",
        "insight_fixed_structure_en.txt",
        "sys_prompt.txt",
        "sys_prompt_en.txt",
        "tools_schema.json",
        "tools_schema_cn.json",
        "tool_usable_history.json"
    )) {
        Copy-Item -LiteralPath (Join-Path $root "assets\$file") -Destination (Join-Path $assetsDest $file) -Force
    }
    Invoke-Robocopy (Join-Path $root "assets\icons") (Join-Path $assetsDest "icons") @(
        "/E", "/XD", "__pycache__", "/XF", "*.pyc", "*.pyo"
    )

    $memoryDest = Join-Path $packageBackend "memory"
    New-Item -ItemType Directory -Force -Path $memoryDest | Out-Null
    Get-ChildItem -Path (Join-Path $root "memory") -Recurse -File |
        Where-Object {
            ($_.Extension -in @(".md", ".txt")) -and
            ($_.FullName -notmatch "\\L4_raw_sessions\\|\\graphify-out\\|__pycache__") -and
            ($_.Name -notin @("history_memory_inbox.md", "history_memory_inbox.md.bak", "global_mem.txt", "global_mem_insight.txt"))
        } |
        ForEach-Object {
            $relative = $_.FullName.Substring((Join-Path $root "memory").Length).TrimStart("\", "/")
            $target = Join-Path $memoryDest $relative
            New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
            Copy-Item -LiteralPath $_.FullName -Destination $target -Force
        }
    Copy-Item -LiteralPath (Join-Path $root "memory\__init__.py") -Destination (Join-Path $memoryDest "__init__.py") -Force

    foreach ($file in @("agentmain.py", "openai_agentmain.py", "pyproject.toml", "requirements.txt", "README.md", "LICENSE", "mykey_template.py")) {
        $source = Join-Path $root $file
        if (Test-Path $source) {
            Copy-Item -LiteralPath $source -Destination (Join-Path $packageBackend $file) -Force
        }
    }

    @(
        "# Desktop backend runtime requirements",
        "# Keep this list focused; the full repository requirements include legacy UI/bot/vision stacks.",
        "beautifulsoup4",
        "fastapi",
        "markdown",
        "numpy",
        "openai",
        "Pillow",
        "PyMuPDF",
        "pyperclip",
        "python-docx",
        "python-dotenv>=1.0",
        "pywin32; platform_system == `"Windows`"",
        "requests",
        "urllib3",
        "uvicorn"
    ) | Set-Content -LiteralPath (Join-Path $packageBackend "requirements-desktop.txt") -Encoding UTF8

    Write-Host "Prepared package backend: $packageBackend" -ForegroundColor Green
}
finally {
    Pop-Location
}
