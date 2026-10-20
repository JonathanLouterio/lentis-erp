#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$ProjectRoot = (Join-Path $PSScriptRoot '..'),
    [string]$BackupDirectory = '',
    [string]$ComposeFile = '',
    [string]$Service = 'db',
    [ValidateRange(30, 86400)][int]$TimeoutSeconds = 1800
)
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'Lentis.Backup.psm1') -Force

$context = Get-LentisContext -ProjectRoot $ProjectRoot -ComposeFile $ComposeFile -Service $Service -TimeoutSeconds $TimeoutSeconds
$source = Get-LentisDatabaseInfo -Context $context
if (-not $BackupDirectory) { $BackupDirectory = Join-Path $context.ProjectRoot 'backups' }
elseif (-not [System.IO.Path]::IsPathRooted($BackupDirectory)) { $BackupDirectory = Join-Path $context.ProjectRoot $BackupDirectory }
$BackupDirectory = Get-LentisLocalPath $BackupDirectory
$null = [System.IO.Directory]::CreateDirectory($BackupDirectory)

$identity = [guid]::NewGuid().ToString('N')
$stamp = [DateTime]::UtcNow.ToString('yyyyMMdd_HHmmss_fff')
$temporaryFolder = Join-Path $BackupDirectory ('.incomplete-' + $identity)
$finalFolder = Join-Path $BackupDirectory ('lentis-' + $stamp + '-' + $identity.Substring(0, 8))
$remoteArchive = '/tmp/lentis-backup-' + $identity + '.dump'
$folderCreated = $false
$finished = $false
try {
    if (Test-Path -LiteralPath $temporaryFolder) { throw 'A pasta temporária já existe. Repita a operação.' }
    $null = [System.IO.Directory]::CreateDirectory($temporaryFolder)
    $folderCreated = $true
    Write-Host "Criando backup do banco '$($source.database)' pelo serviço '$Service'..."
    $script = (Get-LentisShellHeader) + "`n" + @'
# LENTIS_ACTION: backup
umask 077
pg_dump --no-password -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --file="$1"
pg_restore --list "$1" >/dev/null
'@
    $null = Invoke-LentisShell -Context $context -Script $script -Parameters @($remoteArchive)
    $archive = Join-Path $temporaryFolder 'database.dump'
    Copy-LentisContainerFile -Context $context -RemotePath $remoteArchive -LocalPath $archive
    $file = Get-Item -LiteralPath $archive
    if ($file.Length -le 0) { throw 'O Docker retornou um arquivo de backup vazio.' }
    $hash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash
    $manifest = [ordered]@{
        format_version = 1; app = 'lentis-erp'; created_at_utc = [DateTime]::UtcNow.ToString('o')
        archive = 'database.dump'; bytes = $file.Length; sha256 = $hash
        source = $source; service = $Service; container_id = $context.ContainerId
        verification = 'archive-list-and-sha256; restore-test-required'
    }
    Write-LentisJson -Path (Join-Path $temporaryFolder 'manifest.json') -Value $manifest
    $null = Test-LentisArchive -BackupFile $archive
    # Os dois arquivos ficam visíveis juntos somente após completar o backup.
    [System.IO.Directory]::Move($temporaryFolder, $finalFolder)
    $finished = $true
    $result = [pscustomobject]@{
        BackupFile = (Join-Path $finalFolder 'database.dump')
        ManifestFile = (Join-Path $finalFolder 'manifest.json')
        Database = $source.database; Bytes = $file.Length; Sha256 = $hash
        RestoreTested = $false
    }
    Write-Host "Backup criado: $($result.BackupFile)"
    return $result
}
finally {
    try { Remove-LentisContainerFile -Context $context -RemotePath $remoteArchive }
    catch { Write-Warning "Não foi possível remover o arquivo temporário $remoteArchive no contêiner. $($_.Exception.Message)" }
    if (-not $finished -and $folderCreated -and (Test-Path -LiteralPath $temporaryFolder)) {
        Remove-Item -LiteralPath $temporaryFolder -Recurse -Force
    }
}
