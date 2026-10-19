# Regras de negócio do Lentis ERP

Levantamento inicial em 09/10/2026, com referências na documentação oficial de Omie, Bling e TOTVS WinThor. A seleção prioriza estoque, vendas e recebimentos. Não pretende reunir todas as regras desses produtos. As decisões do Lentis abaixo são adaptações para a operação da ótica; a documentação citada não define automaticamente o comportamento do nosso sistema.

## Regras e situação atual

| Código | Regra do Lentis | Situação | Referência |
| --- | --- | --- | --- |
| EST-01 | Permitir estoque negativo por unidade, com opção de bloqueio. O padrão é permitir, conforme solicitado. Avisar antes da confirmação e guardar o saldo efetivamente registrado. | Implementada neste pacote. | [Omie: configuração de estoque negativo][omie-estoque]; [Bling: permitir lançamento negativo][bling-estoque]. |
| EST-02 | Registrar entrada, saída e ajuste com autor, motivo e saldos anterior/posterior. Reposição soma ao saldo atual; nunca zera automaticamente um saldo negativo. | Implementada no Lentis; ampliada para saldos negativos neste pacote. | Decisão do Lentis. |
| EST-03 | Mostrar produtos no estoque mínimo ou abaixo dele. Evoluir para uma lista de reposição e aviso no painel da unidade. | A contagem básica já existe na tela de movimentações; painel e lista de reposição são propostas. | Decisão do Lentis. |
| VND-01 | Rascunho não movimenta estoque nem lança recebimentos. Conclusão registra estoque e financeiro em uma operação. Cancelamento preserva a venda e gera movimentos inversos. | Implementada no fluxo atual. | [Bling: transições com lançamento e estorno][bling-transicoes]. |
| VND-02 | Limitar descontos por perfil/unidade e exigir autorização quando exceder o limite. Registrar solicitante, aprovador, motivo e valores autorizados. | Implementada neste pacote. Limite por perfil/unidade, justificativa, aprovação ou recusa por outra pessoa autorizada e histórico imutável. Sem configuração, permanece o limite de 100% para preservar o comportamento anterior. | [TOTVS: política e autorização de desconto][totvs-desconto]. |
| FIN-01 | Aceitar recebimento parcial e manter separado o valor já recebido do saldo em aberto. Guardar conta, meio de recebimento, data e operador. | Implementada no fluxo de recebimentos. | [Omie: baixa parcial de receitas][omie-parcial]. |
| FIN-02 | Separar forma de pagamento acordada na venda, conta de destino e meio usado no recebimento. Diferenciar dívida do cliente de valor a receber da operadora do cartão. | Implementada no checkout atual; conciliação automática e taxas de cartão são futuras. | Decisão do Lentis. |
| FIN-03 | Montar entrada e saldo parcelado por venda, com intervalos e vencimentos próprios e fechamento exato dos centavos. | Implementada: entrada opcional, saldo em 1 a 12 parcelas, intervalos em meses ou dias, limite por forma/unidade e conferência calculada no servidor. Modelos reutilizáveis de condições são uma evolução futura. | [Omie: opções personalizadas de parcelas][omie-parcelas]. |
| FIN-04 | Controlar dinheiro físico por conta/unidade, com abertura, recebimentos em dinheiro, suprimentos, retiradas e fechamento com contagem e justificativa da diferença. | Implementada nesta etapa; responsável pela abertura e operador de cada movimento ficam registrados. | Decisão do Lentis. |
| PAINEL-01 | Mostrar vendas, recebimentos, dívida atual, caixa físico e estoque por unidade, com filtros e alertas identificados pelo período ou pela situação atual. | Implementada no dashboard operacional; os cálculos e atalhos respeitam a unidade autorizada. | Decisão do Lentis. |
| SEG-01 | Aplicar autorização por unidade no servidor e reavaliar acesso em cada operação, inclusive em repetições. Uma repetição do mesmo envio não duplica venda, estoque ou recebimento. | Implementada no Lentis. | Decisão do Lentis. |
| OTC-01 | Distinguir mercadoria pronta, lente sob encomenda e serviço; acompanhar encomendas em ordem de serviço, com prazo e entrega. | Proposta específica para a ótica. Não há criação automática de encomenda neste pacote. | Decisão do Lentis. |

## Funcionamento do estoque negativo

1. A unidade começa com **Permitir estoque negativo** marcado.
2. Vender uma unidade de um produto com saldo zero resulta em **−1**, com alerta na conferência e no resumo da venda.
3. O servidor calcula o saldo real durante a gravação. O saldo previsto na tela pode mudar se outra pessoa movimentar o produto antes da confirmação.
4. Uma entrada de três unidades após essa venda resulta em **2**. O registro original da venda continua mostrando que ela deixou o saldo em −1.
5. Cancelar a venda devolve a quantidade vendida e estorna os registros financeiros correspondentes. Movimentações posteriores permanecem no histórico.
6. Desmarcar a opção bloqueia novas saídas que deixariam saldo negativo. Entradas continuam permitidas, inclusive quando uma reposição parcial ainda deixa o saldo abaixo de zero.
7. Ajuste representa a quantidade fisicamente contada; aceita zero, mas não aceita contagem negativa.
8. A opção não altera preços, descontos, limite do campo numérico, acesso por unidade ou proteção contra duplicidade. Saldo negativo é informação de estoque, sem gerar uma compra ou encomenda automaticamente.

A configuração inicial fica no **Django Admin → Organizações → Lojas → unidade → Permitir estoque negativo**. Uma tela própria de configurações no frontend é uma evolução futura.

## Próximas evoluções propostas

1. **Condições comerciais adicionais:** regras para margem mínima e alçadas adicionais, a definir. O limite de desconto por perfil/unidade e a autorização registrada já estão implementados.
2. **Modelos de condições de pagamento:** salvar combinações reutilizáveis de entrada e parcelamento. A montagem por venda, os intervalos e o limite por forma/unidade já estão implementados.
3. **Reposição e encomendas:** painel de produtos negativos/abaixo do mínimo e fluxo de pedidos ao fornecedor/laboratório.
4. **Crédito e cobrança:** política de limite de crédito, análise de atraso e autorização; os valores e exceções devem refletir a operação da ótica.
5. **Cartões e caixa:** taxas por modalidade, conciliação e fechamento de caixa.

Os itens desta seção descrevem evoluções futuras. Estoque negativo configurável, autorização de descontos e montagem de entrada com saldo parcelado já fazem parte do Lentis.

## Fontes consultadas

- [Omie — Marcando para não permitir Estoque Negativo][omie-estoque]. Há configuração para impedir operações que negativem o estoque.
- [Bling — O estoque automático não lança para algumas vendas. Como resolver?][bling-estoque]. É possível habilitar o lançamento mesmo quando o saldo for insuficiente.
- [Bling — Gerenciador de transições para situações de pedidos de venda][bling-transicoes]. Transições podem disparar lançamento ou estorno de estoque e contas. O Lentis mantém três estados; não reproduz todas as situações do Bling.
- [TOTVS WinThor — Como definir um percentual máximo de desconto na venda][totvs-desconto]. A política de descontos pode exigir autorização para excedentes.
- [Omie — Realizando uma Baixa Parcial – Receita][omie-parcial]. Recebimentos parciais preservam o controle de valores pagos e em aberto.
- [Omie — Cadastrando um novo Número de Parcelas][omie-parcelas]. Condições podem usar intervalos em dias, parcela à vista e pagamentos mensais.

[omie-estoque]: https://ajuda.omie.com.br/pt-BR/articles/6860674-marcando-para-nao-permitir-estoque-negativo
[bling-estoque]: https://ajuda.bling.com.br/hc/pt-br/articles/360040694834-O-estoque-autom%C3%A1tico-n%C3%A3o-lan%C3%A7a-para-algumas-vendas-Como-resolver
[bling-transicoes]: https://ajuda.bling.com.br/hc/pt-br/articles/360039070654-Gerenciador-de-transi%C3%A7%C3%B5es-para-situa%C3%A7%C3%B5es-de-pedidos-de-venda
[totvs-desconto]: https://centraldeatendimento.totvs.com/hc/pt-br/articles/41233748851991-WINT-Como-definir-um-percentual-m%C3%A1ximo-de-desconto-na-venda
[omie-parcial]: https://ajuda.omie.com.br/pt-BR/articles/499024-realizando-uma-baixa-parcial-receita
[omie-parcelas]: https://ajuda.omie.com.br/pt-BR/articles/10760883-cadastrando-um-novo-numero-de-parcelas

## Detalhes da autorização de desconto

- Limites são configurados no Django Admin em **Vendas → Limites de desconto por perfil**, vinculados a uma unidade e ao perfil do vínculo do usuário. Sem linha cadastrada para aquele perfil, o limite é 100%. O superusuário tem limite de 100%.
- O desconto considerado inclui descontos nos itens, desconto geral e redução do preço unitário em relação ao preço de referência. Os preços de referência de novos itens são capturados no servidor; o cliente não escolhe esse valor.
- Itens anteriores a esta atualização não possuem preço de referência; para esses registros, o valor unitário já negociado é usado como referência. Ao substituir os itens no checkout, a referência passa a ser o preço atual do cadastro.
- A comparação usa valores exatos antes de arredondar o percentual para exibição.
- A solicitação é criada em uma venda em rascunho e não registra estoque ou financeiro. A aprovação também não conclui a venda: o operador ainda precisa conferir e confirmar o atendimento.
- O superusuário pode autorizar. Outros usuários precisam da permissão **Pode autorizar descontos acima do limite**, de acesso ativo à unidade e de ser uma pessoa diferente do solicitante. Marcar apenas **Membro da equipe** não concede essa autorização.
- A autorização vale para o solicitante e para os valores registrados. Mudanças de itens, quantidades, preços de referência, descontos, cliente, perfil ou limite impedem reutilizá-la para valores diferentes. Retornar exatamente aos valores autorizados permite reutilizar aquela autorização. Notas e forma de pagamento não alteram os valores de desconto autorizados.
- Uma recusa pode ser seguida de uma nova solicitação com justificativa. Decisões já registradas não são editadas nem apagadas.
- O vendedor usa **Atualizar autorização** para consultar a decisão. Não há atualização automática por notificações nesta etapa.


## Condições de pagamento da venda

- **Entrada + parcelas** monta duas formas de pagamento: entrada opcional em dinheiro, Pix ou transferência e saldo em cartão de crédito, boleto ou crediário. A entrada pode ser zero; o saldo deve ser positivo. A aplicação substitui os pagamentos atuais, mantendo os produtos e os descontos.
- A entrada só entra no saldo da conta quando **Entrada já recebida e conferida** estiver marcada. Cartão, boleto e crediário permanecem como valores a receber. Cartão gera recebíveis da operadora; boleto e crediário exigem cliente identificado na conclusão.
- O limite é definido por forma de pagamento e unidade no Django Admin, em **Vendas → Formas de pagamento → Máximo de parcelas**, entre 1 e 12. As formas já cadastradas recebem o padrão de 12; dinheiro, Pix, transferência e débito continuam aceitando uma parcela, independentemente do número configurado.
- O intervalo pode ser de 1 a 12 meses ou de 1 a 365 dias. O primeiro vencimento é escolhido na venda. Em meses, o cálculo mantém o dia original e usa o último dia quando necessário: 31/01 → 28 ou 29/02 → 31/03. Um intervalo de 30 dias é contado em dias corridos e pode diferir do mensal. Não há ajuste automático para dia útil.
- A divisão usa centavos exatos; o resto é distribuído nas primeiras parcelas. Exemplo: R$ 550 em três parcelas resulta em R$ 183,34 + R$ 183,33 + R$ 183,33.
- A prévia no formulário é imediata. Ao clicar em **Concluir venda**, a conferência consulta o servidor para validar as formas, limites, intervalos, valores e vencimentos. Essa consulta não salva venda nem gera estoque, parcelas ou recebimentos. A confirmação revalida os dados e grava a operação completa.
- Os intervalos ficam registrados nos pagamentos da venda e são preservados na reabertura. Pagamentos antigos usam um mês de intervalo. Reduzir o limite de uma forma bloqueia novos planos acima do limite e a conclusão de rascunhos que o ultrapassem; não altera parcelas de vendas já finalizadas.
- A entrada e os intervalos não calculam juros, taxas de cartão, correção por atraso ou cobrança bancária. Essas regras continuam futuras. Também não há cadastro de modelos reutilizáveis ou vencimento manual diferente para cada parcela nesta etapa.


## Caixa físico

- Cada conta de dinheiro físico pode ter uma abertura por vez. A conta inicial de código `cash` já aparece nas opções. Contas adicionais são marcadas no admin como **Conta de dinheiro físico**; cada uma representa um caixa separado.
- A primeira abertura ativa o controle de recebimentos em dinheiro naquela conta. Antes dessa ativação, o financeiro existente continua funcionando. Recebimentos anteriores não são importados para uma abertura: o dinheiro presente é informado no saldo inicial contado.
- Depois de ativado, um recebimento ou estorno em dinheiro nessa conta exige caixa aberto. A regra vale no servidor, incluindo recebimentos parciais e conclusão de venda. A interface avisa quando os dados já mostram a conta fechada; uma alteração simultânea é revalidada na gravação.
- O previsto é **dinheiro inicial + suprimentos + recebimentos em dinheiro − retiradas − estornos em dinheiro**. Pix, transferência, débito e crédito não alteram a contagem física, mesmo que usem a mesma conta de recebimento. Contas não ativadas permanecem com o financeiro anterior.
- Suprimento e retirada são movimentos do dinheiro físico e não baixam dívidas de clientes. Não são lançamentos bancários automáticos. O saldo acumulado da conta no financeiro continua refletindo seus recebimentos e estornos; o saldo do caixa é mostrado separadamente nesta tela, por abertura.
- Retiradas e estornos não podem ultrapassar o dinheiro previsto disponível. Um cancelamento que exige estorno em dinheiro e não encontra caixa aberto ou saldo suficiente é recusado por inteiro; a venda, o estoque e o financeiro permanecem intactos. É necessário abrir ou recompor o caixa antes de tentar novamente.
- Se uma venda recebida em dinheiro é cancelada depois de fechar a abertura original, o estorno entra na abertura atual da mesma conta. O fechamento anterior e sua diferença permanecem preservados.
- Fechar registra o previsto no momento da gravação, o contado, a diferença, o responsável e a observação. Diferença diferente de zero exige justificativa. A contagem não gera recebimento, ajuste automático da conta financeira ou correção automática do caixa.
- O responsável pela abertura pode fazer movimentos manuais e fechar o próprio caixa. Outra pessoa precisa da permissão **Pode operar e fechar caixas de outros responsáveis**, além de acesso ativo à unidade. Superusuários possuem essa permissão; apenas marcar **Membro da equipe** não a concede.
- Recebimentos provenientes de vendas ficam com o operador que os registrou e podem entrar no caixa aberto da equipe. Consultas e históricos permanecem restritos à unidade autorizada.
- Abertura, movimentos e fechamento usam identificadores para que uma repetição do mesmo envio recupere a operação sem duplicação. Caixa fechado não aceita novos movimentos nem edição do histórico. Listas de aberturas e movimentos são paginadas.
- Nesta etapa não há troco automático, sangria para banco com transferência financeira, reabertura/edição de caixa fechado, impressão de fechamento, conciliação de cartão, TEF ou controle fiscal. Essas funcionalidades serão evoluções separadas.


## Indicadores do dashboard

- Períodos de vendas e recebimentos: hoje, últimos sete dias, mês até hoje ou personalizado de até 366 dias, em America/Sao_Paulo. Comparação com período anterior de mesma duração; base zero não gera percentual inventado.
- Vendas usam finalização e situação atual não cancelada; valores descontam por item e por venda sem multiplicação por pagamentos. Recebimentos usam datas de lançamento e incluem estornos com sinal negativo.
- Saldo de cliente, repasse de cartão, vencidos, vencimentos hoje, estoque ativo e caixas abertos são situações atuais, identificadas separadamente do período filtrado.
- O painel consulta dados reais e não gera registros. Detalhes são limitados aos cinco primeiros itens e levam aos módulos completos.
- Atalhos para nova venda/cliente e atendimento recente; reposição abre o produto na movimentação. Recebimentos abrem o módulo financeiro, onde se escolhe a parcela.
- Metas, margem, rankings, relatórios exportáveis e notificações automáticas não foram introduzidos nesta etapa.


## Orçamentos

- O orçamento pertence à unidade selecionada e exige acesso ativo a ela. Cliente e produtos devem ser da mesma unidade. Cliente é opcional nesta etapa.
- Rascunhos podem ter zero itens. Preparar a proposta exige itens e validade vigente; o dia da validade ainda é válido, no fuso America/Sao_Paulo.
- Fluxo: rascunho → proposta pronta → aceite registrado → convertido em venda. Preparar não envia mensagem ao cliente. O aceite é registrado pelo operador; não equivale a assinatura digital.
- Cada produto aparece uma vez; quantidades, preços negociados e descontos são preservados na conversão. Valores monetários usam Decimal e arredondamento por item para centavos.
- Revisar uma proposta pronta ou aceita retorna ao rascunho, incrementa a versão e exige nova preparação e novo aceite. Edições concorrentes com versão antiga são rejeitadas.
- Recusa exige motivo; propostas recusadas e convertidas preservam o registro e não são editadas ou excluídas. O histórico identifica operador, data, ação e versão.
- Criar, preparar ou aceitar não reserva nem baixa estoque, não recebe pagamentos e não gera parcelas. Converter cria uma única venda em rascunho; também não movimenta estoque ou financeiro.
- A conversão revalida produtos e cliente ativos. Estoque insuficiente não impede criar o rascunho. Ao concluir a venda, aplicam-se as regras existentes de estoque negativo, pagamento, caixa e autorização de desconto.
- O preço de referência para controle de desconto na venda é o preço atual do cadastro na conversão; o preço negociado do orçamento é mantido. Registrar o aceite não concede autorização de desconto.
- Identificadores de operação permitem repetir um envio sem duplicar o orçamento ou a venda. A conversão de uma proposta já convertida retorna sua venda existente. Respostas incertas são recuperadas na tela com o mesmo identificador.
- O vínculo com a proposta permanece mesmo se a venda gerada for posteriormente cancelada. Uma nova negociação exige novo orçamento.
- Envio por WhatsApp/e-mail, assinatura do cliente e reserva de estoque não fazem parte desta etapa.


## Impressão de orçamentos

- A prévia usa os itens, descontos, observações, revisão e situação salvos. Alterações no formulário precisam ser salvas antes da impressão.
- O documento é aberto em outra aba por um GET autenticado e autorizado para a unidade do orçamento, sem alterar histórico, situação, estoque ou financeiro. A resposta não deve ser armazenada em cache.
- É possível imprimir ou salvar em PDF pelo diálogo do navegador, com papel A4. A impressão repete o cabeçalho da tabela e evita dividir linhas de itens entre páginas. Chrome e Edge atuais também exibem a numeração e o identificador do orçamento nas margens.
- Rascunhos, propostas vencidas, recusadas e convertidas possuem indicação explícita. Converter não significa que o pagamento foi recebido; o documento orienta consultar a venda.
- O orçamento é uma proposta comercial, não é documento fiscal nem comprovante de pagamento.
- Empresa, nome da unidade, telefone e e-mail são consultados no cadastro atual; cliente inclui os dados cadastrais disponíveis e endereço. Não imprime notas internas do cadastro do cliente, RG ou data de nascimento. O cadastro de unidade atual não possui endereço/CNPJ; esses dados não são inventados.
- Valores monetários são formatados no backend com Decimal, em reais e vírgula decimal. Nomes e observações são escapados como texto, sem interpretar HTML inserido nos cadastros.
- O PDF é salvo no computador pelo usuário. Não é arquivado automaticamente no sistema nem enviado a terceiros.


## Receitas oftalmológicas por cliente

- Cadastro em Cadastros → Receitas, sempre vinculado a cliente e unidade. Não é permitido transferir uma receita entre clientes ou unidades; outro paciente exige outro registro.
- É um registro da receita apresentada, não emissão de prescrição: não interpreta os graus, não realiza transposição de cilíndrico, não soma adição e não calcula DP/DNP. Não afeta vendas, caixa, estoque ou recebimentos.
- Registra data da receita, prescritor e registro informado, esférico, cilíndrico, eixo e adição de OD/OE, DP/DNP em milímetros e observações. Não consulta conselho profissional nem determina validade clínica.
- Valores assinados e zero são preservados. Campo não informado fica nulo e não é convertido em zero. Os números aceitam até duas casas decimais; a capacidade de armazenamento não é um limite clínico. Esférico, cilíndrico e adição aceitam os sinais informados, sem conversão.
- Eixo é inteiro entre 0 e 180. Cilíndrico não zero exige eixo; eixo informado exige cilíndrico. DP/DNP informadas precisam ser positivas. Pelo menos um esférico, cilíndrico ou adição deve estar informado; zero conta como valor informado.
- O acesso exige vínculo ativo à unidade e permissão organizations.view_prescription. Cadastro também exige organizations.add_prescription; correção e arquivamento exigem organizations.change_prescription. Superusuário ativo tem as permissões; apenas is_staff ou perfil Vendedor não as concede.
- As permissões globais não liberam acesso a outras unidades. Todos os endpoints, inclusive histórico, validam a unidade. Respostas usam Cache-Control no-store, private.
- Cadastro, correção e arquivamento são operações atômicas. Cada versão guarda os campos registrados, operador, data/hora e motivo. Correções e arquivamento exigem motivo. Versão desatualizada é rejeitada para evitar sobrescrever trabalho de outra pessoa.
- Arquivamento mantém o histórico e impede novas correções naquele registro. Receitas não são excluídas pela API; histórico não é editado. Uma nova receita clínica deve ser outro cadastro; Corrigir serve para corrigir a transcrição.
- Um identificador único permite repetir envios sem duplicação. No navegador, apenas envios com resposta incerta ficam temporariamente no sessionStorage da aba, separados por usuário/unidade, e são removidos após confirmação. Não há armazenamento local automático de rascunhos.
- A consulta pode filtrar cliente e registros ativos/arquivados, com paginação de 25 itens. O histórico é apresentado ao abrir uma receita.
- Não inclui anexos, PDF, ligação com ordem de serviço, cálculo óptico ou agendamento de exame nesta etapa. A ligação com vendas é descrita na próxima seção.


## Receita utilizada na venda

- A seleção é opcional e aparece na tela de vendas para usuários com organizations.view_prescription, além do acesso ativo à unidade. Não exige permissão de corrigir a receita para apenas escolher uma receita já cadastrada.
- A receita escolhida precisa estar ativa, na mesma unidade e vinculada ao cliente identificado na venda. Não é possível escolher receita em venda de balcão sem cliente.
- A escolha usa identificador e versão, sem aceitar graus ou cópias enviados pelo navegador. O backend bloqueia a receita e confere a versão na hora de salvar. Alterações/arquivamento entre a escolha e o salvamento exigem atualizar as opções e conferir novamente.
- Ao salvar o rascunho ou concluir a venda, é criada uma cópia dos valores da versão escolhida, com identificação da origem, cliente, operador e data. A cópia é registrada na mesma transação do checkout; falha no atendimento desfaz o vínculo.
- Salvar a venda sem escolher outra receita mantém exatamente a cópia existente, mesmo quando o cadastro original foi posteriormente corrigido ou arquivado. Nada é atualizado automaticamente.
- Para utilizar uma revisão posterior, escolha explicitamente a versão atual no rascunho e salve. A tela avisa quando identifica outra versão nas opções carregadas. Este aviso não substitui a conferência da receita apresentada e não é uma notificação em tempo real.
- Em rascunhos, usuários autorizados podem selecionar outra receita ou remover o vínculo ao salvar. As cópias anteriores e a remoção permanecem no histórico.
- Mudar o cliente de uma venda vinculada exige remover/substituir o vínculo de forma autorizada na mesma transação. A tela limpa a escolha ao trocar o cliente; o backend impede manter receita de outra pessoa.
- O identificador do vínculo atual precisa corresponder ao que o operador abriu, evitando sobrescrever uma escolha concorrente. Isso protege o vínculo de receita, não implementa um controle geral de versão de todos os campos de venda.
- Vendas concluídas ou canceladas não permitem trocar/remover a cópia. Cancelamento mantém os dados da receita. Vendas com histórico de receita preservam esse histórico e devem usar cancelamento, não exclusão física.
- Usuários sem permissão de receitas continuam operando os demais dados da venda, sem receber graus/cópias. Eles não podem escolher, remover ou consultar o histórico de receitas. As respostas gerais de venda carregam apenas a referência autorizada; os valores são consultados em endpoint específico com Cache-Control no-store, private.
- O checkout continua idempotente: repetir um envio com resposta incerta recupera a mesma venda e cópia, sem duplicar estoque ou financeiro.
- Vendas antigas e vendas convertidas de orçamento iniciam sem receita até uma escolha explícita no rascunho. Não há preenchimento retroativo. A receita da venda não aparece automaticamente no PDF de orçamento.
- Não inclui cálculo óptico, emissão de prescrição, anexos ou OS nesta etapa. A estrutura fica disponível para futura integração com a OS.


## Ordens de serviço da ótica

- Uma OS por venda finalizada, com cliente identificado e itens. Não é criada automaticamente.
- A abertura preserva o nome do cliente, identificação e quantidade dos itens, além do vínculo à cópia imutável de receita da venda, quando existir. Alterações na receita original não atualizam a OS.
- A ausência de receita não bloqueia a abertura, permitindo serviços que não precisam de grau. Nenhum cálculo clínico é realizado.
- Etapas: aberta → laboratório → montagem → conferência → pronta para entrega → entregue. Não é permitido pular etapas.
- A conferência exige confirmação explícita. A entrega exige confirmação e identificação de quem recebeu no campo de observação.
- Retrabalho parte da conferência ou da etapa pronta para entrega, retorna ao laboratório ou montagem e exige motivo.
- Previsão de entrega obrigatória; OS em andamento com previsão anterior à data local do sistema aparece atrasada.
- Edição dos dados de produção exige motivo. Cada alteração preserva os dados da versão, responsável e data no histórico.
- Versão esperada impede gravação de tela desatualizada; UUID de operação impede duplicação por reenvio.
- A OS não movimenta novamente o estoque, contas a receber ou caixa. Cancelar a OS não cancela a venda.
- Cancelar a venda não apaga a OS: as ações de produção ficam bloqueadas, a fila exibe alerta e o operador deve cancelar a OS com motivo. OS já entregue preserva seu encerramento e histórico.
- OS entregue ou cancelada não pode ser editada, excluída ou reaberta nesta etapa.
- Acesso exige vínculo ativo com a unidade e permissão sales.view_serviceorder; abertura exige add_serviceorder; alterações exigem change_serviceorder. Ser staff não concede essas permissões.
- Valores da receita só são retornados com organizations.view_prescription. A permissão operacional de OS não concede acesso clínico.
- Informações operacionais (armação, lentes e observações) são visíveis aos usuários autorizados da OS. Não digitar graus ou outros dados clínicos nesses campos para contornar a separação de acesso.
- Impressão, fornecedores de laboratório, custos, anexos, entregas parciais, múltiplas OS por venda e garantias/reabertura ficam para etapas posteriores.


## Histórico consolidado do cliente

- Consulta somente leitura, limitada ao cliente e à unidade selecionada; não cruza cadastros por CPF/CNPJ nem pesquisa clientes de outras lojas.
- Resumo: vendas finalizadas, rascunhos, orçamentos e contagens de receitas/OS quando autorizadas. O saldo pendente do cliente é separado do saldo devido pela operadora.
- O saldo de cada parcela é seu valor menos a soma dos recebimentos e estornos. Vendas canceladas não compõem pendências nem atraso; suas parcelas continuam consultáveis com situação Cancelada.
- O valor vencido do cliente considera somente parcelas de sua responsabilidade, ainda abertas em vendas finalizadas e com vencimento anterior à data local.
- Seções paginadas: vendas, orçamentos, receitas, ordens de serviço e parcelas. Os detalhes sempre validam também o cliente e a unidade; um ID isolado não concede acesso.
- As seções de receitas e OS exigem as mesmas permissões dos respectivos módulos. Sem permissão, nem suas contagens são retornadas; permissão de OS não concede acesso clínico.
- A lista de receitas não retorna os graus. O detalhe autorizado consulta a versão atual do cadastro, inclusive quando arquivado; cópias imutáveis utilizadas em vendas e OS continuam sendo consultadas nos atendimentos correspondentes.
- Itens de vendas e orçamentos usam os nomes, quantidades e valores registrados. A ficha de contato usa os dados atuais do cliente. Esta consulta não substitui os históricos de versões e eventos dos módulos de origem.
- Cliente inativo mantém o histórico acessível pela API à unidade autorizada, sem reativação. A lista principal de clientes continua com seu filtro existente de cadastros ativos.
- O botão Histórico não altera estoque, financeiro, pagamentos, receitas ou OS. As respostas são privadas e não devem ser armazenadas em cache compartilhado.
