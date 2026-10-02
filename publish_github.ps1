param(
    [string]$RemoteUrl = "",
    [string]$GitUserName = "",
    [string]$GitUserEmail = "",
    [switch]$NoPush
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

if (-not (Test-Path -LiteralPath ".git")) {
    git init
}

if ($GitUserName) {
    git config user.name $GitUserName
}

if ($GitUserEmail) {
    git config user.email $GitUserEmail
}

git branch -M main
git add .
git status --short

$hasChanges = git status --porcelain
if ($hasChanges) {
    git commit -m "Initial crypto portfolio"
} else {
    Write-Host "Nessuna modifica da committare."
}

if ($NoPush) {
    Write-Host "NoPush attivo: commit locale completato, nessun push eseguito."
    exit 0
}

if ($RemoteUrl) {
    if ($RemoteUrl -match "\((https://github\.com/[^)]+)\)") {
        $RemoteUrl = $Matches[1]
    }

    if ($RemoteUrl -match "TUO_UTENTE|NOME_REPO|^\[") {
        throw "RemoteUrl non valido. Usa l'URL reale del repo, es. https://github.com/utente/repo.git"
    }

    $hasOrigin = (git remote) -contains "origin"
    if ($hasOrigin) {
        git remote set-url origin $RemoteUrl
    } else {
        git remote add origin $RemoteUrl
    }
    git push -u origin main
} else {
    Write-Host "Remote non impostato. Esempio:"
    Write-Host ".\\publish_github.ps1 -RemoteUrl https://github.com/TUO_UTENTE/NOME_REPO.git"
}
