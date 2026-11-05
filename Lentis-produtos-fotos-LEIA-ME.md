# Lentis — produtos com fotos e características

Entrega de 04/11/2026, baseada na main 7cb5eb1. Branch: `feat/produtos-fotos`.
Extraia este pacote na raiz `C:\Projetos\lentis-erp`, preservando as pastas.
O pacote contém apenas os arquivos desta implementação. Não inclui `.env`,
credenciais, fotos de teste, banco, dependências instaladas ou arquivos pessoais.

## O que muda

- Cadastro em janela com as seções **Dados e características** e **Fotos**.
- Marca/categoria existentes e novos campos opcionais: modelo/referência, cor,
  material, formato, largura da lente, ponte, haste e detalhes do produto.
- Até três fotos por produto, com prévia, troca, remoção e escolha da principal.
- Miniatura na lista de produtos, busca/seleção e itens de vendas e compras.
- A busca comercial aceita nome, código e código de barras. A compra aceita
  nome e código. São exibidos até 50 resultados por vez; refine a busca para
  localizar produtos fora desse grupo. Os preços/custos das opções são mantidos.
- Produtos sem foto usam um ícone de óculos. Falha ao carregar uma foto também
  usa esse ícone, sem impedir a operação comercial.
- As imagens são ilustrativas e atuais do cadastro, inclusive ao abrir uma venda
  ou compra antiga. Não substituem os dados históricos de preço, descrição,
  custo ou quantidade dos documentos.

Não há criação automática de conta, bucket, token ou recurso pago. Para as fotos
funcionarem na homologação, configure o R2 descrito abaixo. Cadastros sem foto
continuam funcionando mesmo sem essa configuração.

## 1. Instalar e aplicar a migração

Feche o backend antes de atualizar as dependências. No PowerShell:

```powershell
Set-Location C:\Projetos\lentis-erp
& .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
& .\.venv\Scripts\python.exe backend\manage.py migrate
& .\.venv\Scripts\python.exe backend\manage.py check
```

A migração incluída é `organizations.0012`. Não rode `makemigrations` para
substituí-la. Produtos existentes mantêm código, código de barras, marca,
preços, estoque (inclusive negativo) e mínimo. Novos campos começam vazios,
medidas nulas e galeria sem fotos.

## 2. Preparar um bucket privado do Lentis no Cloudflare R2

1. No Cloudflare, abra **R2 Object Storage** e crie um bucket exclusivo para
   esta homologação, por exemplo `lentis-homolog-produtos`.
2. Mantenha o bucket privado, sem domínio público e sem acesso público r2.dev.
3. Crie um token R2 com **Object Read & Write**, limitado a esse bucket.
4. Guarde o **Access Key ID**, **Secret Access Key** e o endpoint S3 fornecidos.
   As chaves devem ficar apenas no `.env` local e no ambiente do Render.
5. No `.env` que já existe na raiz do projeto, adicione estas linhas, trocando
   os exemplos pelos valores reais. Preserve as variáveis do Django e do Neon:

```dotenv
PRODUCT_PHOTO_STORAGE=r2
LENTIS_R2_ENDPOINT=https://SEU_ACCOUNT_ID.r2.cloudflarestorage.com
LENTIS_R2_BUCKET=lentis-homolog-produtos
LENTIS_R2_ACCESS_KEY_ID=SUA_ACCESS_KEY_ID
LENTIS_R2_SECRET_ACCESS_KEY=SUA_SECRET_ACCESS_KEY
```

O Account ID do endpoint contém 32 caracteres hexadecimais. O endpoint não é a
URL pública do bucket e não deve conter `/nome-do-bucket`, parâmetros ou aspas
copiadas de comandos. Não envie essas chaves no chat e não adicione `.env` ao Git.
Não use o bucket nem as credenciais de outro projeto.

Use **o mesmo bucket e configuração no computador e no Render** se os dois
estiverem acessando o mesmo banco Neon. Assim, uma foto enviada localmente fica
disponível na homologação. Reinicie o backend após editar o `.env`.

Confira a conexão pelo PowerShell:

```powershell
Set-Location C:\Projetos\lentis-erp
& .\.venv\Scripts\python.exe backend\manage.py check_product_photo_storage
& .\.venv\Scripts\python.exe backend\manage.py check_product_photo_storage --roundtrip
```

O primeiro comando confere a configuração sem acessar o bucket. O segundo
escreve uma pequena imagem de diagnóstico, lê os bytes e a remove. Não altera
produtos. O resultado esperado termina em **Envio, leitura e remoção conferidos**.

Não é necessário configurar CORS público: o navegador fala com o backend do
Lentis, que valida o acesso antes de buscar cada imagem no bucket privado.

### Teste local isolado, sem R2

Somente para um banco de desenvolvimento separado da homologação, é possível
usar `PRODUCT_PHOTO_STORAGE=local`. Nesse caso, os arquivos ficam em
`media/product-photos` na raiz, ignorados pelo Git. Esse modo é recusado quando
`DEBUG=False`. Fotos locais não são transferidas pelo Git nem pelo deploy;
configure R2 antes de enviar fotos ao banco usado pela nuvem. O modo padrão é R2.

## 3. Testes e build

```powershell
Set-Location C:\Projetos\lentis-erp
& .\.venv\Scripts\python.exe backend\manage.py test organizations.test_product_photos sales.test_access_permissions purchases.test_access_permissions --verbosity 2
Set-Location C:\Projetos\lentis-erp\frontend
npm run build
```

Os testes de fotos usam um diretório temporário, sem chamar seu R2. Os testes do
adaptador R2 usam o SDK simulado; a conexão real é conferida pelo `--roundtrip`.
A concorrência usa PostgreSQL real na sua máquina/CI. Em SQLite esse teste é
explicitamente pulado, pois SQLite não implementa o bloqueio de linha usado.

## 4. Conferência no navegador

Inicie o backend e o frontend em terminais separados:

```powershell
Set-Location C:\Projetos\lentis-erp
& .\.venv\Scripts\python.exe backend\manage.py runserver 127.0.0.1:8000
```

```powershell
Set-Location C:\Projetos\lentis-erp\frontend
npm run dev
```

- Em **Produtos → Novo produto**, preencha os dados e as características.
- Em **Fotos**, envie até três arquivos, escolha outra principal e salve.
- Confira a foto na lista. Reabra, troque/remova uma foto e salve novamente.
- Confira as miniaturas na busca e nos itens de uma venda e de uma compra.
- Abra a edição, altere uma foto e tente fechar: deve pedir confirmação para
  descartar. Nenhuma foto é enviada antes de salvar o formulário.
- Confira no celular/tablet e nos temas claro e escuro.
- Teste com usuário sem permissão de editar produto. Ele não pode alterar fotos.
  Usuários de vendas/compras recebem as imagens necessárias à sua operação,
  sem ganhar acesso ao cadastro completo ou a dados de outra unidade.

## 5. Como a gravação é protegida

JPEG, PNG e WebP estáticos; até 5 MiB e 16 megapixels por arquivo. O servidor
confere o conteúdo real, aplica orientação EXIF e regrava sem metadados. Mantém
proporção: imagem até 1600×1600 / 1 MiB e miniatura até 240×240 / 96 KiB, em JPEG.
Transparência usa fundo branco. Os arquivos originais não são publicados.
Há limite de decodificação simultânea para conter o uso de memória.

As três posições e sua unicidade também são impostas pelo banco. A revisão da
galeria é conferida sob bloqueio do produto; edição desatualizada recebe 409,
e decodificador ocupado pode responder 429. Atualize/reabra antes de repetir uma
edição desatualizada. Isso evita sobrescrever fotos escolhidas em outra sessão.

O upload acontece antes da troca transacional dos vínculos. Falha de armazenamento
não salva metadados pela metade. Falha da transação conserva a galeria anterior e
tenta recolher os novos arquivos. Ativos e chaves pendentes ficam rastreados no
banco para limpeza posterior. A permissão e o vínculo são conferidos novamente
antes da gravação. Nome original, chaves R2 e segredos não aparecem nas respostas.

As imagens são servidas por endpoint autenticado da unidade, com `no-store` e
`nosniff`, sem links públicos ou URLs assinadas compartilháveis. Inativar um
produto preserva as fotos para consulta dos itens existentes.

### Limpeza de sobras

Uma interrupção abrupta ou indisponibilidade do R2 pode deixar objetos sem vínculo.
O comando abaixo considera apenas ativos sem foto vinculada e com mais de 24h:

```powershell
Set-Location C:\Projetos\lentis-erp
& .\.venv\Scripts\python.exe backend\manage.py cleanup_product_photos
# Após conferir a contagem:
& .\.venv\Scripts\python.exe backend\manage.py cleanup_product_photos --apply
```

O primeiro comando só lista a contagem; `--apply` remove os objetos e o registro.
Fotos vinculadas e envios recentes são preservados. Não aplica políticas de
expiração indiscriminada ao bucket inteiro.

### Backup

O backup PostgreSQL existente contém os vínculos e os metadados, **não os arquivos
R2**. Inclua o bucket em uma rotina própria de cópia de objetos e mantenha essa
cópia junto à referência temporal do backup do banco. Fotos removidas/substituídas
podem ser apagadas do bucket; restaurar apenas um dump antigo não as recupera.

## 6. Commit e homologação

Faça o commit apenas dos arquivos deste pacote, sem adicionar `.env`, `media`,
arquivos pessoais ou backups. Após os testes e a conferência, use a lista exata
incluída no manifesto:

```powershell
Set-Location C:\Projetos\lentis-erp
Get-Content .\Lentis-produtos-fotos-ARQUIVOS.txt | ForEach-Object { git add -- $_ }
git diff --cached --check
git --no-pager diff --cached --stat
git commit -m "feat: adiciona fotos e caracteristicas de produtos com armazenamento privado"
git push -u origin feat/produtos-fotos
```

Não use `git add .` neste projeto enquanto houver os arquivos pessoais pendentes.

Depois do push da `feat/produtos-fotos`, aguarde o CI verde e integre à `main`
conforme o fluxo já usado no projeto. Em **Render → lentis-homolog → Environment**,
adicione as cinco variáveis acima com os mesmos valores do `.env`. Não altere as
variáveis de banco, não recrie o banco Render antigo e mantenha o Neon.

Faça o deploy da main e acompanhe a aplicação da migração 0012 nos logs. O
`deploy/start.sh` existente já executa `migrate` antes do servidor. Confira o teste
manual na URL da homologação, incluindo fotos enviadas antes e depois do deploy.

## Referências da integração

- Cloudflare R2 com boto3: https://developers.cloudflare.com/r2/examples/aws/boto3/
- Tokens R2 com escopo por bucket: https://developers.cloudflare.com/r2/api/tokens/
- API S3 get_object: https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/get_object.html


## Validação desta entrega

- Suíte completa local: 757 testes encontrados, 733 aprovados e 24 explicitamente
  pulados por dependerem de PostgreSQL. Nenhuma falha em SQLite.
- 42 testes novos de fotos, armazenamento, migração e concorrência; o teste de
  concorrência deve executar no PostgreSQL do seu ambiente/CI.
- Build TypeScript/Vite aprovado. Migrações conferidas, sem alterações pendentes.
- Navegador automatizado: criação com 3 fotos e características, principal,
  edição/remoção, descarte, busca e itens de venda/compra, teclado/Escape,
  temas claro/escuro e larguras de 1440, 768 e 390 pixels sem estouro horizontal.
- Conexão real com o bucket R2 ainda não foi executada: depende das suas chaves
  e é validada pelo comando check_product_photo_storage --roundtrip.
