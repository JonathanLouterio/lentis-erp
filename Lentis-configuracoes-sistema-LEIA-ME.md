# Lentis — Configurações do sistema

Pacote para a branch `feat/configuracoes-sistema`, preparado sobre o commit
`4192aac` da main (Render gratuito + Neon). Arquivos UTF-8. Extraia o conteúdo
na raiz `C:\Projetos\lentis-erp`, mantendo as pastas backend/, frontend/ e docs/.
Não contém .env, credenciais, banco, node_modules ou arquivos pessoais não rastreados.

## Onde acessar

Entre com um administrador global ativo, abra **Usuários e acessos** e escolha
**Configurações do sistema**. A outra aba mantém **Usuários e permissões**.
A área pode ser aberta mesmo sem unidade ativa ou cadastrada.

1. Selecione uma ótica existente ou use **Nova ótica**.
2. Preencha identificação, contato e endereço. Na aba Redes sociais, use os links
   completos com https:// e WhatsApp com DDI/DDD, por exemplo +55 41 99999-9999.
3. Salve, selecione a ótica e use **Nova unidade**. O código deve ser único em todo
   o sistema. A unidade fica permanentemente vinculada à empresa escolhida.
4. Em **Usuários e permissões**, vincule os usuários às unidades e conceda as
   permissões operacionais necessárias. Ter apenas perfil Gerente não libera
   configurações globais. O administrador global vê todas as óticas por definição.
5. O histórico mostra as alterações feitas por esta área. Use **Atualizar** para
   recarregar cadastros alterados em outra sessão. Conflitos de versão não salvam
   por cima da edição de outro administrador: feche, atualize e reabra o cadastro.

Óticas e unidades usam inativação, preservando dados. A confirmação explica o
bloqueio operacional. Reativação mantém os vínculos anteriores que continuarem
ativos. A inativação da empresa não altera individualmente os vínculos nem as unidades.

Empresas e unidades ficam somente leitura no Django Admin. Faça as alterações
pela nova área para registrar autoria e versões. A alteração de estoque negativo
usa a regra já existente; não recalcula saldos anteriores.

## Instalar e validar no ambiente de desenvolvimento

Mantenha um backup antes da migração, usando os scripts de backup já existentes.
Confira se seu .env aponta para o banco de desenvolvimento que deseja atualizar.
O pacote não modifica variáveis de ambiente nem executa deploy automaticamente.

Na raiz do projeto, com a .venv ativa:

```powershell
cd C:\Projetos\lentis-erp
python backend\manage.py migrate
python backend\manage.py check
python backend\manage.py makemigrations --check --dry-run
python backend\manage.py test organizations.test_configuration accounts --verbosity 2
```

Não é necessário gerar uma nova migração: `organizations.0011` já acompanha o pacote.
Ela preserva IDs, lojas, vínculos e operações anteriores. Depois de criar várias
empresas, não reverta para a antiga restrição de empresa única; uma reversão exige
planejamento dos dados e restauração de backup, se necessário.

Build do frontend:

```powershell
cd C:\Projetos\lentis-erp\frontend
npm run build
```

Para abrir localmente, deixe dois terminais em execução:

```powershell
# Terminal 1 — raiz do projeto, .venv ativa
python backend\manage.py runserver 127.0.0.1:8000
```

```powershell
# Terminal 2 — frontend
cd C:\Projetos\lentis-erp\frontend
npm run dev
```

Antes de integrar e atualizar a homologação, execute a regressão completa no
PostgreSQL local (ou aguarde o CI verde na branch):

```powershell
cd C:\Projetos\lentis-erp
python backend\manage.py test accounts organizations sales purchases deployment_tests --verbosity 2
```

## Conferência manual

- O administrador acessa as duas abas, inclusive com zero unidades ativas.
- A ótica/unidade existente continua aparecendo e os dados anteriores permanecem.
- Nova ótica, unidade, edição e redes sociais salvam e aparecem no histórico.
- Nova unidade aparece no seletor e nas opções de vínculo de usuários com a empresa identificada.
- Usuário comum, mesmo staff/gerente, não abre a área nem seus endpoints.
- Usuário vinculado somente à Ótica A não consulta ou exporta dados da Ótica B.
- Inativação avisa antes de salvar; a próxima requisição da sessão operacional é bloqueada.
- Dois administradores editando o mesmo cadastro: o segundo recebe conflito de versão.
- Teste em celular/tablet e nos temas claro/escuro. Escape/Fechar pede confirmação quando há alterações.

## O que permanece para depois

Meu perfil/avatar e até três fotos por produto serão entregas separadas. Este pacote
não configura armazenamento de arquivos. Redes sociais são links da empresa, sem
publicação automática. Esta tela expõe a política existente de estoque negativo;
não altera a entrada mínima de 40%, a taxa de acréscimo ou as regras de desconto.
O histórico começa com a implantação e não inventa eventos para cadastros antigos.

## Versionamento

Após seus testes, revise o diff e adicione somente os arquivos desta entrega:

```powershell
cd C:\Projetos\lentis-erp
git add backend/accounts/selectors.py backend/accounts/serializers.py backend/accounts/tests.py backend/accounts/user_management_api.py
git add backend/organizations/admin.py backend/organizations/models.py backend/organizations/urls.py
git add backend/organizations/configuration_api.py backend/organizations/configuration_models.py backend/organizations/test_configuration.py
git add backend/organizations/migrations/0011_configurationevent_alter_company_options_and_more.py
git add frontend/src/api.ts frontend/src/components/AppLayout.tsx frontend/src/components/UserManagement.tsx
git add frontend/src/components/AdminWorkspace.tsx frontend/src/components/SystemSettings.tsx frontend/src/components/SystemSettings.css
git add docs/regras-negocio.md docs/plano-configuracoes-perfil-produtos.md Lentis-configuracoes-sistema-LEIA-ME.md
git diff --cached --check
git --no-pager diff --cached --stat
```

Os arquivos de logo, Product-model.txt e demais anotações pessoais já não rastreadas
não precisam ser adicionados. Commit/push e integração na main seguem seu fluxo habitual.

## Validação do pacote em 03/11/2026

- `check` sem problemas e `makemigrations --check --dry-run` sem alterações pendentes.
- Suíte completa: 683 testes encontrados, 661 executados com sucesso e 22 omitidos
  por exigirem recursos/bloqueios do PostgreSQL. Aqui foi usado SQLite temporário
  com hash de senha rápido apenas para testes; isso não altera os settings entregues.
- Dos 35 novos testes, 32 passaram neste ambiente e os 3 de concorrência exigem PostgreSQL.
  A validação em PostgreSQL no ambiente local/CI permanece necessária antes da homologação.
- Build TypeScript/Vite concluído. Área administrativa carregada sob demanda.
- Navegador: login real, navegação, criação de empresa/unidade, edição, confirmação
  de alterações pendentes, temas claro/escuro e larguras desktop/tablet/celular.
  Janela móvel conferida com 390 px, sem transbordamento horizontal.
- Conferência de UTF-8 e `git diff --check` concluídas.
