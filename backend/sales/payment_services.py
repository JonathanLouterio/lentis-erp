"""Parcelas e recebimentos locais. Não executa cobranças ou transferências bancárias."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from accounts.selectors import get_accessible_stores
from .models import CheckoutRequest, FinancialAccount, FinancialEntry, PaymentMethod, Receivable, Sale, SaleItem, SalePayment
from .services import _locked_sale
from .payment_schedule import schedule, validate_terms


IMMEDIATE_KINDS = {'cash', 'pix', 'transfer'}
CUSTOMER_CREDIT_KINDS = {'store_credit', 'boleto'}
CARD_KINDS = {'credit', 'debit'}



def validate_payments(sale):
    payments = list(sale.payments.select_related('method', 'account').order_by('pk'))
    if sale.total < 0:
        raise ValidationError({'discount_amount': 'O desconto ultrapassa o valor da venda.'})
    if sum((payment.amount for payment in payments), Decimal('0')) != sale.total:
        raise ValidationError({'payments': 'Distribua exatamente o total da venda entre as formas de pagamento.'})
    for payment in payments:
        payment.full_clean()
        if not payment.method.is_active or not payment.account.is_active:
            raise ValidationError({'payments': 'Selecione formas e contas de recebimento ativas.'})
        if payment.kind in CUSTOMER_CREDIT_KINDS and (not sale.customer_id or not sale.customer.is_active):
            raise ValidationError({'customer_id': 'Identifique um cliente ativo para boleto ou crediário.'})
        validate_terms(payment.method, payment.amount, payment.installment_count, payment.first_due_date, payment.interval_unit, payment.interval_count, payment.confirmed)
    return payments


def book_sale_payments(sale, user):
    # O chamador mantém o lock da venda até o fim da transação de estoque e financeiro.
    if sale.payments.filter(installments__isnull=False).exists():
        raise ValidationError('Esta venda já possui parcelas registradas.')
    for payment in sale.payments.select_related('method', 'account'):
        for number, (due_date, amount) in enumerate(schedule(payment.amount, payment.installment_count, payment.first_due_date, payment.interval_unit, payment.interval_count), 1):
            receivable = Receivable.objects.create(
                payment=payment, number=number, due_date=due_date, amount=amount,
                debtor=Receivable.Debtor.OPERATOR if payment.kind in CARD_KINDS else Receivable.Debtor.CUSTOMER,
                customer_name=sale.customer.name if sale.customer_id else '',
            )
            if payment.confirmed:
                FinancialEntry.objects.create(
                    receivable=receivable, account=payment.account, method=payment.method,
                    amount=amount, created_by=user, reason=f'Recebimento na venda #{sale.pk}.',
                )


def reverse_sale_financials(sale, user, reason):
    entries = list(FinancialEntry.objects.filter(
        receivable__payment__sale=sale, reversal_of__isnull=True,
    ).select_related('account', 'method', 'receivable__payment__sale').order_by('pk'))
    for entry in entries:
        if not FinancialEntry.objects.filter(reversal_of=entry).exists():
            FinancialEntry.objects.create(
                receivable=entry.receivable, account=entry.account, method=entry.method,
                amount=-entry.amount, created_by=user, reversal_of=entry,
                reason=f'Cancelamento da venda #{sale.pk}: {reason}'[:255],
            )


def complete_sale(*, user, sale_id):
    from .services import finalize_sale
    with transaction.atomic():
        sale = _locked_sale(user, sale_id)
        if sale.status == Sale.Status.DRAFT:
            validate_payments(sale)
        return finalize_sale(user=user, sale_id=sale_id)


def checkout(*, user, store, request_id, payload_digest, validated_values):
    # O lock do usuário serializa inclusive duas tentativas de criar a mesma nova venda.
    # O identificador é único; uma resposta perdida pode ser repetida com segurança.
    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=user.pk)
        if not get_accessible_stores(user).filter(pk=store.pk).exists():
            raise PermissionDenied('O acesso à unidade não está mais disponível.')
        previous = CheckoutRequest.objects.select_related('sale').filter(request_id=request_id).first()
        if previous:
            if previous.created_by_id != user.pk or previous.sale.store_id != store.pk:
                raise PermissionDenied('Esta operação pertence a outra conta ou unidade.')
            if previous.payload_digest != payload_digest:
                raise ValidationError({'request_id': 'O identificador já foi usado com outros dados. Reabra a venda antes de continuar.'})
            return previous.sale
        values = dict(validated_values())
        sale_id = values.pop('sale_id', None)
        action = values.pop('action')
        items = values.pop('items')
        payments = values.pop('payments')
        customer = values.pop('customer_id', None)
        discount = values.pop('discount_amount')
        if sale_id:
            sale = _locked_sale(user, sale_id)
            if sale.store_id != store.pk:
                raise PermissionDenied('A venda pertence a outra unidade.')
            if sale.status != Sale.Status.DRAFT:
                raise ValidationError('Reabra a venda para consultar a conclusão. Vendas finalizadas não podem ser substituídas.')
            sale.discount_amount = Decimal('0')
            sale.customer = customer
            sale.notes = values['notes']
            sale.save()
            for payment in sale.payments.all():
                payment.delete()
            for item in sale.items.all():
                item.delete()
        else:
            sale = Sale.objects.create(store=store, created_by=user, customer=customer, **values)
        for item in items:
            item = dict(item)
            SaleItem.objects.create(sale=sale, product=item.pop('product_id'), **item)
        sale.discount_amount = discount
        sale.save()
        for payment in payments:
            payment = dict(payment)
            SalePayment.objects.create(sale=sale, method=payment.pop('method_id'), account=payment.pop('account_id'), **payment)
        if action == 'complete':
            sale = complete_sale(user=user, sale_id=sale.pk)
        CheckoutRequest.objects.create(request_id=request_id, sale=sale, created_by=user, payload_digest=payload_digest)
        return sale


def receive_installment(*, user, store, receivable_id, account, method, amount, request_id):
    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=user.pk)
        if not user.is_active or not get_accessible_stores(user).filter(pk=store.pk).exists():
            raise PermissionDenied('Entre com uma conta ativa com acesso à unidade.')
        if not (user.is_staff or user.is_superuser):
            raise PermissionDenied('Somente administradores podem registrar recebimentos no financeiro.')
        candidate = Receivable.objects.filter(pk=receivable_id, payment__sale__store=store).first()
        if candidate is None:
            raise ValidationError('Parcela não encontrada nesta unidade.')
        sale = _locked_sale(user, candidate.payment.sale_id)
        receivable = Receivable.objects.select_for_update().select_related('payment__sale').get(pk=candidate.pk)
        previous = FinancialEntry.objects.filter(request_id=request_id).first()
        if previous:
            if (previous.receivable_id, previous.account_id, previous.method_id, previous.amount, previous.created_by_id) != (receivable.pk, account.pk, method.pk, amount, user.pk):
                raise ValidationError({'request_id': 'O identificador já foi usado em outro recebimento.'})
            return receivable
        if sale.status != Sale.Status.COMPLETED:
            raise ValidationError('Somente parcelas de vendas finalizadas podem ser recebidas.')
        if account.store_id != store.pk or method.store_id != store.pk or not account.is_active or not method.is_active:
            raise ValidationError('Selecione uma conta e uma forma de recebimento ativas desta unidade.')
        if method.kind not in IMMEDIATE_KINDS:
            raise ValidationError({'method_id': 'Selecione dinheiro, Pix ou transferência para confirmar o valor recebido.'})
        if not amount.is_finite() or amount <= 0 or amount != amount.quantize(Decimal('0.01')):
            raise ValidationError({'amount': 'Informe um valor positivo com até duas casas decimais.'})
        FinancialEntry.objects.create(
            receivable=receivable, account=account, method=method, amount=amount,
            created_by=user, request_id=request_id, reason=f'Recebimento da parcela {receivable.number}; venda #{sale.pk}.',
        )
        return receivable
