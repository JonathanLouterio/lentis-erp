from decimal import Decimal
from django.db import IntegrityError
from django.db.models import DecimalField, Sum, Value, F, ExpressionWrapper, Exists, OuterRef
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from sales.models import FinancialAccount, PaymentMethod
from sales.views import SalesBaseView, SalesPagination, model_errors
from .access_permissions import PayableActionPermission, payable_capabilities
from .models import PayablePlan, PayableInstallment
from .payable_services import generate_plan, pay_installment, reverse_payment, ALLOWED_METHODS


class PlanInput(serializers.Serializer):
    request_id = serializers.UUIDField()
    purchase_id = serializers.IntegerField(min_value=1, max_value=9223372036854775807)
    installment_count = serializers.IntegerField(min_value=1, max_value=12)
    first_due_date = serializers.DateField()
    interval_unit = serializers.ChoiceField(choices=['months', 'days'], default='months')
    interval_count = serializers.IntegerField(min_value=1, max_value=365, default=1)


class PaymentInput(serializers.Serializer):
    request_id = serializers.UUIDField()
    account_id = serializers.IntegerField(min_value=1, max_value=9223372036854775807)
    method_id = serializers.IntegerField(min_value=1, max_value=9223372036854775807)
    amount = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=Decimal('0.01'))
    paid_on = serializers.DateField()
    reason = serializers.CharField(max_length=255)


class ReversalInput(serializers.Serializer):
    request_id = serializers.UUIDField()
    reason = serializers.CharField(max_length=255)


def permissions(user):
    caps=payable_capabilities(user)
    return {'can_create':caps['generate'],'can_pay':caps['pay'],'can_reverse':caps['reverse']}


def plan_query(store):
    cash = DecimalField(max_digits=28, decimal_places=2)
    due = PayableInstallment.objects.filter(plan_id=OuterRef('pk'), due_date__lt=timezone.localdate()).annotate(net=Coalesce(Sum('payments__amount'), Value(Decimal('0')), output_field=cash)).filter(amount__gt=F('net'))
    return PayablePlan.objects.filter(purchase__store=store).select_related('purchase__supplier', 'created_by').annotate(paid_sum=Coalesce(Sum('installments__payments__amount'), Value(Decimal('0')), output_field=cash)).annotate(remaining_sum=ExpressionWrapper(F('total') - F('paid_sum'), output_field=cash), is_overdue=Exists(due)).order_by('-pk')


def output(plan, user, detail=False):
    result = {'id': plan.pk, 'purchase_id': plan.purchase_id, 'supplier_name': plan.purchase.supplier_snapshot.get('name', plan.purchase.supplier.name), 'reference': plan.purchase.reference,
              'total': f'{plan.total:.2f}', 'paid': f'{plan.paid_sum:.2f}', 'remaining': f'{plan.remaining_sum:.2f}', 'status': 'paid' if plan.remaining_sum == 0 else 'partial' if plan.paid_sum > 0 else 'pending', 'overdue': plan.is_overdue,
              'installment_count': plan.installment_count, 'first_due_date': plan.first_due_date, 'interval_unit': plan.interval_unit, 'interval_count': plan.interval_count,
              'creator_username': plan.created_by.username, 'created_at': plan.created_at, **permissions(user)}
    if detail:
        result['installments'] = []
        for installment in plan.installments.prefetch_related('payments__created_by', 'payments__reversal'):
            payments = list(installment.payments.all())
            paid = sum((p.amount for p in payments), Decimal('0.00'))
            remaining = installment.amount - paid
            result['installments'].append({'id': installment.pk, 'number': installment.number, 'due_date': installment.due_date, 'amount': f'{installment.amount:.2f}', 'paid': f'{paid:.2f}', 'remaining': f'{remaining:.2f}', 'status': 'paid' if remaining == 0 else 'partial' if paid > 0 else 'pending', 'overdue': remaining > 0 and installment.due_date < timezone.localdate(),
                'payments': [{'id': p.pk, 'amount': f'{p.amount:.2f}', 'account_name': p.account_name, 'method_name': p.method_name, 'paid_on': p.paid_on, 'reason': p.reason, 'reversal_of': p.reversal_of_id, 'reversed': hasattr(p, 'reversal'), 'cash_posting_id': p.cash_posting_id, 'creator_username': p.created_by.username, 'created_at': p.created_at} for p in payments]})
    return result


class PayablesView(SalesBaseView):
    permission_classes=[PayableActionPermission]
    def finalize_response(self,request,response,*args,**kwargs):
        response=super().finalize_response(request,response,*args,**kwargs)
        response['Cache-Control']='no-store, private'
        return response
    def check_access(self):
        store = self._selected_store()
        from organizations.access_permissions import fresh_actor
        actor=fresh_actor(self.request)
        if actor is None: raise PermissionDenied('Entre com uma conta ativa.')
        self.request.user=actor
        if not self.request.user.has_perm('purchases.view_payableplan'):
            raise PermissionDenied('Seu usuário precisa da permissão de visualizar contas a pagar.')
        return store

    def get(self, request):
        qs = plan_query(self.check_access())
        state = request.query_params.get('status', 'pending')
        if state not in ('all', 'pending', 'paid', 'overdue'):
            raise ValidationError('Situação de contas a pagar inválida.')
        if state == 'pending': qs = qs.filter(remaining_sum__gt=0)
        if state == 'paid': qs = qs.filter(remaining_sum=0)
        if state == 'overdue': qs = qs.filter(is_overdue=True)
        if 'purchase_id' in request.query_params:
            try:
                purchase_id = int(request.query_params['purchase_id'])
                if not 1 <= purchase_id <= 9223372036854775807: raise ValueError
            except ValueError as exc:
                raise ValidationError('Compra inválida.') from exc
            qs = qs.filter(purchase_id=purchase_id)
        pagination = SalesPagination()
        rows = pagination.paginate_queryset(qs, request, view=self)
        response = pagination.get_paginated_response([output(p, request.user) for p in rows])
        response.data.update(permissions(request.user))
        response['Cache-Control'] = 'no-store, private'
        return response

    def write(self, service, input_class, **target):
        store = self.check_access()
        serializer = input_class(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with model_errors():
                result = service(user=self.request.user, store=store, values=serializer.validated_data, **target)
        except IntegrityError as exc:
            raise ValidationError('Este envio conflitou com outra operação. Confira o título antes de continuar.') from exc
        plan_id = result.pk if isinstance(result, PayablePlan) else result.installment.plan_id
        return Response(output(plan_query(store).get(pk=plan_id), self.request.user, True), headers={'Cache-Control': 'no-store, private'})

    def post(self, request):
        return self.write(generate_plan, PlanInput)


class PayableDetailView(PayablesView):
    http_method_names = ['get', 'head', 'options']
    def get(self, request, plan_id):
        return Response(output(get_object_or_404(plan_query(self.check_access()), pk=plan_id), request.user, True), headers={'Cache-Control': 'no-store, private'})


class PayablePaymentView(PayablesView):
    payable_action='pay'
    http_method_names = ['post', 'options']
    def post(self, request, installment_id):
        return self.write(pay_installment, PaymentInput, installment_id=installment_id)

    def get(self, request, installment_id):
        return self.http_method_not_allowed(request)


class PayableReversalView(PayablesView):
    payable_action='reverse'
    http_method_names = ['post', 'options']
    def post(self, request, payment_id):
        return self.write(reverse_payment, ReversalInput, payment_id=payment_id)

    def get(self, request, payment_id):
        return self.http_method_not_allowed(request)


class PayableOptionsView(PayablesView):
    http_method_names = ['get', 'head', 'options']
    def get(self, request):
        store = self.check_access()
        if not payable_capabilities(request.user)['pay']:
            return Response({'can_cash':False,'can_view_balances':False,'accounts':[],'methods':[],**permissions(request.user)})
        accounts = FinancialAccount.objects.filter(store=store, is_active=True)
        methods = PaymentMethod.objects.filter(store=store, is_active=True, kind__in=ALLOWED_METHODS)
        can_cash=request.user.has_perm('sales.move_cash')
        if not can_cash: methods=methods.exclude(kind='cash')
        balances=request.user.has_perm('sales.view_financialaccount')
        return Response({'can_cash':can_cash,'can_view_balances':balances,'accounts': [{'id': a.pk, 'name': a.name, 'cash_box': a.cash_box, **({'balance': f'{a.balance:.2f}'} if balances else {})} for a in accounts], 'methods': [{'id': m.pk, 'name': m.name, 'kind': m.kind} for m in methods], **permissions(request.user)}, headers={'Cache-Control': 'no-store, private'})
