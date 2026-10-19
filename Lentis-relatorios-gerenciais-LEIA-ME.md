# Lentis ERP — relatórios gerenciais

Pacote incremental para a base `b48ace5`, com contas a pagar já integradas. Contém arquivos completos em UTF-8. Trabalhe na branch `feat/relatorios-gerenciais` já criada e extraia na raiz `C:\Projetos\lentis-erp`, substituindo os arquivos correspondentes e mantendo as pastas do ZIP.

## O que entrou

Menu **Gestão → Relatórios**, com quatro consultas:

| Relatório | Período aplicado sobre | Resultado |
|---|---|---|
| Vendas finalizadas | Data de finalização | Quantidade, total vendido, ticket e vendas detalhadas |
| Movimentações registradas | Data de registro | Entradas, saídas, variação líquida e lançamentos com sinal |
| Contas a receber | Vencimento | Valor original, recebido líquido, saldo e atraso atuais |
| Contas a pagar | Vencimento | Valor original, pago líquido, saldo e atraso atuais |

Todos consultam apenas a unidade selecionada. Totais consideram todos os resultados, além da página mostrada. Filtros incluem datas, situação das parcelas, cliente/operadora e direção/conta financeira conforme o relatório.

O botão **Exportar CSV** baixa os resultados de todas as páginas dos filtros aplicados. Ao alterar um filtro, clique em **Aplicar filtros** para atualizar resultados e liberar a exportação correspondente.

## Instalação e validação no PowerShell

Pare o Django e o Vite com Ctrl+C antes de substituir os arquivos. Com a `.venv` ativa, após extrair:

```powershell
cd C:\Projetos\lentis-erp
python backend\manage.py check
python backend\manage.py test sales.test_reports --verbosity 2
cd C:\Projetos\lentis-erp\frontend
npm run build
```

Este módulo não altera modelos, não exige migrations novas e não instala dependências. Mantém os cadastros, regras, saldos e operações existentes.

Para abrir a aplicação, use dois terminais:

```powershell
cd C:\Projetos\lentis-erp
python backend\manage.py runserver 127.0.0.1:8000
```

```powershell
cd C:\Projetos\lentis-erp\frontend
npm run dev
```

## Permissões

O superusuário ativo pode testar os quatro relatórios nas unidades autorizadas. Para usuários comuns, conceda as permissões existentes por usuário ou grupo, no admin:

| Relatório | Permissões necessárias |
|---|---|
| Vendas | `sales.view_sale` |
| Contas a receber | `sales.view_receivable` |
| Contas a pagar | `purchases.view_payableplan` |
| Movimentações | `sales.view_financialentry` **e** `purchases.view_payableplan` |

O vínculo com a unidade também precisa estar ativo. Staff sozinho não libera os relatórios. O menu mostra apenas os tipos autorizados e a API repete essa verificação, inclusive para o CSV.

## Conferência visual

1. Acesse **Gestão → Relatórios**. Selecione o período e clique em **Aplicar filtros**.
2. Em **Vendas finalizadas**, compare quantidade e valor com vendas finalizadas do mesmo período. Rascunhos e canceladas ficam fora.
3. Em **Movimentações registradas**, confira um recebimento, um pagamento a fornecedor e seus estornos. Entradas têm sinal positivo; saídas, negativo. Teste direção e conta.
4. Em **Contas a receber**, compare saldos parciais, quitados e vencidos. Teste a separação entre cliente e operadora.
5. Em **Contas a pagar**, compare parcelas e pagamentos com o módulo de compras. Uma compra recebida sem plano de parcelas ainda não aparece aqui.
6. Altere uma data e confira que o CSV fica indisponível até aplicar os filtros. Exporte e abra no Excel ou outro leitor de CSV.
7. Havendo mais de uma página, confira que o total dos cartões não muda ao paginar e que o CSV traz todas as páginas.
8. Teste outra unidade e um usuário sem permissões. Nenhum dado da unidade anterior deve aparecer.

## Significado dos números

- **Vendas** usam data de finalização, preços e descontos registrados nos itens e desconto global. Não somamos vendas com seus recebimentos, pois uma venda pode ser parcelada ou recebida em outra data.
- **Movimentações** usam a data de registro. O pagamento a fornecedor pode ter uma data informada anterior; ela aparece em coluna própria. Recebimentos usam o dia do registro por não terem uma data efetiva separada.
- A **variação líquida registrada** soma entradas menos saídas do filtro. Não representa lucro, DRE ou extrato bancário. Abertura e movimentos manuais de caixa não entram nessa conta. O registro financeiro que também aparece no caixa físico é contado uma única vez.
- Estornos ficam no dia em que foram registrados, com o sinal oposto ao lançamento original. Recebimentos e estornos de vendas canceladas continuam no histórico financeiro.
- **Parcelas** usam vencimento no período e saldo atual. Baixas posteriores ao fim do período continuam abatendo a dívida. Não é um relatório de posição histórica naquela data final.
- **Vencida** significa saldo positivo e vencimento anterior ao dia atual em São Paulo. A parcela que vence hoje ainda não está atrasada.
- **Em aberto** inclui pagamentos parciais. Os cartões somam somente as linhas que atendem aos filtros atuais. Um filtro de vencimentos deste mês não inclui dívidas vencidas em outros meses.
- Consultas usam o estado atual. Se uma venda foi cancelada depois, ela deixa de aparecer como finalizada mesmo ao pesquisar seu período original. Os registros financeiros de recebimento e estorno continuam consultáveis.

## CSV

- UTF-8 com BOM, separado por ponto e vírgula, com vírgula decimal e datas brasileiras.
- Exporta todas as páginas dos filtros aplicados, até **20.000 registros**. Acima disso, refine datas ou outros filtros; não há truncamento silencioso ou arquivo parcial.
- Contas financeiras inativas continuam disponíveis nos filtros para consulta de lançamentos antigos.
- Campos livres que possam virar fórmulas em planilhas recebem um apóstrofo de proteção. Valores monetários mantêm o sinal numérico.
- Colunas de recebimento financeiro usam os nomes atuais da conta/forma. Pagamentos a fornecedores preservam os nomes copiados no lançamento; fornecedores de compras recebidas usam a cópia da compra.

## Validação do pacote

Build TypeScript/Vite e testes de API verificados em ambiente isolado com dados fictícios. A conferência no navegador incluiu filtros, totais, download real de CSV, 26 parcelas em duas páginas, CSV com todas as linhas, permissões, tema escuro e largura de celular.

A regressão local passou em 390 casos, com 17 testes de locks ignorados por exigirem PostgreSQL. Após reforçar a proteção contra exportação acima do limite, o módulo final passou em 22 testes específicos. A validação local utiliza SQLite e modelos de apoio. Rode os testes de relatórios acima no PostgreSQL Docker do seu projeto para verificar a integração e o SQL reais.

## Arquivos do pacote

- Backend: `sales/report_services.py`, `sales/report_views.py`, `sales/test_reports.py` e `sales/urls.py`.
- Frontend: `api.ts`, `components/AppLayout.tsx`, `components/Reports.tsx` e `components/Reports.css`.
- Documentação: este guia e `docs/regras-negocio.md`.

Após testes e conferência visual, envie `git branch --show-current` e `git status --short` para separar o commit. Preserve fora dele o logo solto, `backend/organizations/Product-model.txt`, `regras-negocio.md` da raiz e a alteração antiga em `Lentis-regras-comerciais-LEIA-ME.md`.
