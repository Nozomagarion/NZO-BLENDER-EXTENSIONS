[CmdletBinding()]
param(
    [string]$RepositoryUrl = "https://nozomagarion.github.io/NZO-BLENDER-EXTENSIONS/index.json"
)

$ErrorActionPreference = "Stop"
$repoId = "nzo_extensions"
$roots = @(
    "C:\Program Files\Blender Foundation",
    (Join-Path $env:LOCALAPPDATA "Programs")
)

$executables = @(
    foreach ($root in $roots) {
        if (Test-Path -LiteralPath $root) {
            Get-ChildItem -LiteralPath $root -Filter blender.exe -File -Recurse -ErrorAction SilentlyContinue
        }
    }
) | Sort-Object FullName -Unique

if (-not $executables) {
    throw "Aucune installation Blender n'a été trouvée."
}

$connected = 0
foreach ($item in $executables) {
    $versionText = & $item.FullName --version 2>$null | Select-Object -First 1
    if ($versionText -notmatch 'Blender\s+(\d+)\.(\d+)') {
        Write-Warning "Version illisible ou exécutable inutilisable : $($item.FullName)"
        continue
    }

    $major = [int]$Matches[1]
    $minor = [int]$Matches[2]
    if ($major -lt 4 -or ($major -eq 4 -and $minor -lt 2)) {
        continue
    }

    Write-Host "Configuration de $versionText"
    $repositories = (& $item.FullName --online-mode --command extension repo-list 2>&1 | Out-String)
    if ($repositories -notmatch "(?m)^\s*$([regex]::Escape($repoId))\b") {
        & $item.FullName --online-mode --command extension repo-add --name "NZO Extensions" --url $RepositoryUrl $repoId
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Impossible d'ajouter le dépôt à $($item.FullName)"
            continue
        }
    }

    & $item.FullName --online-mode --command extension sync
    if ($LASTEXITCODE -eq 0) {
        $connected++
    } else {
        Write-Warning "Dépôt ajouté, mais synchronisation échouée pour $versionText"
    }
}

if ($connected -eq 0) {
    throw "Aucune installation Blender 4.2+ n'a pu être configurée."
}

Write-Host "$connected installation(s) Blender connectée(s) au catalogue NZO."
