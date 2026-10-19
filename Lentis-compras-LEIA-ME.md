# Lentis ERP — Compras e entrada de mercadorias

## Instalação

Com a branch `feat/compras` ativa, extraia o ZIP na raiz `C:\Projetos\lentis-erp`, preservando as pastas backend, frontend e docs. Substitua os arquivos correspondentes. Todos estão em UTF-8.

A base é main f650509, com Fornecedores integrado, e os settings.py, config/urls.py e stock_services.py enviados em 19/10/2026.

O pacote adiciona o app purchases em INSTALLED_APPS e suas rotas em config/urls.py. O serviço de estoque enviado foi usado sem alterações; ele não precisa ser substituído. Não há novas dependências ou variáveis de ambiente.

```powershell
cd C:\Projetos\lentis-erp
python backend\manage.py makemigrations purchases
python backend\manage.py migrate
python backend\manage.py check
python backend\manage.py test purchases --verbosity 2
cd frontend
npm run build
```

Será gerada a migração inicial do app purchases. Inclua-a no commit depois dos testes. Não modifique migrações anteriores de organizations ou sales.

Para a regressão dos módulos:

```powershell
cd C:\Projetos\lentis-erp
python backend\manage.py test organizations sales purchases --verbosity 2
```

Reinicie o backend: na raiz, `python backend\manage.py runserver 127.0.0.1:8000`. Frontend em outro terminal: `cd frontend`, depois `npm run dev`.

## Permissões

No admin de usuários/grupos, conceda:

- purchases.view_purchase — visualizar compra.
- purchases.add_purchase — adicionar compra/rascunho.
- purchases.change_purchase — editar ou cancelar rascunho.
- purchases.receive_purchase — confirmar entrada de compra (além de visualizar e alterar).
- organizations.view_supplier — visualizar fornecedores para escolhê-los no editor.

O usuário deve ter vínculo ativo com a unidade. Superusuário ativo possui as permissões. Ser staff não as substitui. O admin de compras é somente consulta; a operação é realizada pelo frontend para preservar entrada, versão e histórico.

## Operação

Comercial → Compras → Nova compra.

1. Escolha um fornecedor ativo. Use a paginação para carregar outras páginas do cadastro.
2. Informe a referência do documento (opcional), data e observações.
3. Adicione produtos cadastrados na unidade e informe quantidades e custos unitários. Aceita vírgula ou ponto no frontend.
4. Salvar rascunho apenas registra o documento, sem entrada de estoque.
5. Conferir entrada salva primeiro as alterações do rascunho, quando necessário, e mostra uma revisão com itens e total.
6. Se desejar, marque Atualizar custo cadastrado pelo custo desta entrada. Essa opção é desmarcada por padrão; usa último custo, sem custo médio e sem alterar preço de venda.
7. Marque a confirmação de conferência e use Confirmar entrada. O documento passa a somente leitura e cada item mostra a movimentação correspondente.

A referência é manual, não uma chave fiscal validada. Use uma referência que identifique o documento de forma única por fornecedor/unidade (incluindo série, quando necessário). Uma referência já usada em rascunho ou entrada confirmada é recusada; cancelar um rascunho libera a referência.

Itens têm quantidade positiva com até três casas decimais e custo não negativo com até duas. Cada produto aparece uma vez, com máximo de 100 produtos na compra. Total arredonda cada linha para centavos com half-up e soma as linhas.

## Falhas e reenvio

A entrada usa uma única transação: se um item falhar, nenhuma movimentação, atualização de custo ou mudança de situação é mantida.

Se a resposta de um envio se perder, use Conferir / repetir envio. O UUID permanece o mesmo, recuperando o resultado sem duplicar. O envio é mantido no sessionStorage quando disponível e na memória da tela enquanto aberta. Não remova o envio pendente antes de conferir o resultado.

Uma compra alterada por outra aba exige reabertura. Use Reabrir dados atuais e confirme descartar alterações locais. O servidor confere versão, unidade, permissões e situação do fornecedor/produtos a cada operação.

## Cancelamento e limites

Cancelar rascunho exige motivo e não movimenta estoque. Compras confirmadas não podem ser canceladas ou editadas nesta etapa. O futuro fluxo de devolução será específico para esse fim; não excluir documentos ou movimentações manualmente.

Esta entrega não gera contas a pagar, parcelas, pagamentos, XML ou lançamentos fiscais. Também não trata recebimento parcial, frete, descontos ou custo médio. Esses fluxos serão acrescentados nas próximas etapas. A confirmação desta entrega é uma entrada integral de estoque.

## Teste manual

1. Crie um rascunho com dois produtos; confira que o estoque não mudou.
2. Informe quantidade fracionada e custo com centavos; confira os totais por item e o total geral.
3. Confirme a entrada sem atualizar custos. Confira o aumento do estoque e o custo cadastrado preservado.
4. Faça outra compra com atualização de custo marcada. Confira que o custo muda e o preço de venda permanece.
5. Reabra uma entrada confirmada: ela deve ser somente leitura, com histórico e IDs de movimentação.
6. Tente repetir a referência do documento para o mesmo fornecedor/unidade: deve recusar.
7. Cancele um rascunho com motivo; o histórico deve permanecer, sem entrada de estoque.
8. Teste duas abas editando o mesmo rascunho e usuário sem permissão de confirmar entrada.
9. Inative um produto ou fornecedor depois de salvar um rascunho e tente confirmar: deve recusar sem movimentação parcial.
10. Confira troca de unidade, tema claro/escuro e tela pequena.

Os testes automatizados incluem falha proposital no segundo item (rollback integral), limite de saldo, reenvio sem duplicação e proteção contra campos forjados. Os testes de locks exigem PostgreSQL.

## Arquivos

- backend/config/settings.py e urls.py.
- backend/purchases/: configuração do app, modelos, serviços, API, rotas, admin, testes e pacote de migrações.
- frontend/src/api.ts e components/AppLayout.tsx.
- frontend/src/components/Purchases.tsx e Purchases.css.
- docs/regras-negocio.md e este guia.
