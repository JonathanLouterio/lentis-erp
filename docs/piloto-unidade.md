# Piloto de uma unidade no Lentis

Comece com um ensaio na homologação e, se os valores e acessos conferirem, repita
a rotina em paralelo ao controle atual durante um turno de uma unidade. O objetivo
é conferir se a equipe consegue sair da venda e chegar ao fechamento sem depender
de acertos manuais.

## Antes do ensaio

- Selecione uma unidade de teste na homologação. Use cliente fictício, produto de
  teste e lançamentos de teste. Para o aviso de retirada, use um número autorizado
  da própria equipe ou só revise a mensagem no WhatsApp.
- Use uma conta de operação no tablet e outra de gestão. Confirme que cada uma tem
  vínculo ativo com a unidade e os acessos necessários. O operador abre e fecha o
  próprio caixa; a gestão confere o financeiro e os relatórios. Teste com as contas
  de trabalho, sem usar o superusuário para validar permissões.
- Separe um produto de R$ 100,00 com saldo inicial de 3 unidades, uma conta de
  dinheiro físico sem sessão aberta, uma conta bancária e as formas Dinheiro, Pix e Crediário.
  Use o código de barras do produto para fazer pelo menos uma das vendas no tablet.
- Anote a unidade, data, pessoas responsáveis e saldos iniciais. O exemplo abaixo
  usa caixa físico inicial de R$ 50,00 e valores sem desconto nem acréscimo.
  Se a unidade de teste já tiver lançamentos, compare as diferenças e use os
  números das vendas e dos títulos deste ensaio.

## Roteiro no tablet

| Feito | Ação | Resultado esperado |
| --- | --- | --- |
| ☐ | **Comercial → Caixa:** abrir com R$ 50,00 em dinheiro contado. | Caixa aberto; saldo previsto de R$ 50,00. |
| ☐ | **Comercial → Vendas:** concluir a venda A de uma unidade, com R$ 100,00 em dinheiro. | Venda finalizada, estoque de 3 para 2 e caixa previsto de R$ 150,00. |
| ☐ | Concluir a venda B para o cliente fictício: uma unidade, R$ 40,00 de entrada confirmada em Pix na conta bancária e R$ 60,00 em uma parcela de crediário com vencimento hoje. | Estoque de 2 para 1. Entrada de R$ 40,00 no financeiro da conta bancária e parcela em aberto de R$ 60,00. O caixa físico continua em R$ 150,00. |
| ☐ | **Gestão → Contas a pagar → Nova despesa:** lançar R$ 30,00 de transporte com vencimento ontem, em aberto. | A despesa aparece em **A pagar em atraso** na Agenda, inclusive no período **Próximos 30 dias**. A parcela da venda B aparece no dia de hoje e não soma em **A receber em atraso**. |
| ☐ | Em **Gestão → Relatórios → Agenda financeira**, abrir o dia de hoje, entrar em **Recebimentos** e registrar R$ 20,00 em Pix na parcela B. Clicar em **Voltar à Agenda**. | O mesmo dia e período reabrem. O saldo da parcela cai de R$ 60,00 para R$ 40,00. O caixa físico continua em R$ 150,00. |
| ☐ | Na Agenda, aplicar um período que inclua ontem. Abrir a despesa em **Contas a pagar** e registrar o pagamento simulado de R$ 30,00 por Pix, com data de hoje. Voltar à Agenda. | A despesa sai dos compromissos em aberto; **A pagar em atraso** cai R$ 30,00. A variação registrada na conta bancária neste ensaio fica em **+R$ 30,00** (R$ 40,00 + R$ 20,00 − R$ 30,00). |
| ☐ | Na venda B, abrir uma OS com previsão de entrega. Avançar pela fila até **Pronta para entrega**, revisar o aviso de retirada e concluir a entrega com a identificação de quem recebeu. | O histórico registra as etapas. A OS aparece em **Entregues** e não lança outra saída de estoque, parcela ou recebimento. |
| ☐ | Em **Caixa**, fechar com R$ 150,00 contados. Em **Relatórios**, conferir as vendas, a despesa e a Agenda. Em **Estoque**, conferir as duas saídas. | Diferença de caixa de R$ 0,00; vendas de R$ 200,00; despesa paga de R$ 30,00 na data do pagamento; saldo a receber de R$ 40,00; estoque final de 1 unidade. |
| ☐ | Na conta de operação, conferir o menu e o seletor de unidades. | A conta só vê unidades vinculadas e ações concedidas. Se houver uma segunda unidade de teste sem vínculo, ela não aparece no seletor. |

Os valores bancários acima são lançamentos registrados no Lentis. No ensaio,
não faça transferências ou cobranças reais para reproduzi-los.

## Passagem para um turno em paralelo

1. Antes de usar dados reais, confirme que o ambiente escolhido foi liberado para
   o piloto e tem backup e restauração testada. Os scripts locais cobrem o banco
   local via Docker Compose; não validam o banco da nuvem nem a mídia.
2. Durante um turno, mantenha o controle oficial da ótica e use o Lentis em
   paralelo para uma amostra de operações. Registre uma venda à vista, uma com
   saldo a receber e uma despesa; acompanhe uma OS conforme o prazo real, sem
   marcar etapas ou disparar avisos para simular andamento.
3. No fim do turno, compare vendas, estoque, dinheiro físico e saldos em aberto
   com o controle atual. Compare o financeiro por conta com os movimentos
   correspondentes, separando dinheiro de Pix e cartão.
4. Se houver valor divergente, duplicidade ou acesso indevido, interrompa a
   ampliação do piloto, mantenha o controle oficial e anote o caso para correção.
   Amplie para mais turnos quando os saldos conferirem e a equipe conseguir
   executar a rotina sem intervenção.

Registro sugerido por caso: **data/turno · unidade · perfil · ação · número do
lançamento · esperado · observado · resultado · responsável**. Em issues ou
prints compartilhados, omita nome, telefone e receita de clientes.

Consulte as [regras do Lentis](regras-negocio.md) para detalhes de baixas, caixa,
permissões e OS, e o [guia de backup local](../Lentis-backup-restauracao-LEIA-ME.md)
para o procedimento do Compose.
