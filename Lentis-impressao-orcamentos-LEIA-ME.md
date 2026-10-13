# Lentis ERP — Impressão e PDF de orçamentos

Pacote para o projeto com orçamentos já integrado à main. Arquivos completos em UTF-8, nas pastas corretas. Não há migração nem dependência nova.

## Instalar

Antes de extrair:

```powershell
cd C:\Projetos\lentis-erp
git branch --show-current
git status --short
git switch -c feat/impressao-orcamentos
```

Extraia o ZIP em C:\Projetos\lentis-erp, substituindo os arquivos correspondentes. Preserve a estrutura backend/sales/templates/sales: o arquivo HTML precisa ficar nessa pasta. Não coloque cópias de backup .tsx em frontend/src.

Com .venv ativa e PostgreSQL em execução:

```powershell
cd C:\Projetos\lentis-erp
python backend\manage.py check
python backend\manage.py test sales organizations --verbosity 2
cd frontend
npm run build
```

Reinicie os servidores, cada um no seu terminal:

```powershell
cd C:\Projetos\lentis-erp
python backend\manage.py runserver 127.0.0.1:8000
```

```powershell
cd C:\Projetos\lentis-erp\frontend
npm run dev
```

## Usar

1. Abra Comercial → Orçamentos e selecione um orçamento salvo.
2. Clique em Imprimir / Salvar PDF. Uma nova aba mostra a proposta.
3. Na prévia, clique em Imprimir / Salvar PDF e escolha a impressora ou Salvar como PDF.
4. Selecione A4. Desative os cabeçalhos e rodapés automáticos do navegador para evitar URL/data extras. Use escala 100% ou a escala padrão; a página já tem margens próprias. Gráficos de plano de fundo mantêm as faixas coloridas, mas o documento também é legível sem eles.

O botão fica indisponível enquanto houver alterações não salvas. Se o navegador bloquear a nova aba, permita pop-ups para 127.0.0.1:5173 e clique novamente.

A impressão conserva os preços negociados e totais salvos. Os dados cadastrais da unidade e do cliente são os atuais no momento da consulta. Telefone e e-mail da unidade aparecem se estiverem preenchidos no admin. A unidade ainda não possui campos de endereço/CNPJ; não há dados fictícios no documento.

A prévia não altera o orçamento, não envia mensagens e não confirma pagamentos. O arquivo PDF é salvo pelo navegador, não fica arquivado automaticamente no ERP.

## Conferência sugerida

- Abra uma proposta, confira cliente, produtos, quantidades, descontos, total, validade e revisão.
- Salve o PDF e confira acentos e valores em reais.
- Confira uma proposta com vários itens: cabeçalho da tabela repetido, numeração de páginas no Chrome/Edge e totais ao final.
- Rascunho, validade vencida, recusa e conversão devem aparecer identificados.
- Troque a unidade: um orçamento de outra unidade não pode ser consultado pela URL de impressão.

## Validação local

6 testes novos de impressão passaram. Regressão com 249 testes, 240 aprovados e 9 ignorados por exigirem bloqueios de banco indisponíveis no SQLite isolado. Execute a suíte acima no seu PostgreSQL.

Build TypeScript/Vite aprovado. Fluxo real React + Django conferido com abertura da nova aba, bloqueio de formulário alterado, prévia em celular e PDFs A4 com 1 e 55 itens. As cinco páginas da proposta extensa foram renderizadas e inspecionadas: produtos, acentos, observações, totais e numeração preservados.

## Arquivos incluídos

- backend/sales/urls.py
- backend/sales/quote_print_views.py
- backend/sales/test_quote_print.py
- backend/sales/templates/sales/quote_print.html
- frontend/src/components/Quotes.tsx
- docs/regras-negocio.md
- Este guia

Depois da validação, envie git branch --show-current e git status --short para conferirmos o commit desta etapa.
