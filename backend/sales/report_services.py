"""Relatórios de leitura; vendas, lançamentos e saldos têm bases distintas."""
from django.db.models import Case, When, Value, CharField, F, ExpressionWrapper, Count, Sum, Q
from django.db.models.functions import Coalesce, Concat, Cast, NullIf, TruncDate
from django.db.models.fields.json import KeyTextTransform
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from purchases.models import PayableInstallment, PayablePayment
from .insight_permissions import report_allowed
from .models import FinancialAccount, FinancialEntry, Receivable
from .dashboard_views import BUSINESS_TZ, MONEY, ZERO, bounds, money, sales_for

REPORTS = {
    'sales': {'title': 'Vendas finalizadas', 'permissions': ('sales.view_sale',), 'basis': 'Data de finalização', 'description': 'Vendas que continuam finalizadas, pelo dia de finalização em São Paulo. Rascunhos e vendas canceladas são excluídos. Os valores já incluem os descontos registrados.'},
    'movements': {'title': 'Movimentações registradas', 'permissions': ('sales.view_financialentry', 'purchases.view_payableplan'), 'basis': 'Data de registro', 'description': 'Recebimentos, pagamentos a fornecedores e seus estornos pela data de registro em São Paulo. A data informada do pagamento aparece em outra coluna. Não inclui abertura, suprimento ou retirada manual de caixa, nem representa lucro ou extrato bancário.'},
    'receivables': {'title': 'Contas a receber', 'permissions': ('sales.view_receivable',), 'basis': 'Vencimento · saldo atual', 'description': 'Parcelas com vencimento no período e situação atual, incluindo recebimentos posteriores ao período. Não é um saldo histórico na data final. Vendas canceladas são excluídas. O responsável distingue cliente e operadora de cartão.'},
    'payables': {'title': 'Contas a pagar', 'permissions': ('purchases.view_payableplan',), 'basis': 'Vencimento · saldo atual', 'description': 'Parcelas de compras com vencimento no período e situação atual, incluindo pagamentos posteriores ao período. Não é um saldo histórico na data final. Somente compras com plano de contas a pagar gerado aparecem.'},
}


class ReportInput(serializers.Serializer):
    report = serializers.ChoiceField(choices=list(REPORTS), default='sales')
    start = serializers.DateField(required=False)
    end = serializers.DateField(required=False)
    status = serializers.ChoiceField(choices=['all', 'pending', 'paid', 'overdue'], default='pending')
    debtor = serializers.ChoiceField(choices=['all', 'customer', 'operator'], default='all')
    direction = serializers.ChoiceField(choices=['all', 'in', 'out'], default='all')
    account_id = serializers.IntegerField(min_value=1, max_value=9223372036854775807, required=False)
    page = serializers.IntegerField(min_value=1, required=False)
    page_size = serializers.IntegerField(min_value=1, max_value=100, required=False)
    export = serializers.ChoiceField(choices=['csv'], required=False)


def available_reports(user):
    return [dict(key=key, title=spec['title'], basis=spec['basis']) for key, spec in REPORTS.items() if report_allowed(user,spec['permissions'])]


def parse_filters(request, store, now):
    serializer = ReportInput(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data
    spec = REPORTS[values['report']]
    if not report_allowed(request.user,spec['permissions']):
        raise PermissionDenied('Seu usuário não tem as permissões de consulta exigidas por este relatório.')
    if values.get('export')=='csv' and not request.user.has_perm('sales.export_reports'):
        raise PermissionDenied('Seu usuário não tem permissão de exportar relatórios.')
    today = timezone.localtime(now, BUSINESS_TZ).date()
    if ('start' in values) != ('end' in values):
        raise ValidationError('Informe as datas inicial e final juntas.')
    start = values.get('start', today.replace(day=1))
    end = values.get('end', today)
    if start > end or (end-start).days > 365:
        raise ValidationError('Escolha um período de até 366 dias, com início anterior ou igual ao fim.')
    try:
        lower, upper = bounds(start, end)
    except (ValueError, OverflowError) as exc:
        raise ValidationError('O período ultrapassa o limite de datas suportado.') from exc
    values.update(start=start, end=end)
    account_id = values.get('account_id')
    if values['report'] == 'movements' and account_id and not FinancialAccount.objects.filter(pk=account_id, store=store).exists():
        raise ValidationError('Selecione uma conta da unidade do relatório.')
    return values, today, lower, upper


def col(key, label, kind='text'):
    return {'key': key, 'label': label, 'kind': kind}


def metric(key, label, value, kind='money'):
    return {'key': key, 'label': label, 'value': str(value) if kind=='integer' else money(value), 'kind': kind}


def totals(queryset, field):
    return queryset.aggregate(count=Count('pk'), total=Sum(field))


def installment_rows(queryset, values, today, incoming):
    relation = 'entries__amount' if incoming else 'payments__amount'
    query = queryset.filter(due_date__range=(values['start'], values['end'])).annotate(
        report_paid=Coalesce(Sum(relation), Value(ZERO), output_field=MONEY),
    ).annotate(report_remaining=ExpressionWrapper(F('amount')-F('report_paid'), output_field=MONEY))
    state=values['status']
    if state=='pending': query=query.filter(report_remaining__gt=0)
    elif state=='paid': query=query.filter(report_remaining=0)
    elif state=='overdue': query=query.filter(report_remaining__gt=0, due_date__lt=today)
    return query


def prepare_report(store, values, now, today, lower, upper):
    """Retorna QuerySet paginável e resumo dos mesmos filtros, sem gravar dados."""
    kind=values['report']
    columns=[col('unit', 'Unidade')]
    if kind=='sales':
        query=sales_for(store).filter(completed_at__gte=lower, completed_at__lt=upper, completed_at__lte=now).select_related('customer','created_by').order_by('-completed_at','-pk')
        sums=totals(query,'dashboard_total');count=sums['count'];total=sums['total'] or ZERO
        summary=[metric('count','Vendas finalizadas',count,'integer'),metric('total','Total vendido',total),metric('ticket','Ticket médio',total/count if count else ZERO)]
        columns += [col('id','Venda'),col('date','Finalizada em (São Paulo)','datetime'),col('party','Cliente'),col('author','Usuário da venda'),col('amount','Total da venda','money')]
    elif kind=='movements':
        query, summary=movement_rows(store,values,now,lower,upper)
        columns += [col('id','Lançamento'),col('date','Registrado em (São Paulo)','datetime'),col('paid_on','Data do pagamento / recebimento','date'),col('direction','Direção'),col('type','Tipo'),col('document','Documento'),col('party','Cliente / fornecedor / operadora'),col('account','Conta'),col('method','Forma'),col('author','Registrado por'),col('amount','Valor assinado','money'),col('reason','Referência / motivo')]
    else:
        if kind=='receivables':
            query=Receivable.objects.filter(payment__sale__store=store,payment__sale__status='completed')
            if values['debtor']!='all':query=query.filter(debtor=values['debtor'])
            query=installment_rows(query,values,today,True).select_related('payment')
        else:
            query=installment_rows(PayableInstallment.objects.filter(plan__purchase__store=store),values,today,False).select_related('plan__purchase__supplier')
        sums=query.aggregate(count=Count('pk'),original=Sum('amount'),paid=Sum('report_paid'),remaining=Sum('report_remaining'),overdue=Sum('report_remaining',filter=Q(due_date__lt=today,report_remaining__gt=0)))
        summary=[metric('count','Parcelas no filtro',sums['count'],'integer'),metric('original','Valor original',sums['original']),metric('paid','Recebido líquido' if kind=='receivables' else 'Pago líquido',sums['paid']),metric('remaining','Saldo em aberto',sums['remaining']),metric('overdue','Saldo vencido',sums['overdue'])]
        columns += [col('id','Parcela'),col('document','Venda' if kind=='receivables' else 'Compra'),col('number','Número','integer'),col('party','Cliente' if kind=='receivables' else 'Fornecedor')]
        if kind=='receivables':columns += [col('debtor','Responsável')]
        columns += [col('due_date','Vencimento','date'),col('amount','Valor original','money'),col('paid','Recebido líquido' if kind=='receivables' else 'Pago líquido','money'),col('remaining','Saldo atual','money'),col('status','Situação atual')]
        query=query.order_by('due_date','pk')
    return query, columns, summary


def movement_rows(store,values,now,lower,upper):
    receipts=FinancialEntry.objects.filter(receivable__payment__sale__store=store,created_at__gte=lower,created_at__lt=upper,created_at__lte=now)
    payouts=PayablePayment.objects.filter(installment__plan__purchase__store=store,created_at__gte=lower,created_at__lt=upper,created_at__lte=now)
    if values.get('account_id'):
        receipts=receipts.filter(account_id=values['account_id']);payouts=payouts.filter(account_id=values['account_id'])
    common={'r_date':F('created_at'),'r_author':F('created_by__username'),'r_reason':F('reason')}
    receipts=receipts.annotate(**common,r_id=Concat(Value('REC-'),Cast('pk',CharField())),r_paid_on=TruncDate('created_at',tzinfo=BUSINESS_TZ),r_type=Case(When(amount__gt=0,then=Value('Recebimento de cliente / operadora')),default=Value('Estorno de recebimento')),
        r_document=Concat(Value('Venda #'),Cast('receivable__payment__sale_id',CharField())),
        r_party=Case(When(receivable__debtor='operator',then=Concat(Value('Operadora · '),F('receivable__payment__method_name'))),default=Coalesce(NullIf('receivable__customer_name',Value('')),Value('Venda balcão')),output_field=CharField()),
        r_account=F('account__name'),r_method=F('method__name'),r_amount=ExpressionWrapper(F('amount'),output_field=MONEY))
    payouts=payouts.annotate(**common,r_id=Concat(Value('PAG-'),Cast('pk',CharField())),r_paid_on=F('paid_on'),r_type=Case(When(amount__gt=0,then=Value('Pagamento a fornecedor')),default=Value('Estorno de pagamento a fornecedor')),
        r_document=Concat(Value('Compra #'),Cast('installment__plan__purchase_id',CharField())),
        r_party=Coalesce(NullIf(KeyTextTransform('name','installment__plan__purchase__supplier_snapshot'),Value('')),F('installment__plan__purchase__supplier__name'),output_field=CharField()),
        r_account=F('account_name'),r_method=F('method_name'),r_amount=ExpressionWrapper(-F('amount'),output_field=MONEY))
    if values['direction']!='all':
        condition={'r_amount__gt':0} if values['direction']=='in' else {'r_amount__lt':0}
        receipts=receipts.filter(**condition);payouts=payouts.filter(**condition)
    aggregations={'count':Count('pk'),'incoming':Sum('r_amount',filter=Q(r_amount__gt=0)),'outgoing':Sum('r_amount',filter=Q(r_amount__lt=0))}
    a=receipts.aggregate(**aggregations);b=payouts.aggregate(**aggregations)
    incoming=(a['incoming'] or ZERO)+(b['incoming'] or ZERO)
    outgoing=-((a['outgoing'] or ZERO)+(b['outgoing'] or ZERO))
    summary=[metric('count','Lançamentos',a['count']+b['count'],'integer'),metric('incoming','Entradas registradas',incoming),metric('outgoing','Saídas registradas',outgoing),metric('net','Variação líquida registrada',incoming-outgoing)]
    fields=['r_id','r_date','r_paid_on','r_type','r_document','r_party','r_account','r_method','r_author','r_amount','r_reason']
    query=receipts.order_by().values(*fields).union(payouts.order_by().values(*fields),all=True).order_by('-r_date','r_id')
    return query,summary


def serialize_row(obj,kind,store,today):
    row={'unit':f'{store.code} — {store.name}'}
    if kind=='sales':
        row.update(id=f'#{obj.pk}',date=obj.completed_at.isoformat(),party=obj.customer.name if obj.customer_id else 'Venda balcão',author=obj.created_by.username,amount=money(obj.dashboard_total))
    elif kind=='movements':
        row.update(id=obj['r_id'],date=obj['r_date'].isoformat(),paid_on=obj['r_paid_on'].isoformat(),type=obj['r_type'],document=obj['r_document'],party=obj['r_party'],account=obj['r_account'],method=obj['r_method'],author=obj['r_author'],amount=money(obj['r_amount']),direction='Entrada' if obj['r_amount']>0 else 'Saída',reason=obj['r_reason'])
    else:
        remaining=obj.report_remaining;paid=obj.report_paid
        row.update(id=f'#{obj.pk}',number=str(obj.number),due_date=obj.due_date.isoformat(),amount=money(obj.amount),paid=money(paid),remaining=money(remaining),status='Quitada' if remaining==0 else 'Vencida' if obj.due_date<today else 'Paga parcialmente' if paid>0 else 'Em aberto')
        if kind=='receivables':row.update(document=f'#{obj.payment.sale_id}',party=obj.customer_name or 'Venda balcão',debtor=obj.get_debtor_display())
        else:
            purchase=obj.plan.purchase
            row.update(document=f'#{purchase.pk}',party=purchase.supplier_snapshot.get('name') or purchase.supplier.name)
    return row
