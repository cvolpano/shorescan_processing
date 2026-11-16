# filter_files_Dec.ps1
# Purpose: Copy files whose NAME contains "Dec" from SourceDir to DestDir,
#          preserving the relative folder structure.

$Pattern   = "Dec"
$SourceDir = (Resolve-Path "F:\results_11122026").Path.TrimEnd('\')
$DestDir   = "F:\results_11152026"

if (-not (Test-Path -LiteralPath $DestDir)) {
    New-Item -ItemType Directory -Path $DestDir | Out-Null
}

# -Filter is applied by the file system provider, so it's much faster than
# listing every file and testing each name in PowerShell.
$files = Get-ChildItem -LiteralPath $SourceDir -Recurse -File -Filter "*$Pattern*"

foreach ($file in $files) {
    # Path relative to the source root, e.g. "site1\Dec_run.nc"
    $RelativePath = $file.FullName.Substring($SourceDir.Length).TrimStart('\')
    $DestFilePath = Join-Path $DestDir $RelativePath
    $DestSubDir   = Split-Path -Parent $DestFilePath

    if (-not (Test-Path -LiteralPath $DestSubDir)) {
        New-Item -ItemType Directory -Path $DestSubDir -Force | Out-Null
    }

    Copy-Item -LiteralPath $file.FullName -Destination $DestFilePath -Force
}

Write-Host