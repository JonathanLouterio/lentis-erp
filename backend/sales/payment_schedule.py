"""Calendário de parcelas sem gravação, compartilhado pela prévia e conclusão."""
import calendar
from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError


def schedule(amount, count, first_date, interval_unit='months', interval_count=1):
    if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 12:
        raise ValidationError({'installment_count': 'Informe de 1 a 12 parcelas.'})
    if interval_unit not in ('months', 'days'):
        raise ValidationError({'interval_unit': 'Selecione meses ou dias.'})
    maximum = 12 if interval_unit == 'months' else 365
    if not isinstance(interval_count, int) or isinstance(interval_count, bool) or not 1 <= interval_count <= maximum:
        raise ValidationError({'interval_count': f'Informe um intervalo de 1 a {maximum} {"meses" if interval_unit == "months" else "dias"}.'})
    if not isinstance(first_date, date):
        raise ValidationError({'first_due_date': 'Informe uma data válida.'})
    if not isinstance(amount, Decimal) or not amount.is_finite() or amount <= 0 or amount != amount.quantize(Decimal('0.01')):
        raise ValidationError({'amount': 'Informe um valor positivo com até duas casas decimais.'})
    cents = int(amount * 100)
    if cents < count:
        raise ValidationError({'amount': 'Cada parcela deve ter pelo menos um centavo.'})
    base, remainder = divmod(cents, count)
    result = []
    for index in range(count):
        try:
            if interval_unit == 'days':
                due = first_date + timedelta(days=index * interval_count)
            else:
                month_index = first_date.year * 12 + first_date.month - 1 + index * interval_count
                year, month = divmod(month_index, 12)
                month += 1
                day = min(first_date.day, calendar.monthrange(year, month)[1])
                due = date(year, month, day)
        except (ValueError, OverflowError):
            raise ValidationError({'first_due_date': 'Os vencimentos ultrapassam o limite de datas.'})
        result.append((due, Decimal(base + (index < remainder)) / 100))
    return result


def validate_terms(method, amount, count, first_date, interval_unit, interval_count, confirmed):
    if count > method.installment_limit:
        raise ValidationError({'installment_count': f'{method.name} permite no máximo {method.installment_limit} parcela(s). Atualize as condições de pagamento.'})
    if confirmed and method.kind not in ('cash', 'pix', 'transfer'):
        raise ValidationError({'confirmed': 'Cartão, boleto e crediário são registrados como valores a receber.'})
    return schedule(amount, count, first_date, interval_unit, interval_count)
