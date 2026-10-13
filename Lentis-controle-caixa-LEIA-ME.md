# Lentis — Controle de caixa físico

Pacote completo para a etapa seguinte ao parcelamento. Os arquivos estão em UTF-8 e mantêm a estrutura do projeto.

## Instalação

Pare o Django e o Vite com Ctrl+C nos terminais correspondentes. Na raiz:

```powershell
cd C:\Projetos\lentis-erp
git switch -c feat/controle-caixa
```

Extraia o ZIP diretamente em `C:\Projetos\lentis-erp`, aceitando substituir os arquivos correspondentes. Preserve `backend`, `frontend` e `docs`; os componentes vão em `frontend/src/components` e `api.ts` em `frontend/src`.

Execute na raiz, com o ambiente virtual ativo:

```powershell
python backend\manage.py makemigrations sales
python backend\manage.py migrate
python backend\manage.py check
python backend\manage.py test sales organizations --verbosity 2
cd frontend
npm run build
```

A migração gerada segue a sequência real do seu projeto. Ela adiciona o campo de classificação de dinheiro físico à conta e cria os modelos de abertura e movimentos, incluindo as restrições e a permissão de administração de outros caixas. A atualização não importa recebimentos antigos nem cria uma abertura automaticamente.

Reinicie em terminais separados:

```powershell
cd C:\Projetos\lentis-erp
python backend\manage.py runserver
```

```powershell
cd C:\Projetos\lentis-erp\frontend
npm run dev
```

## Uso e configuração

Acesse **Comercial → Caixa** no frontend. A conta inicial **Caixa da loja**, de código `cash`, aparece automaticamente. Se não há formas e contas iniciais, execute `python backend\manage.py setup_payments` na raiz.

Para um segundo caixa, use o Django Admin em **Vendas → Contas de recebimento**, crie a conta da unidade com um código próprio e marque **Conta de dinheiro físico**. Não use uma conta bancária para representar dinheiro físico. Cada conta pode ter uma abertura por vez.

Qualquer usuário ativo com acesso à unidade pode abrir um caixa e operar a própria abertura. Para permitir que outra pessoa faça suprimento, retirada e fechamento, conceda em **Usuários/Grupos** a permissão **Pode operar e fechar caixas de outros responsáveis**. O superusuário já a possui. Marcar somente **Membro da equipe** não concede essa administração. As permissões existentes do financeiro para baixar parcelas continuam valendo.

## Teste inicial

1. Abra **Comercial → Caixa → Abrir caixa** e informe R$ 100 de dinheiro inicial.
2. Consulte a abertura e faça **Suprimento** de R$ 20, com motivo. O previsto deve ser R$ 120.
3. Faça uma venda de R$ 280 em **Dinheiro**, usando **Caixa da loja**, e marque o recebimento confirmado. O caixa deve mostrar R$ 400 após atualizar; há um movimento associado à venda, com o operador.
4. Registre uma **Sangria / retirada** de R$ 100 com motivo. O previsto passa a R$ 300.
5. Faça uma venda por Pix: ela deve continuar no financeiro, sem aumentar a contagem de dinheiro físico.
6. Clique em **Fechar caixa**. Informando R$ 298 contados, o sistema mostra uma diferença de −R$ 2 e exige justificativa. Após confirmar, o histórico preserva previsto R$ 300, contado R$ 298 e diferença −R$ 2.
7. Uma nova venda com dinheiro recebido na mesma conta exige abrir outro caixa. A interface avisa; o servidor também bloqueia se outra pessoa fechar o caixa durante a operação. Um rascunho sem recebimento ainda pode ser salvo.
8. Abra uma nova abertura com o dinheiro efetivamente contado. O sistema não copia o valor anterior automaticamente.
9. Para testar estorno, cancele uma venda recebida em dinheiro com caixa aberto e saldo suficiente. O estorno entra na abertura atual da mesma conta. Fechamentos anteriores não mudam. Se falta caixa aberto ou dinheiro, a operação inteira é recusada, sem alterar venda ou estoque.

## Regras importantes

- O caixa controla **dinheiro físico**, separado de Pix, transferências e cartões.
- A primeira abertura ativa a exigência de caixa aberto para dinheiro na conta escolhida. Contas sem abertura anterior continuam com o comportamento financeiro anterior.
- Não há importação de recebimentos anteriores para o caixa: informe o dinheiro realmente presente na abertura.
- O saldo do caixa por abertura é diferente do saldo financeiro acumulado de recebimentos da conta. Suprimento, retirada e valor contado não baixam parcelas de clientes nem geram transferências bancárias.
- Diferença exige justificativa e fica registrada. Ela não altera o histórico nem gera um recebimento fictício.
- Caixa fechado não pode ser editado ou reaberto. Abra uma nova sessão de caixa.
- Retirada e estorno exigem saldo físico previsto suficiente. Estoque negativo permitido não significa dinheiro físico negativo permitido.
- Toda operação revalida a unidade e registra o operador. Permissão de outros caixas é avaliada no servidor.
- Se a resposta de uma gravação se perde, a tela oferece **Repetir envio com segurança** e recupera a mesma operação após recarregar a página.
- Troco, impressão do fechamento, transferências para banco e conciliação de cartão não fazem parte desta etapa.

## Validação

A suíte verifica abertura única por conta, repetição, movimentos, limites, justificativa da diferença, integração de recebimentos parciais e vendas, cancelamento na abertura atual, rollback, permissões, sessão/CSRF, histórico imutável e paginação. Há três testes específicos de concorrência de caixa para PostgreSQL, além dos testes de concorrência já existentes.

O ambiente local usa SQLite para a suíte funcional; os cenários que exigem bloqueios reais devem ser executados no PostgreSQL do seu projeto com o comando indicado na instalação. Também foram verificados o build de TypeScript/Vite e o fluxo React + Django no navegador, incluindo perda de resposta, recarga, tema escuro e largura móvel.

Os bloqueios de conta serializam abertura, lançamento e fechamento. O lock de repetição no usuário do checkout/recebimento usa `no_key=True` para permitir os vínculos de histórico durante a transação, conforme a [documentação oficial do Django](https://docs.djangoproject.com/en/5.2/ref/models/querysets/#select-for-update). Essa opção é própria do PostgreSQL; o projeto continua usando PostgreSQL.

## Conteúdo

- Backend: arquivos completos do app `sales`, incluindo modelos e serviços financeiros atualizados; novos `cash_models.py`, `cash_services.py`, `cash_serializers.py`, `cash_views.py` e `test_cash.py`.
- Frontend: `api.ts`, `AppLayout.tsx`, `Sales.tsx`, `Receivables.tsx`, `PaymentPlanBuilder.tsx` e os novos `CashRegister.tsx`/`CashRegister.css`.
- Documentação: este guia e `docs/regras-negocio.md`.
