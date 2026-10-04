#requires -Version 7.3
[CmdletBinding()]
param(
    [string]$Dest,
    [switch]$Help
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($Help) {
    Write-Output 'Usage: ./install.ps1 -Dest DIRECTORY'
    Write-Output 'Copy gws-drive and gws-sheets without overwriting existing paths.'
    exit 0
}
if ([string]::IsNullOrWhiteSpace($Dest)) { throw '-Dest requires a directory' }

$skills = @('gws-drive', 'gws-sheets')
foreach ($required in @('gws-drive/SKILL.md', 'gws-sheets/SKILL.md',
    'gws-sheets/assets/header_style.json', 'gws-sheets/scripts/create_tracker.py')) {
    if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot $required) -PathType Leaf)) {
        throw "Missing source: $required"
    }
}

# Reject junctions and symlinks in destination ancestors so containment checks
# cannot be bypassed by a redirected directory (including a dangling link).
$destination = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Dest)
$ancestor = $destination
while ($ancestor) {
    $entry = Get-Item -LiteralPath $ancestor -Force -ErrorAction SilentlyContinue
    if ($null -ne $entry -and ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw "Destination uses a symbolic link or junction: $ancestor"
    }
    $ancestor = [IO.Path]::GetDirectoryName($ancestor)
}
foreach ($skill in $skills) {
    $source = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot $skill))
    if ($destination.Equals($source, [StringComparison]::OrdinalIgnoreCase) -or
        $destination.StartsWith($source + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Destination is inside source skill: $skill"
    }
}
[IO.Directory]::CreateDirectory($destination) | Out-Null

function Assert-NoConflict {
    foreach ($skill in $skills) {
        $target = Join-Path $destination $skill
        if ($null -ne (Get-Item -LiteralPath $target -Force -ErrorAction SilentlyContinue)) {
            throw "Destination already exists: $target"
        }
    }
}

Assert-NoConflict
$lockPath = Join-Path $destination '.gws-skills-install.lock'
$lock = $null
$stage = $null
try {
    # CreateNew provides exclusive acquisition; never remove another run's lock.
    $lock = [IO.File]::Open($lockPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    $stage = Join-Path $destination ('.gws-skills-install.' + [guid]::NewGuid().ToString('N'))
    [IO.Directory]::CreateDirectory($stage) | Out-Null
    foreach ($skill in $skills) {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot $skill) -Destination $stage -Recurse -Force
    }
    Assert-NoConflict
    foreach ($skill in $skills) {
        $target = Join-Path $destination $skill
        # Directory.Move fails if a target appeared after the conflict check.
        [IO.Directory]::Move((Join-Path $stage $skill), $target)
        Write-Output "Installed: $target"
    }
}
finally {
    try {
        if ($null -ne $stage -and (Test-Path -LiteralPath $stage)) {
            Remove-Item -LiteralPath $stage -Recurse -Force
        }
    }
    finally {
        if ($null -ne $lock) {
            $lock.Dispose()
            Remove-Item -LiteralPath $lockPath -Force
        }
    }
}
