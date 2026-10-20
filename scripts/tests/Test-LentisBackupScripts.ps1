#Requires -Version 5.1
[CmdletBinding()]
param()
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$script:checks = 0
$modulePath = Join-Path $PSScriptRoot '../Lentis.Backup.psm1'
Import-Module $modulePath -Force
function Confirm-Check {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw "Teste falhou: $Message" }
    $script:checks++
}
function Confirm-Failure {
    param([scriptblock]$Action, [string]$Expected)
    $failed = $false
    try { $null = & $Action }
    catch {
        $failed = $true
        if ($_.Exception.Message -notmatch [regex]::Escape($Expected)) { throw "Erro diferente do esperado: $($_.Exception.Message)" }
    }
    Confirm-Check $failed "A operação deveria recusar: $Expected"
}
$scriptDirectory = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
foreach ($path in @(Get-ChildItem -LiteralPath $scriptDirectory -File -Recurse | Where-Object { $_.Extension -in @('.ps1', '.psm1') })) {
    $tokens = $null; $parseErrors = $null
    $null = [System.Management.Automation.Language.Parser]::ParseFile($path.FullName, [ref]$tokens, [ref]$parseErrors)
    Confirm-Check (@($parseErrors).Count -eq 0) "Sintaxe de $($path.Name)"
    $bytes = [System.IO.File]::ReadAllBytes($path.FullName)
    Confirm-Check ($bytes.Length -ge 3 -and $bytes[0] -eq 239 -and $bytes[1] -eq 187 -and $bytes[2] -eq 191) "UTF-8 com BOM em $($path.Name)"
}
$temporaryFolder = Join-Path ([System.IO.Path]::GetTempPath()) ('lentis-backup-check-' + [guid]::NewGuid().ToString('N'))
$null = [System.IO.Directory]::CreateDirectory($temporaryFolder)
try {
    $file = Join-Path $temporaryFolder 'database.dump'
    $bytes = New-Object byte[] 512
    for ($i = 0; $i -lt $bytes.Length; $i++) { $bytes[$i] = $i % 256 }
    [System.IO.File]::WriteAllBytes($file, $bytes)
    $manifest = [ordered]@{ format_version = 1; app = 'lentis-erp'; archive = 'database.dump'; bytes = $bytes.Length; sha256 = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash; source = @{ database = 'fixture' } }
    $manifestPath = Join-Path $temporaryFolder 'manifest.json'
    Write-LentisJson -Path $manifestPath -Value $manifest
    $checked = Test-LentisArchive -BackupFile $file
    Confirm-Check ($checked.Sha256 -eq $manifest.sha256) 'Arquivo íntegro aceito'
    $bytes[100] = 99
    [System.IO.File]::WriteAllBytes($file, $bytes)
    Confirm-Failure { Test-LentisArchive -BackupFile $file } 'SHA256'
    [System.IO.File]::WriteAllBytes($file, (New-Object byte[] 0))
    Confirm-Failure { Test-LentisArchive -BackupFile $file } 'tamanho'
    $manifest.app = 'outro-projeto'
    Write-LentisJson -Path $manifestPath -Value $manifest
    Confirm-Failure { Test-LentisArchive -BackupFile $file } 'não corresponde'
    [System.IO.File]::WriteAllText($manifestPath, '{invalido')
    Confirm-Failure { Test-LentisArchive -BackupFile $file } 'JSON'
    Remove-Item -LiteralPath $manifestPath
    Confirm-Failure { Test-LentisArchive -BackupFile $file } 'manifest.json'
    Confirm-Failure { Assert-LentisTemporaryDatabase -Database 'lentis' -SourceDatabase 'lentis' } 'temporário'
    Confirm-Failure { Assert-LentisTemporaryDatabase -Database 'lentis_restore_test_escolhido' -SourceDatabase 'lentis' } 'temporário'
    Assert-LentisTemporaryDatabase -Database ('lentis_restore_test_' + ('a' * 32)) -SourceDatabase 'lentis'
    Confirm-Check $true 'Nome temporário exclusivo aceito'
}
finally { Remove-Item -LiteralPath $temporaryFolder -Recurse -Force }
Write-Host "$script:checks verificações locais passaram. Nenhum acesso ao Docker ou banco foi feito."
[pscustomobject]@{ Success = $true; Checks = $script:checks; DockerAccessed = $false }
