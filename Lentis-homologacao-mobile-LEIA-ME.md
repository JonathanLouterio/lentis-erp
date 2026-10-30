# Lentis — preparação para nuvem, celular e tablet

Base: `main` em `56859e8ae8e67d58e5457a9627f976352292416f`.

## Entrega desta etapa

- Configuração Django de produção separada (`config.settings_production`).
- Imagem Docker com Python 3.14, build Node 24 e Gunicorn.
- Frontend e API no mesmo endereço, preservando a autenticação por sessão.
- HTTPS, cookies seguros, hosts explícitos e verificação de saúde do banco.
- Proposta de Blueprint Render com banco de homologação separado.
- Menu sobreposto em telas de até 900 px, sem ocupar uma faixa permanente.
- Formulários em tela inteira até 600 px, mantendo cabeçalho, rolagem e ações.
- Controles maiores para toque e suporte às áreas de segurança da tela.
- CI com construção da imagem e teste integrado com PostgreSQL descartável.

Este pacote prepara a publicação. Nenhum serviço foi criado ou contratado.
O desenvolvimento local continua com `config.settings` e Vite, como antes.
Não há PWA, service worker ou operação offline nesta etapa.

## Aplicação no VS Code

```powershell
cd C:\Projetos\lentis-erp
git switch main
git pull --ff-only origin main
git switch -c feat/homologacao-mobile
```

Extraia o ZIP na raiz `C:\Projetos\lentis-erp`, preservando as pastas.
Instale as dependências e execute as verificações:

```powershell
python -m pip install -r backend\requirements-production.txt
python backend\manage.py check
python backend\manage.py test deployment_tests --verbosity 2
cd frontend
npm run build
cd ..
```

Gunicorn é instalado apenas no Linux; no Windows você continua usando `runserver`.
Não é necessário criar ou aplicar novas migrações nesta etapa.

## Conferência da interface

Use os comandos habituais para iniciar o sistema:

```powershell
python backend\manage.py runserver 127.0.0.1:8000
```

Em outro terminal:

```powershell
cd C:\Projetos\lentis-erp\frontend
npm run dev
```

No navegador, use a simulação de dispositivos das ferramentas de desenvolvedor:

1. Celular: o botão de menu abre uma janela lateral. Escape e Fechar menu retornam à página.
2. Ao escolher um módulo, o menu fecha. Os controles respeitam as permissões existentes.
3. Novo cliente: a janela ocupa a tela no celular; o corpo rola e o botão Salvar permanece no rodapé.
4. Tablet: a janela mantém o formato de diálogo e o menu fica sobreposto até 900 px.
5. Computador: a barra lateral continua expansível/recolhível.

O endereço `127.0.0.1` do computador não abre o projeto no celular físico.
A validação em aparelhos reais será feita usando o endereço HTTPS da homologação.
Listas extensas ainda podem usar rolagem horizontal dentro da própria tabela.
Esta é a base responsiva; a revisão detalhada de todos os módulos continuará por etapas.

## Versionamento

Confira o diff, incluindo a mudança do workflow existente:

```powershell
git add .dockerignore .gitattributes Dockerfile render.yaml
git add .github/workflows/ci.yml deploy/
git add backend/config/settings_production.py backend/config/urls_production.py backend/config/deployment_views.py
git add backend/requirements-production.txt backend/deployment_tests/
git add frontend/index.html frontend/src/components/AppLayout.tsx frontend/src/components/MobileWorkspace.css
git add Lentis-homologacao-mobile-LEIA-ME.md docs/plano-configuracoes-perfil-produtos.md
git diff --cached --check
git --no-pager diff --cached --stat
git commit -m "feat: prepara homologacao na nuvem e base responsiva mobile"
git push -u origin feat/homologacao-mobile
```

Aguarde os três jobs ficarem verdes: Backend, Frontend e Homologação — imagem Docker.
O terceiro job valida a imagem, migrações, arquivos estáticos, saúde do banco,
bloqueio de acesso anônimo e proteção CSRF. Ele não publica no Render.

## Infraestrutura proposta — revisar antes de contratar

| Recurso | Proposta |
| --- | --- |
| Aplicação | `lentis-homolog`, Docker, 0.5 CPU / 512 MB |
| Banco | `lentis-homolog-db`, PostgreSQL 17, 0.1 CPU / 256 MB, 1 GB de disco |
| Região | Virginia, igual para aplicação e banco |
| Dados | Banco novo, somente dados fictícios inicialmente |
| Deploy automático | Desativado inicialmente; publicação manual pelo Render |
| Conexão do banco | Rede privada; conexões externas bloqueadas |

Os planos do Blueprint são pagos. Referência consultada em 30/10/2026:
US$ 7/mês para aplicação e US$ 6/mês para computação do banco, além de eventual
armazenamento, uso excedente, impostos e câmbio. Confira o total mostrado no
Dashboard antes de aplicar; a estimativa não é uma cotação fechada.
Fonte: https://render.com/pricing

Os nomes representam recursos novos. Antes da criação, confira se não coincidem
com recursos existentes. O pacote não usa o banco nem os serviços do FieldOps.

## Quando formos publicar

Primeiro integre a branch à `main` após o CI passar. O Render só consegue ler
arquivos já enviados ao repositório.

O Blueprint passou pela validação do schema oficial. A validação com o CLI do
Render não foi executada neste ambiente, pois o CLI não está instalado.
Com o CLI instalado e autenticado no workspace correto, execute:

```powershell
render blueprints validate render.yaml
```

Instruções oficiais de instalação: https://render.com/docs/cli
Essa validação não cria recursos. Depois de revisar o custo e o workspace, use
**New > Blueprint**, selecione `JonathanLouterio/lentis-erp`, branch `main`, e revise
a proposta antes de clicar em **Apply**. Apply inicia a criação e a cobrança.

O serviço gera sua chave secreta e recebe as credenciais do banco por referências
do Blueprint. Não copie o `.env` local, não coloque senhas no Git e não altere os
scripts de backup locais para apontarem ao banco da nuvem.

No primeiro deploy:

1. O Docker compila o frontend com base `/static/app/` e coleta os arquivos estáticos.
2. O comando de pré-deploy aplica as migrações no banco novo.
3. Gunicorn inicia a aplicação e `/healthz/` confirma a conexão com o banco.
4. No Shell do serviço Render, execute `python /app/backend/manage.py createsuperuser`.
5. Cadastre empresa, lojas e contas de teste pelo admin. Só então valide o login no celular/tablet.

A página de login será acessível pela internet. As APIs continuam exigindo os
logins e as permissões do Lentis. `robots.txt` e `X-Robots-Tag` desestimulam indexação;
não equivalem a restringir o site à rede privada.

O hostname gerado é lido de `RENDER_EXTERNAL_HOSTNAME`. Se adicionarmos um domínio
próprio, configure `DJANGO_ALLOWED_HOSTS` com o hostname exato, sem `https://` ou `*`.
O cabeçalho `X-Forwarded-Proto` é confiado no contexto do proxy HTTPS do Render.
O container não deve ficar diretamente exposto à internet sem esse proxy.

## Limites e continuidade

- `check --deploy` pode apresentar W005 e W021: HSTS para todos os subdomínios e
  preload ficaram desativados intencionalmente nesta homologação. HTTPS e cookies
  seguros estão ativos; esses avisos não foram ocultados.
- O disco do container é efêmero. Não usar para anexos ou backups persistentes.
  Armazenamento de arquivos e a rotina de backup da nuvem serão configurados antes
  de liberar dados reais. Os backups locais existentes continuam separados.
- A homologação ainda não é liberação para produção. Antes do uso real, revisar
  proteção contra tentativas repetidas de login, logs/monitoramento, recuperação
  do banco e comportamento nos aparelhos efetivamente usados.
- PWA instalável é uma próxima etapa. Operação offline exige regras próprias para
  sincronização, estoque e pagamentos; não é ativada apenas por instalar um ícone.

## Verificações realizadas

- Nove testes de configuração, hosts, chave, resposta HTML, saúde e indexação.
- Build com as dependências do lockfile, Vite 8.3.3 e TypeScript.
- Teste local do build servido pelo Django/WhiteNoise via HTTPS, com dados fictícios:
  login, sessão persistente, cookies seguros, CSRF e cadastro de cliente.
- Navegação e janelas em Chromium: 360/390 px, tablets 768/820 px, paisagem 1180 px
  e desktop 1440 px; temas e foco do teclado.
- Schema oficial do Render, schema do GitHub Actions e sintaxe Bash.

O teste local de interface usa SQLite isolado. Não substitui o CI com PostgreSQL.
A imagem Docker completa será construída no novo job: este ambiente de preparação
não possui Docker. Não houve deploy real nem teste em um iPhone/iPad físico.

## Escopo empresarial e novas solicitações

As decisões sobre várias óticas independentes, configurações administrativas,
Meu perfil, redes sociais e três fotos por produto estão registradas em
`docs/plano-configuracoes-perfil-produtos.md`. São as próximas etapas; este pacote
não remove a restrição atual de empresa única nem implementa uploads.
