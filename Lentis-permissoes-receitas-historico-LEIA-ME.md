# Lentis — permissões de receitas e histórico do cliente

Extraia na raiz `C:\Projetos\lentis-erp`, preservando as pastas. Substitua somente os arquivos do pacote. Os arquivos de referência Product-model.py/.txt e os compactados não fazem parte desta etapa.

## Aplicação

Com a .venv ativa, execute um comando por vez e pare se houver erro:

```powershell
cd C:\Projetos\lentis-erp
git switch -c feat/permissoes-receitas-historico
Test-Path backend\organizations\clinical_permissions.py
Test-Path backend\organizations\migrations\0009_alter_customer_options_alter_prescription_options.py
Test-Path frontend\src\hooks\useClinicalAccess.ts
python backend\manage.py migrate
python backend\manage.py check
python backend\manage.py test accounts organizations sales purchases --verbosity 2
cd frontend
npm run build
```

Os três Test-Path devem retornar True. Não gere outra migração. A 0009 depende da 0008 de fornecedores e cria as novas permissões a partir das opções de Customer e Prescription.

## Concessões

Como superusuário, abra Usuários e acessos e ajuste as concessões diretas ou os grupos. Os vínculos com a loja continuam obrigatórios. Staff e perfil de gerente não substituem permissões por ação.

| Função | Permissões |
|---|---|
| Consultar receitas e versões | organizations.view_prescription |
| Cadastrar receita | view_prescription + add_prescription, em organizations |
| Corrigir receita | view_prescription + change_prescription, em organizations |
| Arquivar receita | view_prescription + archive_prescription, em organizations |
| Abrir histórico consolidado | organizations.view_customer + organizations.view_customer_history |
| Ver vendas no histórico | direitos de abrir histórico + sales.view_sale |
| Ver orçamentos no histórico | direitos de abrir histórico + sales.view_quote |
| Ver OS no histórico | direitos de abrir histórico + sales.view_serviceorder |
| Ver receitas no histórico | direitos de abrir histórico + organizations.view_prescription |
| Ver parcelas e resumos financeiros | direitos de abrir histórico + sales.view_receivable |

A migração não concede direitos automaticamente. Usuários que já corrigiam receitas precisam receber archive_prescription para continuar arquivando. Usuários que já consultavam o histórico precisam receber view_customer_history, além de view_customer e das permissões dos módulos que devem consultar.

A consulta/cadastro de receitas funciona com um seletor mínimo de clientes (id e nome), sem exigir view_customer. Isso não libera CPF, telefone, endereço ou o cadastro completo do cliente. Use Clientes anteriores/Mais clientes quando houver mais de 25 opções.

Excluir não substitui arquivar: revisões e cópias continuam preservadas. A seleção de receita na venda mantém as exigências de acesso clínico e de alteração da venda já existentes.

## Validação manual

1. Consulta: receitas, valores e histórico de versões visíveis; cadastro/correção/arquivo sem concessão não aparecem.
2. Cadastro: cadastre para um cliente sem dar acesso ao cadastro completo de clientes. Campos em branco continuam diferentes de zero.
3. Correção: motivo e versão atual obrigatórios; a versão anterior permanece no histórico. Não libera arquivamento.
4. Arquivamento: funciona sem permissão de correção, exige motivo e preserva histórico; receita arquivada não aceita nova correção.
5. Histórico: testar usuário com somente acesso de clientes e histórico. Identidade aparece, mas contagens de módulos/saldos sem permissão ficam restritos e as seções correspondentes bloqueadas.
6. Histórico clínico: conceda view_prescription e confirme que só a seção de receitas é liberada, sem conceder vendas ou financeiro.
7. Financeiro: conceda view_receivable e confirme parcelas/saldos, sem liberar dados clínicos ou itens das vendas.
8. Revogação: com a receita aberta no histórico, na venda ou na OS, retire view_prescription e retorne o foco ao navegador. Os dados clínicos devem ser ocultados. As APIs também negam acesso com a mesma sessão.
9. Revogue view_customer_history: o histórico deixa de ser acessível, mesmo mantendo a consulta ao cadastro de clientes.
10. Confira outras unidades, usuários inativos e motivo/versão dos reenvios.

## Validação e escopo

A etapa modifica autorização e apresentação das ações; não adiciona interpretação clínica, cálculos de medidas ou alterações automáticas nas prescrições. As cópias já utilizadas na venda/OS permanecem imutáveis.

Foram adicionados 17 testes de autorização e privacidade. Os cenários antigos foram mantidos com concessões explícitas para continuar verificando suas regras originais, incluindo a exigência independente de consultar orçamentos no histórico.

O ambiente local de validação usa SQLite. Os cenários de concorrência/locks exclusivos do PostgreSQL devem ser executados no seu ambiente, juntamente com o build do projeto completo.
