# Lentis ERP — Receitas oftalmológicas

Pacote baseado nos quatro arquivos enviados em 19/10/2026: models(4).py, urls(6).py, api(4).ts e AppLayout(4).tsx. Preserva as funções existentes e acrescenta receitas por cliente em Cadastros → Receitas. Arquivos completos em UTF-8.

## Instalação

Pare os servidores com Ctrl+C. A branch prevista é feat/receitas-oftalmologicas; se você já a criou, não crie de novo:

```powershell
cd C:\Projetos\lentis-erp
git branch --show-current
git status --short
```

Se ainda estiver na main:

```powershell
git switch -c feat/receitas-oftalmologicas
```

Extraia o ZIP em C:\Projetos\lentis-erp, mantendo as pastas backend e frontend e substituindo os arquivos correspondentes. Não cole trechos. Não coloque backups .tsx dentro de frontend/src.

Com .venv ativa e PostgreSQL em execução:

```powershell
cd C:\Projetos\lentis-erp
python backend\manage.py makemigrations organizations
python backend\manage.py migrate
python backend\manage.py check
python backend\manage.py test organizations sales --verbosity 2
cd frontend
npm run build
```

É esperado criar Prescription, PrescriptionRevision e PrescriptionOperation com suas restrições. A numeração da migração acompanha o histórico do seu projeto. Não modifica os clientes nem precisa preencher campos novos em registros antigos. Nenhuma dependência adicional é necessária.

Em um terminal, com .venv ativa:

```powershell
cd C:\Projetos\lentis-erp
python backend\manage.py runserver 127.0.0.1:8000
```

Em outro terminal:

```powershell
cd C:\Projetos\lentis-erp\frontend
npm run dev
```

## Acesso e permissões

Teste inicialmente com seu superusuário ativo. Abra http://127.0.0.1:5173/ e Cadastros → Receitas.

Para um usuário comum, entre no admin → Usuários → selecione o usuário → Permissões do usuário (ou atribua por Grupo):

- Consultar: organizations.view_prescription — visualizar receita oftalmológica.
- Cadastrar: também organizations.add_prescription — adicionar receita oftalmológica.
- Corrigir/arquivar: também organizations.change_prescription — alterar receita oftalmológica.

Essas permissões são criadas pelo Django após migrate. Na lista do admin, pesquise por receita oftalmológica / prescription. O usuário também precisa ter vínculo ativo com a unidade. Marcar Membro da equipe não concede acesso a receitas. Não é necessário conceder exclusão.

## Fluxo de teste

1. Clique em Nova receita, selecione o cliente e a data do documento.
2. Transcreva os dados disponíveis em OD e OE. Aceita vírgula ou ponto decimal e sinais +/-. Não complete campos desconhecidos com zero: deixe em branco.
3. Informe prescritor, registro, DP/DNP e observações se disponíveis. Não há cálculo automático nem consulta de registro profissional.
4. Salve, abra a receita novamente e confira que campos vazios continuam vazios e zero permanece 0,00.
5. Clique em Corrigir receita, ajuste uma transcrição e informe o motivo. Depois de salvar, expanda as versões no histórico: a anterior deve manter os valores originais.
6. Para outra receita clínica do mesmo cliente, use Nova receita, preservando os registros anteriores.
7. Arquive uma receita de teste com motivo. Selecione Arquivadas no filtro para consultá-la novamente. Não é possível editá-la depois do arquivamento.
8. Confira com outro usuário sem permissão e com outra unidade: o backend deve impedir o acesso aos registros não autorizados.

Se duas pessoas editarem a mesma versão, a segunda recebe uma mensagem de atualização. Use Reabrir dados atuais, confira e aplique a correção novamente. Em resposta de rede incerta, use Repetir envio com segurança para recuperar a mesma operação.

O botão Nova receita exige permissão de cadastro. A tela mostra erro de permissão quando o usuário não pode consultar; nesse caso, ajuste o grupo/permissões no admin.

## Escopo

Cadastro e consulta dos dados transcritos, correções com histórico e arquivamento. Não é emissão de receita, cálculo de graus ou integração com vendas/OS. Anexos e impressão da receita ficam para etapas posteriores. Não altera estoque ou financeiro.

## Validação

16 testes novos de API passaram no SQLite isolado. O pacote também inclui um teste de edição concorrente para PostgreSQL, ignorado no SQLite. Regressão completa: 266 testes, sem falhas; 256 passaram e 10 foram ignorados por dependerem de bloqueios de banco não disponíveis no SQLite. Build TypeScript/Vite aprovado. Os testes acima devem ser executados no seu ambiente PostgreSQL.

Fluxo real React + Django validado no navegador: criação, valores negativos com vírgula, vazio diferente de zero, correção preservando versões, repetição de resposta perdida sem duplicação, arquivamento/filtros e tema escuro em largura de celular sem rolagem horizontal.

## Arquivos completos incluídos

- backend/organizations/models.py
- backend/organizations/urls.py
- backend/organizations/prescription_models.py
- backend/organizations/prescription_api.py
- backend/organizations/test_prescriptions.py
- frontend/src/api.ts
- frontend/src/components/AppLayout.tsx
- frontend/src/components/Prescriptions.tsx
- frontend/src/components/Prescriptions.css
- docs/regras-negocio.md
- Este guia

A migração será gerada localmente e deve entrar no commit. A logo original, Product-model.txt, o regras-negocio.md duplicado da raiz e alterações no guia antigo não fazem parte desta etapa.
