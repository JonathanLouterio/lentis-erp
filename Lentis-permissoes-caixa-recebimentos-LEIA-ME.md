# Lentis — permissões de caixa e recebimentos

## Aplicação

Use a branch `feat/permissoes-caixa-recebimentos`, sobre a main com permissões de vendas já integradas. Extraia o ZIP na raiz `C:\Projetos\lentis-erp`, substituindo os arquivos correspondentes. Os arquivos são completos e estão em UTF-8.

```powershell
cd C:\Projetos\lentis-erp
python backend\manage.py migrate
python backend\manage.py check
python backend\manage.py makemigrations --check --dry-run
python backend\manage.py test sales accounts purchases organizations --verbosity 2
cd frontend
npm run build
```

Reinicie o backend e atualize o navegador. A migração `sales.0011_alter_cashsession_options_alter_receivable_options` registra os novos direitos; não modifica caixas ou parcelas existentes. Não há atribuição automática de direitos a contas ou grupos.

## Liberação das contas

Entre como superusuário em Gestão de usuários, abra a conta e ajuste as seções **Aberturas de caixa**, **Parcelas a receber** e **Contas de recebimento**. O vínculo ativo com a loja continua obrigatório.

| Operação | Permissão |
|---|---|
| Listar caixas e consultar movimentos | `sales.view_cashsession` |
| Abrir caixa | `sales.add_cashsession` |
| Registrar suprimento/sangria | `sales.move_cash` |
| Fechar caixa | `sales.close_cash` |
| Operar caixa de outra pessoa | Ação específica + `sales.manage_cash` |
| Listar parcelas e consultar histórico | `sales.view_receivable` |
| Registrar recebimento | `sales.receive_receivable` |
| Consultar saldo agregado das contas | `sales.view_financialaccount` |

Ser staff, gerente ou responsável pela abertura não concede a ação. Permissões herdadas de grupos continuam valendo. `change_cashsession`, `add_financialentry`, `change_receivable` e direitos semelhantes não substituem os direitos específicos acima.

Combinações sugeridas:

- Consulta de caixa: view_cashsession.
- Operador de caixa próprio: view_cashsession + add_cashsession + move_cash + close_cash.
- Supervisor de fechamento: view_cashsession + close_cash + manage_cash, sem necessidade de liberar suprimento/retirada.
- Recebimentos: view_receivable + receive_receivable. Pode ser uma conta comum, sem staff.
- Saldos agregados: acrescente view_financialaccount somente a quem pode consultar esse dado.

Abertura sem view é possível: o usuário registra sua abertura e recebe a confirmação, sem listar todo o histórico. Para localizar e operar um caixa existente pela tela, conceda consulta junto com a ação. Para selecionar uma parcela pela tela, conceda consulta junto com recebimento.

## Vendas e contas a pagar

**Atenção ao liberar vendedores:** marcar um pagamento como recebido, incluindo entrada em Pix ou dinheiro na própria venda, exige receive_receivable. Sem isso, a interface bloqueia a marcação e a venda pode ser concluída como valor a receber. Também há proteção no servidor para envios diretos e para confirmação de um rascunho que já tinha pagamentos marcados como recebidos.

A edição de um rascunho pode guardar as condições pretendidas; a entrada financeira só acontece na confirmação autorizada. As permissões de criar/editar/confirmar venda continuam obrigatórias.

Receber em dinheiro gera automaticamente a entrada no caixa aberto da conta. Esse lançamento não exige move_cash, pois deriva do recebimento autorizado. Suprimento e retirada manuais continuam separados. Regras de caixa fechado, saldo físico, responsabilidade, justificativas e histórico permanecem.

Cancelar uma venda gera os estornos automáticos autorizados pelo cancelamento, com as regras anteriores. Cancelar venda finalizada continua exigindo conta administrativa e permissão cancel_sale; não exige permissão de suprimento manual.

Para pagar/estornar fornecedor em dinheiro, conceda também move_cash, além dos direitos de contas a pagar. Caixa de outro responsável exige manage_cash. As opções de pagamento ocultam dinheiro sem move_cash, e o servidor confere o direito novamente, inclusive no replay. Pagamentos bancários não exigem move_cash. Os saldos agregados das contas nas opções de fornecedor exigem view_financialaccount.

## Admin e interface

A operação por loja fica na interface do ERP. O admin financeiro global de contas, formas e históricos relacionados fica restrito a superusuários. Históricos de caixas e lançamentos permanecem imutáveis. Este ajuste impede acesso por staff aos históricos financeiros de outras lojas através do admin.

Os menus e botões seguem as capacidades da própria conta. A volta do foco à janela atualiza os direitos; o backend confere todas as requisições. Ocultar um botão não é a proteção principal. Os limites e a idempotência anteriores foram mantidos.

## Conferência manual

1. Superusuário: verificar as novas permissões após migrate e liberar um operador.
2. Somente consulta: abrir históricos e verificar ausência de abertura, suprimento, retirada, fechamento e recebimento.
3. Operador com direitos: abrir seu caixa, registrar suprimento/retirada e fechar, com justificativa quando necessário.
4. Supervisor apenas de fechamento: fechar caixa de outra pessoa; suprimento/retirada devem continuar indisponíveis.
5. Responsável sem move/close e staff sem direitos: operações negadas.
6. Conta comum com view_receivable + receive_receivable: registrar recebimento parcial; saldo da parcela atualizado, sem exibir saldos agregados das contas se não autorizado.
7. Revogar um direito com a sessão aberta e voltar à janela: ação retirada e chamadas diretas negadas.
8. Repetir o mesmo envio: não duplicar abertura, movimento ou recebimento. Após revogação, repetição não dispensa a permissão.
9. Vendedor sem receive_receivable: confirmar venda a receber; envio com pagamento confirmado deve ser bloqueado, sem alterações parciais.
10. Fornecedor: pagamento bancário permanece disponível com seus direitos; dinheiro exige os direitos de caixa adicionais.

## Testes

A entrega acrescenta testes de permissões e ajusta as fixtures antigas para declarar os direitos que os cenários já utilizavam. O teste de vendedor sem recebimento retira explicitamente receive_receivable; o teste de relatórios sem consulta retira os direitos de consulta concedidos pela fixture compartilhada. Nenhum cenário antigo foi removido.

A validação local usa SQLite; os testes de concorrência/locks ignorados nesse ambiente devem passar no PostgreSQL do projeto. A migração foi aplicada e a verificação de modelos não encontrou mudanças pendentes nos quatro apps.

Não use git add .: mantenha o logo avulso, as cópias Product-model e os documentos pessoais fora do commit desta etapa.

Validação final: 517 testes, OK, com 19 cenários exclusivos de PostgreSQL ignorados em SQLite. Os 21 testes novos passaram; build TypeScript/Vite e fluxos no Chromium aprovados.
