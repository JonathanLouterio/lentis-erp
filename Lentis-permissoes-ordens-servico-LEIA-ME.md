# Lentis — permissões das ordens de serviço

Extraia o conteúdo deste pacote na raiz `C:\Projetos\lentis-erp`, preservando as pastas backend, frontend e docs. Não substitua pastas inteiras nem apague arquivos existentes.

## Instalação

Na raiz do projeto, com a .venv ativa:

```powershell
cd C:\Projetos\lentis-erp
git switch -c feat/permissoes-ordens-servico
Test-Path backend\sales\work_order_permissions.py
Test-Path backend\sales\migrations\0013_alter_serviceorder_options.py
Test-Path frontend\src\hooks\useOrderAccess.ts
python backend\manage.py migrate
python backend\manage.py check
python backend\manage.py test accounts organizations sales purchases --verbosity 2
cd frontend
npm run build
```

Os três Test-Path devem retornar True. A migração 0013 depende da 0012 de permissões de orçamentos. Não é necessário gerar outra migração.

## Concessões

Faça login como superusuário e abra Usuários e acessos. As permissões novas aparecem no grupo de ordens de serviço. Nenhuma concessão é automática; usuários com apenas a permissão antiga de edição deixam de avançar, retrabalhar ou cancelar até a concessão explícita correspondente.

| Perfil de teste | Permissões |
|---|---|
| Consulta | view_serviceorder |
| Abertura | view_serviceorder + add_serviceorder |
| Edição de produção | view_serviceorder + change_serviceorder |
| Operação de etapas | view_serviceorder + advance_serviceorder |
| Retrabalho | view_serviceorder + rework_serviceorder |
| Cancelamento | view_serviceorder + cancel_serviceorder |

Todos precisam de vínculo ativo com a unidade, exceto o tratamento já existente de superusuário. Direitos herdados de grupos também contam.

## Validação manual

1. Consulta: abre fila e detalhes; campos bloqueados e sem ações de alteração.
2. Edição: altera produção com motivo, sem avanço, retrabalho nem cancelamento.
3. Etapas: avança sem editar os campos; conferência e entrega preservam confirmações e identificação de quem recebeu.
4. Retrabalho: disponível somente na conferência ou pronta para entrega, com destino e motivo.
5. Cancelamento: cancela com motivo sem alterar venda, pagamentos ou estoque.
6. Abertura: seleciona venda finalizada com cliente sem precisar de view_sale. Vendas com OS existente não aparecem na seleção.
7. Revogação: retire a concessão, volte ao navegador e atualize/retorne o foco. Chamadas diretas também devem ser bloqueadas.
8. Confira o isolamento entre unidades, o histórico do cliente e o acesso separado à receita.

## Alterações e testes

Direitos separados no domínio e na API, verificação antes de reenvios idempotentes, endpoint de capacidades, seleção comercial mínima e interface com ações autorizadas. Testes antigos preservados com concessões explícitas das novas ações; dez cenários de regressão de permissões adicionados.

O ambiente de validação local usa SQLite; os testes de concorrência exclusivos do PostgreSQL precisam ser executados no seu ambiente. A compilação local não substitui o build no seu projeto.
