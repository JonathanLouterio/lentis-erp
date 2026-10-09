# Lentis — Entrada e condições de parcelamento

Este pacote atualiza a etapa já instalada de regras comerciais. Os arquivos são completos, em UTF-8, e mantêm a organização do projeto.

## Instalação no VS Code

1. Pare o Django e o Vite nos seus terminais com Ctrl+C.
2. Na raiz do projeto, crie a branch:

```powershell
cd C:\Projetos\lentis-erp
git switch -c feat/condicoes-pagamento
```

3. Extraia este ZIP diretamente em `C:\Projetos\lentis-erp`, aceitando substituir os arquivos correspondentes. Ele contém as pastas `backend`, `frontend` e `docs`.
   - `api.ts` vai em `frontend/src`.
   - `Sales.tsx`, `Sales.css`, `saleMoney.ts` e `PaymentPlanBuilder.tsx` vão em `frontend/src/components`.
   - Não coloque uma cópia dos componentes diretamente em `frontend/src`.
4. Execute, ainda na raiz:

```powershell
python backend\manage.py makemigrations sales
python backend\manage.py migrate
python backend\manage.py check
python backend\manage.py test sales organizations --verbosity 2
cd frontend
npm run build
```

A migração é gerada sobre a sequência real do seu projeto. Ela adiciona máximo de parcelas à forma de pagamento e os campos de intervalo ao pagamento da venda, além das validações. Os campos têm padrões, então não deve pedir um valor para registros existentes. Pagamentos anteriores ficam mensais.

5. Reinicie o backend e o frontend em terminais separados:

```powershell
# Terminal do backend
cd C:\Projetos\lentis-erp
python backend\manage.py runserver
```

```powershell
# Terminal do frontend
cd C:\Projetos\lentis-erp\frontend
npm run dev
```

## Configuração inicial

Em `http://127.0.0.1:8000/admin/`, abra **Vendas → Formas de pagamento**. Edite, por exemplo, o crediário da matriz e configure **Máximo de parcelas**. O intervalo aceito é 1 a 12 parcelas. Dinheiro, Pix, transferência e débito sempre aceitam uma, mesmo se o cadastro mostrar 12.

Não é necessário executar `setup_payments` novamente se as formas e contas já existem.

## Teste pelo frontend

1. Abra **Comercial → Vendas → Nova venda**.
2. Selecione um cliente ativo e os produtos.
3. No pagamento, clique em **Entrada + parcelas**.
4. Exemplo com total de R$ 700: informe entrada de R$ 150 por Pix; saldo em crediário, três parcelas, primeiro vencimento e intervalo de um mês. Marque a entrada recebida apenas se o recebimento já foi conferido.
5. Clique em **Aplicar entrada e parcelas**. O plano substitui os pagamentos atuais. Enquanto você edita o total, a linha do saldo acompanha a diferença automaticamente; após salvar/reabrir, os valores ficam registrados e podem ser editados.
6. Confira as parcelas. Para R$ 550 de saldo: R$ 183,34, R$ 183,33 e R$ 183,33.
7. Experimente **Dias → 15**: os vencimentos avançam quinze dias corridos a partir do primeiro.
8. Salve como rascunho e reabra. Formas, valores, intervalos e datas devem permanecer.
9. Clique em **Concluir venda**. A conferência mostra as parcelas validadas pelo servidor. Só **Confirmar venda** grava a conclusão e movimenta estoque e financeiro.
10. Reduza no admin o máximo de parcelas do crediário para duas. Um novo plano não deve oferecer três; um rascunho antigo de três deve exigir ajuste antes da conclusão. Vendas já concluídas permanecem com o histórico original.

Boleto e crediário precisam de cliente identificado. Cartão de crédito gera recebíveis da operadora, mantendo a separação já existente no financeiro. A entrada pode ser zero. Para pagamento integral à vista, use a linha normal de pagamento.

## Regras e compatibilidade

- Até 12 parcelas por forma; limite configurável por cadastro/unidade.
- Intervalo em meses de 1 a 12; em dias de 1 a 365.
- Datas impossíveis, intervalo zero, plano fora do limite e parcelas inferiores a um centavo são rejeitados no servidor.
- Parcelas mensais mantêm o dia original, com ajuste no fim do mês. Dias são corridos; não há ajuste para feriado ou dia útil.
- O total dos pagamentos deve ser exatamente o total da venda.
- A prévia não grava dados; o checkout mantém a transação e o identificador para impedir duplicação em repetições.
- Limites são revalidados ao concluir um rascunho. Alterar um cadastro não recalcula parcelas históricas.
- Os cálculos desta etapa são sem juros. Taxas, juros, modelos de condições reutilizáveis e datas individuais por parcela são evoluções futuras.

## Arquivos do pacote

- Backend: `sales/admin.py`, `payment_models.py`, `payment_serializers.py`, `payment_services.py`, `payment_views.py`, `payment_schedule.py`, `urls.py` e `test_payment_terms.py`.
- Frontend: `src/api.ts`, `components/Sales.tsx`, `Sales.css`, `saleMoney.ts` e `PaymentPlanBuilder.tsx`.
- Documentação: este guia e `docs/regras-negocio.md`.

## Validação realizada

Testes de cálculo, entrada + saldo, correspondência entre prévia e parcelas gravadas, intervalos, limites atuais, acesso por unidade, sessão/CSRF, históricos e repetição do checkout. Build de TypeScript/Vite e teste com React e Django reais em navegador, incluindo rascunho, confirmação, tema escuro e largura móvel.

O ambiente local de verificação usa SQLite: os testes existentes de concorrência que exigem bloqueios do PostgreSQL são ignorados nele. Execute a suíte acima no PostgreSQL do seu projeto para validar esses cenários e a migração real.
