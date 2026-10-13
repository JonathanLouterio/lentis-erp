import hashlib
import json
from django.shortcuts import get_object_or_404
from django.utils import timezone
from zoneinfo import ZoneInfo
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from .models import Quote
from .quote_serializers import QuoteSerializer, QuoteWriteSerializer, QuoteActionSerializer
from .quote_services import operate_quote
from .views import SalesBaseView, SalesPagination, model_errors


def quote_queryset(store):
    return Quote.objects.filter(store=store).select_related('customer','created_by').prefetch_related('items','events__created_by')


class QuoteBaseView(SalesBaseView):
    def operate(self, request, action, quote_id=None):
        store = self._selected_store()
        if not isinstance(request.data, dict): raise ValidationError('Envie os dados do orçamento em um objeto JSON.')
        request_id = serializers.UUIDField().run_validation(request.data.get('request_id'))
        digest = hashlib.sha256(json.dumps({'action': action, 'quote_id': quote_id, 'body': request.data}, sort_keys=True, ensure_ascii=False, separators=(',',':')).encode('utf-8')).hexdigest()
        def validated():
            return self.write_serializer(QuoteWriteSerializer if action == 'save' else QuoteActionSerializer, request.data, store).validated_data
        with model_errors():
            quote = operate_quote(user=request.user, store=store, quote_id=quote_id, action=action, request_id=request_id, digest=digest, validated_values=validated)
        return Response(QuoteSerializer(quote_queryset(store).get(pk=quote.pk)).data)


class QuotesView(QuoteBaseView):
    def get(self, request):
        store = self._selected_store()
        queryset = quote_queryset(store)
        state = request.query_params.get('status', 'all')
        if state == 'expired':
            queryset = queryset.filter(valid_until__lt=timezone.localdate(timezone=ZoneInfo('America/Sao_Paulo'))).exclude(status__in=['converted','rejected'])
        elif state in Quote.Status.values: queryset = queryset.filter(status=state)
        elif state != 'all': raise ValidationError({'status': 'Selecione uma situação válida.'})
        pagination = SalesPagination()
        rows = pagination.paginate_queryset(queryset, request, view=self)
        return pagination.get_paginated_response(QuoteSerializer(rows, many=True).data)
    def post(self, request): return self.operate(request, 'save')


class QuoteDetailView(QuoteBaseView):
    def get(self, request, quote_id):
        return Response(QuoteSerializer(get_object_or_404(quote_queryset(self._selected_store()), pk=quote_id)).data)
    def put(self, request, quote_id): return self.operate(request, 'save', quote_id)


class QuoteTransitionView(QuoteBaseView):
    def post(self, request, quote_id, action):
        if action not in ('send','accept','reject','convert'): raise ValidationError('Operação inválida.')
        return self.operate(request, action, quote_id)
