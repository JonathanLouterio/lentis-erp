# Lentis — configurações, perfil e catálogo visual

Decisões registradas com Jonathan em 30/10/2026.
Este documento define o escopo das próximas implementações. As funcionalidades
abaixo ainda não são implementadas pelo pacote de homologação/mobile.

## Estrutura escolhida

O sistema deverá atender várias óticas independentes. Cada empresa terá suas
unidades, dados cadastrais, regras e redes sociais. O modelo atual limita o banco
a uma empresa; será necessária uma migração que preserve a ótica e as unidades
existentes e uma revisão de isolamento antes de cadastrar empresas independentes.

O administrador da plataforma será o único com acesso à configuração global.
Ter perfil de gerente/vendedor, `is_staff` ou permissão operacional não concede
esse acesso. As verificações serão feitas no backend, além da interface.

O acesso operacional continuará limitado às unidades autorizadas. A revisão
deverá definir explicitamente a vinculação de usuários às empresas e testar
consultas, alterações, relatórios, exportações e mídias entre óticas diferentes.
Não basta remover a restrição de empresa única.

## Layout de Usuários e acessos

Abas principais:

1. **Usuários e permissões**: mantém a gestão de usuários, vínculos e permissões.
2. **Configurações do sistema**: área reservada ao administrador da plataforma.

Dentro das configurações:

| Seção | Conteúdo |
| --- | --- |
| Óticas | Lista de empresas, busca, situação, cadastro e edição |
| Dados da ótica | Identificação, contatos e dados cadastrais da empresa selecionada |
| Unidades | Unidades vinculadas à ótica, contatos, situação e configurações por unidade |
| Regras comerciais | Regras existentes organizadas por escopo; entrada mínima, acréscimos, descontos e estoque negativo conforme as políticas do sistema |
| Redes sociais | Instagram, TikTok, Facebook, site e WhatsApp da ótica |
| Histórico | Quem alterou, quando, quais campos e empresa/unidade afetada |

Um cabeçalho fixo identifica a empresa em edição. Trocar de empresa com alterações
pendentes exige confirmação. No computador, navegação por seções; no celular,
seletor de seção e formulário em tela inteira. Inativação exige confirmação e
preserva os históricos. Unidades com movimentação não podem ser transferidas
silenciosamente entre empresas.

## Meu perfil

O nome/avatar no canto inferior esquerdo abre um menu com **Meu perfil**,
**Preferências** e **Sair da conta**. No celular, o mesmo acesso fica no menu móvel.

Campos propostos: foto, nome, sobrenome, e-mail de contato, telefone/WhatsApp e
informações de apresentação. Preferência de tema usa a configuração já existente.
Cargo descritivo não altera o perfil de autorização.

O usuário edita somente os próprios campos permitidos. Empresa, unidades, papéis,
permissões, ativação e privilégios administrativos permanecem sob administração.
Troca de senha deve ter um fluxo separado com conferência da senha atual.

## Redes sociais

As redes pertencem à ótica, não ao perfil pessoal do usuário. Os links devem
ser validados, abrir com segurança em nova aba e manter um escopo explícito de
empresa. A primeira versão registra links; não publica conteúdo nem conecta
automaticamente contas às APIs das redes sociais.

## Produtos com fotos e características

Requisitos solicitados:

- Até **três fotos por produto**.
- Upload na criação e na edição, com prévia, remoção e escolha da foto principal.
- Miniatura na listagem de produtos.
- Miniatura na busca/seleção de produto e nos itens de venda e compra.
- Imagem padrão quando não houver foto.
- Características organizadas por categoria, evitando exigir medidas de armação
  para produtos aos quais elas não se aplicam.

Campos propostos para armações/óculos: marca, modelo/referência, cor, material,
formato, largura da lente, ponte e haste em milímetros, além de descrição.
Outras categorias terão campos pertinentes; os dados operacionais atuais, como
código, preço, custo e estoque, serão preservados.

Layout do cadastro: aba **Dados e características** e aba **Fotos**, com três
posições visuais, ação para tornar uma foto principal e indicação clara de
quantos espaços estão ocupados. No celular, o seletor deve permitir escolher
da galeria ou usar os recursos de câmera oferecidos pelo navegador.

Diretrizes técnicas:

- Armazenamento de objetos persistente, compatível com a hospedagem na nuvem.
- Vinculação inequívoca ao produto e à empresa; acesso conforme permissões.
- Validação real do conteúdo da imagem, tamanho e dimensões; inicialmente
  JPEG, PNG e WebP. SVG/HTML não entram no upload de fotos.
- Remoção de metadados desnecessários e geração de miniaturas para listagens.
- Tratamento de falha de upload, tentativas repetidas e arquivos órfãos.
- Fotos não alteram preços, saldos, totais ou regras de venda e compra.
- Respeitar o limite de três também no backend, inclusive em envios simultâneos.

## Ordem de implementação

1. Finalizar a base de homologação/mobile e validar o novo CI.
2. Migrar e testar o modelo de várias óticas; criar a área administrativa de
   empresas e unidades com auditoria e controles de acesso.
3. Organizar as configurações e redes sociais por ótica.
4. Preparar o armazenamento persistente e os controles de mídia.
5. Criar Meu perfil e upload de avatar.
6. Ampliar produtos com características e três fotos; integrar miniaturas a
   listagens, vendas e compras.
7. Validar em aparelhos reais; então evoluir para PWA instalável.

Critérios transversais: usuário comum recebe bloqueio ao acessar configuração
global; uma ótica não consulta ou altera dados/mídias de outra sem autorização
explícita; a migração preserva dados existentes; teclado, toque, temas claro/escuro
e tratamento de alterações não salvas são verificados em cada entrega.
