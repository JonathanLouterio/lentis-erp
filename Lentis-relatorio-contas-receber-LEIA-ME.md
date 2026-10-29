# Lentis — Relatório gerencial de contas a receber

Entrega: 28/10/2026. Depende das etapas anteriores, incluindo entrada/acréscimo já aplicada e integrada à main.

## Conteúdo

- Consulta em **Gestão > Relatórios > Contas a receber**.
- Resumo de valor original, recebido líquido, saldo aberto, dentro do prazo, a vencer, total vencido e acima de 90 dias.
- Faixas de atraso com saldos e contagem de parcelas: 1–30, 31–60, 61–90 e acima de 90 dias.
- Filtros por cliente registrado, venda, forma de pagamento, situação, responsável, prazo/cor e faixa de atraso.
- Todos os vencimentos ou período de até 366 dias. O modo completo permite ver dívidas antigas sem ficar limitado ao mês atual.
- Verde: prazo além da janela; amarelo: vencimento de hoje até a janela; vermelho: 1–90 dias; preto: mais de 90 dias; cinza: quitada.
- Janela amarela padrão de 7 dias, ajustável de 1 a 90 dias nessa consulta. Ao abrir uma nova consulta, o padrão continua sendo 7 dias.
- Exportação CSV completa e impressão com opção de salvar PDF pelo navegador.

**Não há migração nova, dependência nova ou alteração de saldos.** O relatório usa os registros existentes e não efetua cobranças.

## Aplicação no VS Code

Antes de extrair, na raiz do projeto e com a etapa anterior salva:

```powershell
cd C:\Projetos\lentis-erp
git switch main
git pull --ff-only origin main
git switch -c feat/relatorio-contas-receber
```

Pare temporariamente os servidores (Ctrl+C) e extraia este ZIP na raiz `C:\Projetos\lentis-erp`, preservando as pastas e substituindo somente os arquivos do pacote.

Com a `.venv` ativa:

```powershell
cd C:\Projetos\lentis-erp
python backend\manage.py check
python backend\manage.py makemigrations --check --dry-run
python backend\manage.py test sales.test_receivable_report sales.test_reports sales.test_insight_permissions --verbosity 2
cd frontend
npm run build
```

A verificação dirigida deve encontrar **53 testes**. Para a regressão completa, na raiz:

```powershell
python backend\manage.py test accounts organizations sales purchases --verbosity 2
```

Na base correspondente às entregas anteriores, a regressão completa encontra **639 testes**.

Reinicie em terminais separados:

```powershell
cd C:\Projetos\lentis-erp
python backend\manage.py runserver 127.0.0.1:8000
```

```powershell
cd C:\Projetos\lentis-erp\frontend
npm run dev
```

## Uso e conferência

1. Entre em Gestão > Relatórios > Contas a receber.
2. Confira a unidade selecionada. Todos os vencimentos vem marcado; desmarque para selecionar um período.
3. Use os filtros e clique em Aplicar filtros. Enquanto houver alterações não aplicadas, exportação e impressão ficam indisponíveis.
4. Na base de testes, confira uma parcela futura além de 7 dias (verde), próxima/hoje (amarelo), atrasada até 90 dias (vermelho), acima de 90 dias (preto) e quitada (cinza).
5. Ajuste a janela amarela para 10 dias. Uma parcela que vence em 8 dias deve mudar de verde para amarelo depois de aplicar.
6. Confira recebimentos parciais: apenas o saldo pendente entra nas faixas de atraso. Após quitação, o destaque fica cinza.
7. Aplique filtro de cliente, venda ou faixa e confira se cartões/resumos usam todos os resultados, inclusive outras páginas.
8. Exportar CSV inclui todas as páginas, até 20.000 registros. O CSV tem rótulos de prazo e dias de atraso, sem cores de planilha.
9. Imprimir / Salvar PDF abre outra aba com todos os registros filtrados, até 2.000 parcelas. Use Ctrl+P e escolha a impressora ou Salvar como PDF. Se houver mais de 2.000, refine os filtros.
10. Confira temas claro/escuro e acesso de usuário de consulta sem exportação.

Datas/dias de atraso seguem São Paulo. Hoje não é vencido; 90 dias é vermelho; 91 é preto. Faixas consideram saldo atual, inclusive recebimentos posteriores ao período de vencimento selecionado.

O indicador Total vencido já inclui o valor Acima de 90 dias. Não some esses dois cartões. Valor original já inclui o acréscimo registrado na venda; nenhum acréscimo novo é calculado no relatório.

## Permissões

- Consulta: `sales.view_reports` e `sales.view_receivable`, com acesso ativo à unidade.
- CSV e impressão/PDF: as permissões de consulta e `sales.export_reports`.
- Não há novos direitos nem concessão automática. Quem só consulta não vê os botões de exportação/impressão. A URL também verifica as permissões.
- A janela do relatório e a impressão não mostram cadastro clínico, receitas ou dados de outras unidades.

## Verificações realizadas

- 53 testes dirigidos passaram, incluindo limites dos prazos, saldos parciais/estornos, filtros, paginação, impressão, CSV, isolamento de unidade e revogação.
- Regressão local: 639 testes encontrados, sem falhas, com 19 cenários exclusivos de PostgreSQL pulados no ambiente SQLite.
- O executor local usa hash de senha simplificado somente nos testes para acelerar a regressão. Nenhuma configuração de senha do projeto é alterada.
- Verificação de modelos sem migrações pendentes e build TypeScript/Vite concluídos.
- Fluxo pelo navegador validado: cinco cores, filtros, janela ajustável, CSV, impressão/PDF, tema escuro, mobile e revogação de exportação.
- Execute no seu PostgreSQL para validar os cenários que exigem locks/concorrência.

## Salvar no Git após conferir

```powershell
cd C:\Projetos\lentis-erp
git add backend/sales/receivable_report.py
git add backend/sales/report_print.py
git add backend/sales/report_services.py
git add backend/sales/report_views.py
git add backend/sales/templates/sales/receivable_report_print.html
git add backend/sales/test_receivable_report.py
git add docs/regras-negocio.md
git add frontend/src/api.ts
git add frontend/src/components/Reports.css
git add frontend/src/components/Reports.tsx
git add Lentis-relatorio-contas-receber-LEIA-ME.md
git diff --cached --check
git --no-pager diff --cached --stat
git commit -m "feat: amplia relatorio de contas a receber com faixas cores e impressao"
git push -u origin feat/relatorio-contas-receber
git status
```

Não inclua RARs, imagens soltas ou arquivos de referência antigos neste commit.
