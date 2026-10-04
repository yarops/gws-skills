#requires -Version 7.3
[CmdletBinding()]
param(
    [string]$Dest,
    [switch]$Upgrade,
    [switch]$Help
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($Help) {
    Write-Output 'Usage: ./install.ps1 -Dest DIRECTORY [-Upgrade]'
    Write-Output 'Identical installations are unchanged. -Upgrade replaces differing folders, including local edits, with backups in DIRECTORY/.gws-skills-backups/. Links are rejected.'
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

function Get-Tree([string]$Path) {
    $root = Get-Item -LiteralPath $Path -Force
    if (-not $root.PSIsContainer -or ($root.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw "Expected an ordinary directory: $Path"
    }
    $tree = [Collections.Generic.Dictionary[string, object]]::new([StringComparer]::Ordinal)
    $pending = [Collections.Generic.Stack[string]]::new()
    $pending.Push($Path)
    while ($pending.Count) {
        foreach ($entry in Get-ChildItem -LiteralPath $pending.Pop() -Force) {
            if ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Link or junction in tree: $($entry.FullName)"
            }
            if (-not $entry.PSIsContainer -and $entry -isnot [IO.FileInfo]) {
                throw "Special file in tree: $($entry.FullName)"
            }
            $relative = [IO.Path]::GetRelativePath($Path, $entry.FullName)
            $tree.Add($relative, $entry)
            if ($entry.PSIsContainer) { $pending.Push($entry.FullName) }
        }
    }
    return ,$tree
}

function Test-SameTree([string]$Left, [string]$Right) {
    $a = Get-Tree $Left
    $b = Get-Tree $Right
    if ($a.Count -ne $b.Count) { return $false }
    foreach ($key in $a.Keys) {
        if (-not $b.ContainsKey($key)) { return $false }
        if ($a[$key].PSIsContainer -ne $b[$key].PSIsContainer) { return $false }
        if (-not $a[$key].PSIsContainer) {
            if ($a[$key].Length -ne $b[$key].Length) { return $false }
            $leftStream = [IO.File]::OpenRead($a[$key].FullName)
            $rightStream = $null
            try {
                $rightStream = [IO.File]::OpenRead($b[$key].FullName)
                $leftBuffer = [byte[]]::new(65536)
                $rightBuffer = [byte[]]::new(65536)
                while (($count = $leftStream.Read($leftBuffer, 0, $leftBuffer.Length)) -gt 0) {
                    $offset = 0
                    while ($offset -lt $count) {
                        $read = $rightStream.Read($rightBuffer, $offset, $count - $offset)
                        if ($read -eq 0) { return $false }
                        $offset += $read
                    }
                    for ($i = 0; $i -lt $count; $i++) {
                        if ($leftBuffer[$i] -ne $rightBuffer[$i]) { return $false }
                    }
                }
                if ($rightStream.ReadByte() -ne -1) { return $false }
            }
            finally {
                $leftStream.Dispose()
                if ($null -ne $rightStream) { $rightStream.Dispose() }
            }
        }
    }
    return $true
}

$lockPath = Join-Path $destination '.gws-skills-install.lock'
$lock = $null
$stage = $null
$backup = $null
$published = [Collections.Generic.List[string]]::new()
$saved = [Collections.Generic.List[string]]::new()
$actions = @{}
$committed = $false
try {
    $lock = [IO.File]::Open($lockPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    $stage = Join-Path $destination ('.gws-skills-install.' + [guid]::NewGuid().ToString('N'))
    [IO.Directory]::CreateDirectory($stage) | Out-Null
    foreach ($skill in $skills) {
        $source = Join-Path $PSScriptRoot $skill
        $null = Get-Tree $source
        Copy-Item -LiteralPath $source -Destination $stage -Recurse -Force
        $target = Join-Path $destination $skill
        if ($null -ne (Get-Item -LiteralPath $target -Force -ErrorAction SilentlyContinue)) {
            if (Test-SameTree (Join-Path $stage $skill) $target) {
                $actions[$skill] = 'Already installed'
            }
            elseif ($Upgrade) { $actions[$skill] = 'Updated' }
            else { throw "Different installation: $target; rerun with -Upgrade" }
        }
        else { $actions[$skill] = 'Installed' }
    }
    foreach ($skill in $skills) {
        if ($actions[$skill] -eq 'Already installed') { continue }
        $target = Join-Path $destination $skill
        if ($actions[$skill] -eq 'Updated') {
            if ($null -eq $backup) {
                $backupRoot = Join-Path $destination '.gws-skills-backups'
                $entry = Get-Item -LiteralPath $backupRoot -Force -ErrorAction SilentlyContinue
                if ($null -ne $entry -and ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
                    throw "Backup directory is a link: $backupRoot"
                }
                $backup = Join-Path $backupRoot ([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '-' + [guid]::NewGuid().ToString('N'))
                [IO.Directory]::CreateDirectory($backup) | Out-Null
            }
            [IO.Directory]::Move($target, (Join-Path $backup $skill))
            $saved.Add($skill)
        }
        [IO.Directory]::Move((Join-Path $stage $skill), $target)
        $published.Add($skill)
    }
    $committed = $true
    foreach ($skill in $skills) { Write-Output "$($actions[$skill]): $(Join-Path $destination $skill)" }
    if ($null -ne $backup) { Write-Output "Backup: $backup" }
}
catch {
    if (-not $committed) {
        foreach ($skill in $published) {
            $target = Join-Path $destination $skill
            try { Remove-Item -LiteralPath $target -Recurse -Force }
            catch { Write-Warning "Rollback failed removing: $target; $($_.Exception.Message)" }
        }
        foreach ($skill in $saved) {
            $original = Join-Path $backup $skill
            $target = Join-Path $destination $skill
            try { [IO.Directory]::Move($original, $target) }
            catch { Write-Warning "Rollback failed; restore $original to $target manually; $($_.Exception.Message)" }
        }
    }
    throw
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
