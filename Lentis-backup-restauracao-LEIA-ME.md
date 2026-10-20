# Lentis ERP — backup e restauração de teste

Pacote para a base `52e4ffe`, após relatórios gerenciais. Trabalhe na branch `feat/backup-restauracao` já criada. Extraia na raiz `C:\Projetos\lentis-erp`, mantendo as pastas do ZIP.

## O que entrou

- `scripts/Backup-Lentis.ps1`: backup lógico do PostgreSQL do Docker.
- `scripts/Test-Restore-Lentis.ps1`: restauração em um banco temporário exclusivo, conferência e limpeza.
- `scripts/Backup-E-Teste-Lentis.ps1`: executa as duas etapas em sequência e só informa sucesso depois de concluir o teste.
- `scripts/Lentis.Backup.psm1`: funções compartilhadas.
- `scripts/tests/Test-LentisBackupScripts.ps1`: testes locais sem Docker.
- `backups/.gitignore`: mantém dumps, manifestos e relatórios gerados fora do Git.

Não há alteração no Django, frontend, banco de trabalho ou Compose. Não é necessário gerar migrations, atualizar requirements ou executar build.

## Execute agora

Abra o Docker Desktop. Na raiz do projeto, confira o banco e execute o fluxo completo:

```powershell
cd C:\Projetos\lentis-erp
docker compose ps
.\scripts\Backup-E-Teste-Lentis.ps1
```

Se o banco estiver parado:

```powershell
docker compose up -d --wait db
.\scripts\Backup-E-Teste-Lentis.ps1
```

Não precisa ativar a `.venv`, instalar PostgreSQL no Windows ou parar o backend para uma cópia normal. Evite executar migrations durante o backup. Os utilitários usados são os do contêiner `db`; o PostgreSQL do Windows na porta 5432 não participa deste fluxo. A porta publicada 5434 do Lentis também não precisa ser informada.

O fluxo combinado:

1. Confere o projeto, o contêiner e as tabelas básicas do Lentis.
2. Gera o dump e verifica se o catálogo do arquivo é legível.
3. Copia o arquivo binário pelo Docker e calcula SHA-256.
4. Grava o manifesto e publica a pasta completa do backup.
5. Confere tamanho e hash antes de iniciar a restauração.
6. Cria um banco `lentis_restore_test_<GUID>` no mesmo PostgreSQL.
7. Restaura nesse banco, interrompendo no primeiro erro.
8. Confere tabelas, migrations e contagens restauradas.
9. Remove o banco e o arquivo temporários e grava o relatório.

## Resultado esperado

Ao terminar, o terminal mostra caminhos e indicadores semelhantes a:

```text
BackupFile               C:\Projetos\lentis-erp\backups\lentis-...\database.dump
ManifestFile             C:\Projetos\lentis-erp\backups\lentis-...\manifest.json
ReportFile               C:\Projetos\lentis-erp\backups\restore-tests\restore-....json
RestoreTested            True
TemporaryDatabaseRemoved True
TablesChecked            ...
MigrationsChecked        ...
```

Confira principalmente `RestoreTested=True` e `TemporaryDatabaseRemoved=True`. A quantidade de tabelas e migrations depende do estado do seu projeto.

Se aparecer erro, envie a mensagem e o caminho do relatório, se houver. Não envie o dump nem senhas. O script falha em vez de apresentar sucesso quando o restore ou a limpeza não termina.

## Onde ficam os arquivos

```text
backups/
  .gitignore
  lentis-AAAAMMDD_HHMMSS_mmm-xxxxxxxx/
    database.dump
    manifest.json
  restore-tests/
    restore-AAAAMMDD_HHMMSS_mmm-xxxxxxxx.json
```

Horários dos nomes e do JSON usam UTC. Cada execução cria uma pasta nova. Guarde o par `database.dump` + `manifest.json` junto: o teste exige ambos.

Dumps contêm os dados do sistema, incluindo clientes, usuários e receitas. Guarde cópias em local privado e mantenha uma cópia fora do computador de trabalho. A pasta ignorada pelo Git evita commits acidentais, mas não é criptografia nem uma cópia externa. O script não faz envio externo nem apaga backups antigos.

## Comandos separados

Só criar o backup:

```powershell
cd C:\Projetos\lentis-erp
$backupLentis = .\scripts\Backup-Lentis.ps1
$backupLentis
```

Testar o backup retornado, na mesma sessão:

```powershell
.\scripts\Test-Restore-Lentis.ps1 -BackupFile $backupLentis.BackupFile
```

Testar um backup antigo, informando o caminho real do arquivo:

```powershell
.\scripts\Test-Restore-Lentis.ps1 -BackupFile "C:\Projetos\lentis-erp\backups\PASTA_DO_BACKUP\database.dump"
```

`PASTA_DO_BACKUP` é um exemplo: substitua pela pasta existente. Não é criada automaticamente.

## Opções

Salvar os novos backups em outra pasta:

```powershell
.\scripts\Backup-E-Teste-Lentis.ps1 -BackupDirectory "D:\Backups\Lentis"
```

O relatório de teste continua em `backups\restore-tests` do projeto. Para mudar também o relatório:

```powershell
.\scripts\Backup-E-Teste-Lentis.ps1 -BackupDirectory "D:\Backups\Lentis" -ReportDirectory "D:\Backups\Lentis\testes"
```

Pasta relativa de backup ou relatório é interpretada a partir da raiz do projeto. O `-BackupFile` relativo usa a pasta atual do PowerShell. Caminhos com espaços, acentos e colchetes são aceitos.

Se o nome do serviço ou arquivo Compose mudar:

```powershell
.\scripts\Backup-E-Teste-Lentis.ps1 -Service db -ComposeFile compose.yaml
```

Para um banco grande, o limite padrão é 1.800 segundos por operação. Pode ser ajustado:

```powershell
.\scripts\Backup-E-Teste-Lentis.ps1 -TimeoutSeconds 3600
```

## Testes locais dos scripts

O teste abaixo valida sintaxe, codificação, hash e proteções de nomes. Usa arquivos fictícios na pasta temporária do Windows, sem acessar Docker ou banco:

```powershell
.\scripts\tests\Test-LentisBackupScripts.ps1
```

Resultado esperado: `Success=True` e `DockerAccessed=False`. Isso não substitui o teste de restauração real com `Backup-E-Teste-Lentis.ps1`.

Os scripts foram escritos para Windows PowerShell 5.1 e PowerShell 7, com UTF-8 **com BOM** para preservar os acentos no Windows PowerShell. Se o Windows bloquear a execução de um arquivo baixado, desbloqueie o ZIP em Propriedades antes de extrair. Não é necessário executar como administrador quando seu usuário já consegue usar o Docker.

## Limites do teste

- Restaura apenas no banco temporário gerado pelo script. Não oferece parâmetro para substituir o banco de trabalho.
- A conta PostgreSQL configurada no contêiner precisa conseguir ler o banco e criar/remover o banco temporário. No ambiente inicial do projeto, ela é a conta criada pela imagem do PostgreSQL.
- O teste usa conexão local ao PostgreSQL dentro do contêiner e ferramentas da própria imagem.
- O dump é do banco, não dos arquivos da aplicação, `.env`, mídias, roles ou configurações globais do servidor. Mantenha cópias próprias desses itens.
- O restore de teste ignora proprietários e ACLs e usa a conta atual. Ele confere dados e estrutura, não a reprodução exata de permissões do servidor original.
- As contagens registradas são do banco restaurado. Não comparamos com um banco original que pode receber novos registros durante a cópia.
- Interromper o processo à força, desligar o Docker ou perder energia pode impedir o `finally`. Nesse caso, confira o nome temporário exibido e peça orientação antes de remover qualquer banco. O script nunca remove um banco quando sua criação retornou erro.
- SHA-256 detecta divergência em relação ao manifesto; não autentica a origem de um backup. Restaure somente arquivos de origem conhecida.
- Não há agendamento, retenção automática, nuvem ou recuperação sobre o banco real nesta etapa.

## Validação deste pacote

Foram executadas verificações de parser PowerShell, sintaxe shell e SQL, testes locais e cenários com adaptador Docker simulado: sucesso, serviço ausente/ambíguo, falha de dump, cópia, restore, inspeção, criação e limpeza, além de arquivo alterado e nomes com caracteres especiais. A cópia binária preservou todos os valores de byte.

A execução local usou PowerShell 7.4 em Linux. Não há daemon Docker nem PostgreSQL em execução neste ambiente; por isso a restauração real e a execução no Windows PowerShell 5.1 precisam ser confirmadas no seu computador pelo comando principal acima. Os scripts e o pacote não contêm suas credenciais nem um dump real.

## Referências técnicas

- [PostgreSQL 17 — pg_dump](https://www.postgresql.org/docs/17/app-pgdump.html)
- [PostgreSQL 17 — pg_restore](https://www.postgresql.org/docs/17/app-pgrestore.html)
- [PostgreSQL 17 — createdb](https://www.postgresql.org/docs/17/app-createdb.html)
- [PostgreSQL 17 — dropdb](https://www.postgresql.org/docs/17/app-dropdb.html)
- [Docker — copiar arquivos de/para contêiner](https://docs.docker.com/reference/cli/docker/container/cp/)
- [Microsoft — codificação de caracteres no PowerShell](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_character_encoding)

Após a execução, envie o resultado dos indicadores e depois `git branch --show-current` e `git status --short`. Os arquivos antigos pendentes, o logo solto e as cópias de apoio continuam fora desta etapa.
