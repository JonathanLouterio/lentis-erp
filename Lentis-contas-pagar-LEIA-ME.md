# Lentis ERP — contas a pagar de compras

Pacote incremental para a base com fornecedores e compras já integrados. Extraia na raiz `C:\Projetos\lentis-erp`, substituindo os arquivos correspondentes e preservando as pastas do ZIP. Os arquivos são completos e estão em UTF-8.

## O que entrou

- Menu **Gestão → Contas a pagar** e atalho **Gerar / consultar contas a pagar** nas compras recebidas.
- Geração explícita de um plano por compra, em 1 a 12 parcelas, com prévia exata de valores e vencimentos.
- Listas paginadas de títulos em aberto, vencidos, quitados ou todos.
- Pagamentos parciais/totais, referência do comprovante, data, conta e forma de saída.
- Histórico por parcela, autor, horário, saldo atual e estorno integral com justificativa.
- Pagamentos em dinheiro vinculados ao caixa aberto; o histórico do caixa identifica a compra.
- Reenvio com o mesmo identificador, inclusive após atualizar a página na mesma aba, para recuperar respostas perdidas sem duplicação.
- Permissões, isolamento por unidade, validação de CSRF, transações e proteção contra pagamentos simultâneos acima do saldo.

## Instalação no PowerShell

Pare o servidor Django e o Vite com Ctrl+C antes de substituir os arquivos. Na raiz do projeto, com a `.venv` ativa:

```powershell
cd C:\Projetos\lentis-erp
git switch -c feat/contas-pagar
```

Se essa branch já existir, apenas use `git switch feat/contas-pagar`. Extraia o ZIP **na raiz do projeto**, sem criar uma pasta intermediária. O pacote não contém `.env` nem altera configurações do projeto.

Depois de extrair:

```powershell
cd C:\Projetos\lentis-erp
python backend\manage.py makemigrations purchases
python backend\manage.py migrate
python backend\manage.py check
python backend\manage.py test purchases sales organizations --verbosity 2
cd C:\Projetos\lentis-erp\frontend
npm run build
```

A migration será gerada a partir do histórico real do seu projeto, acrescentando `PayablePlan`, `PayableInstallment` e `PayablePayment`. Nenhuma migration já aplicada precisa ser apagada ou refeita. Não é necessário instalar dependências novas.

Para subir novamente, use dois terminais:

```powershell
# Backend, na raiz e com a .venv ativa
cd C:\Projetos\lentis-erp
python backend\manage.py runserver 127.0.0.1:8000
```

```powershell
# Frontend
cd C:\Projetos\lentis-erp\frontend
npm run dev
```

## Permissões no admin

Um superusuário ativo com acesso à unidade pode testar tudo. Para usuários comuns, conceda por usuário ou grupo:

| Operação | Permissões |
|---|---|
| Consultar títulos e opções | `purchases.view_payableplan` |
| Gerar parcelas | acima + `purchases.add_payableplan` + `purchases.view_purchase` |
| Registrar pagamentos | consulta + `purchases.pay_payable` |
| Estornar pagamentos | consulta + `purchases.reverse_payable` |
| Movimentar caixa aberto por outra pessoa | anteriores conforme ação + `sales.manage_cash` |

Essas permissões aparecem após a migration. O vínculo com a unidade precisa continuar ativo. O indicador staff sozinho não libera operações. Permissões de compras existentes continuam necessárias para abrir ou confirmar compras.

## Teste visual sugerido

1. Abra uma compra recebida com total positivo e clique em **Gerar / consultar contas a pagar**.
2. Escolha 3 parcelas, confira a prévia, marque a confirmação e gere. Não deve aparecer saída financeira neste momento.
3. Abra a primeira parcela e registre um valor menor que seu saldo, por Pix e conta bancária. Confira saldo parcial e histórico.
4. Pague o restante. A parcela deve ficar quitada.
5. Estorne um pagamento com justificativa. O lançamento original permanece, surge a contrapartida e o saldo da parcela é recomposto.
6. Para dinheiro, abra um caixa com saldo suficiente, pague outra parcela e confira **Caixa → Movimentos**. A saída identifica o fornecedor e a compra.
7. Com outro usuário sem as permissões, confira que a consulta ou escrita é bloqueada; outra unidade não pode enxergar ou pagar este título.

Se uma resposta se perder, use **Conferir / repetir envio**. Não crie outro pagamento para substituir um envio incerto. O mesmo identificador fica em memória e, quando o navegador permite, em `sessionStorage` da mesma aba, separado por usuário e unidade.

## Regras e limites desta etapa

- O registro não envia Pix, transferência ou cobrança ao banco. Registre pagamentos já efetuados externamente.
- Pix, transferência e débito exigem conta bancária. Dinheiro exige conta de caixa físico ativa, sessão aberta, responsável ou permissão para operar outro caixa e saldo suficiente. A data do dinheiro é hoje; pagamentos bancários podem ter data passada, nunca futura.
- O saldo da conta é a soma dos recebimentos líquidos menos pagamentos líquidos registrados. Não inclui saldo inicial bancário, nem equivale ao saldo previsto de uma sessão de caixa. Por isso não bloqueamos uma saída bancária com base nesse saldo parcial.
- Estorno é integral por lançamento; para corrigir parte, estorne o lançamento e registre o valor correto. Não há exclusão de histórico. O estorno de dinheiro exige caixa aberto atual e não altera fechamentos anteriores.
- Não há juros, multas, descontos financeiros, renegociação, edição/cancelamento de planos ou devolução de compras nesta etapa. Confira as condições antes de gerar. Compras de total zero não geram dívida.
- Pagamento a fornecedor aparece como retirada no modelo de caixa e estorno como suprimento; a tela mostra rótulos específicos e vínculo com a compra. Movimentos manuais de caixa não baixam contas a pagar.

## Validação do pacote

Regressão local: 367 casos, com 17 casos de locks ignorados por exigirem PostgreSQL. O módulo final também passou em 21 casos, com seus 2 casos de concorrência ignorados no SQLite.

Build TypeScript/Vite e fluxo de navegador verificados em ambiente isolado com dados fictícios, incluindo resposta perdida e reenvio após atualizar a página, parcela parcial/quitada, estorno e saída em caixa.

O ambiente local de validação usa SQLite com modelos de apoio; os testes de concorrência usam PostgreSQL e são ignorados nesse ambiente. Rode os comandos acima no seu PostgreSQL Docker para verificar o projeto real, migrations e locks. O pacote mantém os testes anteriores.

## Arquivos que não pertencem a esta alteração

Preserve fora do commit o logo solto, `backend/organizations/Product-model.txt`, `regras-negocio.md` da raiz e a alteração pendente antiga em `Lentis-regras-comerciais-LEIA-ME.md`. As regras atualizadas deste módulo estão em `docs/regras-negocio.md`.

Após testes e conferência visual, use `git status --short` para separar estes arquivos e a nova migration antes do commit.
