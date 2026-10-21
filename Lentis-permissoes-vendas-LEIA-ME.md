# Lentis — permissões por ação em vendas

## Instalação

Use a branch `feat/permissoes-vendas`, criada sobre a main com as permissões de cadastros/estoque já integradas. Extraia este ZIP na raiz `C:\Projetos\lentis-erp`, substituindo os arquivos correspondentes. São arquivos completos em UTF-8. O pacote não contém credenciais nem altera arquivos pessoais.

No terminal com a .venv ativa:

```powershell
cd C:\Projetos\lentis-erp
python backend\manage.py migrate
python backend\manage.py check
python backend\manage.py makemigrations --check --dry-run
python backend\manage.py test sales accounts organizations --verbosity 2
cd frontend
npm run build
```

A migração `sales.0010_alter_sale_options` registra as permissões de confirmar e cancelar. Não altera as vendas existentes, o estoque ou o financeiro. Reinicie o backend após atualizar os arquivos.

## Liberação dos usuários

Entre como superusuário em **Gestão de usuários**, abra a conta e conceda as ações necessárias na seção **Vendas**. Mantenha o vínculo ativo com a unidade. As permissões de modelo valem nas unidades às quais a conta já tem acesso; não concedem acesso a outra loja.

| Ação | Permissão | Observação |
|---|---|---|
| Consultar | `sales.view_sale` | Lista e abre vendas. |
| Criar | `sales.add_sale` | Cria rascunho e permite converter orçamento em venda. |
| Editar | `sales.change_sale` | Cabeçalho, itens, pagamentos e seleção de receita do rascunho; regras clínicas permanecem. |
| Confirmar | `sales.finalize_sale` | Pode confirmar os dados já salvos, sem poder alterá-los. |
| Cancelar | `sales.cancel_sale` | Cancelamento lógico com motivo. |

**Regra preservada:** cancelar uma venda já finalizada continua exigindo staff ou superusuário, além da permissão de cancelar. Esta entrega não promove contas a staff. Contas comuns com cancel podem cancelar rascunhos. A flag staff sozinha não libera as ações de vendas.

Combinações sugeridas:

- Consulta: view.
- Atendimento: view + add + change + finalize.
- Edição sem confirmação: view + change.
- Conferência e confirmação de rascunho salvo: view + finalize.
- Cancelamento de rascunhos: view + cancel.

`delete_sale` e permissões dos itens não substituem cancel/change. Nenhuma permissão é atribuída automaticamente. Permissões herdadas de grupos continuam efetivas.

## Comportamento da interface

- O menu Vendas aparece quando há alguma ação liberada.
- Nova venda exige add; sem view, o usuário cadastra sem listar/reabrir registros. Após salvar, recebe a confirmação e pode iniciar outra venda.
- Sem change, um rascunho aberto fica somente para leitura. Com view + finalize, aparece **Confirmar venda salva**, que usa os itens e pagamentos persistidos, sem substituir o rascunho.
- Concluir um atendimento novo exige add + finalize. Editar e concluir pelo checkout exige change + finalize.
- O servidor verifica a autorização antes de qualquer alteração e antes de reapresentar o resultado de um checkout repetido. O identificador de operação mantém a proteção contra duplicidade.
- Acesso revogado é atualizado ao focar a janela ou reabrir a página; nenhuma atualização depende do botão estar escondido para bloquear o servidor.
- O atendimento usa opções próprias, sem exigir view_customer ou view_product. Essas opções não contêm custo, saldo bancário, documento, endereço ou contato do cliente. O cadastro completo continua sujeito às permissões da etapa anterior.
- Os dados já existentes de preço, estoque, desconto, parcelas, caixa e receita continuam validados pelas regras anteriores. Aprovação de desconto exige sua autorização própria; confirmação de venda não concede aprovação de desconto.
- Converter orçamento exige add_sale, inclusive em repetições. O botão é ocultado sem essa permissão; abrir a venda gerada exige view.

## Conferência manual

1. Superusuário: conceder direitos de Vendas e confirmar que as duas novas permissões aparecem após migrate.
2. Conta sem direitos, inclusive staff: menu de vendas oculto; API de vendas retorna 403.
3. Consulta: listar/abrir e verificar ausência de ações de escrita.
4. Add sem view: criar rascunho sem consultar cadastros completos ou listar vendas.
5. View + change sem finalize: editar e salvar; confirmação bloqueada, inclusive pelo checkout.
6. View + finalize sem change: abrir rascunho preparado e confirmar seus dados salvos; campos não editáveis.
7. Add + finalize: novo checkout com pagamento, repetição segura sem venda/estoque duplicados.
8. Cancel: testar rascunho e regra administrativa de venda finalizada; motivo e estornos preservados.
9. Revogar uma permissão com a sessão aberta e voltar à janela: acesso atualizado; envio direto continua bloqueado.
10. Outra unidade, vínculo inativo e conta inativa: acesso negado.

## Validação e limites

O pacote acrescenta testes de autorização e atualiza apenas as permissões das fixtures dos testes antigos que exercitam vendas. O teste de negação dos relatórios remove a consulta concedida por essa fixture para continuar verificando ausência de direitos. Nenhuma asserção de regra comercial foi removida.

Migrações executadas em SQLite e conferência de modelos sem migrações pendentes para accounts/organizations/sales. Os cenários de concorrência e locks precisam ser executados no PostgreSQL local; o ambiente de validação desta entrega usa SQLite. Execute também a regressão completa antes de integrar, se houver outras mudanças locais:

```powershell
python backend\manage.py test accounts organizations sales purchases --verbosity 2
```

Caixa, recebimentos, relatórios e demais módulos mantêm as políticas anteriores; esta etapa não redefine todas as permissões financeiras. As opções financeiras antigas seguem seus contratos; a nova tela de vendas usa exclusivamente as opções mínimas desta entrega.

Não use `git add .`: preserve fora deste commit as cópias Product-model, o logo avulso e os documentos pessoais pendentes.

Validação final desta entrega: 496 testes, OK, com 19 cenários exclusivos de PostgreSQL ignorados em SQLite; build TypeScript/Vite e fluxo real no Chromium aprovados. Os 22 testes novos de permissões passaram.
