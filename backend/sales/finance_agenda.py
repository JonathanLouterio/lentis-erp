"""Saldos em aberto por vencimento, sem confundir previsão com saldo bancário."""
from collections import defaultdict

from django.db.models import Case, CharField, Count, F, Q, Subquery, OuterRef, Sum, Value, When
from django.db.models.functions import Cast, Coalesce, Concat, NullIf
from django.db.models.fields.json import KeyTextTransform

from purchases.models import PayableInstallment, PayablePayment, PayablePlan
from .models import FinancialEntry, Receivable
from .dashboard_views import MONEY, ZERO, money

GROUPS = ('customer', 'operator', 'purchases', 'expenses')


def open_balances(query, settlements):
    # O saldo é calculado antes de agrupar/paginar para não multiplicar a parcela pelas baixas.
    settled = Coalesce(Subquery(settlements, output_field=MONEY), Value(ZERO), output_field=MONEY)
    return query.order_by().annotate(settled=settled).annotate(remaining=F('amount')-F('settled')).filter(remaining__gt=0)


def agenda_sources(store, due_dates):
    receipts = FinancialEntry.objects.filter(receivable=OuterRef('pk')).order_by().values('receivable').annotate(
        total=Sum(F('amount') + F('card_fee')),
    ).values('total')
    incoming = open_balances(
        Receivable.objects.filter(due_dates, payment__sale__store=store, payment__sale__status='completed'),
        receipts,
    )
    payouts = PayablePayment.objects.filter(installment=OuterRef('pk')).order_by().values('installment').annotate(
        total=Sum('amount'),
    ).values('total')
    outgoing = open_balances(
        PayableInstallment.objects.filter(PayablePlan.for_stores([store], 'plan__'), due_dates,
                                          plan__cancellation__isnull=True),
        payouts,
    )
    return incoming, outgoing


def prepare_agenda(store, values):
    from .report_services import col, metric

    incoming, outgoing = agenda_sources(store, Q(due_date__range=(values['start'], values['end'])))
    incoming = incoming.values('due_date').annotate(
        customer=Sum('remaining', filter=Q(debtor='customer')),
        operator=Sum('remaining', filter=Q(debtor='operator')),
    )
    outgoing = outgoing.values('due_date').annotate(
        purchases=Sum('remaining', filter=Q(plan__purchase__isnull=False)),
        expenses=Sum('remaining', filter=Q(plan__expense_store__isnull=False)),
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


def agenda_overdue_summary(store, today):
    incoming, outgoing = agenda_sources(store, Q(due_date__lt=today))

    def totals(query):
        result = query.aggregate(amount=Sum('remaining'), count=Count('pk'))
        return {'amount': money(result['amount'] or ZERO), 'count': result['count']}

    return {'incoming': totals(incoming), 'outgoing': totals(outgoing)}


def agenda_day_rows(store, day):
    incoming, outgoing = agenda_sources(store, Q(due_date=day))
    inbound_total = incoming.aggregate(total=Sum('remaining'))['total'] or ZERO
    outbound_total = outgoing.aggregate(total=Sum('remaining'))['total'] or ZERO
    fields = ['row_id','direction','group','document','party','number','original','settled_amount','remaining_amount','target_id','installment_id']
    incoming = incoming.annotate(
        row_id=Concat(Value('REC-'),Cast('pk',CharField())), target_id=F('pk'), installment_id=F('pk'),
        direction=Value('Entrada'), group=Case(When(debtor='operator',then=Value('Repasse de cartão')),default=Value('Cliente'),output_field=CharField()),
        document=Concat(Value('Venda #'),Cast('payment__sale_id',CharField())),
        party=Case(When(debtor='operator',then=Concat(Value('Operadora · '),F('payment__method_name'))),
                   default=Coalesce(NullIf('customer_name',Value('')),Value('Venda balcão')),output_field=CharField()),
        original=F('amount'),settled_amount=F('settled'),remaining_amount=F('remaining'),
    )
    outgoing = outgoing.annotate(
        row_id=Concat(Value('PAG-'),Cast('pk',CharField())), target_id=F('plan_id'), installment_id=F('pk'),
        direction=Value('Saída'), group=Case(When(plan__purchase__isnull=False,then=Value('Compra')),default=Value('Despesa'),output_field=CharField()),
        document=Case(When(plan__purchase__isnull=False,then=Concat(Value('Compra #'),Cast('plan__purchase_id',CharField()))),
                      default=Concat(Value('Despesa #'),Cast('plan_id',CharField())),output_field=CharField()),
        party=Coalesce(NullIf(KeyTextTransform('name','plan__purchase__supplier_snapshot'),Value('')),F('plan__purchase__supplier__name'),
                       NullIf('plan__expense_payee',Value('')),F('plan__expense_description'),output_field=CharField()),
        original=F('amount'),settled_amount=F('settled'),remaining_amount=F('remaining'),
    )
    rows = incoming.values(*fields).union(outgoing.values(*fields),all=True).order_by('direction','row_id')
    return rows, inbound_total, outbound_total
