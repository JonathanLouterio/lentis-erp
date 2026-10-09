import hashlib
import json

from django.db.models import DecimalField, F, Sum, Value
from django.db.models.functions import Coalesce
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .models import FinancialAccount, PaymentMethod, Receivable
from .payment_serializers import AccountSerializer, CheckoutSerializer, MethodSerializer, ReceiptWriteSerializer, ReceivableSerializer
from .payment_services import checkout, receive_installment
from .views import SalesBaseView, SalesPagination, model_errors


class PaymentOptionsView(SalesBaseView):
    def get(self, request):
        store = self._selected_store()
        from .commercial_services import current_policy, can_approve
        role, limit, configured = current_policy(request.user, store)
        return Response({
            'methods': MethodSerializer(PaymentMethod.objects.filter(store=store, is_active=True), many=True).data,
            'accounts': AccountSerializer(FinancialAccount.objects.filter(store=store, is_active=True), many=True).data,
            'allow_negative_stock': store.allow_negative_stock,
            'discount_limit_percentage': str(limit),
            'discount_policy_configured': configured,
            'can_approve_discount': can_approve(request.user, store),
            'discount_role': role,
            'can_receive': request.user.is_staff or request.user.is_superuser,
        })


class SaleCheckoutView(SalesBaseView):
    def post(self, request):
        store = self._selected_store()
        if not isinstance(request.data, dict):
            raise ValidationError('Envie um objeto JSON com os dados da venda.')
        identity = serializers.UUIDField().run_validation(request.data.get('request_id'))
        digest = hashlib.sha256(json.dumps(request.data, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()
        def validated_values():
            return self.write_serializer(CheckoutSerializer, request.data, store).validated_data
        with model_errors():
            sale = checkout(user=request.user, store=store, request_id=identity, payload_digest=digest, validated_values=validated_values)
            return self.output(sale, response_status=status.HTTP_200_OK)


class ReceivablesView(SalesBaseView):
    def get(self, request):
        store = self._selected_store()
        queryset = Receivable.objects.filter(payment__sale__store=store).select_related(
            'payment__sale', 'payment__account',
        ).prefetch_related('entries__account', 'entries__method', 'entries__created_by').annotate(
            received=Coalesce(Sum('entries__amount'), Value(0), output_field=DecimalField(max_digits=28, decimal_places=2)),
        )
        state = request.query_params.get('status', 'pending')
        if state == 'pending':
            queryset = queryset.filter(payment__sale__status='completed', received__lt=F('amount'))
        elif state == 'paid':
            queryset = queryset.filter(payment__sale__status='completed', received=F('amount'))
        elif state == 'cancelled':
            queryset = queryset.filter(payment__sale__status='cancelled')
        elif state != 'all':
            raise ValidationError({'status': 'Informe pending, paid, cancelled ou all.'})
        debtor = request.query_params.get('debtor')
        if debtor:
            if debtor not in Receivable.Debtor.values:
                raise ValidationError({'debtor': 'Selecione cliente ou operadora.'})
            queryset = queryset.filter(debtor=debtor)
        queryset = queryset.order_by("due_date", "pk")
        pagination = SalesPagination()
        page = pagination.paginate_queryset(queryset, request, view=self)
        return pagination.get_paginated_response(ReceivableSerializer(page, many=True, context={'request': request}).data)


class ReceiveInstallmentView(SalesBaseView):
    def post(self, request, receivable_id):
        store = self._selected_store()
        serializer = self.write_serializer(ReceiptWriteSerializer, request.data, store)
        values = dict(serializer.validated_data)
        with model_errors():
            receivable = receive_installment(
                user=request.user, store=store, receivable_id=receivable_id,
                account=values.pop('account_id'), method=values.pop('method_id'), **values,
            )
            return Response(ReceivableSerializer(receivable, context={'request': request}).data)
