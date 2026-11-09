"""Filtros compartilhados entre as filas de trabalho e o painel inicial."""
from zoneinfo import ZoneInfo

from django.db.models import OuterRef, Q, Subquery
from django.utils import timezone

from .quote_models import FOLLOWUP_EVENTS, Quote, QuoteEvent
from .work_order_models import ServiceOrder


ACTIVE_ORDERS = ~Q(status__in=(ServiceOrder.Status.DELIVERED, ServiceOrder.Status.CANCELLED))
READY_FOR_PICKUP = Q(status=ServiceOrder.Status.READY, sale__status='completed')


def order_today():
    return timezone.localdate(timezone=ZoneInfo('America/Sao_Paulo'))


def overdue_orders(today):
    return ACTIVE_ORDERS & Q(promised_on__lt=today)


def with_quote_schedule(queryset):
    schedule = QuoteEvent.objects.filter(
        quote_id=OuterRef('pk'), action__in=FOLLOWUP_EVENTS,
    ).order_by('-version', '-pk')
    return queryset.annotate(next_contact_on=Subquery(schedule.values('next_contact_on')[:1]))


def due_quotes(queryset, store, today):
    return queryset.filter(
        status=Quote.Status.SENT, customer__is_active=True, customer__store=store, next_contact_on__lte=today,
    )
