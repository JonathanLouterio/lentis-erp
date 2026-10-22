"""Locks: usuário, compra/plano, parcela, conta e sessão de caixa."""
import hashlib
import json
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from accounts.selectors import get_accessible_stores
from sales.models import FinancialAccount, PaymentMethod
from sales.payment_schedule import schedule
from sales.cash_services import post_payable_cash
from sales.finance_permissions import require_finance
from .models import Purchase, PayablePlan, PayableInstallment, PayablePayment

ALLOWED_METHODS = ('cash', 'pix', 'transfer', 'debit')


def digest_data(action, target, values):
    return hashlib.sha256(json.dumps({'action': action, 'target': target, 'values': values}, sort_keys=True, default=str).encode()).hexdigest()


def actor(user, store, permission):
    user = get_user_model().objects.select_for_update(no_key=True).get(pk=user.pk)
    if not user.is_active or not get_accessible_stores(user).filter(pk=store.pk).exists():
        raise PermissionDenied('Entre com uma conta ativa com acesso à unidade.')
    if not user.has_perm('purchases.view_payableplan') or not user.has_perm(f'purchases.{permission}'):
        raise PermissionDenied('Seu usuário não tem permissão para esta operação de contas a pagar.')
    return user


def replay(record, user, store, digest):
    purchase = record.purchase if isinstance(record, PayablePlan) else record.installment.plan.purchase
    if record.created_by_id != user.pk or purchase.store_id != store.pk:
        raise PermissionDenied('Este envio pertence a outra conta ou unidade.')
    if record.digest != digest:
        raise ValidationError('O identificador já foi utilizado com outros dados. Confira o envio original.')
    return record


@transaction.atomic
def generate_plan(*, user, store, values):
    user = actor(user, store, 'add_payableplan')
    if not user.has_perm('purchases.view_purchase'):
        raise PermissionDenied('Seu usuário precisa de permissão para visualizar a compra de origem.')
    digest = digest_data('generate', values['purchase_id'], values)
    previous = PayablePlan.objects.filter(request_id=values['request_id']).first()
    if previous:
        if isinstance(previous, PayablePayment) and previous.method.kind == "cash":
            require_finance(user, "move_cash")
        return replay(previous, user, store, digest)
    purchase = get_object_or_404(Purchase.objects.select_for_update(), pk=values['purchase_id'], store=store)
    if purchase.status != 'received':
        raise ValidationError('Confirme a entrada da compra antes de gerar as contas a pagar.')
    if PayablePlan.objects.filter(purchase=purchase).exists():
        raise ValidationError('Esta compra já tem contas a pagar. Abra o título existente.')
    rows = schedule(purchase.total, values['installment_count'], values['first_due_date'], values['interval_unit'], values['interval_count'])
    plan = PayablePlan(purchase=purchase, total=purchase.total, installment_count=values['installment_count'], first_due_date=values['first_due_date'], interval_unit=values['interval_unit'], interval_count=values['interval_count'], request_id=values['request_id'], digest=digest, created_by=user)
    plan.save(_service=True)
    for number, (due, amount) in enumerate(rows, 1):
        PayableInstallment(plan=plan, number=number, due_date=due, amount=amount).save(_service=True)
    return plan


def locked_installment(store, installment_id):
    candidate = get_object_or_404(PayableInstallment.objects.filter(plan__purchase__store=store), pk=installment_id)
    PayablePlan.objects.select_for_update().get(pk=candidate.plan_id)
    return PayableInstallment.objects.select_for_update().select_related('plan__purchase').get(pk=candidate.pk)


@transaction.atomic
def pay_installment(*, user, store, installment_id, values):
    user = actor(user, store, 'pay_payable')
    digest = digest_data('pay', installment_id, values)
    previous = PayablePayment.objects.filter(request_id=values['request_id']).first()
    if previous:
        if isinstance(previous, PayablePayment) and previous.method.kind == "cash":
            require_finance(user, "move_cash")
        return replay(previous, user, store, digest)
    installment = locked_installment(store, installment_id)
    amount = values['amount']
    if not isinstance(amount, Decimal) or not amount.is_finite() or amount <= 0 or amount != amount.quantize(Decimal('0.01')):
        raise ValidationError({'amount': 'Informe um valor positivo com até duas casas decimais.'})
    if amount > installment.remaining:
        raise ValidationError({'amount': 'O valor ultrapassa o saldo atual da parcela. Atualize o título.'})
    account = get_object_or_404(FinancialAccount.objects.select_for_update(of=('self',)), pk=values['account_id'], store=store, is_active=True)
    method = get_object_or_404(PaymentMethod.objects.select_for_update(of=('self',)), pk=values['method_id'], store=store, is_active=True)
    if method.kind not in ALLOWED_METHODS:
        raise ValidationError('Selecione dinheiro, Pix, transferência ou débito para registrar uma saída efetiva.')
    if values['paid_on'] > timezone.localdate():
        raise ValidationError({'paid_on': 'O pagamento não pode ter uma data futura.'})
    if method.kind == 'cash' and values['paid_on'] != timezone.localdate():
        raise ValidationError({'paid_on': 'Pagamentos em dinheiro devem ter a data de hoje e movimentam o caixa aberto.'})
    posting = post_payable_cash(user=user, store=store, account=account, method=method, amount=amount, reason=f'Pagamento da compra #{installment.plan.purchase_id}: {values["reason"]}'[:255], request_id=values['request_id'])
    payment = PayablePayment(installment=installment, account=account, method=method, account_name=account.name, method_name=method.name, amount=amount, paid_on=values['paid_on'], reason=values['reason'], cash_posting=posting, request_id=values['request_id'], digest=digest, created_by=user)
    payment.save(_service=True)
    return payment


@transaction.atomic
def reverse_payment(*, user, store, payment_id, values):
    user = actor(user, store, 'reverse_payable')
    digest = digest_data('reverse', payment_id, values)
    previous = PayablePayment.objects.filter(request_id=values['request_id']).first()
    if previous:
        if isinstance(previous, PayablePayment) and previous.method.kind == "cash":
            require_finance(user, "move_cash")
        return replay(previous, user, store, digest)
    original = get_object_or_404(PayablePayment.objects.filter(installment__plan__purchase__store=store), pk=payment_id)
    installment = locked_installment(store, original.installment_id)
    original = PayablePayment.objects.select_related('method', 'account').get(pk=original.pk)
    if original.reversal_of_id or PayablePayment.objects.filter(reversal_of=original).exists():
        raise ValidationError('Este pagamento já foi estornado ou é um estorno.')
    # Contas bancárias inativas podem receber a contrapartida histórica. Dinheiro
    # exige conta ativa e nova sessão aberta, sem alterar fechamentos anteriores.
    account = FinancialAccount.objects.select_for_update(of=('self',)).get(pk=original.account_id)
    posting = post_payable_cash(user=user, store=store, account=account, method=original.method, amount=-original.amount, reason=f'Estorno da compra #{installment.plan.purchase_id}: {values["reason"]}'[:255], request_id=values['request_id'])
    reversal = PayablePayment(installment=installment, account=account, method=original.method, account_name=original.account_name, method_name=original.method_name, amount=-original.amount, paid_on=timezone.localdate(), reason=values['reason'], reversal_of=original, cash_posting=posting, request_id=values['request_id'], digest=digest, created_by=user)
    reversal.save(_service=True)
    return reversal
