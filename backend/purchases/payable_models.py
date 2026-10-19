"""Títulos de compras e lançamentos imutáveis; escritas pelo serviço transacional."""
from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class PayableRecord(models.Model):
    class Meta:
        abstract = True

    def save(self, *args, _service=False, **kwargs):
        if not _service or not self._state.adding:
            raise ValidationError('O histórico financeiro é imutável. Use as operações de geração, pagamento e estorno.')
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('O histórico financeiro não pode ser excluído.')


class PayablePlan(PayableRecord):
    purchase = models.OneToOneField('purchases.Purchase', on_delete=models.PROTECT, related_name='payable_plan')
    total = models.DecimalField(max_digits=18, decimal_places=2)
    installment_count = models.PositiveSmallIntegerField()
    first_due_date = models.DateField()
    interval_unit = models.CharField(max_length=6, choices=[('months', 'Meses'), ('days', 'Dias')])
    interval_count = models.PositiveSmallIntegerField()
    request_id = models.UUIDField(unique=True)
    digest = models.CharField(max_length=64)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Conta a pagar da compra'
        verbose_name_plural = 'Contas a pagar das compras'
        ordering = ['-pk']
        permissions = [('pay_payable', 'Registrar pagamento de conta a pagar'), ('reverse_payable', 'Estornar pagamento de conta a pagar')]
        constraints = [
            models.CheckConstraint(condition=models.Q(total__gt=0, installment_count__gte=1, installment_count__lte=12), name='payable_plan_values_valid'),
            models.CheckConstraint(condition=(models.Q(interval_unit='months', interval_count__gte=1, interval_count__lte=12) | models.Q(interval_unit='days', interval_count__gte=1, interval_count__lte=365)), name='payable_plan_interval_valid'),
        ]

    def clean(self):
        if self.purchase.status != 'received' or self.total != self.purchase.total:
            raise ValidationError('Gere o título com o total de uma compra recebida.')

    def __str__(self):
        return f'Contas a pagar · compra #{self.purchase_id}'


class PayableInstallment(PayableRecord):
    plan = models.ForeignKey(PayablePlan, on_delete=models.PROTECT, related_name='installments')
    number = models.PositiveSmallIntegerField()
    due_date = models.DateField()
    amount = models.DecimalField(max_digits=18, decimal_places=2)

    class Meta:
        ordering = ['number']
        constraints = [
            models.UniqueConstraint(fields=['plan', 'number'], name='unique_payable_installment'),
            models.CheckConstraint(condition=models.Q(amount__gt=0, number__gte=1, number__lte=12), name='payable_installment_values_valid'),
        ]

    @property
    def paid(self):
        return self.payments.aggregate(value=models.Sum('amount'))['value'] or Decimal('0.00')

    @property
    def remaining(self):
        return self.amount - self.paid


class PayablePayment(PayableRecord):
    installment = models.ForeignKey(PayableInstallment, on_delete=models.PROTECT, related_name='payments')
    account = models.ForeignKey('sales.FinancialAccount', on_delete=models.PROTECT, related_name='payable_payments')
    method = models.ForeignKey('sales.PaymentMethod', on_delete=models.PROTECT, related_name='payable_payments')
    account_name = models.CharField(max_length=100)
    method_name = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    paid_on = models.DateField()
    reason = models.CharField(max_length=255)
    reversal_of = models.OneToOneField('self', on_delete=models.PROTECT, null=True, blank=True, related_name='reversal')
    cash_posting = models.OneToOneField('sales.CashPosting', on_delete=models.PROTECT, null=True, blank=True, related_name='payable_payment')
    request_id = models.UUIDField(unique=True)
    digest = models.CharField(max_length=64)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Pagamento a fornecedor'
        verbose_name_plural = 'Pagamentos a fornecedores'
        ordering = ['-pk']
        constraints = [models.CheckConstraint(condition=(models.Q(amount__gt=0, reversal_of__isnull=True) | models.Q(amount__lt=0, reversal_of__isnull=False)), name='payable_payment_sign_valid')]

    def clean(self):
        store_id = self.installment.plan.purchase.store_id
        if self.account.store_id != store_id or self.method.store_id != store_id:
            raise ValidationError('A conta e a forma devem pertencer à unidade do título.')
        if not self.reason.strip():
            raise ValidationError({'reason': 'Informe a referência ou justificativa.'})
        if self.reversal_of_id:
            original = self.reversal_of
            if original.reversal_of_id or (original.installment_id, original.account_id, original.method_id, -original.amount) != (self.installment_id, self.account_id, self.method_id, self.amount):
                raise ValidationError('O estorno deve corresponder integralmente ao pagamento original.')
        if self.cash_posting_id and (self.cash_posting.session.account_id != self.account_id or self.cash_posting.amount != -self.amount or self.cash_posting.created_by_id != self.created_by_id):
            raise ValidationError('A movimentação de caixa deve corresponder ao pagamento.')
