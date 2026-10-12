<#
.SYNOPSIS
Reject tracked or historically committed files excluded by this repository.
.DESCRIPTION
Checks the index and every reachable local/remote commit against the current
.gitignore, including force-added files. Reports paths only, never contents.
Exit code 1 means prohibited files or a failed Git command were found.
This is a file-policy check, not a general secret scanner.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $repositoryRoot
try {
    $trackedPaths = @(git -c core.quotePath=false ls-files)
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not read the Git index.'
    }
    $historicalPaths = @(
        git -c core.quotePath=false log --all --format= --name-only
    )
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not read Git history.'
    }
    $candidatePaths = @(
        $trackedPaths + $historicalPaths |
            Where-Object { $_ } |
            Sort-Object -Unique
    )
    if ($candidatePaths.Count -eq 0) {
        Write-Output 'Repository file policy passed: no committed files.'
        exit 0
    }

    # --no-index deliberately checks files that Git already tracks.
    $excludedPaths = @()
    # Use arguments rather than stdin: Windows PowerShell adds CRLF to pipes,
    # which Git can interpret as a trailing carriage return in each filename.
    # Small batches also stay below Windows command-line length limits.
    for ($offset = 0; $offset -lt $candidatePaths.Count; $offset += 50) {
        $last = [Math]::Min($offset + 49, $candidatePaths.Count - 1)
        $pathBatch = $candidatePaths[$offset..$last]
        $excludedPaths += @(git check-ignore --no-index -- @pathBatch)
        if ($LASTEXITCODE -gt 1) {
            throw 'Could not evaluate the repository ignore rules.'
        }
    }
    if ($excludedPaths.Count -gt 0) {
        Write-Output 'Push blocked: excluded files exist in the index/history:'
        $excludedPaths | ForEach-Object { Write-Output "  $_" }
        Write-Output 'Untrack staged files or remove them from history first.'
        exit 1
    }
    Write-Output (
        'Repository file policy passed: {0} unique paths checked.' -f
        $candidatePaths.Count
    )
} catch {
    Write-Error $_ -ErrorAction Continue
    exit 1
} finally {
    Pop-Location
}
