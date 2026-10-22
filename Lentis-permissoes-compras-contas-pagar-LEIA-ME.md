# Lentis — permissões de compras e contas a pagar

Extraia este pacote na raiz `C:\Projetos\lentis-erp`, preservando a estrutura de pastas. Substitua apenas os arquivos do pacote; não apague as pastas existentes. O pacote usa os arquivos atuais enviados de purchases, sales, components e api.ts.

## Aplicação

Com a .venv ativa, execute um comando por vez. Pare se houver erro:

```powershell
cd C:\Projetos\lentis-erp
git switch -c feat/permissoes-compras-contas-pagar
Test-Path backend\purchases\access_permissions.py
Test-Path backend\purchases\migrations\0003_alter_purchase_options.py
Test-Path frontend\src\hooks\usePurchaseAccess.ts
python backend\manage.py migrate
python backend\manage.py check
python backend\manage.py test accounts organizations sales purchases --verbosity 2
cd frontend
npm run build
```

Os três Test-Path devem retornar True. Não gere outra migração; a 0003 fornecida altera somente as opções/permissões do modelo Purchase e depende da 0002 de contas a pagar.

## Concessões

Acesse Usuários e acessos com um superusuário. Escolha o usuário, mantenha seu vínculo ativo com a loja e conceda as permissões necessárias. Perfis do vínculo (vendedor/gerente), staff e acesso ao Admin não substituem concessões por ação. Direitos herdados de grupos também contam.

| Função | Permissões de purchases |
|---|---|
| Consultar compras | view_purchase |
| Abrir rascunho | view_purchase + add_purchase |
| Editar rascunho | view_purchase + change_purchase |
| Receber itens já salvos | view_purchase + receive_purchase |
| Receber e atualizar o custo dos produtos | view_purchase + receive_purchase + update_purchase_cost |
| Cancelar rascunho | view_purchase + cancel_purchase |
| Consultar títulos/parcelas/histórico | view_payableplan |
| Gerar parcelas | view_payableplan + add_payableplan + view_purchase |
| Registrar pagamento | view_payableplan + pay_payable |
| Registrar estorno | view_payableplan + reverse_payable |

Nenhuma concessão é automática. Quem apenas tinha edição de compra deve receber cancel_purchase para continuar cancelando rascunhos e update_purchase_cost (junto com receive_purchase) para atualizar o custo cadastrado na entrada.

Dinheiro mantém as permissões adicionais de caixa: sales.move_cash e, se a sessão for de outra pessoa, sales.manage_cash. A sessão deve estar aberta e a operação respeita as demais regras existentes, inclusive saldo suficiente para saída. Pix/transferência/débito não exigem move_cash. Saldo das contas continua sujeito a sales.view_financialaccount.

## Validação manual

1. Consulta de compras: abre lista e detalhes, sem formulário habilitado nem ações de alteração.
2. Cadastro: abre/salva rascunho sem precisar de acesso ao cadastro completo de produtos ou fornecedores. Não recebe mercadoria sem receive_purchase.
3. Edição: salva rascunho; não recebe nem cancela sem concessões adicionais.
4. Recebimento: confirma itens e quantidades já salvos mesmo sem edição; não aparece a opção de atualizar custo sem o direito específico. Confira estoque, histórico e custo preservado.
5. Cancelamento: permite cancelar somente rascunho, com motivo, sem movimentar estoque ou títulos.
6. Consulta de contas a pagar: abre parcelas/histórico, sem pagar, estornar nem ver opções bancárias de pagamento.
7. Pagamento: paga sem conceder geração, estorno ou consulta de compras. Teste conta bancária e regras adicionais de dinheiro.
8. Estorno: estorna com motivo sem conceder pagamento ou geração.
9. Geração: exige consulta da compra e título, além de adicionar plano; não concede pagamento.
10. Revogue uma concessão e retorne o foco ao navegador. A interface deve bloquear a ação; chamadas diretas e reenvios também são negados.
11. Teste outra unidade e confirme que dados, estoque e pagamentos não cruzam lojas.

## Escopo

Não há mudança de cálculo de parcelas, valores, arredondamentos, saldo, idempotência ou política de devolução de compra. A etapa altera autorização, opções de seleção e apresentação das ações. Não há transferência bancária real: o sistema registra pagamentos efetuados.

Foram adicionados 19 cenários de permissões. Os testes antigos preservam os cenários; suas concessões de compras foram atualizadas para incluir os novos direitos explícitos. A validação local usa SQLite; os testes exclusivos de concorrência/locks do PostgreSQL precisam ser rodados no seu ambiente.
