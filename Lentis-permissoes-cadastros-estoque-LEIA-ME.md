# Lentis — Permissões de clientes, produtos e estoque

Base: `d4dc953`, branch `feat/permissoes-cadastros-estoque`. Os arquivos de organizations e a tela de estoque vieram do ZIP enviado nesta etapa. A integração do layout/API parte da gestão de usuários já mesclada.

## Resultado

As APIs de clientes, produtos e movimentações manuais de estoque exigem permissões explícitas por ação, além de uma conta ativa e do acesso à unidade ativa. O frontend esconde ações não autorizadas. A API continua sendo a autoridade, inclusive em chamadas diretas.

**Após instalar, usuários comuns sem essas concessões perderão acesso a esses endpoints.** Entre como superusuário e libere os acessos necessários em Gestão → Usuários e acessos. Não há concessão automática, migração de perfis ou liberação por flag staff.

## Permissões

| Recurso | Operação | Permissão Django |
| --- | --- | --- |
| Clientes | Listar, consultar, HEAD/OPTIONS | `organizations.view_customer` |
| Clientes | Cadastrar | `organizations.add_customer` |
| Clientes | Editar com PUT/PATCH | `organizations.change_customer` |
| Clientes | Inativar com DELETE | `organizations.delete_customer` |
| Produtos | Listar, consultar, HEAD/OPTIONS | `organizations.view_product` |
| Produtos | Cadastrar | `organizations.add_product` |
| Produtos | Editar com PUT/PATCH | `organizations.change_product` |
| Produtos | Inativar com DELETE | `organizations.delete_product` |
| Estoque | Consultar saldos e histórico | `organizations.view_stockmovement` |
| Estoque | Registrar entrada, saída ou ajuste manual | `organizations.add_stockmovement` |

Recomendações práticas:

- Somente consulta: marque as permissões de consultar dos recursos necessários.
- Cadastro/edição pela lista: marque consultar e a ação de cadastrar/editar.
- Inativação pela lista: marque consultar e excluir/inativar.
- Estoque completo: marque consultar e cadastrar movimentação de estoque.
- Um usuário pode ter cadastro sem consulta. Nesse caso, o formulário de novo registro fica disponível, sem carregar a lista existente. Edição e exclusão por ID também são independentes na API, mas a seleção visual pela lista exige consulta.

Grupos existentes continuam concedendo suas permissões. Retirar uma concessão direta não retira uma concessão herdada. As permissões continuam globais por usuário, limitadas às lojas às quais ele tem acesso; não se tornam uma matriz diferente por loja.

## Regras preservadas e caminhos alternativos

- Inativação continua lógica. Não há exclusão física de cliente/produto pela API e o estoque/histórico é preservado.
- Enviar `is_active` em POST, PUT ou PATCH é rejeitado. Assim, edição comum não consegue contornar a permissão de inativar.
- Quantidade em estoque continua protegida contra edição direta de produto. O cadastro começa com saldo zero e as alterações vêm do fluxo de estoque.
- Movimentações continuam imutáveis. Conceder permissões Django de alterar/excluir movimentações não cria endpoints de edição ou exclusão de histórico.
- Staff e as funções Gerente, Vendedor, Caixa e Financeiro não substituem as concessões explícitas.
- Para fechar as telas legadas que permitiam alterar a situação de cadastros por outro caminho, a manutenção de clientes/produtos no Django Admin fica restrita a superusuários. Operadores, inclusive staff comuns, usam o frontend/API. As telas existentes do administrador do sistema continuam funcionando.
- O histórico de estoque no Django Admin continua somente leitura e filtrado pelas unidades acessíveis.
- Superusuário ativo continua com as permissões do sistema, mas não opera sobre unidade ou empresa inativa por estes endpoints.
- Autenticação, CSRF, isolamento por loja, validações de CPF/CNPJ, limites de quantidade e a configuração de estoque negativo permanecem aplicáveis.

## Estoque sem depender do módulo de vendas

A tela de estoque passa a usar `/api/me/stock-options/`, sem consultar opções de pagamento de vendas ou o catálogo comercial completo.

Esse endpoint exige consultar ou registrar movimentação e retorna somente:

- Produtos ativos da unidade: ID, código interno, descrição, saldo e estoque mínimo.
- Política de estoque negativo da unidade.
- Se o usuário pode consultar histórico e/ou registrar movimentações.

Não retorna preços de custo/venda, margem, código de barras ou campos comerciais adicionais. Usuários que podem apenas registrar movimentos veem os dados necessários para selecionar um produto e prever o saldo, mas não consultam o histórico. Usuários de consulta não veem formulário de movimentação.

`/api/me/catalog-access/` informa somente as capacidades do usuário autenticado na unidade selecionada, sem consultar contas de terceiros. As duas respostas têm cache desabilitado.

As movimentações internas de venda, cancelamento e recebimento de compra continuam sob os serviços e regras próprios desses módulos. A permissão de lançamento manual de estoque não é um pré-requisito adicional para vender ou receber compras. Esta entrega não padroniza permissões de vendas nem de outros módulos ainda pendentes.

## Instalação e validação

1. Confira que está em `feat/permissoes-cadastros-estoque` e pare o Django com Ctrl+C.
2. Extraia este ZIP em `C:\Projetos\lentis-erp`, preservando as pastas e substituindo os arquivos incluídos.
3. Com a `.venv` ativa:

```powershell
cd C:\Projetos\lentis-erp
python backend\manage.py check
python backend\manage.py makemigrations --check --dry-run
python backend\manage.py test organizations accounts --verbosity 2
```

Não há alterações de banco/migrações nesta etapa. Os testes existentes de clientes e estoque só receberam concessões explícitas nos respectivos cenários; as verificações de validação e isolamento foram preservadas. O novo arquivo testa separadamente a ausência das concessões e tentativas de contorno.

Para a regressão completa:

```powershell
python backend\manage.py test accounts organizations sales purchases --verbosity 2
```

Compile:

```powershell
cd C:\Projetos\lentis-erp\frontend
npm run build
```

Reinicie o backend e mantenha o frontend em outro terminal:

```powershell
cd C:\Projetos\lentis-erp
python backend\manage.py runserver 127.0.0.1:8000
```

```powershell
cd C:\Projetos\lentis-erp\frontend
npm run dev
```

## Teste manual por perfil

Use contas de teste com vínculo ativo na mesma unidade. Uma janela anônima ajuda a separar a sessão do administrador da sessão do operador.

1. Sem concessões: menus Clientes, Produtos e Estoque devem ficar ocultos. Chamadas diretas correspondentes recebem 403.
2. Somente consultar clientes/produtos: listas disponíveis, sem Novo, Editar e Inativar.
3. Cadastrar sem consultar: Novo disponível, lista restrita. Não deve haver tentativa de carregar a lista pela API.
4. Consultar e editar: pode editar, mas não cadastrar/inativar sem essas concessões.
5. Consultar e inativar: ação disponível mesmo em usuário sem staff; o cadastro é inativado sem exclusão física.
6. Somente consultar estoque: saldos e histórico disponíveis, sem Nova movimentação.
7. Somente registrar movimentação: formulário disponível sem histórico e sem precisar de acesso aos preços do catálogo ou opções de pagamento de vendas.
8. Retire uma permissão no administrador com o operador ainda conectado. Ao retornar à janela ou trocar de página os acessos são conferidos novamente. A API nega imediatamente a próxima requisição que precise da concessão retirada, sem exigir novo login.
9. Retire o vínculo com a unidade. Mesmo com permissões globais, a unidade não pode mais ser operada.
10. Confira que vendas, cancelamentos e recebimentos de compra continuam atualizando o estoque sob suas regras existentes.

Concessões não revogam dados já apresentados em uma página anteriormente autorizada. A interface se atualiza ao voltar à janela/trocar de página; chamadas diretas sempre verificam o estado atual no servidor. Se houver falha ao conferir acessos, os módulos protegidos exibem erro com botão de atualização.

## Arquivos entregues

- `backend/organizations/access_permissions.py`.
- `backend/organizations/views.py` e `urls.py` completos.
- `backend/organizations/admin.py` completo, preservando os recursos existentes do superusuário.
- `backend/organizations/test_access_permissions.py`.
- `backend/organizations/test_api.py` e `test_stock_api.py` completos com ajuste de concessões nos testes anteriores.
- `frontend/src/api.ts` e `frontend/src/components/AppLayout.tsx` completos.
- `frontend/src/components/StockMovements.tsx` e `StockMovements.css` completos, incluindo ajuste para evitar cortes no celular.
- `frontend/src/components/UserManagement.tsx`, com o aviso atualizado sobre os módulos já protegidos.
- `docs/regras-negocio.md` e este guia.

Os arquivos Product-model.py/.txt, a logo e documentos antigos pendentes não fazem parte da entrega.
