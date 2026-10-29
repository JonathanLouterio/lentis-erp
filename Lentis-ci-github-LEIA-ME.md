# Lentis — validação automática no GitHub

Este pacote adiciona `.github/workflows/ci.yml`. Extraia na raiz
`C:\Projetos\lentis-erp`, preservando a pasta `.github`.

## O que será executado

A cada push em uma branch e em pull requests destinados à `main`, o workflow
**Lentis CI** executará duas tarefas independentes:

| Tarefa | Verificações |
| --- | --- |
| Backend | Python 3.14, instalação de `backend/requirements.txt`, `pip check`, configuração Django, migrações ausentes, aplicação de migrações e todos os testes Django |
| Frontend | Node 24, instalação com `npm ci` e `npm run build` para conferir TypeScript e gerar o build |

O backend usa PostgreSQL 17 criado no runner do GitHub, com dados descartáveis.
As credenciais presentes no YAML servem somente para esse banco. Não é necessário
cadastrar secrets nem copiar seu `.env`. O banco local e os backups não são acessados.

As actions oficiais estão fixadas por SHA. As dependências do projeto continuam
definidas pelos arquivos já versionados. O workflow não publica o sistema.

## Instalação e primeiro envio

No PowerShell do VS Code, crie a branch antes de extrair:

```powershell
cd C:\Projetos\lentis-erp
git switch main
git pull --ff-only origin main
git switch -c feat/ci-github-actions
```

Se algum comando falhar, resolva o erro antes de continuar.
Extraia o ZIP na raiz do projeto e confira:

```powershell
Test-Path .github\workflows\ci.yml
git status --short
```

O primeiro comando deve retornar `True`. Evite deixar os arquivos dentro de uma
pasta adicional com o nome do ZIP.

Versione somente os dois arquivos deste pacote:

```powershell
git add .github/workflows/ci.yml Lentis-ci-github-LEIA-ME.md
git diff --cached --check
git --no-pager diff --cached --stat
git commit -m "ci: valida backend com PostgreSQL e build do frontend"
git push -u origin feat/ci-github-actions
```

## Conferência no GitHub

Abra https://github.com/JonathanLouterio/lentis-erp/actions e selecione **Lentis CI**.
A execução do commit enviado deve apresentar as duas tarefas concluídas:

- **Backend - Django e PostgreSQL**
- **Frontend - TypeScript e build**

A suíte completa pode levar vários minutos. O limite do backend é de 60 minutos;
o do frontend é de 20 minutos. Aguarde ambas ficarem verdes antes de integrar à `main`.

Se uma tarefa falhar, abra a etapa em vermelho e consulte a mensagem do erro.
O teste de migrações também falhará quando houver mudanças de modelos sem a
migração correspondente. Nesse caso, gere e revise a migração localmente e
versione-a; o workflow não cria migrações automaticamente.

Depois de integrado à `main`, também será possível iniciar uma execução manual
na página do workflow, pelo botão **Run workflow**. Push e pull request podem
gerar execuções separadas do mesmo código.

Este workflow fornece verificações automáticas. Torná-las obrigatórias para
permitir merges exige uma configuração separada das regras de proteção da branch.

## Validação deste pacote

Foram conferidos o schema do workflow, a sintaxe dos comandos, os parâmetros das
actions nos SHAs indicados, a consistência das variáveis do banco e a compatibilidade
entre o `package.json` e o lockfile da `main` consultada.

A primeira execução real com PostgreSQL no GitHub depende do push deste arquivo.
Não é necessário repetir todo o fluxo manual de compras já validado para instalar
este pacote.

Referência: https://docs.github.com/en/actions/tutorials/use-containerized-services/create-postgresql-service-containers
