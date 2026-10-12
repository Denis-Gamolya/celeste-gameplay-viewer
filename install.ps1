<#
.SYNOPSIS
Install the standalone Celeste gameplay viewer for Codex on Windows.
.DESCRIPTION
Installs Python dependencies from PyPI, extracts preview frames from the
user's Celeste installation, verifies read-only MCP responses, and registers
only the viewer MCP server. It does not install or embed an editing server.
#>
param(
    [Parameter(Mandatory = $true)] [string] $CelestePath,
    [Parameter(Mandatory = $true)] [string] $ModPath,
    [string] $InstallDir = (Join-Path $env:LOCALAPPDATA 'CelesteGameplayViewer'),
    [string] $PythonPath,
    [switch] $SkipCodexRegistration
)

$ErrorActionPreference = 'Stop'

function Assert-CommandSucceeded([string] $description) {
    if ($LASTEXITCODE -ne 0) {
        throw "$description failed with exit code $LASTEXITCODE."
    }
}

function Resolve-Directory([string] $path, [string] $description) {
    if (-not (Test-Path -LiteralPath $path -PathType Container)) {
        throw "$description does not exist: $path"
    }
    return (Resolve-Path -LiteralPath $path).Path.TrimEnd('\', '/')
}

function Assert-Outside([string] $candidate, [string] $protectedRoot) {
    $fullPath = [System.IO.Path]::GetFullPath($candidate).TrimEnd('\', '/')
    if ($fullPath.Equals($protectedRoot,
            [System.StringComparison]::OrdinalIgnoreCase) -or
        $fullPath.StartsWith($protectedRoot + '\',
            [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Install directory must be outside the selected mod: $fullPath"
    }
}

$celesteRoot = Resolve-Directory $CelestePath 'Celeste installation'
$modRoot = Resolve-Directory $ModPath 'Mod project'
$modsRoot = Resolve-Directory (Join-Path $celesteRoot 'Mods') 'Celeste Mods folder'
if (-not $modRoot.StartsWith($modsRoot + '\',
        [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'The selected mod project must be inside this Celeste Mods folder.'
}
if (-not (Test-Path -LiteralPath (Join-Path $modRoot 'Maps') -PathType Container)) {
    throw 'The selected mod project must have a Maps folder.'
}
if (-not (Get-ChildItem -LiteralPath (Join-Path $modRoot 'Maps') -Recurse -File `
            -Filter '*.bin' | Select-Object -First 1)) {
    throw 'The selected mod project must contain a .bin map in Maps.'
}
if (-not (Test-Path -LiteralPath (Join-Path $celesteRoot `
            'Content\Graphics\Atlases\Gameplay.meta') -PathType Leaf)) {
    throw 'The Celeste Gameplay atlas is missing from the selected installation.'
}

$installRoot = [System.IO.Path]::GetFullPath($InstallDir).TrimEnd('\', '/')
Assert-Outside $installRoot $modRoot
$sourceRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path.TrimEnd('\', '/')
if ($installRoot.Equals($sourceRoot,
        [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Choose an install directory separate from the source checkout.'
}

if (-not $PythonPath) {
    $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if (-not $pythonCommand) {
        throw 'Python 3.10+ was not found. Pass -PythonPath to python.exe.'
    }
    $PythonPath = $pythonCommand.Source
}
$pythonExecutable = (Resolve-Path -LiteralPath $PythonPath).Path
$pythonVersion = & $pythonExecutable -c `
    'import sys; print(sys.version_info.major, sys.version_info.minor)'
Assert-CommandSucceeded 'Python version check'
$versionParts = $pythonVersion -split ' '
if ([int] $versionParts[0] -ne 3 -or [int] $versionParts[1] -lt 10) {
    throw 'Python 3.10 or newer is required.'
}

New-Item -ItemType Directory -Path $installRoot -Force | Out-Null
$packageRoot = Join-Path $sourceRoot 'celeste_gameplay_viewer'
$installedPackage = Join-Path $installRoot 'celeste_gameplay_viewer'
New-Item -ItemType Directory -Path $installedPackage, `
    (Join-Path $installedPackage 'assets'), `
    (Join-Path $installedPackage 'assets\sprites'), `
    (Join-Path $installRoot 'tools'), `
    (Join-Path $installRoot 'previews') -Force | Out-Null

# Copy an explicit allowlist so a local checkout cannot install upstream code
# or previously extracted game artwork by accident.
$pythonFiles = @(
    '__init__.py', 'findings.py', 'gallery_data.py', 'map_geometry.py',
    'map_source.py', 'mcp_app.py', 'overview.py', 'render_style.py',
    'progression.py', 'raster.py',
    'room_gallery.py', 'room_view.py', 'serialization.py', 'server.py', 'sprites.py',
    'transport_probe.py', 'viewer.py'
)
foreach ($name in $pythonFiles) {
    Copy-Item -LiteralPath (Join-Path $packageRoot $name) `
        -Destination (Join-Path $installedPackage $name) -Force
}
Copy-Item -LiteralPath (Join-Path $sourceRoot 'run_server.py') `
    -Destination (Join-Path $installRoot 'run_server.py') -Force
Copy-Item -LiteralPath (Join-Path $sourceRoot 'requirements.txt') `
    -Destination (Join-Path $installRoot 'requirements.txt') -Force
Copy-Item -LiteralPath (Join-Path $sourceRoot 'tools\extract_sprites.py') `
    -Destination (Join-Path $installRoot 'tools\extract_sprites.py') -Force
Copy-Item -LiteralPath (Join-Path $sourceRoot 'tools\verify_install.py') `
    -Destination (Join-Path $installRoot 'tools\verify_install.py') -Force
foreach ($name in @('gallery-shell.html', 'layout.html', 'mcp-app-bridge.js',
                    'room-gallery.html', 'room-gallery.js', 'standalone.html')) {
    Copy-Item -LiteralPath (Join-Path $packageRoot ('assets\' + $name)) `
        -Destination (Join-Path $installedPackage 'assets' $name) -Force
}

$venvPython = Join-Path $installRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    & $pythonExecutable -m venv (Join-Path $installRoot '.venv')
    Assert-CommandSucceeded 'Virtual environment creation'
}
& $venvPython -m pip install --disable-pip-version-check -r `
    (Join-Path $installRoot 'requirements.txt')
Assert-CommandSucceeded 'Dependency installation'

& $venvPython (Join-Path $installRoot 'tools\extract_sprites.py') `
    --celeste-path $celesteRoot `
    --output-dir (Join-Path $installedPackage 'assets\sprites')
Assert-CommandSucceeded 'Local sprite extraction'

$env:LOENN_MCP_WORKSPACE = $modRoot
$env:CELESTE_VIEWER_OUTPUT = Join-Path $installRoot 'previews'
$env:PYTHONUTF8 = '1'
& $venvPython (Join-Path $installRoot 'tools\verify_install.py')
Assert-CommandSucceeded 'Read-only viewer smoke test'

if (-not $SkipCodexRegistration) {
    $codex = Get-Command codex -ErrorAction SilentlyContinue
    if (-not $codex) {
        throw 'Codex CLI was not found; viewer installed, but MCP registration is pending.'
    }
    $codexHome = if ($env:CODEX_HOME) {
        $env:CODEX_HOME
    } else {
        Join-Path $env:USERPROFILE '.codex'
    }
    $env:CODEX_HOME = $codexHome
    $configPath = Join-Path $codexHome 'config.toml'
    if (Test-Path -LiteralPath $configPath) {
        $stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
        $backup = Join-Path $codexHome "config.toml.before-viewer-$stamp"
        Copy-Item -LiteralPath $configPath -Destination $backup
        Write-Output "Codex configuration backup: $backup"
    }
    $registered = & $codex.Source mcp list --json | ConvertFrom-Json
    Assert-CommandSucceeded 'Codex MCP listing'
    if ($registered | Where-Object { $_.name -eq 'celeste-gameplay-viewer' }) {
        & $codex.Source mcp remove celeste-gameplay-viewer
        Assert-CommandSucceeded 'Replacing viewer MCP registration'
    }
    & $codex.Source mcp add celeste-gameplay-viewer `
        --env "LOENN_MCP_WORKSPACE=$modRoot" `
        --env "CELESTE_VIEWER_OUTPUT=$env:CELESTE_VIEWER_OUTPUT" `
        --env 'PYTHONUTF8=1' `
        -- $venvPython (Join-Path $installRoot 'run_server.py')
    Assert-CommandSucceeded 'Codex MCP registration'
    $registered = & $codex.Source mcp list --json | ConvertFrom-Json
    Assert-CommandSucceeded 'Codex MCP verification'
    if (-not ($registered | Where-Object { $_.name -eq 'celeste-gameplay-viewer' })) {
        throw 'The standalone viewer MCP server is missing from Codex.'
    }
}

Write-Output "Standalone viewer installed at $installRoot"
Write-Output 'Your Celeste maps were read only.'
