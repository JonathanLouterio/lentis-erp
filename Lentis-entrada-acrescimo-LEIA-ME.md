# Lentis — Entrada mínima e acréscimo sobre o saldo

Entrega: 28/10/2026. Base: etapa de permissões de fornecedores, painel e relatórios já integrada.

## O que muda

- Entrada mínima recebida de 40% dos produtos após descontos, antes do acréscimo, para planos com boleto/crediário parcelado.
- Percentual ajustável por venda, de 0 a 100%, com duas casas decimais. Valor inicial zero.
- Taxa única sobre o saldo de boleto/crediário. Não é taxa mensal nem juros compostos.
- Exemplo: produtos R$ 1.000, entrada R$ 400, saldo R$ 600, taxa 5% → acréscimo R$ 30, total R$ 1.030 e saldo em duas parcelas de R$ 315.
- Entrada pode somar dinheiro, Pix e transferência confirmados, respeitando permissão de recebimento e caixa.
- Entrada + uma parcela de saldo já exige os 40%. Uma única cobrança integral sem outros pagamentos não é considerada parcelamento.
- Cartão fica fora do acréscimo e da regra de entrada. Uma taxa informada sem nenhum saldo em boleto/crediário é rejeitada.
- Pode salvar rascunho com entrada insuficiente ou ainda não recebida. A conclusão revalida a regra no servidor.
- As linhas de pagamento da tela mostram o valor SEM acréscimo; abaixo aparecem acréscimo, total da forma e parcelas COM acréscimo.
- O percentual é aplicado por linha de boleto/crediário, arredondado comercialmente ao centavo. O mínimo da entrada arredonda para cima no centavo.
- Vendas antigas ficam com acréscimo zero. A migração não altera parcelas existentes. Rascunhos antigos devem atender à regra ao serem concluídos.
- O valor do acréscimo não reduz o desconto sujeito a autorização. Painel e relatório de vendas passam a somá-lo no total vendido.
- O relatório ampliado de contas a receber com cores permanece para a próxima etapa.

## Aplicar no VS Code

1. Com seu trabalho anterior salvo, na raiz do projeto, crie a branch ANTES de extrair:

```powershell
cd C:\Projetos\lentis-erp
git switch main
git pull --ff-only origin main
git switch -c feat/entrada-acrescimo
```

2. Se estiver usando dados importantes, execute o backup já disponível no projeto:

```powershell
.\scripts\Backup-E-Teste-Lentis.ps1
```

3. Pare temporariamente backend e frontend com Ctrl+C. Extraia o ZIP na raiz `C:\Projetos\lentis-erp`, preservando as pastas e substituindo somente os arquivos incluídos. Não extraia dentro de `backend` ou `frontend`.

4. Com a `.venv` ativa, execute:

```powershell
cd C:\Projetos\lentis-erp
python backend\manage.py migrate
python backend\manage.py makemigrations --check --dry-run
python backend\manage.py check
python backend\manage.py test accounts organizations sales purchases --verbosity 2
cd frontend
npm run build
```

A migração entregue é `sales.0015_sale_financing`. Não é necessário gerar uma nova migração. Ela depende de sales.0014 e organizations.0010, das etapas anteriores.

Para uma verificação dirigida, sem substituir a regressão completa:

```powershell
python backend\manage.py test sales.test_financing sales.test_payments sales.test_payment_terms sales.test_dashboard organizations.test_customer_history --verbosity 2
```

5. Reinicie em terminais separados:

```powershell
cd C:\Projetos\lentis-erp
python backend\manage.py runserver 127.0.0.1:8000
```

```powershell
cd C:\Projetos\lentis-erp\frontend
npm run dev
```

## Conferência manual

Na base de testes:

1. Abra uma nova venda, selecione cliente e produtos totalizando R$ 1.000.
2. Informe acréscimo de 5%. Abra “Entrada + parcelas”.
3. Informe entrada de R$ 400, selecione Pix e a conta, confirme que foi recebida. Só marque após conferir o recebimento real; para testar sem recebimento, salve rascunho.
4. Selecione crediário e duas parcelas do saldo. Aplique o plano.
5. Confira base de R$ 1.000, acréscimo de R$ 30, total de R$ 1.030 e parcelas de R$ 315.
6. Reduza a entrada para R$ 399,99: a conclusão deve bloquear, mantendo disponível o rascunho.
7. Volte para R$ 400 e desmarque o recebimento: a conclusão também deve bloquear.
8. Salve e reabra o rascunho. A taxa deve continuar 5%, sem aplicar acréscimo sobre acréscimo.
9. Conclua com entrada confirmada e confira parcelas, estoque, caixa/banco e total vendido no painel/relatório.
10. Repita com boleto. Confira também uma venda em cartão sem acréscimo.

## Verificação desta entrega

- Regressão local: 622 testes descobertos, sem falhas; 19 dependem de PostgreSQL e foram pulados no ambiente SQLite.
- O executor local da regressão usa hash de senha simplificado apenas para acelerar testes. Nenhuma configuração de senha do projeto é alterada.
- 67 testes dirigidos de pagamentos/entrada/acréscimo passaram, com 2 skips de concorrência; 29 testes de histórico/painel passaram, com o hash padrão.
- Migração aplicada e verificação de modelos sem alterações pendentes.
- Build TypeScript/Vite concluído no ambiente de verificação.
- Navegador: entrada insuficiente/não confirmada, percentual ajustável, salvar/reabrir rascunho, conferência, confirmação pela API, parcelas e viewport móvel validados.
- Execute os testes acima no seu PostgreSQL para validar também os cenários de locks/concorrência.

Os testes antigos de parcelas, painel e histórico foram adequados para incluir a entrada mínima. As verificações de centavos, idempotência e separação de recebimentos foram mantidas.

## Contrato da API

- Checkout e prévia aceitam `financing_rate`, opcional, padrão 0.
- `payments[].amount` na ESCRITA continua sendo o valor principal distribuído, sem acréscimo. A soma deve ser igual ao valor dos produtos após descontos ao concluir.
- O backend calcula o acréscimo e grava o valor final de cada forma. Na LEITURA, `amount` inclui acréscimo; `principal_amount` e `financing_amount` discriminam a composição.
- A venda retorna `base_total`, `financing_rate`, `financing_amount` e `total` final. A prévia retorna os mesmos totais e as parcelas finais.
- Enviar um `total`/`financing_amount` forjado não altera os valores calculados.
- Nova tentativa após erro de validação deve ter novo `request_id` se o conteúdo foi alterado. A interface já administra esse fluxo.
- Confirmação e cancelamento preservam as permissões existentes; não há novas permissões automáticas.

## Salvar no Git depois de testar

Use apenas os arquivos desta entrega; não inclua imagens soltas, RARs ou arquivos de referência antigos.

```powershell
cd C:\Projetos\lentis-erp
git add backend/organizations/test_customer_history.py
git add backend/sales/commercial_services.py
git add backend/sales/dashboard_views.py
git add backend/sales/financing.py
git add backend/sales/migrations/0015_sale_financing.py
git add backend/sales/models.py
git add backend/sales/payment_models.py
git add backend/sales/payment_serializers.py
git add backend/sales/payment_services.py
git add backend/sales/payment_views.py
git add backend/sales/serializers.py
git add backend/sales/services.py
git add backend/sales/test_dashboard.py
git add backend/sales/test_financing.py
git add backend/sales/test_payment_terms.py
git add backend/sales/test_payments.py
git add docs/regras-negocio.md
git add frontend/src/api.ts
git add frontend/src/components/PaymentPlanBuilder.tsx
git add frontend/src/components/Sales.tsx
git add frontend/src/components/saleFinancing.ts
git add Lentis-entrada-acrescimo-LEIA-ME.md
git diff --cached --check
git --no-pager diff --cached --stat
git commit -m "feat: aplica entrada minima e acrescimo sobre saldo parcelado"
git push -u origin feat/entrada-acrescimo
git status
```
