# Lentis — visual da área de trabalho e janelas de cadastro

Pacote de 28/10/2026. Branch sugerida: `feat/visual-janelas`.

## O que foi implementado

- Menu lateral azul-escuro, perfil no rodapé, seleção roxa e área de trabalho com bordas arredondadas.
- Tema claro com fundo cinza, textos mais escuros, bordas visíveis e campos com fundo suave.
- Tema escuro integrado à preferência já existente do usuário.
- Clientes, produtos, fornecedores, receitas e usuários abrem em janelas sobre a listagem.
- Listagens e filtros permanecem montados enquanto o cadastro está aberto.
- Cabeçalho e rodapé fixos; conteúdo comprido rola dentro da janela; botão de salvar visível no rodapé.
- Depois de salvar o cadastro, a janela fecha e a lista é atualizada.
- Esc ou Fechar solicita confirmação quando há alterações. Clicar no fundo não fecha a janela.
- Tab e Shift+Tab ficam dentro da janela. O foco retorna ao acionador ao fechar, quando disponível.
- Fechamento bloqueado durante envio. Mensagens de validação e recuperação de envio aparecem dentro da janela.
- No celular os campos se organizam em uma coluna.
- Corrigido o envio de data de nascimento vazia: `null` quando o campo foi informado vazio; atualizações que omitem o campo continuam sem alterá-lo.

A inspiração foi a organização da referência enviada. Foram mantidas a marca Lentis e sua cor roxa, sem usar logos, imagens ou código do outro sistema.

## Aplicar

Use a etapa anterior salva em commit como ponto de partida. Confira seu estado antes de substituir os arquivos:

```powershell
cd C:\Projetos\lentis-erp
git branch --show-current
git status --short
git switch -c feat/visual-janelas
```

Extraia este ZIP em `C:\Projetos\lentis-erp`, preservando a pasta `frontend` e substituindo somente os arquivos correspondentes. Não crie outra pasta `frontend` dentro da existente.

O pacote contém sete arquivos de frontend e este documento. Não inclui `.env`, banco de dados, dependências, backups ou arquivos de teste local. Não substitui seu `App.tsx`, `main.tsx`, configuração do Vite ou arquivos de login. Não exige instalação de dependências nem migrações.

Base utilizada: fontes disponíveis do Lentis com as últimas permissões, entrada/acréscimo e relatório gerencial de contas a receber. Caso tenha feito alterações locais nesses mesmos arquivos depois dessas etapas, compare os diffs antes de aplicar.

## Conferir

```powershell
cd C:\Projetos\lentis-erp\frontend
npm run build
npm run dev
```

Mantenha o backend ligado em outro terminal:

```powershell
cd C:\Projetos\lentis-erp
python backend\manage.py runserver 127.0.0.1:8000
```

Abra `http://127.0.0.1:5173/`. Se a página já estava aberta, atualize-a depois de aplicar os arquivos.

### Verificação manual

1. Abra Clientes, digite um filtro e clique em Novo cliente. A janela deve aparecer sobre a lista.
2. Salve um cadastro de teste sem data de nascimento. A janela deve fechar e o filtro permanecer.
3. Abra Editar, altere um campo e pressione Esc. Confira Continuar editando e Descartar alterações.
4. Confira produtos e fornecedores: abrir, salvar e consultar novamente.
5. Confira receita: cadastrar com os valores necessários; corrigir uma receita com motivo; conferir histórico.
6. Confira usuários com uma conta administradora: cadastro, edição de vínculos e permissões; não conceda permissões de teste a contas reais.
7. Verifique os temas claro e escuro, além de uma janela estreita.
8. Confira um usuário de consulta: o cadastro deve respeitar suas permissões e não oferecer edição indevida.

## Validação realizada aqui

- TypeScript e build Vite concluídos.
- Navegador Chromium com backend real em ambiente isolado SQLite e dados fictícios: criação e edição nos cinco cadastros.
- Filtro preservado, foco, Tab/Shift+Tab, Esc, aviso de descarte, campos e fechamento bloqueados durante envio.
- Validação HTTP 400 simulada no formulário e falha HTTP 503 simulada seguida de recuperação de fornecedor.
- Consulta de fornecedor sem permissão de editar.
- Temas claro/escuro e formulário de cliente em largura de 390 px, sem rolagem horizontal da página.
- Nenhum erro JavaScript durante esse roteiro.

A suíte completa do backend não foi repetida: o pacote não altera código do servidor. A conferência local acima valida a integração na sua instalação.

## Versionar após conferir

```powershell
cd C:\Projetos\lentis-erp
git add frontend/src/api.ts frontend/src/components/AppLayout.tsx
git add frontend/src/components/FormDialog.tsx frontend/src/components/WorkspaceVisual.css
git add frontend/src/components/Suppliers.tsx frontend/src/components/Prescriptions.tsx frontend/src/components/UserManagement.tsx
git add Lentis-visual-janelas-LEIA-ME.md
git diff --cached --check
git --no-pager diff --cached --stat
git commit -m "feat: melhora visual e abre cadastros em janelas"
git push -u origin feat/visual-janelas
git status
```

Após validar o resultado e publicar a branch, integre na main pelo fluxo habitual. Arquivos pessoais ou de referência fora desta lista devem permanecer separados do commit.
