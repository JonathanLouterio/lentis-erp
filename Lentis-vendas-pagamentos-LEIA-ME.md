# Lentis — venda, parcelamento e recebimentos

Este pacote substitui a tela básica de vendas por um atendimento com cliente, produtos, desconto, formas de pagamento e resumo. Os arquivos estão completos e codificados em UTF-8.

## Instalação no projeto que já está funcionando

1. Pare o Django e o Vite com Ctrl+C. Extraia o ZIP em `C:\Projetos\lentis-erp`, substituindo os arquivos das pastas `backend` e `frontend`. Não extraia somente dentro de `frontend` ou `backend`.
2. No terminal do VS Code, com `.venv` ativada:

```powershell
cd C:\Projetos\lentis-erp
python backend\manage.py makemigrations sales
python backend\manage.py migrate
python backend\manage.py setup_payments
python backend\manage.py check
python backend\manage.py test sales organizations --verbosity 2
```

A migração deve adicionar `discount_amount` à venda e criar as contas, formas de pagamento, pagamentos da venda, parcelas, lançamentos e identificadores das operações. Não é necessário editar `INSTALLED_APPS`: o pacote usa o app `sales` já instalado. A migração é gerada no seu projeto para respeitar os nomes e dependências das migrações de vendas que você já tem.

`setup_payments` cria contas "Caixa da loja" e "Banco da loja" e sete formas de pagamento para cada unidade ativa. Pode executar novamente: não altera nomes, tipos ou estados dos registros existentes. Para uma única unidade, use `python backend\manage.py setup_payments --store-id 1` com o ID correto.

3. Confira o frontend:

```powershell
cd C:\Projetos\lentis-erp\frontend
npm run build
npm run dev
```

4. Em outro terminal, execute o backend:

```powershell
cd C:\Projetos\lentis-erp
python backend\manage.py runserver
```

Acesse `http://127.0.0.1:5173/`. Em **Comercial → Vendas**, abra **Nova venda**. Em **Gestão → Financeiro**, consulte as parcelas e registre os recebimentos.

## O que está implementado

- Atendimento em uma tela, com busca de produto por nome, código ou código de barras; quantidade, preço, desconto por item e desconto da venda.
- Dinheiro, Pix, transferência, débito, crédito, boleto e crediário, com combinação de até 20 pagamentos.
- Entrada e saldo parcelado sem juros em até 12 parcelas. As diferenças de centavos são distribuídas nas primeiras parcelas. Os vencimentos mensais preservam o dia original, usando o último dia em meses mais curtos.
- Identificação obrigatória do cliente para boleto e crediário; venda balcão para outras formas.
- Conta de recebimento por pagamento. Dinheiro, Pix e transferência só entram como recebidos quando você marcar **Recebimento confirmado**.
- Cartões geram parcelas a receber da operadora; boleto e crediário geram parcelas a receber do cliente. O primeiro repasse de cartão é uma previsão informada no atendimento.
- Salvar rascunho conserva os dados sem gerar parcelas, lançamentos ou baixa de estoque.
- Concluir salva o atendimento, baixa o estoque, gera as parcelas e registra os valores confirmados na mesma transação. Qualquer falha desfaz a operação inteira.
- Uma resposta perdida pode ser recuperada usando **Repetir envio com segurança**. O identificador do envio evita duplicação e fica preservado na sessão do navegador, separado por usuário e unidade.
- Financeiro com filtros por situação e responsável, recebimento total ou parcial, saldo da parcela e histórico de recebimentos e estornos.
- Administradores com acesso à unidade podem confirmar recebimentos posteriores e cancelar vendas concluídas. Ser administrador não concede acesso a uma unidade sem vínculo.
- Cancelamento devolve o estoque, fecha as parcelas e cria estornos para os recebimentos já registrados, preservando o histórico. Não remove a venda, as parcelas ou os lançamentos.
- Contas e formas podem ser configuradas no Django Admin, em **Vendas → Contas de recebimento / Formas de pagamento**. O tipo e a unidade de uma forma já criada são fixos; para outro tipo, cadastre outra forma.
- Vendas antigas continuam acessíveis. Os pagamentos de vendas antigas concluídas não são inventados ou preenchidos automaticamente.

## Limites desta primeira versão

O módulo registra e controla valores dentro do Lentis. Não emite boletos, não gera cobranças Pix, não captura pagamentos em maquininhas e não envia transferências ou reembolsos bancários. Confirme somente recebimentos reais. Em um cancelamento, a devolução efetiva do dinheiro precisa ser realizada e conferida separadamente.

Não há juros, taxas de operadora, antecipação, conciliação bancária, contas a pagar ou saldo inicial de conta. O saldo mostrado representa somente os recebimentos e estornos registrados por este módulo. Pagamentos com cartão são previsões de repasse pelo valor bruto da venda.

## Teste rápido

Use produtos de teste com estoque disponível:

1. Venda de R$ 700: entrada Pix de R$ 150 confirmada e crediário de R$ 550 em 3x, com cliente identificado.
2. Confira parcelas de R$ 183,34, R$ 183,33 e R$ 183,33. Sem cliente identificado, a conclusão deve ficar indisponível.
3. Salve como rascunho; confira que o estoque não mudou. Reabra e conclua.
4. No Financeiro, registre R$ 50 da primeira parcela como administrador. O saldo deve ser R$ 133,34.
5. Cancele a venda de teste com motivo. Confira devolução do estoque, parcelas canceladas e estornos mantendo o histórico.
6. Teste uma venda por cartão: ela deve aparecer como valor a receber da operadora, sem somar ao recebido imediatamente.
7. Troque de unidade e confirme que seus registros ficam separados.

## Verificação realizada antes de entregar

- TypeScript e build Vite passaram.
- 131 testes encontrados no ambiente local: 126 passaram e 5 testes de concorrência foram ignorados por dependerem dos locks de PostgreSQL. Execute o comando de testes acima no seu PostgreSQL para verificar esses casos também. A quantidade total no seu projeto pode variar pelos testes de clientes já existentes.
- Teste no navegador com React e a API Django reais: rascunho, venda com entrada e parcelas, centavos e vencimentos, desconto, exigência de cliente, resposta perdida e recuperação após recarregar, recebimento parcial, cancelamento com estorno e separação por unidade.
- Interface conferida nos temas claro e escuro e em largura de celular.

## Arquivos

O ZIP contém apenas os arquivos do app `sales` e do frontend necessários a esta alteração, além deste guia. Não inclui `.env`, credenciais, banco de dados, `.venv`, `node_modules`, `dist` ou as pastas do servidor usado nos testes.

Depois que tudo passar, adicione os arquivos alterados e a migração gerada ao Git. Mantenha eventuais cópias de segurança fora de `src` e não inclua os arquivos de teste locais ou backups na sua aplicação.
