"""Saldos em aberto por vencimento, sem confundir previsão com saldo bancário."""
from collections import defaultdict

from django.db.models import F, Q, Subquery, OuterRef, Sum, Value
from django.db.models.functions import Coalesce

from purchases.models import PayableInstallment, PayablePayment, PayablePlan
from .models import FinancialEntry, Receivable
from .dashboard_views import MONEY, ZERO

GROUPS = ('customer', 'operator', 'purchases', 'expenses')


def grouped_balances(query, settlements, **groups):
    # A subconsulta calcula o saldo de cada parcela antes de agrupar por data.
    # Assim várias baixas na mesma parcela não multiplicam o valor original.
    remaining = F('amount') - Coalesce(Subquery(settlements, output_field=MONEY), Value(ZERO), output_field=MONEY)
    return query.order_by().annotate(remaining=remaining).filter(remaining__gt=0).values('due_date').annotate(
        **{name: Sum('remaining', filter=condition) for name, condition in groups.items()},
    )


def prepare_agenda(store, values):
    from .report_services import col, metric

    period = (values['start'], values['end'])
    receipts = FinancialEntry.objects.filter(receivable=OuterRef('pk')).order_by().values('receivable').annotate(
        settled=Sum(F('amount') + F('card_fee')),
    ).values('settled')
    incoming = grouped_balances(
        Receivable.objects.filter(payment__sale__store=store, payment__sale__status='completed', due_date__range=period),
        receipts, customer=Q(debtor='customer'), operator=Q(debtor='operator'),
    )
    payouts = PayablePayment.objects.filter(installment=OuterRef('pk')).order_by().values('installment').annotate(
        settled=Sum('amount'),
    ).values('settled')
    outgoing = grouped_balances(
        PayableInstallment.objects.filter(PayablePlan.for_stores([store], 'plan__'),
                                          plan__cancellation__isnull=True, due_date__range=period),
        payouts, purchases=Q(plan__purchase__isnull=False), expenses=Q(plan__expense_store__isnull=False),
    )
    by_date = defaultdict(dict)
    for group in (incoming, outgoing):
        for row in group:
            day = row.pop('due_date')
            by_date[day].update(row)

    rows = []
    totals = dict.fromkeys(GROUPS, ZERO)
    for day, daily in sorted(by_date.items()):
        amounts = {key: daily.get(key) or ZERO for key in GROUPS}
        for key, amount in amounts.items():
            totals[key] += amount
        rows.append({'due_date': day, **amounts,
                     'net': amounts['customer'] + amounts['operator'] - amounts['purchases'] - amounts['expenses']})

    expected_in = totals['customer'] + totals['operator']
    expected_out = totals['purchases'] + totals['expenses']
    summary = [metric('incoming', 'Entradas previstas', expected_in), metric('outgoing', 'Saídas previstas', expected_out),
               metric('net', 'Diferença prevista', expected_in - expected_out)]
    columns = [col('unit', 'Unidade'), col('due_date', 'Vencimento', 'date'),
               col('customer', 'A receber de clientes', 'money'), col('operator', 'Repasses de cartão', 'money'),
               col('purchases', 'Compras a pagar', 'money'), col('expenses', 'Despesas a pagar', 'money'),
               col('net', 'Diferença prevista', 'money')]
    return rows, columns, summary
