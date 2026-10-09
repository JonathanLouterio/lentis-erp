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
