"""Indicadores operacionais: vendas, recebimentos e dinheiro físico separados."""
from datetime import datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum, Value, OuterRef, Subquery
from django.db.models.functions import Coalesce, Round, TruncDate
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from organizations.models import Product
from .models import CashSession, FinancialEntry, Receivable, Sale, SaleItem
from .views import SalesBaseView

BUSINESS_TZ = ZoneInfo('America/Sao_Paulo')
MONEY = DecimalField(max_digits=28, decimal_places=2)
ZERO = Decimal('0')


def money(value):
    return f'{(value or ZERO).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP):.2f}'


def bounds(start, end):
    return datetime.combine(start, time.min, tzinfo=BUSINESS_TZ), datetime.combine(end + timedelta(days=1), time.min, tzinfo=BUSINESS_TZ)


def period_for(params, today):
    preset = params.get('preset', 'today')
    if preset == 'today': start = end = today
    elif preset == '7days': start, end = today - timedelta(days=6), today
    elif preset == 'month': start, end = today.replace(day=1), today
    elif preset == 'custom':
        start = serializers.DateField().run_validation(params.get('start'))
        end = serializers.DateField().run_validation(params.get('end'))
    else: raise ValidationError({'preset': 'Selecione today, 7days, month ou custom.'})
    if start > end or (end - start).days > 365:
        raise ValidationError({'period': 'Escolha um período de até 366 dias, com início anterior ou igual ao fim.'})
    try:
        previous_end = start - timedelta(days=1)
        previous_start = previous_end - (end - start)
        bounds(start, end); bounds(previous_start, previous_end)
    except (OverflowError, ValueError):
        raise ValidationError({'period': 'Os limites de data não permitem calcular este período.'})
    return preset, start, end, previous_start, previous_end


def sales_for(store):
    # Total de cada venda em uma subconsulta: pagamentos não multiplicam itens.
    line = Round(ExpressionWrapper(F('quantity') * F('unit_price'), output_field=DecimalField(max_digits=28, decimal_places=5)), 2) - F('discount_amount')
    totals = SaleItem.objects.filter(sale_id=OuterRef('pk')).values('sale_id').annotate(value=Sum(line, output_field=MONEY)).values('value')
    return Sale.objects.filter(store=store, status='completed').annotate(
        dashboard_total=ExpressionWrapper(Coalesce(Subquery(totals, output_field=MONEY), Value(ZERO), output_field=MONEY) - F('discount_amount'), output_field=MONEY),
    )


def sales_stats(queryset, start, end):
    lower, upper = bounds(start, end)
    rows = list(queryset.filter(completed_at__gte=lower, completed_at__lt=upper).annotate(day=TruncDate('completed_at', tzinfo=BUSINESS_TZ)).values('day').annotate(count=Count('pk'), total=Sum('dashboard_total')).order_by('day'))
    by_day = {row['day'].isoformat(): (row['count'], row['total']) for row in rows}
    total = sum((row['total'] for row in rows), ZERO)
    count = sum(row['count'] for row in rows)
    return {'count': count, 'total': money(total), 'ticket': money(total / count if count else ZERO)}, by_day


class DashboardView(SalesBaseView):
    def get(self, request):
        store = self._selected_store()
        now = timezone.now()
        today = timezone.localtime(now, BUSINESS_TZ).date()
        preset, start, end, previous_start, previous_end = period_for(request.query_params, today)
        lower, upper = bounds(start, end)
        sales = sales_for(store)
        current, daily = sales_stats(sales, start, end)
        previous, _ = sales_stats(sales, previous_start, previous_end)
        previous_total = Decimal(previous['total'])
        variation = money((Decimal(current['total']) - previous_total) * 100 / previous_total) if previous_total else None

        entries = FinancialEntry.objects.filter(receivable__payment__sale__store=store)
        selected_entries = entries.filter(created_at__gte=lower, created_at__lt=upper)
        receipts = selected_entries.aggregate(gross=Sum('amount', filter=Q(amount__gt=0)), refunds=Sum('amount', filter=Q(amount__lt=0)))
        gross, refunds = receipts['gross'] or ZERO, -(receipts['refunds'] or ZERO)
        entry_days = {row['day'].isoformat(): row['amount'] for row in selected_entries.annotate(day=TruncDate('created_at', tzinfo=BUSINESS_TZ)).values('day').annotate(amount=Sum('amount')).order_by('day')}
        chart = []
        for index in range((end - start).days + 1):
            day = (start + timedelta(days=index)).isoformat()
            chart.append({'date': day, 'sales_count': daily.get(day, (0, ZERO))[0], 'sales': money(daily.get(day, (0, ZERO))[1]), 'received': money(entry_days.get(day, ZERO))})

        # Estado atual das parcelas: exclui vendas canceladas e conta o saldo
        # parcial, sem multiplicar os valores pela quantidade de recebimentos.
        pending = Receivable.objects.filter(payment__sale__store=store, payment__sale__status='completed').annotate(
            remaining=ExpressionWrapper(F('amount') - Coalesce(Sum('entries__amount'), Value(ZERO), output_field=MONEY), output_field=MONEY),
        ).filter(remaining__gt=0)
        def balance(query):
            result = query.aggregate(count=Count('pk'), amount=Sum('remaining'))
            return {'count': result['count'], 'amount': money(result['amount'])}
        customer = pending.filter(debtor='customer')
        operator = pending.filter(debtor='operator')
        overdue = customer.filter(due_date__lt=today)
        due_today = customer.filter(due_date=today)
        next_due = [
            {'id': item.pk, 'sale_id': item.payment.sale_id, 'customer_name': item.customer_name, 'due_date': item.due_date.isoformat(), 'remaining': money(item.remaining), 'overdue': item.due_date < today}
            for item in customer.filter(due_date__lte=today).select_related('payment').order_by('due_date', 'pk')[:5]
        ]
        products = Product.objects.filter(store=store, is_active=True)
        low = products.filter(stock_quantity__lte=F('minimum_stock'))
        low_rows = [{'id': item.pk, 'name': item.name, 'code': item.internal_code, 'quantity': str(item.stock_quantity), 'minimum': str(item.minimum_stock)} for item in low.order_by('stock_quantity', 'pk')[:5]]
        cash = CashSession.objects.filter(account__store=store, closed_at__isnull=True).annotate(
            dashboard_balance=ExpressionWrapper(F('opening_amount') + Coalesce(Sum('postings__amount'), Value(ZERO), output_field=MONEY), output_field=MONEY),
        )
        cash_summary = cash.aggregate(count=Count('pk'), amount=Sum('dashboard_balance'))
        cash_rows = [{'id': item.pk, 'account_name': item.account.name, 'owner': item.opened_by.username, 'opened_at': item.opened_at.isoformat(), 'expected_cash': money(item.dashboard_balance)} for item in cash.select_related('account', 'opened_by').order_by('-opened_at', '-pk')[:5]]
        recent = [{'id': item.pk, 'customer_name': item.customer.name if item.customer_id else 'Venda balcão', 'completed_at': item.completed_at.isoformat(), 'total': money(item.dashboard_total)} for item in sales.filter(completed_at__gte=lower, completed_at__lt=upper).select_related('customer').order_by('-completed_at', '-pk')[:5]]
        return Response({
            'store_id': store.pk, 'generated_at': now.isoformat(), 'today': today.isoformat(), 'timezone': 'America/Sao_Paulo',
            'period': {'preset': preset, 'start': start.isoformat(), 'end': end.isoformat(), 'previous_start': previous_start.isoformat(), 'previous_end': previous_end.isoformat()},
            'sales': {**current, 'previous_total': previous['total'], 'previous_count': previous['count'], 'variation': variation},
            'receipts': {'gross': money(gross), 'refunds': money(refunds), 'net': money(gross - refunds)},
            'receivables': {'customer': balance(customer), 'operator': balance(operator), 'overdue': balance(overdue), 'due_today': balance(due_today), 'attention': next_due},
            'stock': {'low_count': low.count(), 'negative_count': products.filter(stock_quantity__lt=0).count(), 'items': low_rows},
            'cash': {'count': cash_summary['count'], 'expected_cash': money(cash_summary['amount']), 'items': cash_rows},
            'chart': chart, 'recent_sales': recent,
        })
