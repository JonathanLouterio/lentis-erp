# Lentis — limites de desconto e autorização

Pacote para a versão da main que já contém vendas, pagamentos, recebimentos e estoque negativo. Arquivos completos em UTF-8, com a estrutura de pastas preservada.

## Instalação

1. Pare Django e Vite (Ctrl+C).
2. No terminal com a .venv ativa:

```powershell
cd C:\Projetos\lentis-erp
git switch -c feat/regras-comerciais
```

3. Extraia o ZIP diretamente em `C:\Projetos\lentis-erp`, substituindo os arquivos correspondentes. Preserve as pastas do ZIP. Os componentes `.tsx` ficam em `frontend/src/components`; `api.ts` fica em `frontend/src`. Não coloque cópias de componentes em `frontend/src`.
4. Execute:

```powershell
cd C:\Projetos\lentis-erp
python backend\manage.py makemigrations sales
python backend\manage.py migrate
python backend\manage.py check
python backend\manage.py test sales organizations --verbosity 2
cd C:\Projetos\lentis-erp\frontend
npm run build
```

O Django gera a próxima migração de sales. Ela cria as políticas e os registros de autorização, acrescenta o preço de referência nos itens e registra a nova permissão. Não são necessárias dependências novas. Reinicie os servidores pelos comandos habituais.

## Configuração inicial

Até configurar um perfil/unidade, o comportamento anterior permanece: limite de 100%. Nenhum percentual comercial foi escolhido automaticamente.

1. Acesse `http://127.0.0.1:8000/admin/` com o superusuário.
2. Em **Vendas → Limites de desconto por perfil → Adicionar**, escolha a unidade, o perfil **Vendedor** e um percentual. Para conferir o fluxo, um exemplo é **10%**. Cadastre cada perfil/unidade que desejar restringir.
3. Seu superusuário já pode autorizar descontos. Para outra conta autorizadora, conceda em Usuários/Grupos a permissão **Pode autorizar descontos acima do limite** do modelo de registros de autorização. Essa conta também precisa de vínculo ativo com a unidade.
4. O solicitante e o autorizador devem ser pessoas diferentes.

## Conferência na interface

Use duas sessões de navegador: uma normal e outra anônima, ou navegadores diferentes. Entre com o vendedor em uma e com o administrador na outra.

1. Com limite de 10% para o vendedor, crie uma venda e aplique 20% de desconto. **Concluir venda** fica bloqueado, mas o rascunho pode ser salvo.
2. Informe **Justificativa do desconto** e clique em **Solicitar autorização**. O sistema salva o rascunho quando necessário e registra a solicitação. Nenhum estoque ou recebimento é lançado.
3. Na sessão do administrador, abra **Comercial → Vendas → Atualizar lista**. A venda aparece com **Desconto aguardando autorização**.
4. Abra a venda. Em **Autorizações de desconto**, informe **Motivo da decisão** e clique em **Autorizar desconto** ou **Recusar desconto**.
5. Na sessão do vendedor, clique em **Atualizar autorização**. Com os mesmos valores aprovados, **Concluir venda** será habilitado após carregar os dados.
6. Confirme a venda. A baixa de estoque e os registros financeiros seguem o fluxo atual. A decisão continua no histórico.
7. Confira também que alterar o desconto acima do limite bloqueia novamente a conclusão para valores não autorizados. Alterar o preço unitário para baixo também conta como desconto.

A aprovação não finaliza a venda automaticamente. Para conferir a regra do vendedor, faça o atendimento com uma conta comum vinculada à unidade: o superusuário tem limite de 100%.

## Validação

- 170 testes executados no ambiente isolado SQLite: 165 passaram e cinco testes existentes de concorrência dependem de PostgreSQL. A suíte inclui 25 testes novos das regras comerciais; execute os comandos acima no seu banco para conferir também a concorrência.
- Build de produção e TypeScript aprovados.
- Fluxo Django + React verificado com sessões distintas: solicitação de 20% por vendedor com limite de 10%, aprovação administrativa, alteração de valores bloqueada e conclusão com histórico.
- Configuração e histórico do Django Admin respeitam as unidades acessíveis à conta.

O catálogo atualizado está em `docs/regras-negocio.md`.
