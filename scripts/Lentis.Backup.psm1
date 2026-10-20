Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

function ConvertTo-LentisNativeArgument {
    param([AllowEmptyString()][string]$Value)
    # ProcessStartInfo.Arguments: aspas e barras finais seguem o formato nativo.
    $escaped = [regex]::Replace($Value, '(\\*)"', '${1}${1}\"')
    $escaped = [regex]::Replace($escaped, '(\\+)$', '${1}${1}')
    return '"' + $escaped + '"'
}

function Invoke-LentisNative {
    param([string]$Executable, [string[]]$Arguments, [string]$WorkingDirectory,
          [AllowEmptyString()][string]$InputText = '', [int]$TimeoutSeconds = 1800)
    $info = New-Object System.Diagnostics.ProcessStartInfo
    $info.FileName = $Executable
    $info.Arguments = (($Arguments | ForEach-Object { ConvertTo-LentisNativeArgument $_ }) -join ' ')
    $info.WorkingDirectory = $WorkingDirectory
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardInput = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    $info.StandardOutputEncoding = $utf8
    $info.StandardErrorEncoding = $utf8
    if ($null -ne $info.PSObject.Properties['StandardInputEncoding']) { $info.StandardInputEncoding = $utf8 }
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $info
    try {
        if (-not $process.Start()) { throw 'Não foi possível iniciar o Docker.' }
        $outputTask = $process.StandardOutput.ReadToEndAsync()
        $errorTask = $process.StandardError.ReadToEndAsync()
        if ($InputText) { $process.StandardInput.Write($InputText.Replace("`r`n", "`n") + "`n") }
        $process.StandardInput.Close()
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            try { $process.Kill() } catch { }
            $process.WaitForExit()
            throw "A operação excedeu $TimeoutSeconds segundos. Confira o Docker antes de repetir."
        }
        $stdout = $outputTask.GetAwaiter().GetResult()
        $stderr = $errorTask.GetAwaiter().GetResult()
        if ($process.ExitCode -ne 0) {
            $detail = $stderr.Trim()
            if (-not $detail) { $detail = $stdout.Trim() }
            throw "Docker retornou código $($process.ExitCode). $detail"
        }
        if ($stderr.Trim()) { Write-Warning $stderr.Trim() }
        return $stdout.Trim()
    }
    finally { $process.Dispose() }
}

function Get-LentisLocalPath {
    param([string]$Path)
    return [System.IO.Path]::GetFullPath($ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Path))
}

function Get-LentisContext {
    param([string]$ProjectRoot, [string]$ComposeFile = '', [string]$Service = 'db', [int]$TimeoutSeconds = 1800)
    $root = Get-LentisLocalPath $ProjectRoot
    if (-not (Test-Path -LiteralPath (Join-Path $root 'backend/manage.py') -PathType Leaf)) {
        throw "A pasta informada não contém backend/manage.py: $root"
    }
    if ($Service -notmatch '^[A-Za-z0-9][A-Za-z0-9_.-]{0,62}$') { throw 'Nome de serviço Compose inválido.' }
    if (-not $ComposeFile) {
        foreach ($candidate in @('compose.yaml', 'compose.yml', 'docker-compose.yml', 'docker-compose.yaml')) {
            $path = Join-Path $root $candidate
            if (Test-Path -LiteralPath $path -PathType Leaf) { $ComposeFile = $path; break }
        }
    }
    elseif (-not [System.IO.Path]::IsPathRooted($ComposeFile)) { $ComposeFile = Join-Path $root $ComposeFile }
    if (-not $ComposeFile -or -not (Test-Path -LiteralPath $ComposeFile -PathType Leaf)) { throw 'Arquivo Compose não encontrado na raiz do projeto.' }
    $docker = Get-Command docker -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $docker) { throw 'Docker não encontrado. Abra o Docker Desktop e confira docker version no terminal.' }
    $context = [pscustomobject]@{ ProjectRoot = $root; ComposeFile = [System.IO.Path]::GetFullPath($ComposeFile); Service = $Service; Docker = $docker.Source; ContainerId = ''; TimeoutSeconds = $TimeoutSeconds }
    $output = Invoke-LentisNative -Executable $context.Docker -WorkingDirectory $root -Arguments @('compose', '--project-directory', $root, '-f', $context.ComposeFile, 'ps', '-q', $Service) -TimeoutSeconds $TimeoutSeconds
    $containers = @($output -split '\r?\n' | Where-Object { $_.Trim() })
    if ($containers.Count -ne 1 -or $containers[0].Trim() -notmatch '^[a-fA-F0-9]{12,64}$') {
        throw "É necessário exatamente um contêiner em execução no serviço '$Service'. Confira docker compose ps."
    }
    $context.ContainerId = $containers[0].Trim()
    return $context
}

function Invoke-LentisShell {
    param($Context, [string]$Script, [string[]]$Parameters = @(), [int]$TimeoutSeconds = 0)
    if (-not $TimeoutSeconds) { $TimeoutSeconds = $Context.TimeoutSeconds }
    # Código textual por stdin; o arquivo .dump nunca passa pelo pipeline PowerShell.
    return Invoke-LentisNative -Executable $Context.Docker -WorkingDirectory $Context.ProjectRoot -Arguments (@('exec', '-i', $Context.ContainerId, 'sh', '-s', '--') + $Parameters) -InputText $Script -TimeoutSeconds $TimeoutSeconds
}

function Get-LentisShellHeader {
    return @'
set -eu
: "${POSTGRES_USER:?POSTGRES_USER is required in the database container}"
: "${POSTGRES_DB:?POSTGRES_DB is required in the database container}"
unset PGHOSTADDR PGSERVICE PGSERVICEFILE
export PGHOST=/var/run/postgresql
export PGPORT=5432
export PGCLIENTENCODING=UTF8
export PGCONNECT_TIMEOUT=15
if [ -n "${POSTGRES_PASSWORD:-}" ]; then
  PGPASSWORD=$POSTGRES_PASSWORD; export PGPASSWORD
elif [ -n "${POSTGRES_PASSWORD_FILE:-}" ]; then
  PGPASSWORD=$(cat "$POSTGRES_PASSWORD_FILE"); export PGPASSWORD
fi
'@
}

function Get-LentisDatabaseInfo {
    param($Context, [string]$Database = '')
    $script = (Get-LentisShellHeader) + "`n" + @'
# LENTIS_ACTION: metadata
if [ -n "${1:-}" ]; then target=$1; else target=$POSTGRES_DB; fi
psql -X -q -A -t --no-password -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$target" <<'SQL'
BEGIN READ ONLY;
SELECT json_build_object(
 'database', current_database(), 'user', current_user,
 'server_version', current_setting('server_version'),
 'server_version_num', current_setting('server_version_num')::integer,
 'encoding', current_setting('server_encoding'),
 'size_bytes', pg_database_size(current_database()),
 'is_lentis', to_regclass('public.django_migrations') IS NOT NULL
   AND to_regclass('public.accounts_user') IS NOT NULL
   AND to_regclass('public.organizations_company') IS NOT NULL
   AND to_regclass('public.organizations_store') IS NOT NULL
);
COMMIT;
SQL
'@
    $raw = Invoke-LentisShell -Context $Context -Script $script -Parameters @($Database)
    try { $metadata = $raw | ConvertFrom-Json -ErrorAction Stop } catch { throw 'O PostgreSQL não retornou metadados JSON válidos.' }
    if ($metadata.is_lentis -ne $true) { throw 'O banco selecionado não contém as tabelas básicas do Lentis. Operação interrompida.' }
    return $metadata
}

function Copy-LentisContainerFile {
    param($Context, [string]$RemotePath, [string]$LocalPath, [switch]$ToContainer)
    $remote = $Context.ContainerId + ':' + $RemotePath
    $arguments = if ($ToContainer) { @('cp', $LocalPath, $remote) } else { @('cp', $remote, $LocalPath) }
    $null = Invoke-LentisNative -Executable $Context.Docker -WorkingDirectory $Context.ProjectRoot -Arguments $arguments -TimeoutSeconds $Context.TimeoutSeconds
}

function Remove-LentisContainerFile {
    param($Context, [string]$RemotePath)
    if ($RemotePath -notmatch '^/tmp/lentis-(backup|restore)-[a-f0-9]{32}\.dump$') { throw 'Caminho temporário não permitido.' }
    $script = "set -eu`n# LENTIS_ACTION: remove-file`nrm -f -- " + '"$1"' + "`n"
    $null = Invoke-LentisShell -Context $Context -Script $script -Parameters @($RemotePath) -TimeoutSeconds 60
}

function Write-LentisJson {
    param([string]$Path, $Value)
    $json = $Value | ConvertTo-Json -Depth 12
    [System.IO.File]::WriteAllText($Path, $json, (New-Object System.Text.UTF8Encoding($false)))
}

function Test-LentisArchive {
    param([string]$BackupFile)
    $path = Get-LentisLocalPath $BackupFile
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Backup não encontrado: $path" }
    $manifestPath = Join-Path ([System.IO.Path]::GetDirectoryName($path)) 'manifest.json'
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw 'manifest.json não encontrado junto ao backup.' }
    try { $manifest = [System.IO.File]::ReadAllText($manifestPath, [System.Text.Encoding]::UTF8) | ConvertFrom-Json -ErrorAction Stop }
    catch { throw 'O manifesto do backup não é um JSON válido.' }
    foreach ($required in @('format_version','app','archive','bytes','sha256','source')) {
        if ($null -eq $manifest.PSObject.Properties[$required]) { throw 'O manifesto do backup está incompleto.' }
    }
    if ($manifest.format_version -ne 1 -or $manifest.app -ne 'lentis-erp' -or $manifest.archive -ne [System.IO.Path]::GetFileName($path)) { throw 'O manifesto não corresponde ao backup Lentis selecionado.' }
    if ($manifest.sha256 -notmatch '^[a-fA-F0-9]{64}$') { throw 'SHA256 inválido no manifesto.' }
    $file = Get-Item -LiteralPath $path
    if ($file.Length -le 0 -or $file.Length -ne $manifest.bytes) { throw 'O tamanho do arquivo difere do manifesto. Restauração não iniciada.' }
    $hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
    if ($hash -ne $manifest.sha256) { throw 'O SHA256 do backup não confere. Restauração não iniciada.' }
    return [pscustomobject]@{ BackupFile = $path; Manifest = $manifest; Sha256 = $hash }
}

function Assert-LentisTemporaryDatabase {
    param([string]$Database, [string]$SourceDatabase)
    if ($Database -notmatch '^lentis_restore_test_[a-f0-9]{32}$' -or $Database -eq $SourceDatabase) {
        throw 'A operação exige um banco temporário exclusivo, diferente do banco original.'
    }
}

Export-ModuleMember -Function ConvertTo-LentisNativeArgument, Invoke-LentisNative, Get-LentisContext, Invoke-LentisShell, Get-LentisShellHeader, Get-LentisDatabaseInfo, Copy-LentisContainerFile, Remove-LentisContainerFile, Write-LentisJson, Test-LentisArchive, Assert-LentisTemporaryDatabase, Get-LentisLocalPath
