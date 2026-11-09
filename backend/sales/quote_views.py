from rest_framework.permissions import IsAuthenticated
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from .quote_permissions import QuoteActionPermission
import hashlib
import json
from django.shortcuts import get_object_or_404
from django.db.models import Count, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from .models import Quote, QuoteEvent
from .quote_models import FOLLOWUP_EVENTS, QuoteLossCategory, quote_today
from .quote_serializers import (
    QuoteActionSerializer, QuoteFollowupSerializer, QuoteRejectSerializer, QuoteSerializer, QuoteWriteSerializer,
)
from .quote_services import operate_quote
from .views import SalesBaseView, SalesPagination, model_errors


def quote_queryset(store):
    schedule = QuoteEvent.objects.filter(quote_id=OuterRef('pk'), action__in=FOLLOWUP_EVENTS).order_by('-version','-pk')
    loss = QuoteEvent.objects.filter(quote_id=OuterRef('pk'), action='reject').order_by('-version','-pk')
    return Quote.objects.filter(store=store).select_related('customer','created_by').prefetch_related(
        'items','events__created_by',
    ).annotate(
        next_contact_on=Subquery(schedule.values('next_contact_on')[:1]),
        loss_category=Coalesce(Subquery(loss.values('loss_category')[:1]), Value('')),
    )


@method_decorator(never_cache,name="dispatch")
class QuoteBaseView(SalesBaseView):
    permission_classes=[IsAuthenticated,QuoteActionPermission]

    def operate(self, request, action, quote_id=None):
        store = self._selected_store()
        if not isinstance(request.data, dict): raise ValidationError('Envie os dados do orçamento em um objeto JSON.')
        request_id = serializers.UUIDField().run_validation(request.data.get('request_id'))
        digest = hashlib.sha256(json.dumps({'action': action, 'quote_id': quote_id, 'body': request.data}, sort_keys=True, ensure_ascii=False, separators=(',',':')).encode('utf-8')).hexdigest()
        def validated():
            cls = {'save': QuoteWriteSerializer, 'followup': QuoteFollowupSerializer, 'reject': QuoteRejectSerializer}.get(action, QuoteActionSerializer)
            return self.write_serializer(cls, request.data, store).validated_data
        with model_errors():
            quote = operate_quote(user=request.user, store=store, quote_id=quote_id, action=action, request_id=request_id, digest=digest, validated_values=validated)
        return Response(QuoteSerializer(quote_queryset(store).get(pk=quote.pk),context={"request":request}).data)


class QuotesView(QuoteBaseView):
    quote_actions={"GET":"view","POST":"add"}

    def get(self, request):
        store = self._selected_store()
        queryset = quote_queryset(store)
        today = quote_today()
        state = request.query_params.get('status', 'all')
        if state == 'expired':
            queryset = queryset.filter(valid_until__lt=today).exclude(status__in=['converted','rejected'])
        elif state in Quote.Status.values: queryset = queryset.filter(status=state)
        elif state != 'all': raise ValidationError({'status': 'Selecione uma situação válida.'})
        followup = request.query_params.get('followup')
        if followup == 'due':
            queryset = queryset.filter(status=Quote.Status.SENT, customer__is_active=True, customer__store=store,
                                       next_contact_on__lte=today).order_by('next_contact_on','pk')
        elif followup is not None:
            raise ValidationError({'followup': 'Filtro de retorno inválido.'})
        loss_filter = request.query_params.get('loss')
        if loss_filter is not None and (state != Quote.Status.REJECTED or followup is not None
                                        or loss_filter not in ('uncategorized', *QuoteLossCategory.values)):
            raise ValidationError({'loss': 'Selecione uma categoria válida na lista de orçamentos recusados.'})
        summary = None
        if state == Quote.Status.REJECTED and followup is None:
            counts = {row['loss_category']: row['count'] for row in queryset.order_by().values('loss_category').annotate(count=Count('pk'))}
            summary = [{'category': category, 'count': counts.get(category, 0)}
                       for category in (*QuoteLossCategory.values, '')]
            if loss_filter is not None:
                queryset = queryset.filter(loss_category='' if loss_filter == 'uncategorized' else loss_filter)
        pagination = SalesPagination()
        rows = pagination.paginate_queryset(queryset, request, view=self)
        response = pagination.get_paginated_response(QuoteSerializer(rows, many=True, context={"request":request}).data)
        if summary is not None:
            response.data['loss_summary'] = summary
        return response
    def post(self, request): return self.operate(request, 'save')


class QuoteDetailView(QuoteBaseView):
    quote_actions={"GET":"view","PUT":"change"}

    def get(self, request, quote_id):
        return Response(QuoteSerializer(get_object_or_404(quote_queryset(self._selected_store()), pk=quote_id),context={"request":request}).data)
    def put(self, request, quote_id): return self.operate(request, 'save', quote_id)


class QuoteTransitionView(QuoteBaseView):
    quote_actions={"POST":"transition"}

    def post(self, request, quote_id, action):
        if action not in ('send','accept','reject','convert','followup'): raise ValidationError('Operação inválida.')
        return self.operate(request, action, quote_id)
