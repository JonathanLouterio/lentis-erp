# Lentis ERP — Orçamentos

Pacote completo para o projeto que já possui vendas, pagamentos, caixa e dashboard operacional. Arquivos em UTF-8. Extraia na raiz C:\Projetos\lentis-erp, preservando as pastas backend e frontend. Substitua os arquivos correspondentes; não cole trechos e não mantenha cópias .tsx de backup dentro de src.

## Instalação

Pare os servidores com Ctrl+C e confira sua branch antes de extrair:

```powershell
cd C:\Projetos\lentis-erp
git branch --show-current
git status --short
git switch -c feat/orcamentos
```

Depois de extrair, com a .venv ativa e o PostgreSQL em execução:

```powershell
cd C:\Projetos\lentis-erp
python backend\manage.py makemigrations sales
python backend\manage.py migrate
python backend\manage.py check
python backend\manage.py test sales organizations --verbosity 2
cd frontend
npm run build
```

A migração é gerada conforme o histórico do seu projeto. É esperado criar Quote, QuoteItem, QuoteEvent e QuoteOperation, com restrições de valores e conversão. Não há preenchimento de campos obrigatórios em registros antigos.

Em um terminal:

```powershell
cd C:\Projetos\lentis-erp
python backend\manage.py runserver 127.0.0.1:8000
```

Em outro:

```powershell
cd C:\Projetos\lentis-erp\frontend
npm run dev
```

## Teste na tela

Acesse http://127.0.0.1:5173/ e abra Comercial → Orçamentos.

1. Crie um orçamento, selecione cliente, validade e produtos; confira quantidades, preços e descontos.
2. Salve. Prepare a proposta e registre o aceite após confirmar com o cliente.
3. Converta em venda. Abra a venda gerada e confira os itens: ela começa em rascunho, sem movimentação de estoque ou financeiro.
4. Defina os pagamentos e conclua pelo fluxo de vendas existente. Somente a conclusão movimenta estoque e financeiro.
5. Em outra proposta, altere os valores após o aceite. Salvar deve retornar ao rascunho e exigir novo aceite.
6. Confira a validade vencida, a recusa com motivo e o histórico. Orçamentos de outra unidade não devem aparecer ao trocar a unidade.

Preparar proposta apenas muda a situação no sistema: não envia e-mail ou WhatsApp. O aceite é registrado pelo operador. PDF e assinatura digital ficam para uma etapa posterior.

## Validação deste pacote

- 17 testes de API passaram no ambiente isolado com SQLite; mais 1 teste de conversão concorrente acompanha o pacote para execução em PostgreSQL (ignorado no SQLite).
- Regressão final: 243 testes executados, sem falhas; 9 testes que exigem bloqueios de banco foram ignorados no ambiente SQLite (234 passaram).
- Build TypeScript/Vite e fluxo real React + Django conferidos no navegador, incluindo conversão com resposta interrompida e repetição sem duplicar venda, conclusão pelo pagamento, tema escuro e largura de celular.
- O ambiente isolado não substitui os testes acima no seu PostgreSQL. Nenhum arquivo de configuração de teste é incluído neste pacote.

## Arquivos

Backend: models.py, admin.py, urls.py e novos quote_models.py, quote_services.py, quote_serializers.py, quote_views.py, test_quotes.py em backend/sales.
Frontend: api.ts, components/AppLayout.tsx, components/Quotes.tsx, components/Quotes.css em frontend/src.
Documentação: docs/regras-negocio.md e este guia. Os arquivos de vendas, caixa e dashboard existentes são reutilizados.

Não inclua a logo original, Product-model.txt ou o regras-negocio.md duplicado da raiz no commit deste passo. Preserve outras alterações locais que não façam parte dos orçamentos.
