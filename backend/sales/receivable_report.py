"""Carteira a receber: consulta atual por vencimento, sem movimentar valores."""
from datetime import timedelta
from django.db.models import Count, Sum, Q, F, Value, ExpressionWrapper
from django.db.models.functions import Coalesce
from .models import Receivable
from .dashboard_views import MONEY, ZERO, money

RISK_LABELS = {
    'within': 'Dentro do prazo', 'soon': 'A vencer', 'overdue': 'Vencido',
    'critical': 'Acima de 90 dias', 'paid': 'Quitada',
}
RISK_TONES = {'within': 'green', 'soon': 'yellow', 'overdue': 'red', 'critical': 'black', 'paid': 'gray'}
AGE_LABELS = {'1_30': '1 a 30 dias', '31_60': '31 a 60 dias', '61_90': '61 a 90 dias', 'over_90': 'Acima de 90 dias'}


def risk_conditions(today, warning_days):
    future = today + timedelta(days=warning_days)
    open_balance = Q(report_remaining__gt=0)
    return {
        'within': open_balance & Q(due_date__gt=future),
        'soon': open_balance & Q(due_date__gte=today, due_date__lte=future),
        'overdue': open_balance & Q(due_date__lt=today, due_date__gte=today-timedelta(days=90)),
        'critical': open_balance & Q(due_date__lt=today-timedelta(days=90)),
        'paid': Q(report_remaining__lte=0),
    }


def aging_conditions(today):
    return {
        '1_30': Q(due_date__lt=today, due_date__gte=today-timedelta(days=30)),
        '31_60': Q(due_date__lt=today-timedelta(days=30), due_date__gte=today-timedelta(days=60)),
        '61_90': Q(due_date__lt=today-timedelta(days=60), due_date__gte=today-timedelta(days=90)),
        'over_90': Q(due_date__lt=today-timedelta(days=90)),
    }


def classify(due_date, remaining, today, warning_days):
    if remaining <= 0:
        return 'paid', 0, ''
    days = (today-due_date).days
    if days > 90: return 'critical', days, 'over_90'
    if days > 0: return 'overdue', days, '1_30' if days <= 30 else '31_60' if days <= 60 else '61_90'
    return ('soon' if -days <= warning_days else 'within'), 0, ''


def receivable_query(store, values, today):
    query = Receivable.objects.filter(payment__sale__store=store, payment__sale__status='completed')
    if not values.get('all_dates'):
        query = query.filter(due_date__range=(values['start'], values['end']))
    if values['debtor'] != 'all': query = query.filter(debtor=values['debtor'])
    if values.get('customer'):
        query = query.filter(customer_name__icontains=values['customer'])
    if values.get('sale_id'): query = query.filter(payment__sale_id=values['sale_id'])
    if values.get('method', 'all') != 'all': query = query.filter(payment__kind=values['method'])
    # Só há um relacionamento de valores no SUM; os demais filtros são da própria parcela/venda.
    query = query.annotate(report_paid=Coalesce(Sum('entries__amount'), Value(ZERO), output_field=MONEY))
    query = query.annotate(report_remaining=ExpressionWrapper(F('amount')-F('report_paid'), output_field=MONEY))
    state = values['status']
    if state == 'pending': query = query.filter(report_remaining__gt=0)
    elif state == 'paid': query = query.filter(report_remaining=0)
    elif state == 'partial': query = query.filter(report_remaining__gt=0, report_paid__gt=0)
    elif state == 'overdue': query = query.filter(report_remaining__gt=0, due_date__lt=today)
    risk = values.get('risk', 'all')
    if risk != 'all': query = query.filter(risk_conditions(today, values.get('warning_days',7))[risk])
    age = values.get('aging', 'all')
    if age != 'all': query = query.filter(report_remaining__gt=0).filter(aging_conditions(today)[age])
    return query.select_related('payment', 'payment__account').order_by('due_date','pk')


def prepare_receivables(store, values, today):
    from .report_services import col, metric
    query = receivable_query(store, values, today)
    risk = risk_conditions(today, values.get('warning_days',7))
    sums = query.aggregate(
        count=Count('pk'), original=Sum('amount'), paid=Sum('report_paid'),
        remaining=Sum('report_remaining'), overdue=Sum('report_remaining', filter=Q(due_date__lt=today, report_remaining__gt=0)),
        soon=Sum('report_remaining',filter=risk['soon']), within=Sum('report_remaining',filter=risk['within']),
        critical=Sum('report_remaining',filter=risk['critical']),
    )
    summary = [metric('count','Parcelas no filtro',sums['count'],'integer'), metric('original','Valor original',sums['original']),
        metric('paid','Recebido líquido',sums['paid']), metric('remaining','Saldo em aberto',sums['remaining']),
        metric('within','Dentro do prazo',sums['within']), metric('soon','A vencer',sums['soon']),
        metric('overdue','Total vencido',sums['overdue']), metric('critical','Acima de 90 dias',sums['critical'])]
    columns = [col('unit','Unidade'), col('id','Parcela'), col('document','Venda'), col('number','Número','integer'),
        col('party','Cliente registrado'), col('debtor','Responsável'), col('method','Forma de pagamento'),
        col('due_date','Vencimento','date'), col('amount','Valor original','money'), col('paid','Recebido líquido','money'),
        col('remaining','Saldo atual','money'), col('status','Recebimento'), col('risk_label','Prazo'),
        col('days_overdue','Dias em atraso','integer'), col('aging_label','Faixa de atraso')]
    return query, columns, summary


def aging_summary(query, today):
    aggregations = {}
    for key, condition in aging_conditions(today).items():
        condition &= Q(report_remaining__gt=0)
        aggregations['count_'+key] = Count('pk',filter=condition)
        aggregations['amount_'+key] = Sum('report_remaining',filter=condition)
    result = query.aggregate(**aggregations)
    return [{'key': key, 'label': label, 'count': result['count_'+key], 'amount': money(result['amount_'+key]),
             'tone': 'black' if key=='over_90' else 'red'} for key,label in AGE_LABELS.items()]


def decorate_row(row, obj, today, warning_days):
    risk, days, age = classify(obj.due_date, obj.report_remaining, today, warning_days)
    row.update(method=obj.payment.method_name, risk=risk, tone=RISK_TONES[risk], risk_label=RISK_LABELS[risk],
        days_overdue=str(days), aging_label=AGE_LABELS.get(age,''),
        status='Quitada' if obj.report_remaining<=0 else 'Paga parcialmente' if obj.report_paid>0 else 'Em aberto')
    return row
