#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$ProjectRoot = (Join-Path $PSScriptRoot '..'),
    [string]$BackupDirectory = '',
    [string]$ReportDirectory = '',
    [string]$ComposeFile = '',
    [string]$Service = 'db',
    [ValidateRange(30, 86400)][int]$TimeoutSeconds = 1800
)
$ErrorActionPreference = 'Stop'
$common = @{ ProjectRoot = $ProjectRoot; ComposeFile = $ComposeFile; Service = $Service; TimeoutSeconds = $TimeoutSeconds }
$backupLentisResult = & (Join-Path $PSScriptRoot 'Backup-Lentis.ps1') @common -BackupDirectory $BackupDirectory
$restoreLentisResult = & (Join-Path $PSScriptRoot 'Test-Restore-Lentis.ps1') @common -BackupFile $backupLentisResult.BackupFile -ReportDirectory $ReportDirectory
[pscustomobject]@{
    BackupFile = $backupLentisResult.BackupFile
    ManifestFile = $backupLentisResult.ManifestFile
    ReportFile = $restoreLentisResult.ReportFile
    RestoreTested = $restoreLentisResult.Success
    TemporaryDatabaseRemoved = $restoreLentisResult.TemporaryDatabaseRemoved
    TablesChecked = $restoreLentisResult.TablesChecked
    MigrationsChecked = $restoreLentisResult.MigrationsChecked
}
