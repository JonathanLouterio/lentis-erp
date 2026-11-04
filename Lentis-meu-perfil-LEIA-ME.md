# Lentis — Meu perfil e foto pessoal

Pacote para `feat/meu-perfil`, preparado sobre a main `840c12e`.
Arquivos UTF-8. Extraia todo o conteúdo diretamente em `C:\Projetos\lentis-erp`,
substituindo os arquivos correspondentes e preservando as pastas do ZIP.

## O que está pronto

Clique no seu nome/foto no canto inferior esquerdo e escolha **Meu perfil**.
No celular, abra primeiro o menu principal. O menu da conta também oferece
**Preferências** e **Sair da conta**.

- Página de perfil com nome, sobrenome, e-mail de contato, telefone/WhatsApp,
  cargo/apresentação e Sobre mim.
- **Editar perfil** abre uma janela com confirmação de alterações não salvas.
- **Escolher foto**, prévia, remoção e desfazer a alteração antes de salvar.
- Nome e foto atualizam no menu ao salvar e continuam após atualizar a página.
- Preferências usa o tema Claro/Escuro/Automático já existente.
- Qualquer usuário ativo pode editar o próprio perfil, inclusive sem unidade.
  Permissões, vínculos, usuário de login, ativação e senha mantêm seus fluxos atuais.
- Cargo é uma descrição pessoal. O perfil de autorização mostrado no menu continua
  vindo do vínculo real com a unidade selecionada.

## Foto e persistência

Uma foto estática JPG/PNG/WebP por envio, até 5 MB e 16 megapixels.
A foto recebe orientação correta, recorte central e redução para JPEG de 256x256;
transparência vira fundo branco e metadados são removidos. Escolha uma imagem
com o rosto próximo ao centro. Imagens animadas, SVG/GIF, arquivos corrompidos
ou acima dos limites são rejeitados sem substituir o avatar anterior.

O avatar reduzido (máximo 96 KiB) fica no banco existente e acompanha seu backup.
A foto permanece após deploy/reinício do Render. Basta instalar a dependência
nova e aplicar a migração; não há configuração adicional de armazenamento para
este avatar. A galeria de três fotos por produto será uma entrega separada.

A imagem tem acesso privado na sessão do próprio usuário. O sistema não publica
um endereço aberto da foto nem mostra fotos pessoais para outros usuários nesta etapa.

## Instalação local

Use a .venv já existente; os comandos abaixo chamam diretamente o Python dela.
Confira se o .env aponta para o banco que pretende atualizar e tenha backup
antes da migração. As configurações atuais de Render/Neon atendem a entrega.

```powershell
Set-Location C:\Projetos\lentis-erp

& .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
& .\.venv\Scripts\python.exe backend\manage.py migrate
& .\.venv\Scripts\python.exe backend\manage.py check
& .\.venv\Scripts\python.exe backend\manage.py makemigrations --check --dry-run
& .\.venv\Scripts\python.exe backend\manage.py test accounts.test_profile --verbosity 2

Set-Location C:\Projetos\lentis-erp\frontend
npm run build
```

A nova dependência é Pillow 13.0.0, usada para validar e reduzir a imagem.
A migração `accounts.0005_userprofile` acompanha o pacote. Ela cria uma tabela
adicional e preserva contas, credenciais, temas, vínculos e permissões existentes.
Não precisa gerar outra migração. Reinicie o backend depois de instalar/atualizar.

Para abrir o sistema local, deixe dois terminais:

```powershell
# Terminal 1 — raiz do projeto, .venv ativa
Set-Location C:\Projetos\lentis-erp
& .\.venv\Scripts\python.exe backend\manage.py runserver 127.0.0.1:8000
```

```powershell
# Terminal 2 — frontend
Set-Location C:\Projetos\lentis-erp\frontend
npm run dev
```

Antes da integração, o CI deve passar em PostgreSQL. Para executar a regressão
completa localmente:

```powershell
Set-Location C:\Projetos\lentis-erp
& .\.venv\Scripts\python.exe backend\manage.py test accounts organizations sales purchases deployment_tests --verbosity 2
```

## Validação manual

1. Usuário comum abre Meu perfil e altera nome, contato e apresentação.
2. Escolha uma foto e salve; confira a imagem na página e no menu.
3. Atualize a página, saia/entre e confira os dados novamente.
4. Remova a foto, salve e confira as iniciais no lugar da imagem.
5. Altere um campo e feche a janela: confirme continuar editando ou descartar.
6. Teste Preferências nos temas Claro/Escuro/Automático.
7. Confira em celular/tablet: menu do usuário, janela e rolagem dos campos.
8. Outro usuário vê somente o próprio perfil e não baixa o avatar alheio.
9. Duas sessões editando o perfil: a segunda recebe conflito; feche, Atualizar e reabra.

Envio inválido preserva os dados anteriores. Em conflito ou acesso revogado,
feche a janela e atualize. Em falha de rede após salvar, atualize a página para
conferir o resultado antes de reenviar. O cadastro não é duplicado.

## Arquivos e versionamento

O pacote contém somente os arquivos desta entrega. As alterações locais já
existentes em .dockerignore, .gitattributes, homologação, settings_production,
deploy, index.html e MobileWorkspace.css permanecem fora desta entrega.
O ZIP não contém .env, credenciais, banco, node_modules ou fotos pessoais.

Depois dos testes e da conferência visual:

```powershell
Set-Location C:\Projetos\lentis-erp

git add backend/accounts/models.py backend/accounts/urls.py backend/requirements.txt
git add backend/accounts/profile_models.py backend/accounts/profile_api.py backend/accounts/profile_images.py backend/accounts/profile_uploads.py backend/accounts/test_profile.py
git add backend/accounts/migrations/0005_userprofile.py
git add frontend/src/App.tsx frontend/src/api.ts frontend/src/components/AppLayout.tsx
git add frontend/src/components/MyProfile.tsx frontend/src/components/MyProfile.css frontend/src/components/ProfileMenu.tsx frontend/src/components/ThemeSelect.tsx
git add docs/regras-negocio.md docs/plano-configuracoes-perfil-produtos.md Lentis-meu-perfil-LEIA-ME.md

git diff --cached --check
git --no-pager diff --cached --stat
```

Revise o resumo antes de fazer commit e push na branch. Após o CI verde, siga
seu fluxo de integração na main e confira o deploy da homologação. O Render
instala a dependência e aplica a migração pelo processo já configurado.

## Escopo posterior

Troca de senha, galeria/fotos de produtos e logotipo da ótica continuam para
entregas próprias. O e-mail deste formulário é de contato; ele não é verificado
nem dispara mensagens. Preferências de tema são a funcionalidade já existente.

## Validação desta entrega

- Backend completo: 713 testes encontrados; 690 passaram neste ambiente e 23
  exigem PostgreSQL e foram omitidos. Foi usado SQLite temporário e hash de senha
  rápido somente para testes; esses settings não acompanham o pacote.
- Dos 30 testes novos de perfil, 29 passaram e o de concorrência permanece para
  o PostgreSQL local/CI. Ele deve concluir com um salvamento e um conflito 409.
- TypeScript/Vite build, check e detecção de migrações pendentes conferidos.
- Navegador: usuário comum sem unidade, atualização de dados, envio/remoção da
  foto, persistência após reiniciar o backend, preferências e temas, acesso pelo
  menu móvel, janela em 390 px e confirmação de descarte. Sem erro JavaScript
  ou transbordamento horizontal nas telas conferidas.
- UTF-8 e `git diff --check` conferidos. Banco, dependências locais, fotos de
  teste e credenciais não acompanham o ZIP.
