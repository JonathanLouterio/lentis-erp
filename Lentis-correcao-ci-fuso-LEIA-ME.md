# Lentis — correção do CI na validade de orçamentos

Base: branch feat/meu-perfil, commit d642648.
Extraia o conteúdo diretamente na raiz C:\Projetos\lentis-erp.
O pacote contém o arquivo de testes corrigido e este guia.

## Causa confirmada

Os dois CIs do commit 840c12e falharam no mesmo teste:
`sales.test_quote_permissions.QuotePermissionTests.test_expired_quote_and_wrong_state_remain_blocked`.
O frontend e a imagem Docker passaram; o backend teve uma falha entre 683 testes.

O teste usava `timezone.localdate()` no fuso padrão UTC, enquanto a propriedade
`Quote.is_expired` utiliza explicitamente America/Sao_Paulo. Às 00:45 UTC de
04/11/2026, ainda eram 21:45 de 03/11 em São Paulo. A validade montada como
“ontem em UTC” correspondia ao dia atual da regra de negócio, e o orçamento
continuava válido. Assim, o envio retornava 200 enquanto o teste esperava 400.

Reproduzi a falha congelando o relógio em 04/11/2026 01:00 UTC. Após a correção,
o mesmo cenário passou.

## Alteração

Somente `backend/sales/test_quote_permissions.py` é alterado:

- Datas dos cenários usam o fuso explícito de São Paulo.
- O teste que falhou usa um relógio fixo na janela em que UTC e São Paulo
  estão em datas diferentes, para reproduzir sempre a condição do CI.
- Novos testes conferem o limite de 23:59:59 e 00:00 em São Paulo, incluindo
  execução com fuso ativo UTC, São Paulo e Tóquio.
- Confere também que um orçamento válido hoje em São Paulo ainda pode ser
  preparado após a meia-noite UTC.

A regra de negócio permanece: orçamento é válido durante toda a data de
validade em São Paulo e fica vencido no dia seguinte. Não há migração nem
alteração de modelos, serviços, permissões, dados ou configuração do CI.

## Aplicar e testar

Mantenha a correção na branch Meu perfil antes de integrar na main:

```powershell
Set-Location C:\Projetos\lentis-erp
git switch feat/meu-perfil

& .\.venv\Scripts\python.exe backend\manage.py test sales.test_quote_permissions --verbosity 2
```

São 22 testes neste arquivo. Depois que passarem:

```powershell
git add backend/sales/test_quote_permissions.py Lentis-correcao-ci-fuso-LEIA-ME.md
git diff --cached --check
git --no-pager diff --cached --stat
```

Revise o resumo (apenas o teste e este guia). Registre e envie:

```powershell
git commit -m "test: corrige fuso horario nos testes de validade de orcamentos"
git push origin feat/meu-perfil
```

O push aciona uma nova execução do GitHub Actions. Aguarde essa execução verde
antes de integrar Meu perfil na main. As execuções antigas continuam mostrando
seu resultado histórico; acompanhe a do novo commit.

Validação local desta correção: reprodução antes/depois com relógio fixo e
conjunto de orçamentos/permissões/impressão com 46 testes, 45 aprovados e um
omitido porque exige concorrência real em PostgreSQL. Aqui foi usado SQLite
apenas para testes. O PostgreSQL local/CI valida a integração final.

Regressão completa após a correção: 715 testes encontrados, 692 aprovados e
23 omitidos por exigirem PostgreSQL. Não foram alteradas as opções de execução
ou os critérios do GitHub Actions.
