# Lentis ERP — Ordens de serviço

## Instalação

Com a branch `feat/ordens-servico` ativa, extraia o conteúdo do ZIP em `C:\Projetos\lentis-erp`, preservando as pastas backend, frontend e docs. Substitua apenas os arquivos do pacote. Todos estão em UTF-8.

O pacote usa os arquivos enviados em 19/10/2026, após a integração de receita na venda (main 42ba40b). Não contém settings, banco de dados, dependências, logo ou arquivos temporários.

No PowerShell, na raiz do projeto:

```powershell
cd C:\Projetos\lentis-erp
python backend\manage.py makemigrations sales
python backend\manage.py migrate
python backend\manage.py check
python backend\manage.py test sales.test_work_orders --verbosity 2
python backend\manage.py test organizations sales --verbosity 2
cd frontend
npm run build
```

A migração é gerada no seu projeto, normalmente com prefixo 0009. Inclua-a no commit depois da validação. Não renomeie migrações anteriores.

Backend: `python backend\manage.py runserver 127.0.0.1:8000` na raiz. Frontend em outro terminal: `cd frontend` e `npm run dev`.

## Como usar

Operação → Ordens de serviço → Nova OS. Escolha uma venda finalizada com cliente identificado, informe previsão, laboratório, armação e lentes. Na tela Vendas, abra uma venda finalizada e use **Abrir / acompanhar OS desta venda**: abre a ordem existente ou prepara a abertura.

A seleção de vendas é paginada. Cada venda admite uma OS, inclusive se a primeira for cancelada. Se tentar abrir outra, a API informa o número existente; abra pela fila e filtro Todas.

Avance por laboratório, montagem e conferência. Confirme a conferência para liberar. Em Pronta para entrega, informe no campo de motivo quem recebeu, marque a confirmação e avance para Entregue. O histórico guarda usuário, data, situação, motivo e dados de produção de cada versão.

Para corrigir dados de produção, altere os campos e preencha o motivo antes de **Salvar dados de produção**. Salve as alterações antes de avançar uma etapa. Retrabalho exige motivo e pode voltar ao laboratório ou montagem a partir da conferência ou de pronta para entrega.

Uma falha de rede mantém o mesmo envio na memória e, quando permitido pelo navegador, no sessionStorage. Use **Conferir / repetir envio** para obter o resultado sem duplicar. Não remova esse registro do navegador durante um envio incerto. Uma resposta 4xx libera a tela; se houver aviso de versão desatualizada, descarte as mudanças locais e reabra a OS pela fila.

## Permissões

No admin, em usuários ou grupos, conceda Visualizar ordem de serviço. Para abrir, também Adicionar ordem de serviço. Para editar/avançar/cancelar, Alterar ordem de serviço. O usuário deve possuir vínculo ativo com a unidade.

A consulta dos valores da receita exige ainda a permissão Visualizar receita (organizations.view_prescription). Superusuário ativo tem as permissões; staff por si só não tem.

## Roteiro de validação manual

1. Finalize uma venda com cliente e receita vinculada; abra sua OS pelo botão da venda.
2. Verifique os itens e a receita preservada. Confirme que não houve nova baixa de estoque ou lançamento financeiro.
3. Avance ao laboratório, montagem e conferência. Teste retorno para retrabalho com motivo.
4. Confirme a conferência; registre quem recebeu e conclua a entrega. A ordem passa a somente leitura.
5. Teste previsão anterior ao dia atual e o filtro Somente atrasadas; entregues e canceladas não devem constar como atraso.
6. Abra a mesma OS em duas abas. Salve numa e tente gravar na outra: deve pedir para reabrir.
7. Usuário sem permissão não consulta OS. Usuário com OS mas sem permissão de receita não vê graus. Outra unidade não pode consultar ou alterar a ordem.
8. Cancele uma venda com OS aberta: a OS apresenta alerta e bloqueia avanço; encerre-a com Cancelar OS e motivo. Cancelar a OS não altera a venda.
9. Confira tema claro/escuro, navegação e tela estreita.

## Limites desta etapa

Não há impressão da OS, integrações com laboratório, custos de produção, anexos, múltiplas ordens por venda ou reabertura de entregue/cancelada. Não há bloqueio por saldo financeiro pendente para entrega nesta etapa.

A lista não inclui valores da receita; o detalhe autorizado usa a cópia registrada na venda. Não inclua informações clínicas nas observações operacionais.

## Arquivos

Backend: models.py, urls.py, work_order_models.py, work_order_services.py, work_order_views.py, test_work_orders.py.
Frontend: api.ts, AppLayout.tsx, Sales.tsx, ServiceOrders.tsx e ServiceOrders.css.
Documentação: este guia e docs/regras-negocio.md.
