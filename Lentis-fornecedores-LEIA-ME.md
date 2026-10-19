# Lentis ERP — Cadastro de fornecedores

## Instalação

Na branch `feat/fornecedores`, extraia o ZIP em `C:\Projetos\lentis-erp`, preservando as pastas backend, frontend e docs e substituindo os arquivos correspondentes. Todos estão em UTF-8.

A base é a main cdf53e0 (histórico do cliente), com models.py/admin.py enviados em 19/10/2026. Não há novas dependências.

```powershell
cd C:\Projetos\lentis-erp
python backend\manage.py makemigrations organizations
python backend\manage.py migrate
python backend\manage.py check
python backend\manage.py test organizations.test_suppliers --verbosity 2
cd frontend
npm run build
```

A migração é gerada no seu ambiente, normalmente com prefixo 0008 no app organizations. Inclua esse novo arquivo no commit depois de validar. Não altere migrações anteriores.

Para regressão completa:

```powershell
cd C:\Projetos\lentis-erp
python backend\manage.py test organizations sales --verbosity 2
```

Reinicie o backend depois da migração. Na raiz: `python backend\manage.py runserver 127.0.0.1:8000`. Em outro terminal, dentro de frontend: `npm run dev`.

## Permissões e acesso

Cadastros → Fornecedores.

No admin de usuários/grupos, conceda Visualizar fornecedor (organizations.view_supplier). Para cadastrar, Adicionar fornecedor; para editar, inativar e reativar, Alterar fornecedor. É obrigatório possuir vínculo ativo com a unidade. Superusuário ativo possui as permissões. Ser staff não substitui essas permissões.

A seção Fornecedores do admin é somente consulta e respeita as unidades autorizadas. O cadastro/edição deve ser feito na tela do sistema, garantindo versão e histórico.

## Uso

Novo fornecedor → selecione pessoa jurídica ou física → informe nome/razão social e os demais dados → Cadastrar fornecedor.

CPF/CNPJ é opcional. Se preenchido, precisa ser válido para o tipo de pessoa. CNPJ aceita formato numérico e alfanumérico, com ou sem pontuação e letras minúsculas; é salvo sem pontuação e em maiúsculas. A conferência é local (estrutura e dígitos verificadores), sem consulta automática à Receita.

Um documento não pode repetir na unidade, mesmo quando o cadastro anterior está inativo. Use o filtro Inativos e reative o registro existente. Em unidades diferentes os cadastros são independentes.

Selecione o fornecedor na lista para consultar ou editar. Os campos disponíveis incluem nome fantasia, inscrição estadual/RG, pessoa de contato, telefone, WhatsApp, e-mail, CEP, logradouro, número, complemento, bairro, cidade, UF e observações.

Inativar ou reativar exige motivo. Salve alterações de campos antes de mudar a situação. O histórico registra operação, versão, usuário, data e motivo. A edição não armazena uma fotografia completa dos campos anteriores.

Se duas telas editarem o mesmo fornecedor, a tela antiga recebe um aviso para reabrir. Use Reabrir dados atuais e confirme descartar as mudanças locais antes de continuar.

Em falha de rede, os campos ficam bloqueados com um envio pendente. Use Conferir / repetir envio; o mesmo UUID recupera o resultado sem duplicar. O navegador mantém o envio no sessionStorage quando disponível e na memória enquanto a tela estiver aberta.

## Teste manual

1. Cadastre fornecedor PJ com contato e endereço. Verifique validação de e-mail, CEP e UF.
2. Teste CPF/CNPJ com dígito errado: deve retornar mensagem, sem erro 500.
3. Teste PF com CPF válido e PJ com CNPJ numérico válido.
4. Teste o exemplo fictício do manual RFB, 12.ABC.345/01DE-35; deve ser armazenado como 12ABC34501DE35. Não utilizar dados reais de terceiros em testes.
5. Tente duplicar o documento na mesma unidade: deve recusar. Inative e tente novamente: deve orientar a consultar os inativos.
6. Edite um contato, inative com motivo e reative com motivo. O ID deve permanecer o mesmo e o histórico deve registrar as operações.
7. Abra o mesmo cadastro em duas abas e teste conflito de versão.
8. Usuário apenas com Visualizar pode consultar, mas não cadastrar ou editar. Usuário sem vínculo com a unidade não acessa dados.
9. Confira pesquisa, paginação, filtro de situação, tema claro/escuro e tela pequena.

## API

- GET `/api/me/suppliers/?store_id=<id>&status=active|inactive|all&search=<texto>&page=1`.
- GET `/api/me/suppliers/<id>/?store_id=<id>` inclui histórico de operações.
- POST na coleção cria; POST no detalhe executa update, archive ou restore.
- Corpo: request_id (UUID), action, campos do fornecedor; alterações exigem expected_version; archive/restore exigem reason.
- Não há DELETE ou transferência para outra unidade.

## Referência técnica do CNPJ

Manual da Receita Federal: https://www.gov.br/receitafederal/pt-br/centrais-de-conteudo/publicacoes/documentos-tecnicos/cnpj/manual-dv-cnpj.pdf

O suporte ao CNPJ alfanumérico desta entrega é aplicado ao novo cadastro de fornecedores. A adaptação de validadores de outros módulos deve ser tratada em etapa própria.

## Arquivos do pacote

Backend: organizations/models.py, admin.py, urls.py, supplier_models.py, supplier_api.py e test_suppliers.py.
Frontend: src/api.ts, components/AppLayout.tsx, Suppliers.tsx e Suppliers.css.
Documentação: docs/regras-negocio.md e este guia.

O cadastro ainda não lança compras, contas a pagar ou estoque. Esses fluxos serão integrados nas próximas etapas.
