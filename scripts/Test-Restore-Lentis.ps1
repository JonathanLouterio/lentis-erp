#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$BackupFile,
    [string]$ProjectRoot = (Join-Path $PSScriptRoot '..'),
    [string]$ReportDirectory = '',
    [string]$ComposeFile = '',
    [string]$Service = 'db',
    [ValidateRange(30, 86400)][int]$TimeoutSeconds = 1800
)
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'Lentis.Backup.psm1') -Force

# Recusa arquivo alterado antes de acessar Docker ou criar banco.
$checked = Test-LentisArchive -BackupFile $BackupFile
$context = Get-LentisContext -ProjectRoot $ProjectRoot -ComposeFile $ComposeFile -Service $Service -TimeoutSeconds $TimeoutSeconds
$source = Get-LentisDatabaseInfo -Context $context
if (-not $ReportDirectory) { $ReportDirectory = Join-Path $context.ProjectRoot 'backups/restore-tests' }
elseif (-not [System.IO.Path]::IsPathRooted($ReportDirectory)) { $ReportDirectory = Join-Path $context.ProjectRoot $ReportDirectory }
$ReportDirectory = Get-LentisLocalPath $ReportDirectory
$null = [System.IO.Directory]::CreateDirectory($ReportDirectory)
$identity = [guid]::NewGuid().ToString('N')
$temporaryDatabase = 'lentis_restore_test_' + $identity
$remoteArchive = '/tmp/lentis-restore-' + $identity + '.dump'
Assert-LentisTemporaryDatabase -Database $temporaryDatabase -SourceDatabase $source.database
$reportFile = Join-Path $ReportDirectory ('restore-' + [DateTime]::UtcNow.ToString('yyyyMMdd_HHmmss_fff') + '-' + $identity.Substring(0, 8) + '.json')
$created = $false
$restored = $false
$removed = $false
$remoteRemoved = $false
$inspection = $null
$failure = ''
try {
    Write-Host "Conferindo restauração no banco temporário '$temporaryDatabase'..."
    Copy-LentisContainerFile -Context $context -RemotePath $remoteArchive -LocalPath $checked.BackupFile -ToContainer
    $create = (Get-LentisShellHeader) + "`n" + @'
# LENTIS_ACTION: create-test
case "$1" in lentis_restore_test_*) ;; *) exit 71 ;; esac
[ "$1" != "$POSTGRES_DB" ] || exit 72
createdb --no-password -U "$POSTGRES_USER" --maintenance-db=postgres --template=template0 --encoding="$2" "$1"
'@
    $null = Invoke-LentisShell -Context $context -Script $create -Parameters @($temporaryDatabase, $source.encoding)
    # Só assume propriedade do banco depois de createdb terminar sem erro.
    $created = $true
    $restore = (Get-LentisShellHeader) + "`n" + @'
# LENTIS_ACTION: restore-test
case "$1" in lentis_restore_test_*) ;; *) exit 71 ;; esac
[ "$1" != "$POSTGRES_DB" ] || exit 72
pg_restore --no-password -U "$POSTGRES_USER" --dbname="$1" --exit-on-error --single-transaction --clean --if-exists --no-owner --no-privileges "$2"
'@
    $null = Invoke-LentisShell -Context $context -Script $restore -Parameters @($temporaryDatabase, $remoteArchive)
    $null = Get-LentisDatabaseInfo -Context $context -Database $temporaryDatabase
    $inspect = (Get-LentisShellHeader) + "`n" + @'
# LENTIS_ACTION: inspect-test
psql -X -q -A -t --no-password -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$1" <<'SQL'
BEGIN;
CREATE FUNCTION pg_temp.lentis_row_count(schema_name text, table_name text) RETURNS bigint
LANGUAGE plpgsql AS $$
DECLARE result bigint;
BEGIN
 EXECUTE format('SELECT count(*) FROM %I.%I', schema_name, table_name) INTO result;
 RETURN result;
END;
$$;
SELECT json_build_object(
 'database', current_database(),
 'migration_count', (SELECT count(*) FROM public.django_migrations),
 'tables', COALESCE((SELECT json_agg(json_build_object('schema', n.nspname, 'table', c.relname,
   'rows', pg_temp.lentis_row_count(n.nspname, c.relname)) ORDER BY n.nspname, c.relname)
   FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
   WHERE c.relkind IN ('r','p') AND n.nspname NOT IN ('pg_catalog','information_schema')
     AND n.nspname NOT LIKE 'pg_toast%' AND n.nspname NOT LIKE 'pg_temp%'), '[]'::json),
 'migrations', COALESCE((SELECT json_agg(json_build_object('app', app, 'name', name) ORDER BY app, name)
   FROM public.django_migrations), '[]'::json)
);
ROLLBACK;
SQL
'@
    $raw = Invoke-LentisShell -Context $context -Script $inspect -Parameters @($temporaryDatabase)
    $inspection = $raw | ConvertFrom-Json -ErrorAction Stop
    if ($inspection.database -ne $temporaryDatabase -or $inspection.migration_count -lt 1 -or @($inspection.tables).Count -lt 4) {
        throw 'A restauração não passou na conferência de tabelas e migrations.'
    }
    $restored = $true
}
catch { $failure = $_.Exception.Message }
finally {
    if ($created) {
        try {
            Assert-LentisTemporaryDatabase -Database $temporaryDatabase -SourceDatabase $source.database
            $drop = (Get-LentisShellHeader) + "`n" + @'
# LENTIS_ACTION: drop-test
case "$1" in lentis_restore_test_*) ;; *) exit 71 ;; esac
[ "$1" != "$POSTGRES_DB" ] || exit 72
dropdb --no-password -U "$POSTGRES_USER" --maintenance-db=postgres --if-exists --force "$1"
'@
            $null = Invoke-LentisShell -Context $context -Script $drop -Parameters @($temporaryDatabase) -TimeoutSeconds 60
            $removed = $true
        }
        catch { $failure += " Falha ao remover $temporaryDatabase`: $($_.Exception.Message)" }
    }
    try { Remove-LentisContainerFile -Context $context -RemotePath $remoteArchive; $remoteRemoved = $true }
    catch { $failure += " Falha ao remover $remoteArchive`: $($_.Exception.Message)" }
}
$success = $restored -and $removed -and $remoteRemoved -and (-not $failure)
$report = [ordered]@{
    format_version = 1; app = 'lentis-erp'; tested_at_utc = [DateTime]::UtcNow.ToString('o')
    success = $success; backup_file = $checked.BackupFile; sha256 = $checked.Sha256
    original_database = $source.database; temporary_database = $temporaryDatabase
    temporary_database_created = $created; temporary_database_removed = $removed
    temporary_file_removed = $remoteRemoved; error = $failure; inspection = $inspection
    note = 'Contagens do banco restaurado; não são comparadas ao banco original em uso.'
}
Write-LentisJson -Path $reportFile -Value $report
if (-not $success) { throw "O teste de restauração falhou. $failure Relatório: $reportFile" }
Write-Host "Restauração validada e banco temporário removido. Relatório: $reportFile"
return [pscustomobject]@{
    Success = $true; BackupFile = $checked.BackupFile; ReportFile = $reportFile
    OriginalDatabase = $source.database; TemporaryDatabaseRemoved = $removed
    TablesChecked = @($inspection.tables).Count; MigrationsChecked = $inspection.migration_count
}
