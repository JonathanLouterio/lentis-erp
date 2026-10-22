# Lentis — permissões por ação em orçamentos

## Instalação

Use `feat/permissoes-orcamentos`, criada sobre a main com a etapa de caixa e recebimentos já integrada. Extraia o ZIP diretamente na raiz `C:\Projetos\lentis-erp`, substituindo os arquivos correspondentes.

Confira a extração antes de testar:

```powershell
cd C:\Projetos\lentis-erp
git branch --show-current
Test-Path backend\sales\quote_permissions.py
Test-Path frontend\src\hooks\useQuoteAccess.ts
```

Os dois testes de caminho devem retornar True. Depois:

```powershell
python backend\manage.py migrate
python backend\manage.py check
python backend\manage.py makemigrations --check --dry-run
python backend\manage.py test sales accounts purchases organizations --verbosity 2
cd frontend
npm run build
```

A migração `sales.0012_alter_quote_options` cria cinco direitos operacionais. Ela não altera propostas, vendas, saldos ou estoque existentes. Reinicie o backend e atualize o navegador após a instalação.

## Liberação de usuários

Entre como superusuário em **Gestão de usuários → Orçamentos** e conceda os direitos necessários. Mantenha os vínculos ativos com as lojas. Staff e perfil de gerente não concedem direitos automaticamente; permissões herdadas de grupos continuam efetivas.

| Operação | Permissão |
|---|---|
| Consultar/listar | `sales.view_quote` |
| Criar | `sales.add_quote` |
| Editar/revisar | `sales.change_quote` |
| Preparar proposta | `sales.send_quote` |
| Registrar aceite | `sales.accept_quote` |
| Recusar com motivo | `sales.reject_quote` |
| Imprimir / salvar PDF | view_quote + `sales.print_quote` |
| Converter em venda | `sales.convert_quote` + `sales.add_sale` |

A migração não concede direitos a usuários ou grupos. Após atualizar, contas comuns precisarão de liberação explícita para as ações que usavam antes.

Combinações sugeridas:

- Consulta: view_quote.
- Montagem/revisão: view_quote + add_quote + change_quote.
- Preparação: view_quote + send_quote.
- Aceite: view_quote + accept_quote.
- Impressão: view_quote + print_quote.
- Recusa: view_quote + reject_quote.
- Conversão: view_quote + convert_quote + add_sale; acrescente view_sale para abrir a venda gerada.

As ações de preparar/aceitar/recusar/converter não exigem editar. Para selecionar uma proposta existente pela tela, conceda consulta junto com a ação. Criar sem consultar é permitido: o usuário monta a proposta e recebe confirmação, sem listar ou reabrir propostas.

## Comportamento

O menu e os botões refletem os direitos da própria conta. Os campos ficam desabilitados sem edição; transições autorizadas continuam disponíveis conforme a situação. Os direitos são atualizados ao voltar o foco à janela. Se uma ação acabou de ser concedida, use Reabrir dados atuais para atualizar também os dados e as ações disponíveis do registro aberto.

A consulta e o contador de orçamentos no histórico do cliente também exigem view_quote. Sem ela, a seção fica restrita e o contador não é informado. O admin dos históricos exige consulta de orçamentos, preserva o filtro por loja e continua somente para leitura.

O atendimento consulta opções próprias, com dados mínimos de clientes e produtos ativos da loja. Não é necessário liberar view_customer/view_product para criar propostas. O endpoint não retorna custos, documentos/contatos do cliente, quantidade de estoque ou dados financeiros.

Preparar exige rascunho com itens e validade vigente; aceitar exige proposta preparada; converter exige aceite. Revisar termos retorna ao rascunho e exige novo preparo/aceite. Recusar exige motivo. Propostas convertidas/recusadas preservam seus termos e histórico. As permissões não dispensam nenhuma dessas regras.

Impressão exige consulta e impressão e usa os dados salvos. Alterações locais precisam ser salvas antes de imprimir. O documento pode incluir identificação/endereço do cliente conforme o modelo existente, por isso o direito de impressão é separado da consulta simples.

Converter cria uma venda em rascunho com preços/descontos preservados. Não baixa estoque nem registra financeiro. A conta não recebe implicitamente permissão de consultar, confirmar ou receber essa venda. As regras comerciais e as permissões da venda serão verificadas nas etapas posteriores.

Envios repetidos mantêm a proteção contra duplicidade, mas a autorização é conferida antes de devolver uma operação anterior. Revogar convert_quote ou add_sale impede reapresentar a conversão, mesmo com a proposta já convertida.

## Conferência manual

1. Conta sem direitos, inclusive staff: menu oculto e APIs de orçamentos negadas.
2. Consulta: abre propostas, sem editar, preparar, aceitar, recusar, converter ou imprimir.
3. Cadastro sem consulta: cria com as opções mínimas, sem listar propostas ou consultar cadastros completos.
4. Edição sem preparo: revisa/salva, mas não prepara.
5. Preparação e aceite em contas diferentes: cada uma executa sua transição sem editar os valores.
6. Impressão: somente view + print imprime; consulta isolada e print isolado são insuficientes.
7. Conversão: testar falta de cada direito, depois converter com ambos; resultado somente em rascunho.
8. Recusa: exige motivo, mantém registro e bloqueia edição posterior.
9. Histórico do cliente: lista/detalhe/contador de propostas bloqueados sem view_quote.
10. Revogar acesso com a sessão aberta e voltar à janela; testar outra unidade e repetição de um envio.

## Validação

A entrega acrescenta testes de autorização e preserva os cenários antigos. As fixtures de orçamento declaram os direitos de seus cenários. O teste antigo de conversão continua isolando add_sale, com convert_quote explícito; os testes de histórico que consultam propostas recebem view_quote.

O ambiente local usa SQLite. Os cenários de concorrência/locks ignorados aqui devem passar no PostgreSQL do projeto. A migração foi aplicada e a verificação de modelos não encontrou mudanças pendentes nos quatro apps. As operações também foram verificadas no navegador, incluindo a interface em tela pequena.

Não use git add .: mantenha arquivos RAR, logo avulso, cópias Product-model e documentos pessoais fora deste commit.

Resultado final: 537 testes, OK, com 19 cenários exclusivos de PostgreSQL ignorados em SQLite. Os 20 testes novos estão incluídos nessa execução. Build TypeScript/Vite e verificações no Chromium aprovados, incluindo revogação com o histórico do cliente aberto.
