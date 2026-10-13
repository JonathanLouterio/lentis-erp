# Lentis — Dashboard operacional

Esta etapa substitui o painel provisório da Visão geral por indicadores reais da unidade. Os arquivos são completos, em UTF-8, e o pacote pressupõe que as etapas de caixa e parcelamento já estão instaladas.

## Instalação no VS Code

Pare Django e Vite nos terminais com Ctrl+C. Na raiz do projeto:

```powershell
cd C:\Projetos\lentis-erp
git switch -c feat/dashboard-operacional
```

Extraia o ZIP nessa raiz, substituindo os arquivos correspondentes e preservando as pastas. `api.ts` fica em `frontend/src`; `AppLayout.tsx`, `Sales.tsx`, `Dashboard.tsx` e `Dashboard.css` ficam em `frontend/src/components`.

Execute:

```powershell
python backend\manage.py check
python backend\manage.py test sales organizations --verbosity 2
cd frontend
npm run build
```

Esta etapa não altera modelos de banco e não exige uma nova migração. Reinicie o backend e o frontend em terminais separados:

```powershell
cd C:\Projetos\lentis-erp
python backend\manage.py runserver
```

```powershell
cd C:\Projetos\lentis-erp\frontend
npm run dev
```

Abra **Visão geral** no frontend. Os valores já registrados nas etapas anteriores aparecem automaticamente.

## O que aparece

- Vendas e ticket médio do período, comparação com o período anterior de mesma duração.
- Recebido líquido, com valor bruto recebido e estornos separados.
- Saldo atual a receber dos clientes; recebíveis da operadora ficam separados.
- Gráfico diário de vendas ou recebimentos líquidos, com consulta do valor ao passar o ponteiro e tabela acessível dos dados. Um período de um dia é representado por uma barra.
- Alertas de parcelas do cliente vencidas/que vencem hoje, produtos negativos e produtos no mínimo ou abaixo.
- Dinheiro previsto nos caixas atualmente abertos, com seus responsáveis.
- Até cinco produtos para reposição, cinco vendas finalizadas recentes e cinco parcelas do cliente vencidas/com vencimento hoje.
- Atalhos para nova venda, novo cliente, financeiro, caixa e estoque; vendas recentes abrem diretamente o atendimento e produtos abrem a movimentação do produto escolhido.
- Claro/escuro e disposição adaptada à largura móvel.

## Períodos e significado dos valores

**Hoje**, **Últimos 7 dias**, **Mês até hoje** e **Personalizado** consultam vendas e recebimentos. O personalizado aceita até 366 dias e só é aplicado após clicar em **Aplicar período**. O período anterior possui o mesmo número de dias e termina no dia anterior ao início escolhido. Se seu valor é zero, o painel mostra que não há base para comparação, sem inventar um percentual.

Os dias e horários do dashboard usam **America/Sao_Paulo**. Vendas são filtradas pela data de finalização; recebimentos e estornos, pela data de seus lançamentos. São incluídas vendas finalizadas e atualmente não canceladas. Rascunhos não entram nos indicadores. Ao cancelar uma venda, ela deixa de integrar o total vendido no período original; o estorno financeiro aparece no período em que foi registrado. Assim, o recebido líquido de um dia pode ser negativo.

Os totais de venda respeitam arredondamento por item, desconto dos itens e desconto geral aplicado uma vez. Recebimentos parciais não multiplicam o valor vendido nem a dívida restante. O ticket médio é o total vendido dividido pela quantidade de vendas finalizadas, arredondado em centavos.

**A receber agora**, **Atenção hoje**, **Caixa físico** e **Reposição** mostram a situação atual, mesmo se você escolher um período antigo. Parcelas canceladas/quitadas e produtos inativos são excluídos dos alertas correspondentes. A dívida do cliente é separada do repasse da operadora do cartão.

Vendas anteriores ao módulo financeiro sem parcelas registradas não ganham recebimento ou dívida presumidos. O saldo físico usa dinheiro inicial e movimentos das aberturas ainda abertas. Não se confunde com valor vendido ou saldo financeiro acumulado das contas.

O dashboard não cria vendas, recebimentos, movimentações ou ajustes. Use **Atualizar painel** para consultar novamente. Os detalhes mostram até cinco registros por área, e os botões levam aos módulos completos. Atualização por notificações em tempo real, metas, margens, ranking, exportações e filtros por vendedor são evoluções futuras.

## Teste recomendado

1. Em uma unidade, faça uma venda de R$ 700 com R$ 150 recebidos por Pix e R$ 550 em crediário, três parcelas.
2. Atualize a Visão geral: vendido R$ 700, recebido R$ 150 e dívida do cliente R$ 550. Se for a única venda do período, ticket médio R$ 700.
3. Abra um caixa com R$ 100: o painel mostra R$ 100 de dinheiro físico; a entrada por Pix não aumenta esse saldo.
4. Consulte sete dias e alterne o gráfico entre vendas e recebido líquido. Expanda **Ver dados do gráfico** para conferir os dias sem movimento e os valores exatos.
5. Aplique um período anterior sem vendas: as vendas ficam zeradas, mas o saldo atual do cliente e o caixa aberto continuam aparecendo.
6. Clique em **Abrir venda** numa venda recente, **Nova venda** e **Cadastrar cliente** e confira o destino correto.
7. Clique em um produto com baixo estoque: a tela de estoque deve selecionar esse produto.
8. Troque a unidade: os valores da anterior não devem permanecer na tela.
9. Teste tema escuro, largura móvel e um cancelamento; recebido e estorno devem permanecer separados.

## Validação e arquivos

Os testes verificam valores reais, arredondamento de meio centavo, desconto geral, recebimentos parciais, comparação, dias sem movimento, limites de data, fronteira de dia em São Paulo, cancelamento e estorno, separação de cartão/cliente, saldo físico, estoque ativo, autorização por unidade e ausência de gravações na consulta. Build de TypeScript/Vite e navegador com Django/React reais foram verificados, incluindo atalhos, personalizado, troca de unidade e tema escuro/móvel.

O ambiente local usa SQLite. Execute a suíte completa indicada acima no PostgreSQL do projeto para verificar também os testes de concorrência já existentes e os cálculos nesse banco.

- Backend: `sales/dashboard_views.py`, `sales/test_dashboard.py` e `sales/urls.py`.
- Frontend: `src/api.ts` e `components/AppLayout.tsx`, `Sales.tsx`, `Dashboard.tsx`, `Dashboard.css`.
- Documentação: este guia e `docs/regras-negocio.md`.
