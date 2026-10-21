# Lentis — Gestão de usuários e acessos

Base: arquivos enviados do commit `a52c6e2`. Branch: `feat/gestao-usuarios`.

## Recursos

Menu **Gestão → Usuários e acessos**, disponível para superusuários ativos:

- Lista de contas com busca, paginação e situação ativa/inativa.
- Cadastro com senha inicial, edição dos dados básicos e ativação/desativação de contas comuns.
- Vínculos com várias lojas e função Gerente, Vendedor, Caixa ou Financeiro.
- Concessão de permissões Django diretas dos módulos operacionais existentes.
- Consulta das concessões herdadas de grupos, preservadas mesmo se a permissão direta for retirada.
- Redefinição de senha, invalidando sessões anteriores.
- Histórico das alterações feitas por esta funcionalidade, com responsável, data e dados anteriores/novos na API. A tela resume os campos alterados.
- Proteção contra sobrescrever edições mais recentes de outra aba ou do Django Admin.
- Menu lateral recolhido ao iniciar no celular e após trocar de página.

## Limite importante das permissões existentes

Esta entrega administra permissões do projeto; **não modifica os validadores de cada módulo**.

Desmarcar uma permissão não deve ser considerado bloqueio universal do módulo. Clientes, produtos e parte das vendas/estoque antigos ainda usam vínculos, perfil e regras próprias sem consultar todos os códigos de permissão Django. A padronização desses bloqueios por ação é a próxima etapa.

Receitas, fornecedores, compras, contas a pagar, ordens de serviço, consultas clínicas e relatórios possuem verificações específicas nas implementações existentes. As opções desta tela complementam essas verificações e não substituem bloqueios de estado, imutabilidade ou regras comerciais.

As permissões são globais para o usuário e se aplicam nas unidades às quais ele tem acesso. Esta etapa não cria uma matriz de permissões diferentes por loja. Funções por loja continuam participando das regras comerciais existentes e não preenchem permissões automaticamente.

Para retirar todo acesso a uma unidade, desative o vínculo. Para bloquear a conta inteira, desative a conta. Uma permissão herdada de grupo continua efetiva mesmo com sua concessão direta desmarcada. Grupos continuam sendo geridos pelo Django Admin.

## Instalação

1. Confira a branch `feat/gestao-usuarios`.
2. Pare o Django com Ctrl+C.
3. Extraia o ZIP na raiz `C:\Projetos\lentis-erp`, preservando as pastas e substituindo os arquivos do pacote.
4. Com a `.venv` ativa:

```powershell
cd C:\Projetos\lentis-erp
python backend\manage.py migrate
python backend\manage.py makemigrations --check --dry-run
python backend\manage.py check
python backend\manage.py test accounts --verbosity 2
```

A migração `accounts.0004_useraccessevent` já está incluída. Ela cria somente o histórico, sem modificar contas, senhas, vínculos ou concessões anteriores. Não gere outra migração se a conferência acima disser que não há mudanças.

Compile o frontend:

```powershell
cd C:\Projetos\lentis-erp\frontend
npm run build
```

Reinicie o backend:

```powershell
cd C:\Projetos\lentis-erp
python backend\manage.py runserver 127.0.0.1:8000
```

Em outro terminal:

```powershell
cd C:\Projetos\lentis-erp\frontend
npm run dev
```

Abra `http://127.0.0.1:5173/`, entre com o superusuário e recarregue a página. O menu fica em Gestão → Usuários e acessos.

## Teste manual

1. Cadastre uma pessoa com uma senha de teste forte e marque uma unidade. O perfil inicial desse vínculo é Vendedor.
2. Selecione as permissões necessárias e salve. Reabra o cadastro e confira os valores.
3. Edite nome, função e permissões. Carregue o histórico e confira o responsável.
4. Abra a mesma conta em duas abas. Salve a primeira e tente salvar a segunda: deve aparecer conflito, sem sobrescrever. Reabra o usuário pela lista para atualizar a versão.
5. Entre com um usuário comum em outra sessão. Revogue seu vínculo e confira `/api/me/stores/`: a loja deve desaparecer na próxima consulta da sessão aberta.
6. Desative a conta e confira que a próxima requisição autenticada é negada. Reative se for uma conta necessária.
7. Redefina uma senha. A sessão antiga deve perder validade e a nova senha deve permitir nova autenticação, se a conta estiver ativa.
8. Entre como usuário comum, mesmo com flag staff: o menu de gestão não aparece e a API responde 403.
9. Abra a conta do superusuário: ela é somente consulta nesta tela, evitando retirada acidental do acesso administrativo.
10. Confira a tela clara/escura e com o menu recolhido no celular.

## Segurança, concorrência e histórico

- A gestão é global e exige superusuário ativo conferido no banco a cada chamada. Perfil Gerente e flag staff não bastam.
- Não há exclusão física na API, promoção a staff/superusuário, alteração de grupos nem atribuição de permissões técnicas de auth/accounts.
- Contas de superusuários, inclusive a própria, são protegidas contra edição e redefinição por esta API. A manutenção delas continua pelo Django Admin.
- O catálogo inclui somente modelos operacionais dos módulos de organizações, vendas e compras. Permissões técnicas ou fora do catálogo já existentes são preservadas.
- Vínculos omitidos em uma edição são inativados, não apagados. Não se concede novo vínculo ativo a loja/empresa inativa. Um vínculo antigo pode ser preservado ou revogado.
- Senhas usam hash e validadores configurados no Django, com mínimo adicional de 8 caracteres. Senhas e hashes não são expostos em respostas, histórico ou localStorage.
- Alterações exigem sessão e CSRF. Campos extras e tentativas de escalada de privilégios são rejeitados, inclusive em vínculos.
- Edição e redefinição exigem token de versão HMAC sobre o estado atual, concessões diretas/herdadas, vínculos e estado da credencial. O hash da credencial nunca é exposto pelo token.
- Operações desta API bloqueiam as contas administrativas numa ordem comum e, depois, o usuário alvo, dentro de uma transação PostgreSQL. Isso serializa alterações desta tela e evita criações concorrentes de logins que diferem só por capitalização.
- Cadastro, concessões, vínculos e histórico são gravados na mesma transação. Falhas desfazem a operação inteira.
- Conflitos retornam 409 sem sobrescrever o cadastro atual. O usuário deve reabrir o cadastro pela lista, conferir e reaplicar a edição desejada.
- Não há reenvio automático de gravações. Se uma criação perder a resposta, confira a lista pelo login antes de repetir.
- O histórico contém alterações desta funcionalidade; não retroage às edições do Django Admin. Não há endpoints para editar ou excluir eventos. A tela mostra os últimos 50 registros do usuário selecionado.
- Listagem paginada em 25 contas. Campos e opções têm limites de tamanho na API.
- `/api/me/`, o tema e o contrato de login/logout existentes são preservados.

## Validação

- A suíte de accounts inclui 54 testes: 52 executáveis em SQLite e 2 cenários de locks reservados ao PostgreSQL.
- Execute os testes no PostgreSQL do projeto para validar os dois cenários de concorrência reais.
- O pacote inclui somente código, documentação e migração. Não inclui bancos, credenciais reais nem arquivos de teste do harness.

## Arquivos

- `backend/accounts/models.py` e `urls.py` completos, baseados no ZIP enviado.
- `backend/accounts/user_management_models.py`.
- `backend/accounts/user_management_api.py`.
- `backend/accounts/test_user_management.py`.
- `backend/accounts/migrations/0004_useraccessevent.py`.
- `frontend/src/api.ts` e `frontend/src/components/AppLayout.tsx` completos.
- `frontend/src/components/UserManagement.tsx` e `UserManagement.css`.
- `docs/regras-negocio.md`, preservando as regras de backup anteriores.
- Este guia.
